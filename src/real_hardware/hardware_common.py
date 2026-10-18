# hardware_common.py

import csv
import json
import os
import random
import sys
from datetime import datetime, timezone

import qiskit
import qiskit_aer
import qiskit_ibm_runtime
from qiskit import QuantumCircuit
from qiskit.transpiler import Target, generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.executor_sampler import Sampler

# The error-correction codes and helpers live in src/noisy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
from compare_fez import prob_one                              
from breakeven_y import no_error_chance, physical_qubits     

CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images")
ENV_FILE = os.path.join(HERE, "..", "..", ".env")


def load_env(path=ENV_FILE):
    # Read KEY=VALUE lines from the .env file into the environment 
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
    # Connect to IBM Quantum. Uses the API key and instance in .env (QISKIT_IBM_TOKEN, QISKIT_IBM_INSTANCE) 
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


def working_target(backend, max_error=0.5):
    # The machine's target (its gates, connections and error rates) without connections whose error is max_error
    # or more. Real machines already leave out faulty qubits and connections, but fake backends list broken
    # connections with an error of 1.0. 
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


def y_circuit(bit, num_gates):
    # Prepare |bit>, then num_gates Y gates in a row
    qc = QuantumCircuit(1)
    for _ in range(num_gates):
        qc.y(0)
    return qc


def to_isa(circuit, options, **extra):
    # The circuit in the machine's own gates and connections (an "ISA" circuit), ready to run on it
    return generate_preset_pass_manager(**options, **extra).run(circuit)


def choose_layout(code, options, target, tries):
    # Starting qubits for the code: try `tries` placements (one per transpiler seed) and keep the one where
    # the code (with 0 Y gates) has the best chance of running with no error at all
    circuit = code(y_circuit(0, 0))
    best, best_chance = None, -1
    for seed in range(tries):
        tried = {**options, "seed_transpiler": seed}
        layout = to_isa(circuit, tried, layout_method="sabre").layout.initial_index_layout(filter_ancillas=True)
        chance = no_error_chance(to_isa(circuit, tried, initial_layout=layout[:circuit.num_qubits]), target)
        if chance > best_chance:
            best, best_chance = layout, chance
    return best[:circuit.num_qubits]


def build_jobs(code_name, code, num_gates, backend, seed, layout, layout_tries, start_states=(0,)):
    # The transpiled circuits to run (no correction, then the code, for each starting state), in order,
    # with what is needed to read their results
    options = dict(optimization_level=0, routing_method="sabre", seed_transpiler=seed, target=working_target(backend))
    if layout is None:
        layout = choose_layout(code, options, backend.target, layout_tries)

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


def wrong_answers(counts, start, num_gates):
    # How many shots gave the wrong answer, and P(1)
    ones, zeros = prob_one(counts)
    exact = (start + num_gates) % 2
    return (zeros if exact else ones), ones / (ones + zeros)


