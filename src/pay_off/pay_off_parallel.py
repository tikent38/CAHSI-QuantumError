# pay_off_parallel.py
# The same experiment as pay_off.py, but with one process for each backend and gate set, JOBS_AT_ONCE at a time,
# instead of one after another. Each job writes its CSV files to a folder of its own, since two jobs on one backend
# would otherwise overwrite each other's, and each backend's jobs are merged into one pay_off.csv and one
# pay_off_points.csv as they finish. Running this again skips the jobs that already finished, so an interrupted run
# picks up where it left off (delete OUT_DIR/jobs to start over).
# Everything goes in OUT_DIR, so the results of pay_off.py in csvs/ and images/ aren't touched:
#   csvs/<backend>/   every finished gate set, merged
#   images/<backend>/ pay_off_<gate set>.png for each gate set
#   logs/             what each job printed, including every number of gates as it goes
#   jobs/             each job's own CSV files
# Change the experiment in the settings block at the bottom of the file
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# One thread per process: more threads barely speed up a single run, and with many processes they would only compete
# for the same cores. These have to be set before Qiskit and Aer load
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["RAYON_NUM_THREADS"] = "1"

from pay_off import CODES, experiments
from pay_off_common import HERE, backend_folder, run
from output_tools import read_csv, write_csv   # in src/output_tools, which importing pay_off_common puts on the path


def job_folder(out_dir, gate_set):
    # Where one gate set's jobs write their CSV files. run() adds a folder for the backend (see backend_folder)
    return os.path.join(out_dir, "jobs", gate_set)


def job_finished(out_dir, backend, gate_set, pick):
    # A job writes its points file last, so a job that was stopped partway has none
    return os.path.exists(os.path.join(backend_folder(job_folder(out_dir, gate_set), backend, pick),
                                       "pay_off_points.csv"))


def run_job(backend, gate_set, out_dir, max_gates, shots, seed, pick):
    # One backend and one gate set, the way pay_off.py runs them
    run(experiments([gate_set]), CODES, backend=backend, max_gates=max_gates, shots=shots, seed=seed, data_qubits=None,
        pick=pick, csv_dir=job_folder(out_dir, gate_set), plot_dir=os.path.join(out_dir, "images"), csv_name="pay_off",
        sweep_column="parity")


def start_job(backend, gate_set, out_dir, max_gates, shots, seed, pick):
    # Runs this file on one job in a process of its own, with what it prints in logs/<backend>_<gate set>.log, and
    # waits for it. Returns the job and how long it took. A job that crashes doesn't stop the others
    log_path = os.path.join(out_dir, "logs", f"{backend}_{gate_set}.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    start = time.time()
    with open(log_path, "w") as log:
        done = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), backend, gate_set, out_dir,
                               str(max_gates), str(shots), str(seed), pick], stdout=log, stderr=subprocess.STDOUT)
    return backend, gate_set, done.returncode, time.time() - start


def merge(backend, gate_sets, out_dir, pick):
    # Joins the finished jobs of one backend into csvs/<backend>/pay_off.csv and pay_off_points.csv
    for name in ("pay_off.csv", "pay_off_points.csv"):
        rows = []
        for gate_set in gate_sets:
            if job_finished(out_dir, backend, gate_set, pick):
                rows += read_csv(os.path.join(backend_folder(job_folder(out_dir, gate_set), backend, pick), name))
        if rows:
            write_csv(os.path.join(backend_folder(os.path.join(out_dir, "csvs"), backend, pick), name),
                      list(rows[0]), [list(row.values()) for row in rows])


def run_all(backends, gate_sets, jobs_at_once, out_dir, max_gates, shots, seed, pick):
    # Every backend with every gate set, jobs_at_once at a time, in the order given. Returns the jobs that failed
    jobs = [(b, g) for b in backends for g in gate_sets if not job_finished(out_dir, b, g, pick)]
    print(f"{len(jobs)} jobs to run, {jobs_at_once} at a time, in {out_dir}", flush=True)
    failed = []
    with ThreadPoolExecutor(jobs_at_once) as pool:
        running = [pool.submit(start_job, b, g, out_dir, max_gates, shots, seed, pick) for b, g in jobs]
        for count, finished in enumerate(as_completed(running), 1):
            backend, gate_set, code, seconds = finished.result()
            print(f"[{count}/{len(jobs)}] {backend} {gate_set}: {'done' if code == 0 else f'FAILED (exit {code})'} "
                  f"in {seconds / 60:.1f} min", flush=True)
            if code == 0:
                merge(backend, gate_sets, out_dir, pick)
            else:
                failed.append((backend, gate_set))
    return failed


if __name__ == "__main__":
    if len(sys.argv) > 1:   # started by start_job: run one job
        name, gates, folder, limit, num_shots, job_seed, job_pick = sys.argv[1:]
        run_job(name, gates, folder, int(limit), int(num_shots), int(job_seed), job_pick)
        sys.exit()

    # ---- Settings: change these to run a different experiment ----
    BACKENDS_TO_RUN = ["fez", "kingston", "marrakesh", "torino", "washington", "brisbane", "kolkata", "sherbrooke"]
    GATE_SETS_TO_RUN = ["x", "y", "repeat", "id"]
    JOBS_AT_ONCE = 10      # how many processes run at the same time. This machine has 12 cores
    MAX_GATES = 1500       # stop counting here if a code still hasn't paid off
    SHOTS = 5000           # shots per run, at every number of gates
    SEED = 3               # fixes the test circuit, the transpiler and the simulator (same SEED = same results)
    PICK_QUBITS = "like fez"   # "like fez" or "best", see pay_off.py
    OUT_DIR = os.path.join(HERE, "parallel_runs")   # where everything goes (see the top of the file)

    failures = run_all(BACKENDS_TO_RUN, GATE_SETS_TO_RUN, JOBS_AT_ONCE, OUT_DIR, MAX_GATES, SHOTS, SEED, PICK_QUBITS)
    print("All jobs finished" if not failures else f"Failed: {failures}")
    sys.exit(1 if failures else 0)
