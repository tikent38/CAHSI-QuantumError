# pay_off.py
# Finds how many gates each Toffoli code (bit-flip and phase-flip) needs to pay off: the fewest gates where it has a
# smaller error than no correction. Runs compare_fez.py at 0, 2, 4, ... gates and at 1, 3, 5, ... gates, since for X
# and Y gates the exact answer is 0 after an even number and 1 after an odd number, and the codes do worse when it is 1.
# Plots the errors and writes them to CSV files. Change the experiment in the settings block at the bottom of the file
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from compare_fez import GATE_SETS, compare
from fez_common import DEFAULT_DATA_QUBITS
from output_tools import COLORS, INK, MUTED, print_table_header, pyplot, save_plot, style, write_csv

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")

# The codes compared with no correction (keys of compare_fez.CODES)
CODES = ["bit-flip, Toffoli", "phase-flip, Toffoli"]
# Where each count starts: even numbers of gates from 0, odd numbers from 1
STARTS = {"even": 30, "odd": 111}


def find_pay_off(gate_set, first, max_gates, shots, seed, data_qubits):
    # Runs compare_fez at first, first + 2, first + 4, ... gates until every code has a smaller error than no
    # correction, or max_gates is passed, printing one row per number of gates. Returns the numbers of gates run,
    # {run: [error at each]}, {code: first number of gates where it was better, or None}, and the no-correction run
    # each code is compared with (no correction runs on the qubit the code is measured on, e.g.
    # "no correction (Fez 86)")
    ns, errors, found = [], {}, {code: None for code in CODES}
    n = first
    while n <= max_gates and None in found.values():
        result, plain_for = compare(num_gates=n, shots=shots, seed=seed, gate_set=gate_set, codes=CODES,
                                    data_qubits=data_qubits, show=False)
        result = {run.removeprefix("Fez noise, "): error for run, error in result.items() if run != "no noise"}
        if not errors:   # the first number of gates: print the table's header
            print_table_header(f"{'gates':>8}" + "".join(f"{run:>24}" for run in result))
        ns.append(n)
        for run, error in result.items():
            errors.setdefault(run, []).append(error)
        for code in CODES:
            if found[code] is None and result[code] < result[plain_for[code]]:
                found[code] = n
        print(f"{n:>8}" + "".join(f"{error:>24.4f}" for error in result.values()), flush=True)
        n += 2
    return ns, errors, found, plain_for


# ---- Printing, CSV files and plots ----

def gate_set_label(gate_set):
    # e.g. 'gate set "repeat" (X, Y, Z)'
    return f'gate set "{gate_set}" ({", ".join(g.upper() for g in GATE_SETS[gate_set][1])})'


def pay_off_text(n, max_gates):
    return f"never, up to {max_gates} gates" if n is None else f"{n} gates"


def plot(gate_set, results, max_gates, shots, path):
    # Error vs number of gates for no correction and each code: even numbers of gates as solid lines, odd as dashed,
    # with a dotted line where each code pays off
    plt = pyplot()
    colors = dict(zip(next(iter(results.values()))[1], COLORS))

    fig, ax = plt.subplots(figsize=(11, 6))
    for parity, (ns, errors, found) in results.items():
        for run, run_errors in errors.items():
            legend = f"{run}, {parity}"
            if run in found:
                legend += ": pays off at " + pay_off_text(found[run], max_gates)
                if found[run] is not None:
                    ax.axvline(found[run], color=colors[run], ls=":", lw=1.2)
            ax.plot(ns, run_errors, "-" if parity == "even" else "--", color=colors[run], lw=2, label=legend)
    ax.set_title(f"{gate_set_label(gate_set)} on Fez noise: error with and without correction ({shots} shots)",
                 color=INK)
    ax.set_xlabel("number of gates (solid = even, dashed = odd)", color=MUTED)
    ax.set_ylabel("error from the exact answer, |P(1) - exact P(1)|", color=MUTED)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    style(ax)
    save_plot(fig, path)


