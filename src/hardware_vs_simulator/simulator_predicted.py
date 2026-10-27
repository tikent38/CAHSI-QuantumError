# simulator_predicted.py
# The Y gate circuit's error on every Fez qubit, calculated exactly from the simulator's own noise model: no shots,
# so no shot noise. If the simulator works, running the circuit (simulator_measured.py) gives this within shot noise
import statistics

import numpy as np
from qiskit.quantum_info import Operator, SuperOp
from qiskit_aer.noise.device import basic_device_gate_errors, basic_device_readout_errors
from qiskit_ibm_runtime.fake_provider import FakeFez

from noise_common import fez_ops, ideal_result


def simulator_predicted(backend, qubits, num_gates, start_bit):
    # {qubit: error} for every qubit, from the simulator's noise model
    ops = fez_ops(num_gates, start_bit)
    ideal_bit = ideal_result(num_gates, start_bit)
    gates, readout = aer_noise(backend)
    return {q: predicted_error(ops, gates[q], readout[q], ideal_bit) for q in qubits}


def aer_noise(backend):
    # The noise the simulator applies to each qubit, from the same Aer functions AerSimulator.from_backend uses to
    # build its noise model: the X gate's noise channel and the readout error matrix, keyed by qubit
    gates = {q[0]: error for name, q, error in basic_device_gate_errors(target=backend.target)
             if name == "x" and len(q) == 1}
    readout = {q[0]: error.probabilities for q, error in basic_device_readout_errors(target=backend.target)}
    return gates, readout


def predicted_error(ops, channel, readout, ideal_bit):
    # Exact chance the circuit gives the wrong answer, with no shots: follow the qubit's density matrix through every
    # gate, apply the noise channel after each noisy gate (sx and x; rz has no noise on Fez), then apply the readout
    # error. This is the same noise, in the same order, that Aer applies when it runs the circuit
    noise = SuperOp(channel).data
    vec = np.array([1, 0, 0, 0], dtype=complex)   # |0><0|, written as a column
    for op in ops:
        vec = SuperOp(Operator(op)).data @ vec
        if op.name in ("sx", "x"):
            vec = noise @ vec
    p0, p1 = vec[0].real, vec[3].real   # the diagonal of the density matrix
    read_1 = p0 * readout[0][1] + p1 * readout[1][1]
    return read_1 if ideal_bit == 0 else 1 - read_1


if __name__ == "__main__":
    # ---- Settings ----
    QUBITS = None              # list of Fez qubits, e.g. [0, 1, 2]; None uses all 156
    NUM_GATES = 150            # how many Y gates in a row on each qubit
    START_BIT = 0              # start each qubit in |0> or |1>

    backend = FakeFez()
    qubits = QUBITS if QUBITS is not None else list(range(backend.num_qubits))
    errors = simulator_predicted(backend, qubits, NUM_GATES, START_BIT)
    best = sorted(qubits, key=errors.get)[:5]
    print(f"Simulator predicted error, {NUM_GATES} Y gates starting in |{START_BIT}>: mean "
          f"{statistics.mean(errors.values()):.4f}, best qubits {', '.join(f'{q} ({errors[q]:.4f})' for q in best)}")
