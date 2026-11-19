# mapping_common.py
# The code the qubit-mapping scripts share: where their files go, the options they compare, building the test circuit
# and placing it on Fez's qubits, running circuits on the noise simulator for their exact error, and the small pieces
# of text, CSV rows and plots that repeat across their reports. Each script's own experiment, report and plot stay in
# it:
#   mapping_sweep.py              no correction on every Fez qubit, the Toffoli codes on every placement
#   mapping_pay_off.py            each option's best and worst mappings, and when the codes pay off on them
#   mapping_hardware.py           the best and worst mappings on the real ibm_fez, ranked from a calibration file
#   mapping_hardware_pay_off.py   mapping_pay_off.py's plots for a job mapping_hardware.py ran
import os
import sys

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise.device import basic_device_readout_errors

# Importing this file puts the folders of src/ these scripts use on the import path: the codes and Fez helpers in
# src/noisy, the code for printing, CSV files and plots in src/output_tools, the pay-off rules in src/pay_off,
# connecting to IBM in src/real_hardware_runs, and reading a calibration file in src/hardware_vs_simulator
HERE = os.path.dirname(os.path.abspath(__file__))
for folder in ("hardware_vs_simulator", "real_hardware_runs", "pay_off", "noisy", "output_tools"):
    sys.path.insert(0, os.path.join(HERE, "..", folder))
from compare_fez import GATE_SETS, encode_all, on_fez, test_circuit
from fez_common import physical_qubits
from output_tools import COLORS, write_text

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")
REPORT_DIR = os.path.join(HERE, "reports")

# The options compared, and their colors in the plots: the same as in theory_validation.py and the pay-off plots
OPTIONS = ("no correction", "bit-flip, Toffoli", "phase-flip, Toffoli")
CODES = OPTIONS[1:]   # keys of compare_fez.py's CODES
OPTION_COLORS = dict(zip(OPTIONS, COLORS))
CHUNK = 300   # circuits sent to the simulator at once: enough to keep every core busy, few enough to fit in memory


# ---- The settings ----

def check_test(gate_set, start_states):
    # Stops with an error if the test circuit's settings are wrong. Returns the starting states as a tuple
    if gate_set not in GATE_SETS:
        raise ValueError(f"unknown gate set '{gate_set}'; use any of {list(GATE_SETS)}")
    start_states = tuple(start_states)
    if not start_states or set(start_states) - {0, 1}:
        raise ValueError(f"start_states must be 0, 1 or both, got {start_states}")
    return start_states


# ---- The circuits ----

def test_versions(gate_set, num_gates, seed, start_states):
    # For each starting state, {state: (the exact chance of 1, the circuit with no correction, {code: its circuit})}.
    # The state is prepared on q_0 before encoding (an X for |1>), so both codes pay the same for it
    circuit = test_circuit(gate_set, num_gates, seed, False)
    encoded, _ = encode_all(circuit, CODES)
    versions = {}
    for bit in start_states:
        state = QuantumCircuit(1)
        if bit:
            state.x(0)
        logical = state.compose(circuit)
        plain = logical.copy()
        plain.measure_all()   # the codes add their own measurement
        versions[bit] = (Statevector(logical).probabilities()[1],   # the exact answer: no shots or noise
                         plain, {name: qc.compose(state, qubits=[0], front=True) for name, qc in encoded.items()})
    return versions


def placed(options, mapping, plain, encoded, backend, seed):
    # Each option's circuit on one mapping, transpiled for Fez as in compare_fez.py: {option: circuit}. options is
    # either [no correction], which runs on the Fez qubit mapping[0], or codes, whose q_0, q_1, q_2 start on mapping's
    # Fez qubits. plain and encoded: the circuit with no correction and each code's, from test_versions
    codes = {name: encoded[name] for name in options if name in CODES}
    circuits, _ = on_fez(plain, codes, backend, {"bit/phase-flip": list(mapping)}, seed)
    # With no codes, on_fez's one circuit is no correction on mapping[0]
    return {name: circuits[name] if name in codes else next(iter(circuits.values())) for name in options}


def mapping_circuits(mappings, gate_set, num_gates, seed, start_states, backend):
    # Each mapping's circuit from each starting state, transpiled for Fez as in the sweep, so it is the very circuit
    # the sweep ran. mappings: [(option, mapping)]. Yields (option, mapping, start, the exact chance of 1, circuit),
    # one mapping's starting states in turn
    versions = test_versions(gate_set, num_gates, seed, start_states)
    for option, mapping in mappings:
        for bit, (exact_p1, plain, encoded) in versions.items():
            yield option, mapping, bit, exact_p1, placed([option], mapping, plain, encoded, backend, seed)[option]


