# calibration_predicted.py
# The Y gate circuit's error on every Fez qubit if the real ibm_fez behaved exactly as a calibration file downloaded
# from IBM Quantum says. Calculated exactly like simulator_predicted.py (same predicted_error), but with each qubit's
# noise built from the calibration file's T1, T2, gate length, X gate error and readout errors instead of FakeFez's
import os
import statistics

import numpy as np
from qiskit.quantum_info import SuperOp, average_gate_fidelity
from qiskit_aer.noise import depolarizing_error, thermal_relaxation_error
from qiskit_ibm_runtime.fake_provider import FakeFez

from noise_common import CSV_DIR, fez_ops, ideal_result, load_calibration
from simulator_predicted import aer_noise, predicted_error


def calibration_predicted(calibration_file, qubits, num_gates, start_bit):
    # {qubit: error}, or None for a qubit with numbers missing from the calibration file
    ops = fez_ops(num_gates, start_bit)
    real, _ = load_calibration(calibration_file, qubits)
    errors = {}
    for q in qubits:
        channel, readout = calibration_noise(real.get(q))
        errors[q] = None if channel is None else predicted_error(ops, channel, readout, ideal_result(num_gates,
                                                                                                   start_bit))
    return errors


def gate_channel(t1_us, t2_us, gate_ns, gate_error):
    # The single-qubit gate noise built from a qubit's T1, T2, gate length and gate error, the same way Aer builds
    # the simulator's: T1/T2 relaxation for the length of the gate, plus depolarizing noise for whatever part of the
    # gate error T1/T2 don't explain (none if T1/T2 alone are already worse). T2 is capped at 2 * T1 as Aer does
    t1, t2, time = t1_us * 1e-6, min(t2_us, 2 * t1_us) * 1e-6, gate_ns * 1e-9
    relax = thermal_relaxation_error(t1, t2, time)
    relax_fid = average_gate_fidelity(relax)
    if gate_error <= 1 - relax_fid:
        return relax
    depol = min(2 * (gate_error - (1 - relax_fid)) / (2 * relax_fid - 1), 4 / 3)
    return depolarizing_error(depol, 1).compose(relax)


def calibration_noise(cal):
    # Gate noise and readout error for one qubit from the calibration file, or (None, None) if a number is missing.
    # Unlike the simulator, the readout error is different for 0 -> 1 and 1 -> 0, as the file lists them
    needed = ("t1_us", "t2_us", "gate_length_ns", "x_error", "p1_given_0", "p0_given_1")
    if cal is None or any(cal.get(key) is None for key in needed):
        return None, None
    channel = gate_channel(cal["t1_us"], cal["t2_us"], cal["gate_length_ns"], cal["x_error"])
    readout = [[1 - cal["p1_given_0"], cal["p1_given_0"]], [cal["p0_given_1"], 1 - cal["p0_given_1"]]]
    return channel, readout


def check_gate_channel(backend, qubits):
    # gate_channel is how the calibration noise is built. Build the simulator's noise with it from FakeFez's numbers
    # and compare with Aer's own: if they match (difference ~0), the calibration prediction is made the same way as
    # the simulator's. Returns the largest difference over all qubits
    target = backend.target
    aer_gates, _ = aer_noise(backend)
    worst = 0
    for q in qubits:
        props = target.qubit_properties[q]
        mine = gate_channel(props.t1 * 1e6, props.t2 * 1e6, target["x"][(q,)].duration * 1e9, target["x"][(q,)].error)
        worst = max(worst, np.abs(SuperOp(mine).data - SuperOp(aer_gates[q]).data).max())
    return worst


if __name__ == "__main__":
    # ---- Settings ----
    QUBITS = None              # list of Fez qubits, e.g. [0, 1, 2]; None uses all 156
    NUM_GATES = 150            # how many Y gates in a row on each qubit
    START_BIT = 0              # start each qubit in |0> or |1>
    # Real calibration file downloaded from IBM Quantum
    CALIBRATION_FILE = os.path.join(CSV_DIR, "ibm_fez_calibrations_2026-10-24T18_48_15Z.csv")

    backend = FakeFez()
    qubits = QUBITS if QUBITS is not None else list(range(backend.num_qubits))
    errors = calibration_predicted(CALIBRATION_FILE, qubits, NUM_GATES, START_BIT)
    known = [q for q in qubits if errors[q] is not None]
    best = sorted(known, key=errors.get)[:5]
    print(f"Calibration predicted error ({os.path.basename(CALIBRATION_FILE)}), {NUM_GATES} Y gates starting in "
          f"|{START_BIT}>: mean {statistics.mean(errors[q] for q in known):.4f}, best qubits "
          f"{', '.join(f'{q} ({errors[q]:.4f})' for q in best)}")
    missing = [q for q in qubits if errors[q] is None]
    if missing:
        print(f"No prediction (numbers missing from the calibration file): {missing}")
    print(f"Calibration noise built the same way as Aer's (largest difference on FakeFez's numbers: "
          f"{check_gate_channel(backend, qubits):.1e})")
