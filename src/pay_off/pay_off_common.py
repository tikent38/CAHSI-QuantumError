# pay_off_common.py
# The code pay_off.py and pay_off_h.py share: counting up through numbers of gates until each error-correction code
# pays off (starts having a smaller error than no correction IN_A_ROW times in a row), printing the results, plotting
# them, writing them to CSV files, and doing all of that on one backend after another. Those two files only say which
# experiments to run (see Experiment), with which codes, and hold the settings.
# pay_off_parallel.py runs pay_off.py's experiments through run() here, one process each, and pay_off_report.py reads
# the CSV files this writes (see backend_folder for where they go)
import os
import sys
from typing import Callable, NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from compare_backends import GATE_SETS, backend_label, compare, get_backend, print_match, set_layout, short_name
from output_tools import COLORS, INK, MUTED, print_table_header, pyplot, save_plot, style, write_csv

# Each backend's CSV files and plots go in a folder of their own in these: e.g. images/<backend> with the qubits
# matched to Fez's noise, and images/<backend>/best with its least noisy qubits (see backend_folder)
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")
# A code only counts as paid off once it beats no correction this many times in a row, so one lucky result from shot
# noise doesn't count. Its pay-off point is the first number of gates in that run
IN_A_ROW = 5
# The line style of each sweep in a plot, in order, and its name for the x axis label
LINE_STYLES = [("-", "solid"), ("--", "dashed"), ("-.", "dash-dot")]


class Experiment(NamedTuple):
    # One test circuit to find each code's pay-off point for: one plot, and its rows in the CSV files
    name: str           # short, for the summary table, e.g. "x"
    title: str          # the start of the plot's title, e.g. 'gate set "x" (X)'
    file: str           # the plot's file name, without .png
    columns: dict       # its own CSV columns and their values, e.g. {"gate_set": "x"}
    starts: dict        # {sweep: first number of gates}, e.g. {"even": 0, "odd": 1}. Each sweep is counted up on its
                        # own and is one line style in the plot
    step: int           # how many gates each step adds
    options: Callable   # (number of gates, seed) -> the keyword arguments for compare_backends.compare that make the
                        # circuit, e.g. dict(num_gates=40, gate_set="x")
    note: str = ""      # added to the plot's x axis label, e.g. how the circuit was padded


# ---- Small helpers ----

def gate_set_label(gate_set):
    # e.g. 'gate set "repeat" (X, Y, Z)'
    return f'gate set "{gate_set}" ({", ".join(g.upper() for g in GATE_SETS[gate_set][1])})'


def pay_off_text(n, max_gates):
    return f"never, up to {max_gates} gates" if n is None else f"{n} gates"


def backend_folder(base, backend, pick):
    # Where a backend's CSV files or plots go inside base: base/<backend>, e.g. images/marrakesh. Runs on the backend's
    # least noisy qubits (pick="best") go in base/<backend>/best instead, so they don't overwrite the runs on the
    # qubits matched to Fez's noise (pick="like fez"). Fez only has base/fez: both picks use its default qubits
    return os.path.join(base, backend, "best") if pick == "best" and backend != "fez" else os.path.join(base, backend)


# ---- Finding the pay-off points ----

