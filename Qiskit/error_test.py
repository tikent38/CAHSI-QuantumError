from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from bit_flip_code import bit_flip_code

SHOTS = 4000
simulator = AerSimulator()

#Example of generating a circuit to run the error codes test on
def h_circuit():
    prep = QuantumCircuit(1)
    prep.h(0)
    return prep


def run(error_qubit=None):

    errors = None if error_qubit is None else [error_qubit] #convert error qubits into an array
    qc = bit_flip_code(h_circuit(), errors)

    counts = simulator.run(qc, shots=SHOTS).result().get_counts()

    # Count keys look like "out s", e.g. "1 11" -> out=1, syndrome a_1 a_0 = 11
    syndromes = {key.split()[1] for key in counts}
    ones = sum(n for key, n in counts.items() if key.split()[0] == "1")
    return syndromes, ones / SHOTS


if __name__ == "__main__":
    for error in [None, 0, 1, 2]:
        syndromes, p1 = run(error)
        label = "no error" if error is None else f"X on q{error}"
        print(f"H|0>, {label:8}: syndrome {syndromes}, P(out=1) = {p1:.3f}")
