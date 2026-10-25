import matplotlib.pyplot as plt
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
    print("=" * 60)
    print("  BIT FLIP CODE   (input: |0>)")
    print("=" * 60)
    for error in [None, 0, 1, 2]:
        label = "no error" if error is None else f"X on q{error}"
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run(error, bit_flip_code)
        print_result(syndromes, p1)
        for s in sorted(syndromes):
            print_bit_flip_correction(s)


def test_phase_flip():
    print("=" * 60)
    print("  PHASE FLIP CODE   (input: |0>)")
    print("=" * 60)
    for error in [None, 0, 1, 2]:
        label = "no error" if error is None else f"Z on q{error}"
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run(error, phase_flip_code)
        print_result(syndromes, p1)
        for s in sorted(syndromes):
            print_phase_flip_correction(s)


def test_shor():
    print("=" * 60)
    print("  SHOR CODE   (input: |0>)")
    print("=" * 60)
    # (label, x_errors, z_errors). X and Z on the same qubit is a Y error
    cases = [("no error", None, None)]
    cases += [(f"X on q{q}", [q], None) for q in (0, 4, 8)]
    cases += [(f"Z on q{q}", None, [q]) for q in (0, 4, 8)]
    cases += [("Y on q4", [4], [4]), ("X on q2 and Z on q7", [2], [7])]
    for label, x_errors, z_errors in cases:
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run_shor(x_errors, z_errors, label)
        print(f"\n  {'P(out=1):':20} {p1:.3f}\n")
        for p, b2, b1, b0 in sorted(syndromes):
            print_shor_correction([b0, b1, b2], p)


def run(error_qubit=None, code=bit_flip_code):

    errors = None if error_qubit is None else [error_qubit] #convert error qubits into an array
    qc = code(QuantumCircuit(1), errors)
    #comment out the line below to stop the circuit diagram printing to the terminal
    #fold=-1 keeps the whole circuit on one line instead of splitting it into pieces
    print(qc.draw(fold=-1))

    counts = simulator.run(qc, shots=SHOTS).result().get_counts()
    # Neither code corrects inside the circuit. After decoding, both leave an error on
    # q_0 as a flipped out bit, so the same fix works for both
    counts = correct_bit_flip(counts)

    # Count keys look like "out s", e.g. "1 11" -> out=1, syndrome a_1 a_0 = 11
    syndromes = {key.split()[1] for key in counts}
    ones = sum(n for key, n in counts.items() if key.split()[0] == "1")
    return syndromes, ones / SHOTS


def run_shor(x_errors=None, z_errors=None, label=""):
    qc = shor_code(QuantumCircuit(1), x_errors, z_errors)
    #comment out the lines below to stop the circuit diagrams from opening
    #draws each circuit as a matplotlib figure; they all open together at plt.show() in test_shor
    fig = qc.draw(output="mpl", fold=-1)
    fig.suptitle(f"Shor code: {label}")

    counts = correct_shor(simulator.run(qc, shots=SHOTS).result().get_counts())

    # Count keys look like "out p b2 b1 b0", e.g. "0 11 00 00 00" -> out=0, phase syndrome a_7 a_6 = 11
    syndromes = {tuple(key.split()[1:]) for key in counts}
    ones = sum(n for key, n in counts.items() if key.split()[0] == "1")
    return syndromes, ones / SHOTS


def correct_bit_flip(counts):
    # bit_flip_code and phase_flip_code don't correct inside the circuit, so fix the results here.
    # Only a flip on q_0 (syndrome 01) changes the decoded output, so flip the out bit for those
    corrected = {}
    for key, n in counts.items(): # key is of form "out s" and n is shot count
        out, s = key.split() # out is the measured qbit s is the syndrome
        if s == "01": #if the syndrome says q0 flipped then flip it back
            out = "1" if out == "0" else "0"
        new_key = f"{out} {s}" #rebuild the dict with a new corrected out
        corrected[new_key] = corrected.get(new_key, 0) + n
    return corrected


def correct_shor(counts):
    # shor_code doesn't correct inside the circuit either. After decoding, only a sign flip in
    # block 0 (phase syndrome 01) changes the measured output, so flip the out bit for those.
    # (A bit flip on q_0, q_3 or q_6 flips the sign of the result, which measuring out can't see)
    corrected = {}
    for key, n in counts.items(): # key is of form "out p b2 b1 b0" and n is shot count
        out, p, *bits = key.split() # out is the measured qbit, p the phase syndrome, bits the bit syndromes
        if p == "01": #if the phase syndrome says block 0 flipped sign then flip out back
            out = "1" if out == "0" else "0"
        new_key = " ".join([out, p, *bits]) #rebuild the dict with a new corrected out
        corrected[new_key] = corrected.get(new_key, 0) + n
    return corrected


def print_result(syndromes, p1):
    print(f"\n  {'syndrome (a_1 a_0):':20} {', '.join(sorted(syndromes))}")
    print(f"  {'P(out=1):':20} {p1:.3f}\n")


    #plt.show() #open every circuit diagram once all the cases have run


if __name__ == "__main__":
    test_bit_flip() #run bit_flip_code

    #test_phase_flip() #run phase_flip_code
    #test_shor() #run shor_code