def find_pay_off(experiment, first, codes, backend, max_gates, shots, seed, data_qubits, pick):
    # Runs compare_backends on backend at first, first + step, first + 2 * step, ... gates of experiment's circuit
    # until every code has paid off (beaten no correction IN_A_ROW times in a row) or max_gates is passed, printing
    # one row per number of gates. Returns the numbers of gates run, {run: [error at each]}, the pay-off points {code:
    # first number of gates of the winning run, or None}, and the no-correction run each code is compared with
    label = backend_label(get_backend(backend))
    ns, errors, found = [], {}, {code: None for code in codes}
    streak = {code: 0 for code in codes}   # how many times in a row each code has beaten no correction
    n = first
    while n <= max_gates and None in found.values():
        result, plain_for = compare(backend=backend, shots=shots, seed=seed, codes=codes, data_qubits=data_qubits,
                                    pick=pick, show=False, **experiment.options(n, seed))
        missing = [code for code in codes if code not in plain_for]
        if missing:   # compare_backends skipped them: the backend or circuit can't run them
            raise ValueError(f"{', '.join(missing)} can't run on {label} with {experiment.title}; take it out of "
                             f"CODES (compare_backends.py with BACKEND = \"{backend}\" prints why)")
        result = {run.removeprefix(f"{label} noise, "): error for run, error in result.items() if run != "no noise"}
        width = max(24, max(len(run) for run in result) + 2)   # columns grow to fit longer backend names
        if not errors:   # the first number of gates: print the table's header
            print_table_header(f"{'gates':>8}" + "".join(f"{run:>{width}}" for run in result))
        ns.append(n)
        for run, error in result.items():
            errors.setdefault(run, []).append(error)
        for code in codes:
            streak[code] = streak[code] + 1 if result[code] < result[plain_for[code]] else 0
            if found[code] is None and streak[code] == IN_A_ROW:
                found[code] = n - experiment.step * (IN_A_ROW - 1)
        print(f"{n:>8}" + "".join(f"{error:>{width}.4f}" for error in result.values()), flush=True)
        n += experiment.step
    return ns, errors, found, plain_for


# ---- Printing and plots ----

def print_pay_offs(points, codes, max_gates, label):
    # A table of how many gates each code needs to pay off: one row per experiment (and sweep), one column per code.
    # points: {row name: {code: pay-off point or None}}
    print(f"\nHow many gates each code needs to pay off on {label} (where it starts beating no correction {IN_A_ROW} "
          "times in a row):")
    width = max(len(name) for name in points) + 2
    print_table_header(f"  {'':<{width}}" + "".join(f"{code:<26}" for code in codes))
    for name, found in points.items():
        print(f"  {name:<{width}}" + "".join(f"{pay_off_text(found[code], max_gates):<26}" for code in codes))


def plot(experiment, sweeps, max_gates, shots, label, path, like_fez=False):
    # Error vs number of gates for no correction and each code, one line style per sweep (see LINE_STYLES), with a
    # dotted line where each code pays off. sweeps: {sweep: (numbers of gates, {run: [errors]}, pay-off points)}.
    # label is the backend's name for the title, e.g. "Fez". like_fez says in the title that the qubits were matched
    # to Fez's noise
    plt = pyplot()
    runs = dict.fromkeys(run for _, errors, _ in sweeps.values() for run in errors)
    colors = dict(zip(runs, COLORS))
    styles = dict(zip(sweeps, LINE_STYLES))
    several = len(sweeps) > 1

    fig, ax = plt.subplots(figsize=(11, 6))
    for sweep, (ns, errors, found) in sweeps.items():
        for run, run_errors in errors.items():
            legend = run + (f", {sweep}" if several else "")
            if run in found:
                legend += ": pays off at " + pay_off_text(found[run], max_gates)
                if found[run] is not None:
                    ax.axvline(found[run], color=colors[run], ls=":", lw=1.2)
            ax.plot(ns, run_errors, styles[sweep][0], color=colors[run], lw=2, label=legend)
    ax.set_title(f"{experiment.title} on {label} noise: error with and without correction ({shots} shots)"
                 + ("\non qubits matched to Fez's noise" if like_fez else ""), color=INK)
    notes = [experiment.note, several and ", ".join(f"{styles[sweep][1]} = {sweep}" for sweep in sweeps)]
    ax.set_xlabel("number of gates" + "".join(f" ({note})" for note in notes if note), color=MUTED)
    ax.set_ylabel("error from the exact answer, |P(1) - exact P(1)|", color=MUTED)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    style(ax)
    save_plot(fig, path)


# ---- Running ----

