# error_test.py
# Runs each noiseless code (bit_flip_code.py, phase_flip_code.py, shor_code.py) with no error and with an error on
# each qubit, and prints the circuit, the measured syndrome, and the correction it calls for.
# Choose which codes to test at the bottom of the file
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from bit_flip_code import bit_flip_code
from bit_flip_code import print_correction as print_bit_flip_correction
from phase_flip_code import phase_flip_code
from phase_flip_code import print_correction as print_phase_flip_correction
from shor_code import shor_code
from shor_code import print_correction as print_shor_correction

SHOTS = 4000
simulator = AerSimulator()


def test_bit_flip():
    # The bit-flip code with no error, then an X error on each qubit in turn
    test_three_qubit_code("BIT FLIP CODE", bit_flip_code, "X", print_bit_flip_correction)


def test_phase_flip():
    # The phase-flip code with no error, then a Z error on each qubit in turn
    test_three_qubit_code("PHASE FLIP CODE", phase_flip_code, "Z", print_phase_flip_correction)


def test_shor(show_diagrams=False):
    # The Shor code with no error, single X and Z errors, a Y error, and an X and a Z on different qubits.
    # show_diagrams=True also opens every circuit as a picture once all the cases have run
    print_title("SHOR CODE")
    # (label, x_errors, z_errors). X and Z on the same qubit is a Y error
    cases = [("no error", None, None)]
    cases += [(f"X on q{q}", [q], None) for q in (0, 4, 8)]
    cases += [(f"Z on q{q}", None, [q]) for q in (0, 4, 8)]
    cases += [("Y on q4", [4], [4]), ("X on q2 and Z on q7", [2], [7])]
    for label, x_errors, z_errors in cases:
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run_shor(x_errors, z_errors, label, show_diagrams)
        print(f"\n  {'P(out=1):':20} {p1:.3f}\n")
        for p, b2, b1, b0 in sorted(syndromes):
            print_shor_correction([b0, b1, b2], p)
    if show_diagrams:
        import matplotlib.pyplot as plt
        plt.show()


# ---- Helpers ----

def test_three_qubit_code(title, code, error_gate, print_correction):
    # Runs a 3-qubit code with no error, then with an error_gate ("X" or "Z") error on q_0, q_1 and q_2 in turn
    print_title(title)
    for error in [None, 0, 1, 2]:
        label = "no error" if error is None else f"{error_gate} on q{error}"
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run_code(code, error)
        print_result(syndromes, p1)
        for s in sorted(syndromes):
            print_correction(s)


def run_code(code, error_qubit=None):
    # Runs a 3-qubit code with an error on error_qubit (None = no error). Returns the syndromes measured and P(out=1)
    errors = None if error_qubit is None else [error_qubit]
    qc = code(QuantumCircuit(1), errors)
    # Comment out the line below to stop the circuit diagram printing to the terminal.
    # fold=-1 keeps the whole circuit on one line instead of splitting it into pieces
    print(qc.draw(fold=-1))

    counts = simulator.run(qc, shots=SHOTS).result().get_counts()
    # Neither 3-qubit code corrects inside the circuit. After decoding, both leave an error on q_0 as a flipped
    # out bit, so the same fix works for both
    counts = correct_out_bit(counts)

    # Count keys look like "out s", e.g. "1 11" -> out=1, syndrome a_1 a_0 = 11
    syndromes = {key.split()[1] for key in counts}
    ones = sum(n for key, n in counts.items() if key.split()[0] == "1")
    return syndromes, ones / SHOTS


def run_shor(x_errors=None, z_errors=None, label="", show_diagram=False):
    # Runs the Shor code with the given errors. Returns the syndromes measured and P(out=1)
    qc = shor_code(QuantumCircuit(1), x_errors, z_errors)
    if show_diagram:
        # Draw the circuit as a matplotlib figure; test_shor opens them all together at the end
        fig = qc.draw(output="mpl", fold=-1)
        fig.suptitle(f"Shor code: {label}")

    counts = correct_out_bit(simulator.run(qc, shots=SHOTS).result().get_counts())

    # Count keys look like "out p b2 b1 b0", e.g. "0 11 00 00 00" -> out=0, phase syndrome a_7 a_6 = 11
    syndromes = {tuple(key.split()[1:]) for key in counts}
    ones = sum(n for key, n in counts.items() if key.split()[0] == "1")
    return syndromes, ones / SHOTS


def correct_out_bit(counts):
    # None of the noiseless codes correct inside the circuit, so fix the results here. Every count key starts with the
    # out bit, then the syndrome that decides whether it needs fixing: "out s" for bit_flip_code and phase_flip_code,
    # "out p b2 b1 b0" for shor_code (p = the phase syndrome, then the three bit syndromes). After decoding, only
    # syndrome 01 changes the out bit: a flip on q_0 for the 3-qubit codes, a sign flip in block 0 for the Shor code.
    # (In the Shor code a bit flip on q_0, q_3 or q_6 only flips the sign of the result, which measuring out can't see)
    corrected = {}
    for key, n in counts.items():   # n is how many shots gave this key
        out, syndrome, *rest = key.split()
        if syndrome == "01":   # flip the out bit back
            out = "1" if out == "0" else "0"
        new_key = " ".join([out, syndrome, *rest])
        corrected[new_key] = corrected.get(new_key, 0) + n
    return corrected


# ---- Printing ----

def print_title(title):
    print("=" * 60)
    print(f"  {title}   (input: |0>)")
    print("=" * 60)


def print_result(syndromes, p1):
    print(f"\n  {'syndrome (a_1 a_0):':20} {', '.join(sorted(syndromes))}")
    print(f"  {'P(out=1):':20} {p1:.3f}\n")


if __name__ == "__main__":
    # Uncomment the codes to test
    test_bit_flip()        # run bit_flip_code
    # test_phase_flip()    # run phase_flip_code
    # test_shor()          # run shor_code; test_shor(show_diagrams=True) also opens every circuit as a picture
