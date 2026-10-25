# simulator_measured.py
# The Y gate circuit's error on every Fez qubit, from actually running it on the Fez noise simulator. Each result is
# a fraction of shots, so it comes with shot noise (one standard error)
import math
import random
import statistics

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

from noise_common import fez_ops, ideal_result


def simulator_measured(backend, qubits, num_gates, start_bit, shots, seed):
    # {qubit: (error, shot noise)}: the fraction of shots that didn't read the no-noise result
    ops = fez_ops(num_gates, start_bit)
    wrong = str(1 - ideal_result(num_gates, start_bit))
    circuits = [y_test_circuit(backend, q, ops) for q in qubits]
    # Every qubit's circuit runs in one call, so Aer can run them in parallel
    counts = make_simulator(backend).run(circuits, shots=shots,
                                         seed_simulator=random.Random(seed).randrange(2**31)).result().get_counts()
    results = {}
    for q, c in zip(qubits, counts):
        error = c.get(wrong, 0) / shots
        results[q] = (error, binomial_error(error, shots))
    return results


def y_test_circuit(backend, qubit, ops):
    # The Y gate circuit on one physical Fez qubit, already in Fez's gates so nothing is transpiled or moved
    qc = QuantumCircuit(backend.num_qubits, 1)
    for op in ops:
        qc.append(op, [qubit])
    qc.measure(qubit, 0)
    return qc


def make_simulator(backend):
    # The Fez noise simulator. density_matrix applies every noise channel exactly instead of sampling which error
    # happened, so the only randomness left is from the limited number of shots, as on the hardware.
    # max_parallel_experiments=0 lets Aer run as many circuits at once as the computer has cores
    return AerSimulator.from_backend(backend, method="density_matrix", max_parallel_experiments=0)


def binomial_error(p, shots):
    # Standard error of a fraction measured from `shots` shots. Floored at half a shot so a result of exactly 0 still
    # gets an uncertainty
    return max(math.sqrt(p * (1 - p) / shots), 0.5 / shots)


if __name__ == "__main__":
    # ---- Settings ----
    QUBITS = None              # list of Fez qubits, e.g. [0, 1, 2]; None uses all 156
    NUM_GATES = 150            # how many Y gates in a row on each qubit
    START_BIT = 0              # start each qubit in |0> or |1>
    SHOTS = 10000              # shots per qubit
    SEED = 3                   # sets the simulator's randomness (same SEED = same results)

    backend = FakeFez()
    qubits = QUBITS if QUBITS is not None else list(range(backend.num_qubits))
    results = simulator_measured(backend, qubits, NUM_GATES, START_BIT, SHOTS, SEED)
    best = sorted(qubits, key=lambda q: results[q][0])[:5]
    print(f"Simulator measured error, {NUM_GATES} Y gates starting in |{START_BIT}>, {SHOTS} shots: mean "
          f"{statistics.mean(e for e, _ in results.values()):.4f}, best qubits "
          f"{', '.join(f'{q} ({results[q][0]:.4f} ± {results[q][1]:.4f})' for q in best)}")