def run(experiments, codes, backend="fez", max_gates=500, shots=1000, seed=3, data_qubits=None, pick="best",
        csv_dir=None, plot_dir=None, csv_name="pay_off", sweep_column=None):
    # Finds each code's pay-off points for every experiment on one backend, then prints a summary table, and plots
    # each experiment and writes the CSV files.
    # backend: which fake backend to run on (any of compare_backends.py's BACKENDS, e.g. "fez", "torino").
    # seed fixes the test circuit, transpiler and simulator. data_qubits: the backend's qubits for q_0, q_1, q_2 (None
    # picks them for the backend the way pick says: "best" = its least noisy qubits, "like fez" = the ones whose noise
    # is closest to the Fez defaults', see compare_backends.py's PICKS).
    # csv_dir / plot_dir: <csv_name>.csv (every error) and <csv_name>_points.csv (each code's pay-off points) / each
    # experiment's plot are saved in a folder for the backend inside them (see backend_folder). sweep_column: the name
    # of the CSV column saying which sweep a row is from (e.g. "parity"), or None to leave it out
    backend = short_name(backend)
    label = backend_label(get_backend(backend))
    small = set_layout(get_backend(backend), data_qubits, pick=pick)["bit/phase-flip"]
    data = small[:3] if small else None   # the qubits q_0, q_1, q_2 run on, to print
    like_fez = pick == "like fez"
    if like_fez and data and backend != "fez" and data_qubits is None:
        print_match(get_backend(backend), data)
    rows, point_rows, points = [], [], {}
    for experiment in experiments:
        print(f"\n{experiment.title}, {shots} shots, seed {seed}, {label} qubits {data}. Error = |P(1) - exact P(1)| on {label} "
              "noise")
        sweeps, several = {}, len(experiment.starts) > 1
        for sweep, first in experiment.starts.items():
            print(f"\n{experiment.name}, {sweep}:" if several else "")
            ns, errors, found, plain_for = find_pay_off(experiment, first, codes, backend, max_gates, shots, seed,
                                                        data_qubits, pick)
            sweeps[sweep] = ns, errors, found
            points[experiment.name + (f", {sweep}" if several else "")] = found
            columns = list(experiment.columns.values()) + ([sweep] if sweep_column else [])
            rows += [columns + [n, run, shots, seed, round(errors[run][i], 6)]
                     for i, n in enumerate(ns) for run in errors]
            point_rows += [columns + [code, plain_for[code], shots, seed, "" if found[code] is None else found[code]]
                           for code in codes]
        if plot_dir:
            plot(experiment, sweeps, max_gates, shots, label,
                 os.path.join(backend_folder(plot_dir, backend, pick), experiment.file + ".png"), like_fez)
    print_pay_offs(points, codes, max_gates, label)
    if csv_dir:
        folder = backend_folder(csv_dir, backend, pick)
        columns = list(experiments[0].columns) + ([sweep_column] if sweep_column else [])
        write_csv(os.path.join(folder, f"{csv_name}.csv"), columns + ["gates", "run", "shots", "seed", "error"], rows)
        write_csv(os.path.join(folder, f"{csv_name}_points.csv"),
                  columns + ["code", "compared_with", "shots", "seed", "pays_off_at_gates"], point_rows)


def run_backends(backends, experiments, **options):
    # run() on each backend in backends, one after another (options are run's other arguments). A backend that can't
    # run (e.g. a code it can't run) is skipped with the reason, and the loop goes on to the next one. The names are
    # checked before the first run, so a typo doesn't stop the loop hours in
    backends = [short_name(b) for b in backends]
    finished, skipped = [], {}
    for i, backend in enumerate(backends, 1):
        print(f"\n{'=' * 40} {backend_label(get_backend(backend))} ({i} of {len(backends)}) {'=' * 40}")
        try:
            run(experiments, backend=backend, **options)
            finished.append(backend)
        except ValueError as err:
            print(f"\nSkipped {backend}: {err}")
            skipped[backend] = err
    print(f"\nFinished: {', '.join(finished) or 'none'}")
    for backend, err in skipped.items():
        print(f"Skipped {backend}: {err}")