def run_experiment(code_name, code, num_gates=100, shots=4000, backend_name="ibm_fez", account=None, seed=3,
                   layout=None, layout_tries=100, compare_with_simulator=True, resume=False, csv_file=None,
                   image_file=None, start_states=(0,)):
    # start_states: which states every run starts in, (0,) for |0> only or (0, 1) for both
    start_states = tuple(start_states)
    job_file = os.path.splitext(csv_file)[0] + "_job.json"
    
    print(f"Connecting to {backend_name}...")
    backend, service = get_backend(backend_name, account)
    runs, layout = build_jobs(code_name, code, num_gates, backend, seed, layout, layout_tries, start_states)
    code_run = next(r for r in runs if r["run"] == code_name)

    print(f"Backend: {backend.name}")
    print(f"{code_name}: {num_gates} Y gates, {shots} shots per circuit, starting in "
          + " and ".join(f"|{b}>" for b in start_states))
    print(f"Code starts on qubits {layout}, uses {code_run['qubits_used']}, measured on {code_run['measured_on']}")
    print(f"No correction runs on qubit {runs[0]['measured_on']} (the qubit the code is measured on)")
    for r in runs:
        ops = r["circuit"].count_ops()
        print(f"  {r['run']:<22} start |{r['start']}>: {r['circuit'].size()} gates, depth {r['circuit'].depth()}, "
              f"{ops.get('cz', 0) + ops.get('ecr', 0)} two-qubit gates")

    sampler = Sampler(mode=backend)
    sampler.options.default_shots = shots
    sampler.options.dynamical_decoupling.enable = False   
    sampler.options.twirling.enable_gates = False
    sampler.options.twirling.enable_measure = False
    job = sampler.run([r["circuit"] for r in runs], shots=shots)
    submitted = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if csv_file:
        os.makedirs(os.path.dirname(job_file), exist_ok=True)
        with open(job_file, "w") as f:
            json.dump({"job_id": job.job_id(), "backend": backend.name, "account": account,
                        "submitted": submitted, "num_gates": num_gates, "shots": shots, "seed": seed,
                        "layout": list(layout), "start_states": list(start_states)}, f, indent=2)
        print(f"\nSubmitted job {job.job_id()} at {submitted}")
        print(f"Saved the job details to {job_file}")
        print("Waiting for the results. If the queue is long, you can stop the script (Ctrl+C) and later run it")
        print("again with RESUME = True to collect them without submitting again.")
    result = job.result()

    rows = []
    hardware = {}
    for r, pub in zip(runs, result):
        counts = getattr(pub.data, r["register"]).get_counts()
        wrong, p1 = wrong_answers(counts, r["start"], num_gates)
        hardware[(r["run"], r["start"])] = wrong / shots
        rows.append({**{k: r[k] for k in ("run", "start")}, "source": backend.name, "p1": p1, "wrong": wrong})

    if compare_with_simulator:
        # The same circuits on a simulator using the machine's current calibration (its own noise model).
        # If building or running it fails, the hardware results are still printed and saved
        try:
            sim = AerSimulator.from_backend(backend)
            rng = random.Random(seed)
            sim_rows = []
            for r in runs:
                counts = sim.run(r["circuit"], shots=shots, seed_simulator=rng.randrange(2**31)).result().get_counts()
                wrong, p1 = wrong_answers(counts, r["start"], num_gates)
                sim_rows.append({**{k: r[k] for k in ("run", "start")},
                                 "source": f"simulator ({backend.name} noise model)", "p1": p1, "wrong": wrong})
            rows += sim_rows
        except Exception as err:
            print(f"\nSkipped the simulator comparison, it failed with: {err}")

    print(f"\nResults ({shots} shots each; failure rate = how often the result was not the exact answer):")
    print(f"{'source':<38}{'run':<24}{'start':>6}{'exact':>7}{'P(1)':>9}{'failure rate':>14}")
    print("-" * 98)
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

    if csv_file:
        versions = f"qiskit {qiskit.__version__}, qiskit-aer {qiskit_aer.__version__}, " \
                   f"qiskit-ibm-runtime {qiskit_ibm_runtime.__version__}"
        info = {r["run"] + str(r["start"]): r for r in runs}
        os.makedirs(os.path.dirname(csv_file), exist_ok=True)
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "backend", "job_id", "run", "start_state", "y_gates", "shots", "exact_answer",
                             "p1", "failure_rate", "qubits_used", "measured_on", "seed", "software"])
            for row in rows:
                r = info[row["run"] + str(row["start"])]
                writer.writerow([row["source"], backend.name, job.job_id(), row["run"], row["start"], num_gates, shots,
                                 (row["start"] + num_gates) % 2, round(row["p1"], 6), round(row["wrong"] / shots, 6),
                                 " ".join(map(str, r["qubits_used"])), r["measured_on"], seed, versions])
        print(f"\nWrote results to {csv_file}")
        if image_file:
            plot_results(csv_file, image_file)

COLORS = ["#2a78d6", "#eb6834"]


def plot_results(csv_file, image_file):
    # Bar chart of a CSV written by run_experiment(): for the real machine and the simulator, the failure rate
    # with no correction and with the code (bars = average over the starting states, markers = each one)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    with open(csv_file, newline="") as f:
        rows = list(csv.DictReader(f))
    sources = list(dict.fromkeys(r["source"] for r in rows))
    runs = list(dict.fromkeys(r["run"] for r in rows))
    code_row = next(r for r in rows if r["run"] != "no correction")

    width = 0.36
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for j, run in enumerate(runs):
        for i, source in enumerate(sources):
            mine = [r for r in rows if r["source"] == source and r["run"] == run]
            rates = [float(r["failure_rate"]) for r in mine]
            average = sum(rates) / len(rates)
            x = i + (j - (len(runs) - 1) / 2) * width
            ax.bar(x, average, width * 0.94, color=COLORS[j % len(COLORS)], label=run if i == 0 else None, zorder=2)
            for r in mine:
                ax.plot(x, float(r["failure_rate"]), "o" if r["start_state"] == "0" else "s", color=ink, ms=6,
                        markerfacecolor="white", markeredgewidth=1.5, zorder=3)
            ax.annotate(f"{average:.4f}", (x, max([average, *rates])), xytext=(0, 4), textcoords="offset points",
                        ha="center", va="bottom", color=ink, fontsize=9)
    for start, marker in (("0", "o"), ("1", "s")):
        if any(r["start_state"] == start for r in rows):
            ax.plot([], [], marker, color=ink, markerfacecolor="white", markeredgewidth=1.5,
                    label=f"starting in |{start}>")

    ax.set_xticks(range(len(sources)), [f"{s} (real hardware)" if s == code_row["backend"] and not s.startswith("fake_")
                                        else s for s in sources])
    ax.set_ylim(0, max(float(r["failure_rate"]) for r in rows) * 1.25)
    ax.set_ylabel("probability the result is wrong", color=muted)
    ax.set_title(f"{code_row['y_gates']} Y gates on {code_row['backend']}: {code_row['run']} vs no correction",
                 color=ink)
    fig.text(0.5, 0.01, f"job {code_row['job_id']}  |  {code_row['shots']} shots per circuit  |  code on qubits "
             f"{code_row['qubits_used']}, both measured on qubit {code_row['measured_on']}",
             ha="center", color=muted, fontsize=8)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1))
    ax.grid(axis="y", color=grid, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=muted)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    image_file = image_file.format(gates=code_row["y_gates"])
    os.makedirs(os.path.dirname(image_file) or ".", exist_ok=True)
    fig.savefig(image_file, dpi=150)
    print(f"Saved plot to {image_file}")