def run(gate_sets, max_gates=300, shots=1000, seed=3, data_qubits=DEFAULT_DATA_QUBITS, csv_file=None,
        pay_off_csv_file=None, plot_dir=None):
    # For each gate set, counts up through the even and the odd numbers of gates until both codes pay off (or
    # max_gates). seed fixes the test circuit, transpiler and simulator. data_qubits: the Fez qubits for q_0, q_1, q_2
    unknown = [g for g in gate_sets if g not in GATE_SETS]
    if unknown:
        raise ValueError(f"unknown gate set(s) {unknown}; use any of {list(GATE_SETS)}")
    rows, pay_off_rows = [], []
    for gate_set in gate_sets:
        print(f"\n{gate_set_label(gate_set)}, {shots} shots, seed {seed}, Fez qubits {list(data_qubits)}. "
              f"Error = |P(1) - exact P(1)| on Fez noise")
        results = {}
        for parity, first in STARTS.items():
            print(f"\n{parity.capitalize()} numbers of gates:")
            ns, errors, found, plain_for = find_pay_off(gate_set, first, max_gates, shots, seed, data_qubits)
            results[parity] = ns, errors, found
            rows += [[gate_set, n, parity, run, shots, seed, round(errors[run][i], 6)]
                     for i, n in enumerate(ns) for run in errors]
            pay_off_rows += [[gate_set, code, parity, plain_for[code], shots, seed,
                              "" if found[code] is None else found[code]] for code in CODES]
        print("\nHow many gates each code needs to pay off (the fewest where it beats no correction):")
        for code in CODES:
            print(f"  {code:<22}" + "    ".join(f"{parity}: {pay_off_text(results[parity][2][code], max_gates):<26}"
                                                for parity in STARTS))
        if plot_dir:
            plot(gate_set, results, max_gates, shots, os.path.join(plot_dir, f"pay_off_{gate_set}.png"))
    if csv_file:
        write_csv(csv_file, ["gate_set", "gates", "parity", "run", "shots", "seed", "error"], rows)
    if pay_off_csv_file:
        write_csv(pay_off_csv_file, ["gate_set", "code", "parity", "compared_with", "shots", "seed",
                                     "pays_off_at_gates"], pay_off_rows)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    # Gate sets to run (keys of compare_fez.GATE_SETS), one plot each: "all" = random X, Y, Z, S, T, id
    # "xz" = random X and Z   "repeat" = X, Y, Z in order, over and over   "x", "y", "z" = only that gate
    # (even/odd decides the exact answer for "x" and "y"; for "z" it is always 0, and for "repeat" it depends on the
    # number of gates mod 3)
    GATE_SETS_TO_RUN = ["x", "y", "z", "repeat"]
    MAX_GATES = 200        # stop counting here if a code still hasn't paid off
    SHOTS = 1000          # shots per run, at every number of gates
    SEED = 3               # fixes the test circuit, the transpiler and the simulator (same SEED = same results)
    # Fez qubits for q_0, q_1, q_2 of the codes: compare_fez's defaults (in fez_common.py). No correction runs on the
    # qubit each code is measured on after routing, as in the hardware runs
    DATA_QUBITS = DEFAULT_DATA_QUBITS
    CSV_FILE = os.path.join(CSV_DIR, "pay_off.csv")                   # every error, for every gate set
    PAY_OFF_CSV_FILE = os.path.join(CSV_DIR, "pay_off_points.csv")    # each code's pay-off points
    PLOT_DIR = IMAGE_DIR                                              # pay_off_<gate set>.png for each gate set
    # (None skips any of the output files)

    run(GATE_SETS_TO_RUN, max_gates=MAX_GATES, shots=SHOTS, seed=SEED, data_qubits=DATA_QUBITS, csv_file=CSV_FILE,
        pay_off_csv_file=PAY_OFF_CSV_FILE, plot_dir=PLOT_DIR)
