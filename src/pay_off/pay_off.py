# pay_off.py
# Runs compare_fez.py's comparison at several numbers of gates, for each chosen gate set, and plots how far the result
# is from the exact answer with no correction and with the Toffoli bit-flip and phase-flip codes. Shows where each code
# starts paying off (has a smaller error than no correction). Change the experiment in the settings block at the bottom
# of the file
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


def sweep(gate_set, ns, shots, seed, data_qubits):
    # compare_fez's comparison at every number of gates in ns, printing one table row per number as it goes.
    # Returns {run: [error at each number of gates]}, where error = |P(1) - exact P(1)| on the Fez noise simulator, and
    # the no-correction run each code is compared with, {code: run} (no correction runs on the qubit the code is
    # measured on, e.g. "no correction (Fez 86)")
    errors = {}
    for n in ns:
        result, plain_for = compare(num_gates=n, shots=shots, seed=seed, gate_set=gate_set, codes=CODES,
                                    data_qubits=data_qubits, show=False)
        result = {run.removeprefix("Fez noise, "): error for run, error in result.items() if run != "no noise"}
        if not errors:   # the first number of gates: print the table's header
            print_table_header(f"{'gates':>8}" + "".join(f"{run:>24}" for run in result))
        elif list(result) != list(errors):
            raise RuntimeError(f"at {n} gates routing measured a code on a different qubit: {list(result)}")
        row = f"{n:>8}"
        for run, error in result.items():
            errors.setdefault(run, []).append(error)
            better = run in plain_for and error < result[plain_for[run]]
            row += f"{error:>23.4f}{'*' if better else ' '}"
        print(row, flush=True)
    return errors, plain_for


def pays_off(ns, plain, coded):
    # Where the code starts having a smaller error than no correction: (estimated number of gates, last number tested
    # where it was worse, first where it was better), with the estimate on a straight line between the two and None
    # for "worse" if it was already better at the fewest gates tested; or None if it is never better.
    # Works back from where the code helps the most, so shot noise at large numbers of gates (where both errors level
    # off) doesn't count as paying off
    helps = [p - c for p, c in zip(plain, coded)]
    best = max(range(len(ns)), key=lambda i: helps[i])
    if helps[best] <= 0:
        return None
    i = best
    while i > 0 and helps[i - 1] > 0:
        i -= 1
    if i == 0:
        return ns[0], None, ns[0]
    before, after = helps[i - 1], helps[i]
    return ns[i - 1] + (ns[i] - ns[i - 1]) * -before / (after - before), ns[i - 1], ns[i]


# ---- Printing, CSV files and plots ----

def gate_set_label(gate_set):
    # e.g. 'gate set "repeat" (X, Y, Z)'
    return f'gate set "{gate_set}" ({", ".join(g.upper() for g in GATE_SETS[gate_set][1])})'


def print_pay_off(found):
    print("Where each code starts paying off:")
    for name, point in found.items():
        if point is None:
            print(f"  {name:<22} never, for the numbers of gates tested")
        elif point[1] is None:
            print(f"  {name:<22} already better at {point[2]} gates, the fewest tested")
        else:
            print(f"  {name:<22} about {point[0]:.0f} gates  (worse at {point[1]}, better from {point[2]})")


def plot(gate_set, ns, errors, found, shots, path):
    # Error vs number of gates for no correction and each code, with a dashed line where each code starts paying off
    plt = pyplot()
    colors = dict(zip(errors, COLORS))

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for run in errors:
        legend = run
        if run in found:
            point = found[run]
            legend += ": " + ("doesn't pay off" if point is None else f"pays off at about {point[0]:.0f} gates")
        ax.plot(ns, errors[run], "-o", color=colors[run], lw=2, ms=5, markeredgecolor="white", markeredgewidth=1,
                label=legend)
    for name, point in found.items():
        if point is not None:
            ax.axvline(point[0], color=colors[name], ls="--", lw=1.2)

    # Linear up to 10 gates, then logarithmic, so the pay-off region and large numbers of gates both fit
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xlim(0, max(ns) * 1.1)
    ax.set_title(f"{gate_set_label(gate_set)} on Fez noise: error with and without correction ({shots} shots)",
                 color=INK)
    ax.set_xlabel("number of gates", color=MUTED)
    ax.set_ylabel("error from the exact answer, |P(1) - exact P(1)|", color=MUTED)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    style(ax)
    save_plot(fig, path)


def run(gate_sets, ns, shots=10000, seed=3, data_qubits=DEFAULT_DATA_QUBITS, csv_file=None, plot_dir=None):
    # One sweep and one plot per gate set. seed fixes the test circuit, transpiler and simulator, so every number of
    # gates uses the same circuit, just cut to a different length. data_qubits: the Fez qubits for q_0, q_1, q_2 of
    # the codes
    ns = sorted(set(ns))
    unknown = [g for g in gate_sets if g not in GATE_SETS]
    if unknown:
        raise ValueError(f"unknown gate set(s) {unknown}; use any of {list(GATE_SETS)}")
    rows = []
    for gate_set in gate_sets:
        print(f"\n{gate_set_label(gate_set)}, {shots} shots, seed {seed}, Fez qubits {list(data_qubits)}. "
              f"Error = |P(1) - exact P(1)| on Fez noise")
        errors, plain_for = sweep(gate_set, ns, shots, seed, data_qubits)
        print("(* = smaller error than no correction on the qubit the code is measured on)")
        found = {code: pays_off(ns, errors[plain_for[code]], errors[code]) for code in CODES}
        print_pay_off(found)
        rows += [[gate_set, n, run, shots, seed, round(errors[run][i], 6)] for i, n in enumerate(ns) for run in errors]
        if plot_dir:
            plot(gate_set, ns, errors, found, shots, os.path.join(plot_dir, f"pay_off_{gate_set}.png"))
    if csv_file:
        write_csv(csv_file, ["gate_set", "gates", "run", "shots", "seed", "error"], rows)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    # Gate sets to run (keys of compare_fez.GATE_SETS), one plot each: "all" = random X, Y, Z, S, T, id
    # "xz" = random X and Z   "repeat" = X, Y, Z in order, over and over   "x", "y", "z" = only that gate
    GATE_SETS_TO_RUN = ["x","y","z", "repeat"]
    # Numbers of gates to try. Keep them close together where the codes start paying off: the pay-off point is
    # estimated between the two numbers on either side of it. These are multiples of 6, so the exact answer is 0 at
    # every point for "x" (each X flips it) and "repeat" (X, Y, Z repeats every 3 gates); mixing answers of 0 and 1
    # makes the curves zig-zag, since the codes do worse when the answer is 1
    N_VALUES = [0, 12, 24, 35, 48, 59, 72]
    SHOTS = 10000          # shots per run, at every number of gates
    SEED = 3               # fixes the test circuit, the transpiler and the simulator (same SEED = same results)
    # Fez qubits for q_0, q_1, q_2 of the codes: compare_fez's defaults (in fez_common.py). No correction runs on the
    # qubit each code is measured on after routing, as in the hardware runs
    DATA_QUBITS = DEFAULT_DATA_QUBITS
    CSV_FILE = os.path.join(CSV_DIR, "pay_off.csv")   # every error, for every gate set; None skips it
    PLOT_DIR = IMAGE_DIR                              # pay_off_<gate set>.png for each gate set; None skips them

    run(GATE_SETS_TO_RUN, N_VALUES, shots=SHOTS, seed=SEED, data_qubits=DATA_QUBITS, csv_file=CSV_FILE,
        plot_dir=PLOT_DIR)
