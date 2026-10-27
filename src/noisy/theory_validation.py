# theory_validation.py
# Theoretical validation: run the three-qubit codes with X or Z errors of a chosen probability p, and compare the
# logical error rate with what theory says. Writes every result to a CSV file and plots theory vs simulation.
#
# What is tested, and what theory says (each qubit has the error with probability p):
#   no correction, X or Z error:          wrong if the one qubit has it            P = p
#   bit-flip code, X errors:              wrong if 2 or 3 of the 3 qubits do       P_L = 3p^2(1 - p) + p^3 = 3p^2 - 2p^3
#   phase-flip code, Z errors:            the same, in the |+>, |-> basis          P_L = 3p^2 - 2p^3
#   bit-flip code, Z errors (not fixed):  any odd number of Z's is a logical Z     P = 3p(1 - p)^2 + p^3
#   phase-flip code, X errors (not fixed): any odd number of X's is a logical Z    P = 3p(1 - p)^2 + p^3
#
# Which states: an error only shows up in the result if it changes the state being measured.
#   X errors flip |0> and |1>, so those runs start in |0> or |1> and measure normally.
#   Z errors don't change |0> or |1> (only their sign), so the no-correction and bit-flip-code runs
#   with Z errors start in |+> or |-> (H after preparing |0> or |1>) and put H before the measurement.
#   The phase-flip code already stores |0> as |+++>, so Z errors flip it and it uses |0> and |1>.
#   The same reasoning gives |+> and |-> for the phase-flip code with X errors.
# Every run is done for both starting states, and the failure rate is over both together (their average).
import os
import random
import sys

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, pauli_error

from bit_flip_encoded import bit_flip_encoded
from bit_flip_toffoli import bit_flip_toffoli
from fez_common import prob_one
from phase_flip_encoded import phase_flip_encoded
from phase_flip_toffoli import phase_flip_toffoli

# The code for printing, CSV files and plots lives in src/output_tools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from output_tools import COLORS, INK, MUTED, print_table_header, pyplot, save_plot, style, write_csv

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")

# Every run that can be tested: the code (None for no correction) and the error it corrects. A code's color in the
# plot follows its place here. To add a code, add it here
CODES = {
    "no correction": (None, None),
    "bit-flip, Toffoli": (bit_flip_toffoli, "X"),
    "phase-flip, Toffoli": (phase_flip_toffoli, "Z"),
    "bit-flip, if blocks": (bit_flip_encoded, "X"),
    "phase-flip, if blocks": (phase_flip_encoded, "Z"),
}
DEFAULT_CODES = ("no correction", "bit-flip, Toffoli", "phase-flip, Toffoli")   # run() runs these unless told otherwise

# Each kind of run: the formula as printed, and the formula itself
FORMULAS = {
    "unprotected": ("p", lambda p: p),
    "corrected": ("3p^2 - 2p^3", lambda p: 3 * p**2 - 2 * p**3),
    "not corrected": ("3p(1-p)^2 + p^3", lambda p: 3 * p * (1 - p) ** 2 + p**3),
}


def case(name, error):
    # Which formula applies, and whether to use |+>/|-> (True) or |0>/|1> (False)
    corrects = CODES[name][1]
    if corrects is None:
        return "unprotected", error == "Z"
    if corrects == error:
        return "corrected", False
    return "not corrected", True


def build_circuits(name, plus_minus):
    # circuits[bit]: the run for this code, starting in state number bit
    circuits = {}
    for bit in (0, 1):
        qc = logical_circuit(bit, plus_minus)
        if name == "no correction":
            qc.measure_all()
        else:
            qc = CODES[name][0](qc)
        circuits[bit] = qc
    return circuits


def error_noise(error, p):
    # An X or Z error with probability p on every id gate, on every qubit. Nothing else is noisy
    noise = NoiseModel(basis_gates=["id"])
    if p > 0:
        noise.add_all_qubit_quantum_error(pauli_error([(error, p), ("I", 1 - p)]), "id")
    return noise


def failure(sim, circuits, shots, rng):
    # Fraction of shots where the measured result was wrong
    wrong = 0
    for bit, circuit in circuits.items():
        counts = sim.run(circuit, shots=shots, seed_simulator=rng.randrange(2**31)).result().get_counts()
        ones, zeros = prob_one(counts)
        wrong += zeros if bit else ones
    return wrong / (shots * len(circuits))


def simulate(ps, codes, errors, shots, seed):
    # One row per code, error type and p: the simulated and theoretical logical error rates
    rng = random.Random(seed)
    rows = []
    for error in errors:
        sims = {p: AerSimulator(noise_model=error_noise(error, p)) for p in ps}
        for name in codes:
            kind, plus_minus = case(name, error)
            formula, theory = FORMULAS[kind]
            circuits = build_circuits(name, plus_minus)
            states = "|+>,|->" if plus_minus else "|0>,|1>"
            for p in ps:
                simulated = failure(sims[p], circuits, shots, rng)
                expected = theory(p)
                total = 2 * shots
                rows.append({
                    "code": name,
                    "error": error,
                    "case": kind,
                    "states": states,
                    "p": p,
                    "shots": total,
                    "failures": round(simulated * total),
                    "simulated": round(simulated, 6),
                    "theory": round(expected, 6),
                    "formula": formula,
                    "difference": round(simulated - expected, 6),
                })
            print(f"done: {name}, {error} errors", flush=True)
    return rows


# ---- Helpers ----

