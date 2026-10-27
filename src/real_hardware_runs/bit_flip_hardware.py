# bit_flip_hardware.py
# Runs the bit-flip code (Toffoli version) on a real IBM machine next to no correction, and saves the results and a
# plot. See run_experiment() in hardware_common.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
from bit_flip_toffoli import bit_flip_toffoli
from hardware_common import CSV_DIR, IMAGE_DIR, run_experiment


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 200            # Y gates in the circuit
    SHOTS = 10000              # shots per circuit (no correction and the code, for each starting state)
    BACKEND_NAME = "ibm_fez"   # a real machine, "least_busy" for the shortest queue, or "fake_fez" to test locally
    ACCOUNT = None             # only used if .env has no API key: name of a saved IBM account; None = default one
    SEED = 3                   # sets the transpiler's choices and the comparison simulator's randomness
    LAYOUT = None              # starting qubits for q_0, q_1, q_2, e.g. [87, 88, 86]; None = fez_common.py's
                               # DEFAULT_DATA_QUBITS
    START_STATES = [0]         # [0] starts the circuits in |0>, [1] in |1>, [0, 1] runs both (one circuit each)
    COMPARE_WITH_SIMULATOR = True   # also run the same circuits on a simulator using the machine's noise model
    # Where to save the results and the plot; {gates} is filled in with NUM_GATES. IMAGE_FILE = None skips the plot
    CSV_FILE = os.path.join(CSV_DIR, "single_runs", "bit_flip", "bit_flip_hardware_{gates}_gates.csv")
    IMAGE_FILE = os.path.join(IMAGE_DIR, "single_runs", "bit_flip", "bit_flip_hardware_{gates}_gates.png")

    run_experiment("bit-flip, Toffoli", bit_flip_toffoli, num_gates=NUM_GATES, shots=SHOTS,
                   backend_name=BACKEND_NAME, account=ACCOUNT, seed=SEED, layout=LAYOUT, start_states=START_STATES,
                   compare_with_simulator=COMPARE_WITH_SIMULATOR, csv_file=CSV_FILE, image_file=IMAGE_FILE)
