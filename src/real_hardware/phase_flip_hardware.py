# phase_flip_hardware.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
from phase_flip_toffoli import phase_flip_toffoli         
from hardware_common import CSV_DIR, IMAGE_DIR, plot_results, run_experiment    


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 150            # Y gates in the circuit
    SHOTS = 10000               # shots per circuit (no correction and the code, for each starting state)
    BACKEND_NAME = "ibm_fez"   # a real machine, "least_busy" for the shortest queue, or "fake_fez" to test locally
    ACCOUNT = None             # only used if .env has no API key: name of a saved IBM account; None = default one
    SEED = 3                   # sets the transpiler's choices and the comparison simulator's randomness
    LAYOUT = None              # starting qubits for q_0, q_1, q_2, e.g. [87, 88, 86]; None = compare_fez.py's
                               # DEFAULT_DATA_QUBITS
    START_STATES = [0]         # [0] starts the circuits in |0>, [1] in |1>, [0, 1] runs both (one circuit each)
    COMPARE_WITH_SIMULATOR = True   # also run the same circuits on a simulator using the machine's noise model
    CSV_FILE = os.path.join(CSV_DIR, "single_runs", "phase_flip", "phase_flip_hardware_{gates}_gates.csv")
    # Plot of the results; {gates} is filled in with the number of Y gates in the CSV. None skips the plot
    IMAGE_FILE = os.path.join(IMAGE_DIR, "single_runs", "phase_flip", "phase_flip_hardware_{gates}_gates.png")

  
    run_experiment("phase-flip, Toffoli", phase_flip_toffoli, num_gates=NUM_GATES, shots=SHOTS,
                    backend_name=BACKEND_NAME, account=ACCOUNT, seed=SEED, layout=LAYOUT,
                    start_states=START_STATES,
                    compare_with_simulator=COMPARE_WITH_SIMULATOR, csv_file=CSV_FILE,
                    image_file=IMAGE_FILE)
