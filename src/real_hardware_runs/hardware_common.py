# hardware_common.py
# Shared code for running the error-correction codes on a real IBM machine (or a fake one, to test locally):
# connecting to IBM Quantum, building the circuits, submitting the job, then printing, saving and plotting the
# results. The scripts in this folder (bit_flip_hardware.py, phase_flip_hardware.py, y_sweep_hardware.py) call
# run_experiment()
import json
import os
import random
import sys
from datetime import datetime, timezone

import qiskit
import qiskit_aer
import qiskit_ibm_runtime
from qiskit.transpiler import Target, generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.executor_sampler import Sampler

# The circuit and result helpers live in src/noisy, and the code for printing, CSV files and plots in src/output_tools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from fez_common import DEFAULT_DATA_QUBITS, physical_qubits, prob_one, y_circuit
from output_tools import (COLORS, GRID, INK, MUTED, label_above, print_table_header, pyplot, read_csv, save_plot, style,
                          write_csv, write_text)

CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")
ENV_FILE = os.path.join(HERE, "..", "..", ".env")


def build_jobs(code_name, code, num_gates, backend, seed, layout, start_states=(0,)):
    # The transpiled circuits to run (no correction, then the code, for each starting state), in order,
    # with what is needed to read their results.
    # layout = starting qubits for q_0, q_1, q_2; None uses fez_common.py's DEFAULT_DATA_QUBITS, so the
    # hardware runs on the same qubits as the simulations in compare_fez.py
    options = dict(optimization_level=0, routing_method="sabre", seed_transpiler=seed, target=working_target(backend))
    if layout is None:
        layout = list(DEFAULT_DATA_QUBITS)

    runs = []
    code_circuits = {bit: to_isa(code(y_circuit(bit, num_gates)), options, initial_layout=layout)
                     for bit in start_states}
    used, measured_on = physical_qubits(code_circuits[start_states[0]])
    # No correction on the qubit the code is measured on (optimization_level=0 keeps all the Y gates)
    for bit in start_states:
        plain = y_circuit(bit, num_gates)
        plain.measure_all()
        runs.append({"run": "no correction", "start": bit, "register": "meas",
                     "circuit": to_isa(plain, options, initial_layout=[measured_on]),
                     "qubits_used": [measured_on], "measured_on": measured_on})
    for bit in start_states:
        runs.append({"run": code_name, "start": bit, "register": "out", "circuit": code_circuits[bit],
                     "qubits_used": used, "measured_on": measured_on})
    return runs, layout


# ---- Helpers: connecting to the machine ----

def load_env(path=ENV_FILE):
    # Read KEY=VALUE lines from the .env file into the environment.
    # Values already set in the environment are kept
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def connect(account=None):
    # Connect to IBM Quantum. Uses the API key and instance in .env (QISKIT_IBM_TOKEN, QISKIT_IBM_INSTANCE) if
    # there is one, otherwise a saved IBM account (account, or the default one)
    load_env()
    token = os.environ.get("QISKIT_IBM_TOKEN")
    if token:
        return QiskitRuntimeService(channel="ibm_quantum_platform", token=token,
                                    instance=os.environ.get("QISKIT_IBM_INSTANCE") or None)
    return QiskitRuntimeService(name=account) if account else QiskitRuntimeService()


def get_backend(backend_name, account):
    # The machine to run on, and the IBM service it came from (None for a fake backend).
    # "fake_..." names use the matching fake backend locally (e.g. "fake_fez"); "least_busy" picks the real
    # machine with the shortest queue
    if backend_name.startswith("fake_"):
        from qiskit_ibm_runtime import fake_provider
        fake = "Fake" + backend_name[len("fake_"):].capitalize()
        return getattr(fake_provider, fake)(), None
    service = connect(account)
    if backend_name == "least_busy":
        return service.least_busy(operational=True, simulator=False), service
    return service.backend(backend_name), service


# ---- Helpers: the circuits and the job ----

def working_target(backend, max_error=0.5):
    # The machine's target (its gates, connections and error rates) without connections whose error is max_error
    # or more. Real machines already leave out faulty qubits and connections, but fake backends list broken
    # connections with an error of 1.0
    target = backend.target
    kept = Target(num_qubits=target.num_qubits, dt=target.dt, granularity=target.granularity,
                  min_length=target.min_length, pulse_alignment=target.pulse_alignment,
                  acquire_alignment=target.acquire_alignment, qubit_properties=target.qubit_properties,
                  concurrent_measurements=target.concurrent_measurements)
    for name in target.operation_names:
        props = target[name]
        if props is None or list(props) == [None]:
            props = None   # available on every qubit (e.g. if_else, barrier)
        else:
            props = {qargs: p for qargs, p in props.items()
                     if len(qargs) < 2 or p is None or p.error is None or p.error < max_error}
        kept.add_instruction(target.operation_from_name(name), props, name=name)
    return kept


