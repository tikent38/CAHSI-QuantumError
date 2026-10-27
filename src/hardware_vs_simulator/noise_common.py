# noise_common.py
# Shared code for comparing the Fez noise simulator (FakeFez) with the real ibm_fez: output folders, the Y gate
# circuit, and reading a calibration file downloaded from IBM Quantum. The code for printing, CSV files and plots is
# in src/output_tools, which importing this file also makes available to the scripts below.
# The scripts that use it:
#   model_check.py              every number the simulator's noise is built from vs the real calibration, per qubit
#   y_gate_test.py              a Y gate circuit on every qubit: runs the three below and compares them
#     simulator_predicted.py      the circuit's error calculated exactly from the simulator's noise model
#     simulator_measured.py       the circuit's error from actually running it on the simulator
#     calibration_predicted.py    the circuit's error calculated exactly from the real calibration file
import os
import sys

from qiskit import transpile

# The Y gate circuit lives in src/noisy (shared with src/real_hardware_runs and src/simulator_noise_sources), and the
# code for printing, CSV files and plots in src/output_tools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from fez_common import y_circuit
from output_tools import COLORS, read_csv

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")

FAIL_COLOR = COLORS[7]   # points that don't agree or are far off


# ---- The Y gate circuit ----

def fez_ops(num_gates, start_bit):
    # The Y gate circuit written in Fez's gates (each Y becomes RZ(pi) + X). optimization_level=0 keeps every gate
    fez = transpile(y_circuit(start_bit, num_gates), basis_gates=["rz", "sx", "x"], optimization_level=0)
    return [inst.operation for inst in fez.data]


def ideal_result(num_gates, start_bit):
    # What the Y gate circuit reads with no noise: each Y flips the qubit
    return (start_bit + num_gates) % 2


# ---- Reading the calibration file ----

def number(text):
    # A number from the calibration file; blank entries (things IBM didn't measure) become None
    return float(text) if text not in ("", None) else None


def pair_values(text):
    # The calibration file lists per-connection values like "1:0.0093;0:0.0113" (neighbour:value)
    if not text:
        return {}
    return {int(n): float(v) for n, v in (item.split(":") for item in text.split(";")) if v}


def load_calibration(path, qubits):
    # A real ibm_fez calibration file downloaded from IBM Quantum, in the same form as model_check.simulator_model,
    # plus each qubit's CZ errors and whether IBM marks it as working
    real, cz = {}, {}
    for row in read_csv(path):
        q = int(row["Qubit"])
        for neighbour, error in pair_values(row["CZ error"]).items():
            cz[tuple(sorted((q, neighbour)))] = error
        if q not in qubits:
            continue
        real[q] = dict(t1_us=number(row["T1 (us)"]), t2_us=number(row["T2 (us)"]),
                       p1_given_0=number(row["Prob meas1 prep0"]), p0_given_1=number(row["Prob meas0 prep1"]),
                       readout_error=number(row["Readout assignment error"]),
                       sx_error=number(row["√x (sx) error"]), x_error=number(row["Pauli-X error"]),
                       gate_length_ns=number(row["Single-qubit gate length (ns)"]),
                       readout_length_ns=number(row["Readout length (ns)"]), init_error=number(row["Init error"]),
                       operational=row["Operational"] == "Yes")
    return real, cz


# ---- Comparing ----

def ratio(real, sim):
    # real / simulator, or None if either is missing or the simulator's is 0
    if real is None or sim is None or sim == 0:
        return None
    return real / sim
