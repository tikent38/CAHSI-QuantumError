# pay_off.py
# Finds how many gates each code in CODES needs to pay off: where it starts having a smaller error than no correction
# IN_A_ROW times in a row. Runs compare_backends.py, on each backend in the settings (BACKENDS_TO_RUN) one after
# another, at even and at odd numbers of gates, since for X and Y gates the exact answer is 0 after an even number and 1
# after an odd number, and the codes do worse when it is 1.
# Each backend's qubits are either its least noisy ones or the ones whose noise is closest to the Fez defaults
# (PICK_QUBITS). Plots the errors and writes them to CSV files, in a folder for each backend. The counting, printing,
# plots and CSV files are in pay_off_common.py, shared with pay_off_h.py. Change the experiment in the settings block
# at the bottom of the file
from functools import partial

from pay_off_common import CSV_DIR, GATE_SETS, IMAGE_DIR, Experiment, gate_set_label, run_backends

# The codes to test (keys of compare_fez.py's CODES). Each is compared with no correction on the qubit it is measured
# on. "Shor, if blocks" also works, but it takes about 2 minutes per number of gates instead of about 5 seconds
CODES = ["bit-flip, Toffoli", "phase-flip, Toffoli"]
STARTS = {"even": 0, "odd": 1}
# How many gates to add each step. An even step keeps the exact answer the same for X and Y gates, which flip it every
# gate. "repeat" (X, Y, Z) needs a multiple of 6 to keep it the same: its answer cycles every
# 3 gates, and a multiple of 6 also keeps even/odd. "id" never changes the answer (always 0)
STEPS = {"x": 2, "y": 2, "z": 2, "repeat": 6, "id": 2}   # any gate set not listed here steps by 20


def check_settings(gate_sets):
    unknown = [g for g in gate_sets if g not in GATE_SETS]
    if unknown:
        raise ValueError(f"unknown gate set(s) {unknown}; use any of {list(GATE_SETS)}")


def gate_set_options(num_gates, seed, gate_set):
    # What compare_backends.compare needs to make gate_set's circuit with num_gates gates (compare gets the seed
    # anyway, so it isn't needed here)
    return dict(num_gates=num_gates, gate_set=gate_set)


def experiments(gate_sets):
    # One experiment (one plot, pay_off_<gate set>.png) for each gate set, counted up through even and odd numbers of
    # gates
    check_settings(gate_sets)
    return [Experiment(name=gate_set, title=gate_set_label(gate_set), file=f"pay_off_{gate_set}",
                       columns={"gate_set": gate_set}, starts=STARTS, step=STEPS.get(gate_set, 20),
                       options=partial(gate_set_options, gate_set=gate_set))
            for gate_set in gate_sets]


if __name__ == "__main__":
    # Which fake backends to run on, one after another: any of compare_backends.py's BACKENDS, e.g. "fez", "torino",
    # "kingston", "marrakesh", "brisbane", "sherbrooke", "washington", "kolkata". Each gets its own CSV and plot folder
    BACKENDS_TO_RUN = ["brisbane"]
    GATE_SETS_TO_RUN = ["id"]   # "id" = only waiting (see compare_fez.py's GATE_SETS)
    #GATE_SETS_TO_RUN = ["repeat"]
    MAX_GATES = 1500        # stop counting here if a code still hasn't paid off
    SHOTS = 5000           # shots per run, at every number of gates
    SEED = 3               # fixes the test circuit, the transpiler and the simulator (same SEED = same results)
    DATA_QUBITS = None     # the backend's qubits for q_0, q_1, q_2; None picks them (on Fez, fez_common.py's defaults)
    # How DATA_QUBITS = None picks them on the other backends: "like fez" = the qubits whose noise is closest to the
    # Fez defaults' (files in csvs/<backend>/ and images/<backend>/), "best" = the backend's least noisy qubits
    # (csvs/<backend>/best/ and images/<backend>/best/). Fez always uses csvs/fez/ and images/fez/
    PICK_QUBITS = "like fez"
    CSV_DIR_TO_USE = CSV_DIR   # pay_off.csv (every error) and pay_off_points.csv (each code's pay-off points)
    PLOT_DIR = IMAGE_DIR       # pay_off_<gate set>.png for each gate set

    run_backends(BACKENDS_TO_RUN, experiments(GATE_SETS_TO_RUN), codes=CODES, max_gates=MAX_GATES,
                 shots=SHOTS, seed=SEED, data_qubits=DATA_QUBITS, pick=PICK_QUBITS, csv_dir=CSV_DIR_TO_USE,
                 plot_dir=PLOT_DIR, csv_name="pay_off", sweep_column="parity")