def to_isa(circuit, options, **extra):
    # The circuit in the machine's own gates and connections (an "ISA" circuit), ready to run on it
    return generate_preset_pass_manager(**options, **extra).run(circuit)


def circuit_stats(circuit, target):
    # Size of a transpiled circuit, to see the overhead the code adds: gates (barriers left out, measurements
    # counted), two-qubit gates, depth, and how long it takes to run on the machine (rz gates take no time)
    ops = circuit.count_ops()
    try:
        duration_us = round(circuit.estimate_duration(target, unit="s") * 1e6, 3)
    except Exception:
        duration_us = ""   # the target has no gate durations (e.g. some fake backends)
    return {"gates": circuit.size(), "two_qubit_gates": circuit.num_nonlocal_gates(), "depth": circuit.depth(),
            "duration_us": duration_us,
            "gate_counts": " ".join(f"{name}:{n}" for name, n in ops.items() if name != "barrier")}


def submit(runs, backend, shots):
    # Send every circuit to the machine as one job. Dynamical decoupling and twirling are turned off, so the machine
    # runs exactly the circuits given
    sampler = Sampler(mode=backend)
    sampler.options.default_shots = shots
    sampler.options.dynamical_decoupling.enable = False
    sampler.options.twirling.enable_gates = False
    sampler.options.twirling.enable_measure = False
    return sampler.run([r["circuit"] for r in runs], shots=shots)


def result_row(run, counts, source, num_gates):
    # One result row: which circuit, where it ran (source), P(1), and how many shots gave the wrong answer
    ones, zeros = prob_one(counts)
    exact = (run["start"] + num_gates) % 2
    return {"run": run["run"], "start": run["start"], "source": source, "p1": ones / (ones + zeros),
            "wrong": zeros if exact else ones}


def hardware_rows(runs, result, backend, num_gates):
    # One result row per circuit the machine ran
    return [result_row(r, getattr(pub.data, r["register"]).get_counts(), backend.name, num_gates)
            for r, pub in zip(runs, result)]


def simulator_rows(runs, backend, shots, seed, num_gates):
    # The same circuits on a simulator using the machine's current calibration (its own noise model), one result row
    # per circuit
    sim = AerSimulator.from_backend(backend)
    rng = random.Random(seed)
    rows = []
    for r in runs:
        counts = sim.run(r["circuit"], shots=shots, seed_simulator=rng.randrange(2**31)).result().get_counts()
        rows.append(result_row(r, counts, f"simulator ({backend.name} noise model)", num_gates))
    return rows


# ---- Printing, files and plots ----

def print_plan(code_name, num_gates, shots, start_states, backend, layout, runs):
    # What is about to run: the backend, the qubits, and every transpiled circuit's size
    code_run = next(r for r in runs if r["run"] == code_name)
    print(f"Backend: {backend.name}")
    print(f"{code_name}: {num_gates} Y gates, {shots} shots per circuit, starting in "
          + " and ".join(f"|{b}>" for b in start_states))
    print(f"Code starts on qubits {layout}, uses {code_run['qubits_used']}, measured on {code_run['measured_on']}")
    print(f"No correction runs on qubit {runs[0]['measured_on']} (the qubit the code is measured on)")
    print("Transpiled circuits:")
    for r in runs:
        s = r["stats"]
        duration = f", about {s['duration_us']} us" if s["duration_us"] != "" else ""
        print(f"  {r['run']:<22} start |{r['start']}>: {s['gates']} gates, {s['two_qubit_gates']} two-qubit, "
              f"depth {s['depth']}{duration}  ({s['gate_counts']})")


def save_job_details(path, job, backend, account, submitted, num_gates, shots, seed, layout, start_states):
    # The job's ID and settings, saved as soon as it is submitted, so the job can still be found on IBM Quantum if
    # the script is stopped while it waits
    print(f"\nSubmitted job {job.job_id()} at {submitted}")
    write_text(path, json.dumps({"job_id": job.job_id(), "backend": backend.name, "account": account,
                                 "submitted": submitted, "num_gates": num_gates, "shots": shots, "seed": seed,
                                 "layout": list(layout), "start_states": list(start_states)}, indent=2))
    print("Waiting for the results. If the queue is long you can stop the script (Ctrl+C): the job keeps running,")
    print("and its results can be found on IBM Quantum by the job ID above.")


