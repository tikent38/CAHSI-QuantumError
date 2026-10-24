# y_sweep_hardware.py
# Runs the bit-flip and phase-flip codes on real hardware at several numbers of Y gates (one job per code per
# gate count) and prints whether each code paid off compared with no correction, and how much bigger the code's
# transpiled circuit is (gates, two-qubit gates, depth)
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
from bit_flip_toffoli import bit_flip_toffoli
from phase_flip_toffoli import phase_flip_toffoli
from hardware_common import CSV_DIR, IMAGE_DIR, get_backend, run_experiment

CODES = {
    "bit_flip": ("bit-flip, Toffoli", bit_flip_toffoli),
    "phase_flip": ("phase-flip, Toffoli", phase_flip_toffoli),
}


def failure_rates(csv_file, code_name):
    # Failure rates on the real machine (not the simulator) from a CSV written by run_experiment(),
    # averaged over the starting states: (no correction, code)
    with open(csv_file, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["source"] == r["backend"]]
    rate = {}
    for name in ("no correction", code_name):
        mine = [float(r["failure_rate"]) for r in rows if r["run"] == name]
        rate[name] = sum(mine) / len(mine)
    return rate["no correction"], rate[code_name]


def circuit_sizes(csv_file, code_name):
    # (gates, two-qubit gates, depth) of the transpiled no correction and code circuits from a CSV written by
    # run_experiment(); None for CSVs from before these were saved
    with open(csv_file, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows[0].get("gates"):
        return None, None
    first = {name: next(r for r in rows if r["run"] == name) for name in ("no correction", code_name)}
    return tuple(tuple(int(first[name][k]) for k in ("gates", "two_qubit_gates", "depth"))
                 for name in ("no correction", code_name))


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    GATE_COUNTS = [0, 200, 250]   # one job per code for each of these numbers of Y gates
    RUN_CODES = ["bit_flip", "phase_flip"]          # which codes to run (keys of CODES)
    SHOTS = 10000              # shots per circuit (no correction and the code, for each starting state)
    BACKEND_NAME = "ibm_fez"   # a real machine, "least_busy" for the shortest queue, or "fake_fez" to test locally
    ACCOUNT = None             # only used if .env has no API key: name of a saved IBM account; None = default one
    SEED = 3                   # sets the transpiler's choices and the comparison simulator's randomness
    LAYOUT = None              # starting qubits for q_0, q_1, q_2 of every code, e.g. [87, 88, 86];
                               # None = compare_fez.py's DEFAULT_DATA_QUBITS
    START_STATES = [0,1]         # [0] starts every circuit in |0>, [1] in |1>, [0, 1] runs both (one circuit each)
    COMPARE_WITH_SIMULATOR = True   # also run the same circuits on a simulator using the machine's noise model
    SKIP_DONE = False           # skip gate counts whose CSV already exists, so a stopped sweep can be restarted

    # Every code starts on the same qubits (LAYOUT) for every gate count, so only the number of Y gates changes
    backend, _ = get_backend(BACKEND_NAME, ACCOUNT)

    # Runs that start in |1> (or both) get their own files, so they don't skip or overwrite the |0> ones
    suffix = "" if START_STATES == [0] else "_start" + "".join(map(str, START_STATES))
    # CSVs and images go in csvs/sweep/<code>/start_<state>/ and images/sweep/<code>/start_<state>/,
    # e.g. csvs/sweep/bit_flip/start_0/
    start_folder = "start_" + "".join(map(str, START_STATES))
    summary = []
    for num_gates in GATE_COUNTS:
        for key in RUN_CODES:
            code_name, code = CODES[key]
            csv_file = os.path.join(CSV_DIR, "sweep", key, start_folder,
                                    f"{key}_sweep_{num_gates}_gates{suffix}.csv")
            image_file = os.path.join(IMAGE_DIR, "sweep", key, start_folder,
                                      f"{key}_sweep_{num_gates}_gates{suffix}.png")
            if SKIP_DONE and os.path.exists(csv_file):
                print(f"\nSkipping {code_name} at {num_gates} Y gates, {csv_file} already exists")
            else:
                print(f"\n===== {code_name}: {num_gates} Y gates =====")
                run_experiment(code_name, code, num_gates=num_gates, shots=SHOTS, backend_name=BACKEND_NAME,
                               account=ACCOUNT, seed=SEED, layout=LAYOUT, start_states=START_STATES,
                               compare_with_simulator=COMPARE_WITH_SIMULATOR, csv_file=csv_file,
                               image_file=image_file)
            plain, coded = failure_rates(csv_file, code_name)
            summary.append((num_gates, code_name, plain, coded, *circuit_sizes(csv_file, code_name)))

    print(f"\nSummary on {backend.name} (failure rate = how often the result was not the exact answer):")
    print("Circuit sizes are the transpiled circuits, no correction -> with code")
    print(f"{'Y gates':>8}  {'code':<22}{'no correction':>15}{'with code':>12}  {'paid off?':<11}"
          f"{'gates':>14}{'two-qubit':>11}{'depth':>14}")
    print("-" * 112)
    for num_gates, code_name, plain, coded, plain_size, code_size in summary:
        sizes = "".join(f"{f'{a} -> {b}':>{w}}" for (a, b), w in zip(zip(plain_size, code_size), (14, 11, 14))) \
            if plain_size else f"{'(not in this CSV)':>39}"
        print(f"{num_gates:>8}  {code_name:<22}{plain:>15.4f}{coded:>12.4f}  {'yes' if coded < plain else 'no':<11}"
              f"{sizes}")
