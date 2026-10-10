from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import matplotlib

from bit_flip_code import bit_flip_code
from bit_flip_code import print_correction as print_bit_flip_correction
from phase_flip_code import phase_flip_code
from phase_flip_code import print_correction as print_phase_flip_correction

SHOTS = 4000
simulator = AerSimulator()

#Example of generating a circuit to run the error codes test on



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


def print_result(syndromes, p1):
    print(f"\n  {'syndrome (a_1 a_0):':20} {', '.join(sorted(syndromes))}")
    print(f"  {'P(out=1):':20} {p1:.3f}\n")


def test_bit_flip():
    print("=" * 60)
    print("  BIT FLIP CODE   (input: H|0>)")
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
    print("  PHASE FLIP CODE   (input: H|0>)")
    print("=" * 60)
    for error in [None, 0, 1, 2]:
        label = "no error" if error is None else f"Z on q{error}"
        print(f"\n--- {label} ---\n")
        syndromes, p1 = run(error, phase_flip_code)
        print_result(syndromes, p1)
        for s in sorted(syndromes):
            print_phase_flip_correction(s)


if __name__ == "__main__":
    #test_bit_flip() #run bit_flip_code 
    test_phase_flip() #run phase_flip_code