def print_results(rows, code_name, num_gates, shots, start_states):
    print(f"\nResults ({shots} shots each; failure rate = how often the result was not the exact answer):")
    print_table_header(f"{'source':<38}{'run':<24}{'start':>6}{'exact':>7}{'P(1)':>9}{'failure rate':>14}")
    for row in rows:
        exact = (row["start"] + num_gates) % 2
        print(f"{row['source']:<38}{row['run']:<24}{'|' + str(row['start']) + '>':>6}{exact:>7}"
              f"{row['p1']:>9.4f}{row['wrong'] / shots:>14.4f}")

    print("\nAveraged over starting in " + " and ".join(f"|{b}>" for b in start_states) + ":")
    sources = list(dict.fromkeys(row["source"] for row in rows))
    for source in sources:
        rate = {name: sum(row["wrong"] for row in rows if row["source"] == source and row["run"] == name)
                / (len(start_states) * shots)
                for name in ("no correction", code_name)}
        verdict = "the code helps" if rate[code_name] < rate["no correction"] else "the code does not help"
        print(f"  {source:<38} no correction {rate['no correction']:.4f}   {code_name} {rate[code_name]:.4f}"
              f"   -> {verdict} at {num_gates} Y gates")


def write_results_csv(path, rows, runs, backend, job, num_gates, shots, seed):
    # One row per result (machine and simulator), with the circuit's size and the software versions used
    versions = f"qiskit {qiskit.__version__}, qiskit-aer {qiskit_aer.__version__}, " \
               f"qiskit-ibm-runtime {qiskit_ibm_runtime.__version__}"
    info = {r["run"] + str(r["start"]): r for r in runs}
    lines = []
    for row in rows:
        r = info[row["run"] + str(row["start"])]
        s = r["stats"]
        lines.append([row["source"], backend.name, job.job_id(), row["run"], row["start"], num_gates, shots,
                      (row["start"] + num_gates) % 2, round(row["p1"], 6), round(row["wrong"] / shots, 6),
                      " ".join(map(str, r["qubits_used"])), r["measured_on"], s["gates"],
                      s["two_qubit_gates"], s["depth"], s["duration_us"], s["gate_counts"], seed, versions])
    write_csv(path, ["source", "backend", "job_id", "run", "start_state", "y_gates", "shots", "exact_answer",
                     "p1", "failure_rate", "qubits_used", "measured_on", "gates", "two_qubit_gates", "depth",
                     "duration_us", "gate_counts", "seed", "software"], lines)


def plot_circuit_table(ax, rows, runs):
    # Table of the transpiled circuits' sizes (no correction, the code, and how many times bigger the code is),
    # taken from the first starting state of each run
    columns = [("gates", "gates"), ("two_qubit_gates", "2-qubit gates"), ("depth", "depth"),
               ("duration_us", "time (µs, est.)"), ("qubits_used", "qubits")]
    first = {run: next(r for r in rows if r["run"] == run) for run in runs}

    def value(row, key):
        return len(row[key].split()) if key == "qubits_used" else row[key]

    def overhead(key):
        plain, coded = (value(first[run], key) for run in runs)
        if plain == "" or coded == "":
            return "-"
        plain, coded = float(plain), float(coded)
        return f"+{coded:g}" if plain == 0 else f"{coded / plain:.2f}x"

    # The row names go in the first column (rather than rowLabels) so they stay inside the figure
    cells = [[run, *(str(value(first[run], key)) or "-" for key, _ in columns)] for run in runs]
    cells.append(["overhead (code / none)", *(overhead(key) for key, _ in columns)])

    ax.axis("off")
    table = ax.table(cellText=cells, colLabels=["", *(name for _, name in columns)], cellLoc="center",
                     colWidths=[0.3] + [0.14] * len(columns), bbox=(0, 0.3, 1, 0.7))
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.get_text().set_color(MUTED if i == 0 else INK)
        if j == 0:
            cell.get_text().set_horizontalalignment("left")
            cell.PAD = 0.03
            if 1 <= i <= len(runs):
                cell.get_text().set_color(COLORS[(i - 1) % len(COLORS)])
        if i == len(cells):
            cell.get_text().set_fontweight("bold")
    ax.set_title("transpiled circuits (what actually ran on the machine)", color=INK, fontsize=10, loc="left")
    ax.text(0, 0.22, "\n".join(f"{run}: {first[run]['gate_counts']}" for run in runs), transform=ax.transAxes,
            ha="left", va="top", color=MUTED, fontsize=8)


