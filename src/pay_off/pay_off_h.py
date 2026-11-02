# pay_off_h.py
# Like pay_off.py, but the test circuit has an H gate every k gates (K_VALUES in the settings). None of the codes can
# apply H while the qubit is encoded: the bit-flip and phase-flip codes decode, apply H to the bare qubit and encode
# again, so each H leaves the qubit unprotected for a moment and costs 4 more 2-qubit gates (the Shor codes can't run
# H at all). Each H also moves the qubit between |0>/|1> and a superposition, which the 3-qubit codes protect worse.
# This finds how often a code can afford an H and still pay off: where it starts having a smaller error than no
# correction IN_A_ROW times in a row (the same rule as pay_off.py), for every gate set in GATE_SETS_TO_RUN between the
# H gates.
# Runs compare_backends.py on each backend in BACKENDS_TO_RUN, and plots the errors and writes them to CSV files in a
# folder for each backend, the same folders as pay_off.py. The counting, printing, plots and CSV files are in
# pay_off_common.py, shared with pay_off.py. Change the experiment in the settings block at the bottom
from functools import partial

from pay_off_common import CSV_DIR, GATE_SETS, IMAGE_DIR, Experiment, gate_set_label, run_backends
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from compare_fez import test_circuit   # in src/noisy, which importing pay_off_common puts on the path

# The codes to test (keys of compare_fez.py's CODES). "bit-flip, if blocks" and "phase-flip, if blocks" also work. The
# Shor codes can't: they only allow Pauli gates (X, Y, Z, id), since H would need part of the code decoded around it
CODES = ["bit-flip, Toffoli", "phase-flip, Toffoli"]
# The gate sets that can go between the H gates: the ones with only Pauli gates (and id), so the qubit always ends at
# exactly 0 or 1 (see h_circuit)
PAULI_SETS = [name for name, (_, gates) in GATE_SETS.items() if set(gates) <= {"x", "y", "z", "id"}]


def h_circuit(num_gates, k, base, seed):
    # The test circuit: num_gates gates from the gate set base, with every k-th one (gate k, 2k, 3k, ...) an H instead
    # (k=None: no H, the plain gate set). Then up to 2 gates at the end bring the qubit back to exactly |0>, so every
    # number of gates has the same exact answer, 0, as the even numbers of gates do in pay_off.py:
    #   an H if there is an odd number of H gates (otherwise the qubit would end in a 50/50 superposition, where noise
    #   is hard to see), then an X if it would end at |1>
    gates = test_circuit(base, num_gates, seed, False)
    qc = QuantumCircuit(1)
    for i, inst in enumerate(gates.data, 1):
        if k and i % k == 0:
            qc.h(0)
        else:
            qc.append(inst.operation, [0])
    if k and (num_gates // k) % 2:
        qc.h(0)
    if Statevector(qc).probabilities()[1] > 0.5:
        qc.x(0)
    return qc


def check_settings(gate_sets, k_values):
    bad = [g for g in gate_sets if g not in PAULI_SETS]
    if bad:
        raise ValueError(f"gate set(s) {bad} can't go between the H gates; use any of {PAULI_SETS} (with other gates, "
                         "e.g. S and T, the qubit can end in a superposition, where noise is hard to see)")
    bad = [k for k in k_values if k is not None and not (isinstance(k, int) and k >= 1)]
    if bad:
        raise ValueError(f"every k must be a whole number of at least 1 (or None for no H), got {bad}")


def h_options(num_gates, seed, base, k):
    # What compare_backends.compare needs to run h_circuit with num_gates gates
    return dict(circuit=h_circuit(num_gates, k, base, seed))


def experiments(gate_sets, k_values, step):
    # One experiment (one plot, pay_off_h_<gate set>_every_<k>.png) for each gate set and k, counted up from 0 gates
    check_settings(gate_sets, k_values)
    return [Experiment(name=f"{base}, " + (f"H every {k}" if k else "no H"),
                       title=gate_set_label(base) + (f" with an H every {k} gates" if k else " with no H"),
                       file=f"pay_off_h_{base}_every_{k or 'none'}",
                       columns={"base_gate_set": base, "h_every": k or ""}, starts={"all": 0}, step=step,
                       options=partial(h_options, base=base, k=k),
                       note="plus up to 2 at the end that bring the exact answer back to 0")
            for base in gate_sets for k in k_values]


if __name__ == "__main__":
    # Which fake backends to run on, one after another: any of compare_backends.py's BACKENDS, e.g. "fez", "torino",
    # "kingston", "marrakesh", "brisbane", "sherbrooke", "washington", "kolkata"
    BACKENDS_TO_RUN = ["fez"]
    # The gates between the H gates: any of PAULI_SETS ("x", "y", "z", "id", "repeat", "xz"). Each gets a run and plot
    # for each k
    GATE_SETS_TO_RUN = PAULI_SETS
    # How often an H comes: every k-th gate is an H. Each k gets its own run and plot. None = no H at all, to compare
    # with (the same as pay_off.py's even numbers of gates)
    K_VALUES = [None, 100, 50, 26, 10, 5]
    MAX_GATES = 500        # stop counting here if a code still hasn't paid off
    STEP = 10              # how many gates to add each step
    SHOTS = 5000           # shots per run, at every number of gates
    SEED = 3               # fixes the test circuit, the transpiler and the simulator (same SEED = same results)
    DATA_QUBITS = None     # the backend's qubits for q_0, q_1, q_2; None picks them (on Fez, fez_common.py's defaults)
    # How DATA_QUBITS = None picks them on the other backends: "like fez" = the qubits whose noise is closest to the
    # Fez defaults' (files in csvs/<backend>/ and images/<backend>/), "best" = the backend's least noisy qubits
    # (csvs/<backend>/best/ and images/<backend>/best/). Fez always uses csvs/fez/ and images/fez/
    PICK_QUBITS = "like fez"
    CSV_DIR_TO_USE = CSV_DIR   # pay_off_h.csv (every error) and pay_off_h_points.csv (each code's pay-off points)
    PLOT_DIR = IMAGE_DIR       # pay_off_h_<gate set>_every_<k>.png for each gate set and k

    run_backends(BACKENDS_TO_RUN, experiments(GATE_SETS_TO_RUN, K_VALUES, STEP), codes=CODES, max_gates=MAX_GATES,
                 shots=SHOTS, seed=SEED, data_qubits=DATA_QUBITS, pick=PICK_QUBITS, csv_dir=CSV_DIR_TO_USE,
                 plot_dir=PLOT_DIR, csv_name="pay_off_h")