# ---- Running them on the noise simulator ----

def noise_simulator(backend, readout=None):
    # The noise simulator for backend, which runs every circuit as a density matrix, so a run gives the exact chance of
    # each result, with no shots. Also each qubit's readout error as read_one takes it: readout's ({qubit: matrix}) for
    # the qubits it has, and for the rest the one AerSimulator.from_backend puts on that qubit's measurement
    sim = AerSimulator.from_backend(backend, method="density_matrix", max_parallel_experiments=0)
    errors = {qargs[0]: err.probabilities for qargs, err in basic_device_readout_errors(target=backend.target)}
    return sim, errors | (readout or {})


def measured_qubit(circuit):
    # The Fez qubit a transpiled circuit's result is measured on. The measurement is the circuit's last instruction,
    # since every circuit here ends with a barrier and then the measurement
    last = circuit.data[-1]
    if last.operation.name != "measure":
        raise ValueError(f"expected the circuit to end with its measurement, not '{last.operation.name}'")
    return circuit.find_bit(last.qubits[0]).index


def exact_version(circuit):
    # The circuit with its measurement swapped for saving the exact chance that the measured qubit is 1, and that qubit
    qubit = measured_qubit(circuit)
    exact = circuit.copy()
    del exact.data[-1]
    exact.save_probabilities([qubit])
    return exact, qubit


def read_one(p1, readout):
    # The chance of reading 1 when the qubit is 1 with chance p1. readout[i][j] is the chance of reading j when the
    # qubit is i (see noise_simulator)
    return p1 * readout[1][1] + (1 - p1) * readout[0][1]


def run_batch(batch, sim, readout):
    # Runs every (row, circuit) of batch on the simulator, CHUNK circuits at a time, and returns the rows with each
    # run's result added. Each row already has its exact answer, exact_p1
    rows = []
    for start in range(0, len(batch), CHUNK):
        part = batch[start:start + CHUNK]
        exact = [exact_version(qc) for _, qc in part]
        result = sim.run([qc for qc, _ in exact]).result()
        for i, ((row, qc), (_, qubit)) in enumerate(zip(part, exact)):
            p_read_1 = read_one(result.data(i)["probabilities"][1], readout[qubit])
            rows.append(row | dict(measured_on=qubit, qubits_used=len(physical_qubits(qc)[0]), gates=qc.size(),
                                   two_qubit_gates=qc.num_nonlocal_gates(), depth=qc.depth(), p_read_1=p_read_1,
                                   error=abs(p_read_1 - row["exact_p1"])))
    return rows


# ---- Text, CSV files and plots ----

def short_name(name):
    # "bit-flip, Toffoli" -> "bit-flip"
    return name.split(",")[0]


def mapping_text(mapping):
    # A mapping as the reports write it: "Fez 86" for no correction, "(87, 88, 86)" for a code's q_0, q_1, q_2
    return f"Fez {mapping[0]}" if len(mapping) == 1 else str(tuple(mapping))


def states_text(start_states):
    return " and ".join(f"|{bit}>" for bit in start_states)


def heading(text):
    # text starting with a capital letter, for a title
    return text[0].upper() + text[1:]


def md_table(header, rows, align):
    # A Markdown table with its columns padded to line up, so it also reads well printed in a terminal. align has one
    # "<" (left) or ">" (right) per column
    cells = [[str(c) for c in row] for row in [header, *rows]]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    line = "| " + " | ".join(f"{{:{a}{w}}}" for a, w in zip(align, widths)) + " |"
    rule = "|" + "|".join("-" * (w + 1) + ":" if a == ">" else "-" * (w + 2) for a, w in zip(align, widths)) + "|"
    return [line.format(*cells[0]), rule] + [line.format(*row) for row in cells[1:]]


def save_report(path, text):
    # Prints a report, then writes it to path
    print("\n" + text)
    write_text(path, text)


def mapping_cells(mapping):
    # A mapping as the q0, q1 and q2 cells of a CSV row: no correction's one Fez qubit leaves the last two blank
    return [*mapping, *[""] * (3 - len(mapping))]


def log_axis(axis):
    # Ticks at 1, 2 and 5 times each power of 10, written as plain numbers
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    axis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    axis.set_minor_formatter(NullFormatter())


def log_limits(values, pad=1.3, top=1):
    # The limits of a log axis that shows every value above 0, with a factor of pad to spare at each end, but none
    # below 1e-4 and none above top (None: no cap)
    values = np.asarray(values, dtype=float)
    low, high = max(values[values > 0].min() / pad, 1e-4), values.max() * pad
    return low, high if top is None else min(high, top)