def plot_results(csv_file, image_file):
    # Bar chart of a CSV written by run_experiment(): for the real machine and the simulator, the failure rate
    # with no correction and with the code (bars = average over the starting states, markers = each one).
    # {gates} in image_file is filled in with the number of Y gates in the CSV
    plt = pyplot()
    rows = read_csv(csv_file)
    sources = list(dict.fromkeys(r["source"] for r in rows))
    runs = list(dict.fromkeys(r["run"] for r in rows))
    code_row = next(r for r in rows if r["run"] != "no correction")

    # CSVs from before the circuit sizes were saved have no "gates" column; those get the bar chart only
    has_stats = bool(code_row.get("gates"))
    width = 0.36
    if has_stats:
        fig, (ax, table_ax) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [3, 1.3]})
    else:
        fig, ax = plt.subplots(figsize=(10, 5.5))
    for j, run in enumerate(runs):
        for i, source in enumerate(sources):
            mine = [r for r in rows if r["source"] == source and r["run"] == run]
            rates = [float(r["failure_rate"]) for r in mine]
            average = sum(rates) / len(rates)
            x = i + (j - (len(runs) - 1) / 2) * width
            ax.bar(x, average, width * 0.94, color=COLORS[j % len(COLORS)], label=run if i == 0 else None, zorder=2)
            for r in mine:
                ax.plot(x, float(r["failure_rate"]), "o" if r["start_state"] == "0" else "s", color=INK, ms=6,
                        markerfacecolor="white", markeredgewidth=1.5, zorder=3)
            label_above(ax, f"{average:.4f}", x, max([average, *rates]), gap=4, fontsize=9)
    for start, marker in (("0", "o"), ("1", "s")):
        if any(r["start_state"] == start for r in rows):
            ax.plot([], [], marker, color=INK, markerfacecolor="white", markeredgewidth=1.5,
                    label=f"starting in |{start}>")

    ax.set_xticks(range(len(sources)), [f"{s} (real hardware)" if s == code_row["backend"] and not s.startswith("fake_")
                                        else s for s in sources])
    ax.set_ylim(0, max(float(r["failure_rate"]) for r in rows) * 1.25)
    ax.set_ylabel("probability the result is wrong", color=MUTED)
    ax.set_title(f"{code_row['y_gates']} Y gates on {code_row['backend']}: {code_row['run']} vs no correction",
                 color=INK)
    fig.text(0.5, 0.01, f"job {code_row['job_id']}  |  {code_row['shots']} shots per circuit  |  code on qubits "
             f"{code_row['qubits_used']}, both measured on qubit {code_row['measured_on']}",
             ha="center", color=MUTED, fontsize=8)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1))
    style(ax, grid_axis="y")
    if has_stats:
        plot_circuit_table(table_ax, rows, runs)
    save_plot(fig, image_file.format(gates=code_row["y_gates"]), rect=(0, 0.03, 1, 1))


def run_experiment(code_name, code, num_gates=100, shots=4000, backend_name="ibm_fez", account=None, seed=3,
                   layout=None, compare_with_simulator=True, csv_file=None, image_file=None, start_states=(0,)):
    # Runs one code at num_gates Y gates on backend_name, next to no correction on the qubit the code is measured on,
    # starting in each of start_states ((0,) for |0> only, (0, 1) for both). Prints the results; if csv_file is given
    # it also saves them, the job details, and (with image_file) a plot. {gates} in csv_file and image_file is filled
    # in with num_gates
    start_states = tuple(start_states)
    print(f"Connecting to {backend_name}...")
    backend, _ = get_backend(backend_name, account)
    runs, layout = build_jobs(code_name, code, num_gates, backend, seed, layout, start_states)
    for r in runs:
        r["stats"] = circuit_stats(r["circuit"], backend.target)
    print_plan(code_name, num_gates, shots, start_states, backend, layout, runs)

    job = submit(runs, backend, shots)
    submitted = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if csv_file:
        csv_file = csv_file.format(gates=num_gates)
        save_job_details(os.path.splitext(csv_file)[0] + "_job.json", job, backend, account, submitted, num_gates,
                         shots, seed, layout, start_states)
    rows = hardware_rows(runs, job.result(), backend, num_gates)

    if compare_with_simulator:
        # If building or running the simulator fails, the hardware results are still printed and saved
        try:
            rows += simulator_rows(runs, backend, shots, seed, num_gates)
        except Exception as err:
            print(f"\nSkipped the simulator comparison, it failed with: {err}")

    print_results(rows, code_name, num_gates, shots, start_states)
    if csv_file:
        write_results_csv(csv_file, rows, runs, backend, job, num_gates, shots, seed)
        if image_file:
            plot_results(csv_file, image_file)