def logical_circuit(bit, plus_minus):
    # Prepare |bit> (or |+>/|-> if plus_minus), then one id gate: the place where the injected error happens.
    # With plus_minus, H at the end turns |+>/|-> back into 0/1 for the measurement
    qc = QuantumCircuit(1)
    if bit:
        qc.x(0)
    if plus_minus:
        qc.h(0)
    qc.id(0)
    if plus_minus:
        qc.h(0)
    return qc


# ---- CSV, plot, and printing ----

def derivation(ax):
    # Where the three formulas come from, written onto ax (which is left without axes)
    ax.axis("off")
    lines = [
        ("No correction:", r"one qubit, wrong if it has the error, so  $P = p$"),
        ("Code fixes this error\n(bit-flip + X, phase-flip + Z):",
         r"majority vote fixes 1 error but not 2 or 3:  "
         r"$P_L = \binom{3}{2}p^2(1-p) + \binom{3}{3}p^3 = 3p^2 - 2p^3$"),
        ("", r"it helps when $P_L < p$:  $p - 3p^2 + 2p^3 = p(1-p)(1-2p) > 0$,  so for every $0 < p < 1/2$"),
        ("Code can't see this error\n(bit-flip + Z, phase-flip + X):",
         r"each error flips the whole encoded qubit's sign (e.g. Z: $|000\rangle + |111\rangle \to |000\rangle - |111\rangle$)"
         r" and two cancel,"),
        ("", r"so it is wrong after an odd number:  $P = \binom{3}{1}p(1-p)^2 + \binom{3}{3}p^3 = 3p(1-p)^2 + p^3$"
             r"  (worse than $p$ for $0 < p < 1/2$)"),
    ]
    y = 0.97
    for label, body in lines:
        ax.text(0, y, label, color=INK, fontsize=10, weight="bold", va="top", transform=ax.transAxes)
        ax.text(0.2, y, body, color=MUTED, fontsize=10.5, va="top", transform=ax.transAxes)
        y -= 0.15 if label == "" or "\n" not in label else 0.13


def plot(rows, path):
    # One panel per error type: theory (lines) vs simulation (dots) for every code,
    # with a short derivation of the formulas underneath
    plt = pyplot()
    errors = list(dict.fromkeys(r["error"] for r in rows))
    codes = list(dict.fromkeys(r["code"] for r in rows))
    colors = {name: COLORS[list(CODES).index(name) % len(COLORS)] if name in CODES else MUTED for name in codes}
    p_max = max(r["p"] for r in rows)
    fine = [p_max * i / 200 for i in range(201)]

    fig = plt.figure(figsize=(max(12, 6 * len(errors)), 9))
    layout = fig.add_gridspec(2, len(errors), height_ratios=[3, 1.5])
    axes = [fig.add_subplot(layout[0, i]) for i in range(len(errors))]
    for ax, error in zip(axes, errors):
        for name in codes:
            mine = [r for r in rows if r["code"] == name and r["error"] == error]
            if not mine:
                continue
            theory = FORMULAS[mine[0]["case"]][1]
            label = f"{name}  ({mine[0]['formula']})"
            ax.plot(fine, [theory(p) for p in fine], "-", color=colors[name], lw=2, alpha=0.55)
            ax.plot([r["p"] for r in mine], [r["simulated"] for r in mine], "o", color=colors[name], ms=6,
                    markeredgecolor="white", markeredgewidth=1, label=label)

        ax.set_title(f"{error} errors: theory (lines) vs simulation (dots)", color=INK)
        ax.set_ylabel("logical error rate", color=MUTED)
        ax.set_xlabel(f"{error}-error probability p on each qubit", color=MUTED)
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        style(ax)
    derivation(fig.add_subplot(layout[1, :]))
    save_plot(fig, path)


def print_summary(rows, codes, errors):
    # The largest gap between simulation and theory for each code and error
    print()
    print_table_header(f"{'code':<24}{'error':>6}{'formula':>18}{'largest |difference|':>22}")
    for name in codes:
        for error in errors:
            mine = [r for r in rows if r["code"] == name and r["error"] == error]
            worst = max(mine, key=lambda r: abs(r["difference"]))
            print(f"{name:<24}{error:>6}{mine[0]['formula']:>18}{abs(worst['difference']):>22.4f}")


def run(ps, codes=DEFAULT_CODES, errors=("X", "Z"), shots=10000, seed=3, csv_file="theory_validation.csv",
        plot_file=None):
    rows = simulate(ps, codes, errors, shots, seed)
    write_csv(csv_file, list(rows[0]), [list(r.values()) for r in rows])
    print_summary(rows, codes, errors)
    if plot_file:
        plot(rows, plot_file)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    P_VALUES = [0, 0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]   # error probability per qubit
    ERRORS = ("X", "Z")   # which error types to inject
    # Which runs to test (keys of CODES); add "bit-flip, if blocks" or "phase-flip, if blocks" for the if-block codes
    CODES_TO_RUN = ["no correction", "bit-flip, Toffoli", "phase-flip, Toffoli"]
    SHOTS = 10000         # shots per starting state, for every p and every run
    SEED = 3              # sets the simulator's randomness (same SEED = same results)
    CSV_FILE = os.path.join(CSV_DIR, "theory_validation.csv")     # where to write the results (csvs/)
    PLOT_FILE = os.path.join(IMAGE_DIR, "theory_validation.png")  # where to save the plot (images/); None skips it

    run(P_VALUES, codes=CODES_TO_RUN, errors=ERRORS, shots=SHOTS, seed=SEED, csv_file=CSV_FILE, plot_file=PLOT_FILE)
