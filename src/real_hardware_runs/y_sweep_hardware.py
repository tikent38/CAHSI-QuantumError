# y_sweep_hardware.py
# Runs the bit-flip and phase-flip codes on real hardware at several numbers of Y gates (one job per code per
# gate count) and prints whether each code paid off compared with no correction, and how much bigger the code's
# transpiled circuit is (gates, two-qubit gates, depth)
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from bit_flip_toffoli import bit_flip_toffoli
from phase_flip_toffoli import phase_flip_toffoli
from hardware_common import CSV_DIR, IMAGE_DIR, get_backend, run_experiment
from output_tools import print_table_header, read_csv

# Every code the sweep can run: key used in file names and RUN_CODES, label printed, and the code. To add a code,
# add it here
CODES = {
    "bit_flip": ("bit-flip, Toffoli", bit_flip_toffoli),
    "phase_flip": ("phase-flip, Toffoli", phase_flip_toffoli),
}


def run_sweep(gate_counts, run_codes, shots, backend_name, account, seed, layout, start_states,
              compare_with_simulator, skip_done):
    # Runs every code in run_codes at every number of Y gates in gate_counts, all starting on the same qubits
    # (layout), so only the number of Y gates changes. Returns the backend's name and one summary row per run:
    # (Y gates, code, no correction failure rate, code failure rate, no correction size, code size)
    backend, _ = get_backend(backend_name, account)
    summary = []
    for num_gates in gate_counts:
        for key in run_codes:
            code_name, code = CODES[key]
            csv_file, image_file = sweep_files(key, num_gates, start_states)
            if skip_done and os.path.exists(csv_file):
                print(f"\nSkipping {code_name} at {num_gates} Y gates, {csv_file} already exists")
            else:
                print(f"\n===== {code_name}: {num_gates} Y gates =====")
                run_experiment(code_name, code, num_gates=num_gates, shots=shots, backend_name=backend_name,
                               account=account, seed=seed, layout=layout, start_states=start_states,
                               compare_with_simulator=compare_with_simulator, csv_file=csv_file,
                               image_file=image_file)
            plain, coded = failure_rates(csv_file, code_name)
            summary.append((num_gates, code_name, plain, coded, *circuit_sizes(csv_file, code_name)))
    return backend.name, summary


# ---- Helpers ----

def sweep_files(key, num_gates, start_states):
    # Where one run's CSV and plot go: csvs/sweep/<code>/start_<states>/ and images/sweep/<code>/start_<states>/,
    # e.g. csvs/sweep/bit_flip/start_0/. Runs that start in |1> (or both) also get "_start1" (or "_start01") in their
    # file names, so they don't skip or overwrite the |0> ones
    states = "".join(map(str, start_states))
    name = f"{key}_sweep_{num_gates}_gates" + ("" if list(start_states) == [0] else f"_start{states}")
    return (os.path.join(CSV_DIR, "sweep", key, f"start_{states}", f"{name}.csv"),
            os.path.join(IMAGE_DIR, "sweep", key, f"start_{states}", f"{name}.png"))


def failure_rates(csv_file, code_name):
    # Failure rates on the real machine (not the simulator) from a CSV written by run_experiment(),
    # averaged over the starting states: (no correction, code)
    rows = [r for r in read_csv(csv_file) if r["source"] == r["backend"]]
    rate = {}
    for name in ("no correction", code_name):
        mine = [float(r["failure_rate"]) for r in rows if r["run"] == name]
        rate[name] = sum(mine) / len(mine)
    return rate["no correction"], rate[code_name]


def circuit_sizes(csv_file, code_name):
    # (gates, two-qubit gates, depth) of the transpiled no correction and code circuits from a CSV written by
    # run_experiment(); None for CSVs from before these were saved
    rows = read_csv(csv_file)
    if not rows[0].get("gates"):
        return None, None
    first = {name: next(r for r in rows if r["run"] == name) for name in ("no correction", code_name)}
    return tuple(tuple(int(first[name][k]) for k in ("gates", "two_qubit_gates", "depth"))
                 for name in ("no correction", code_name))


# ---- Printing ----

def print_summary(backend_name, summary):
    print(f"\nSummary on {backend_name} (failure rate = how often the result was not the exact answer):")
    print("Circuit sizes are the transpiled circuits, no correction -> with code")
    print_table_header(f"{'Y gates':>8}  {'code':<22}{'no correction':>15}{'with code':>12}  {'paid off?':<11}"
                       f"{'gates':>14}{'two-qubit':>11}{'depth':>14}")
    for num_gates, code_name, plain, coded, plain_size, code_size in summary:
        if plain_size:
            gates, two_qubit, depth = (f"{a} -> {b}" for a, b in zip(plain_size, code_size))
            sizes = f"{gates:>14}{two_qubit:>11}{depth:>14}"
        else:
            sizes = f"{'(not in this CSV)':>39}"
        print(f"{num_gates:>8}  {code_name:<22}{plain:>15.4f}{coded:>12.4f}  {'yes' if coded < plain else 'no':<11}"
              f"{sizes}")


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    GATE_COUNTS = [0, 200, 250]       # one job per code for each of these numbers of Y gates
    RUN_CODES = ["bit_flip", "phase_flip"]   # which codes to run (keys of CODES)
    SHOTS = 10000                     # shots per circuit (no correction and the code, for each starting state)
    BACKEND_NAME = "ibm_fez"          # a real machine, "least_busy" for the shortest queue, or "fake_fez" to test locally
    ACCOUNT = None                    # only used if .env has no API key: name of a saved IBM account; None = default one
    SEED = 3                          # sets the transpiler's choices and the comparison simulator's randomness
    LAYOUT = None                     # starting qubits for q_0, q_1, q_2 of every code, e.g. [87, 88, 86];
                                      # None = fez_common.py's DEFAULT_DATA_QUBITS
    START_STATES = [0, 1]             # [0] starts every circuit in |0>, [1] in |1>, [0, 1] runs both (one circuit each)
    COMPARE_WITH_SIMULATOR = True     # also run the same circuits on a simulator using the machine's noise model
    SKIP_DONE = False                 # skip gate counts whose CSV already exists, so a stopped sweep can be restarted

    name, summary = run_sweep(GATE_COUNTS, RUN_CODES, SHOTS, BACKEND_NAME, ACCOUNT, SEED, LAYOUT, START_STATES,
                              COMPARE_WITH_SIMULATOR, SKIP_DONE)
    print_summary(name, summary)
