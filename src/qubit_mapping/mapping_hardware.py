# mapping_hardware.py
# mapping_pay_off.py on the real ibm_fez, at one number of Y gates (200 by default). Every mapping (no correction on
# each Fez qubit, the bit-flip and phase-flip Toffoli codes on each placement) is ranked by the error the noise
# simulator predicts for it from a real ibm_fez calibration file. Then the best and worst mappings of each option run
# on the machine, all in one job, and the report sets what the machine measured against what the simulator predicted,
# to answer two questions: do the mappings matter as much on the machine as on the simulator, and which matters more
# there, picking good qubits or using a code? Every run reports the Fez qubits it ran on.

import json
import math
import os
import re
import time
from datetime import datetime, timezone

import numpy as np
from qiskit_ibm_runtime.fake_provider import FakeFez
from scipy.stats import spearmanr

# The code the mapping scripts share (importing it also puts the folders of src/ the imports below come from on the
# import path), the sweep, and mapping_pay_off.py's lists and match-ups
from mapping_common import (CODES, CSV_DIR, IMAGE_DIR, OPTION_COLORS, OPTIONS, REPORT_DIR, check_test, heading,
                            log_axis, log_limits, mapping_cells, mapping_circuits, mapping_text, md_table,
                            noise_simulator, run_batch, save_report, short_name, states_text)
from mapping_sweep import spread_parts, sweep
from mapping_pay_off import (KINDS, MATCHUPS, RANK_COLUMNS, average_states, check_compare, lists, lists_table,
                             rank_rows, ranked, top_of)
from compare_fez import GATE_SETS
from fez_common import physical_qubits, prob_one, working_coupling_map
from hardware_common import circuit_stats, get_backend, submit
from noise_common import load_calibration, pair_values
from output_tools import GRID, INK, MUTED, print_table_header, pyplot, read_csv, save_plot, style, write_csv, write_text

MAX_CZ_ERROR = 0.5   # a connection with a CZ error this high is left out, as fez_common.py's working_coupling_map does
# The numbers a qubit needs in the calibration file for the simulator to predict its errors (noise_common.py's names)
NEEDED = ("t1_us", "t2_us", "sx_error", "x_error", "gate_length_ns", "readout_length_ns", "p1_given_0", "p0_given_1")
HARDWARE_COLUMNS = ["job_id", "backend", "option", "q0", "q1", "q2", "why", "start", "qubits_used", "measured_on",
                    "shots", "ones", "p1", "exact_p1", "measured_error", "measured_error_sd", "predicted_error",
                    "gates", "two_qubit_gates", "depth", "duration_us"]
PREDICTED_COLUMNS = ["option", "q0", "q1", "q2", "measured_on", "start", "predicted_error"]


# ---- The calibration file ----

def read_calibration(path):
    # A real ibm_fez calibration file downloaded from IBM Quantum: each qubit's numbers ({qubit: numbers}, as
    # noise_common.py's load_calibration reads them), each connection's CZ error and CZ length in ns ({(a, b): value},
    # with a < b), and when it was taken, from the time IBM puts in the file's name (None if it has none)
    rows = read_csv(path)
    numbers, cz = load_calibration(path, [int(r["Qubit"]) for r in rows])
    lengths = {tuple(sorted((int(r["Qubit"]), neighbour))): length for r in rows
               for neighbour, length in pair_values(r["Gate length (ns)"]).items()}
    found = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2})_(\d{2})_(\d{2})Z", os.path.basename(path))
    taken = datetime.fromisoformat("{}T{}:{}:{}+00:00".format(*found.groups())) if found else None
    return numbers, cz, lengths, taken


def age_text(taken):
    # How long ago the calibration was taken, e.g. "3.2 days"
    if taken is None:
        return "an unknown time"
    hours = (datetime.now(timezone.utc) - taken).total_seconds() / 3600
    return f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.1f} days"


def working_edges(cz, qubits, offered=None):
    # The connections the runs may use, as a set of (a, b) with a < b: a CZ error below MAX_CZ_ERROR, both qubits in
    # qubits, and, when offered is given, among the connections the machine offers
    return {pair for pair, error in cz.items()
            if error < MAX_CZ_ERROR and set(pair) <= qubits and (offered is None or pair in offered)}


def usable(numbers, cz, machine):
    # The Fez qubits and connections the runs may use, as (set of qubits, set of (a, b) with a < b). A qubit needs every
    # number in NEEDED and IBM marking it working; a connection needs a CZ error below MAX_CZ_ERROR and both its qubits
    # usable. Both must also be in the machine's current target (IBM leaves faulty qubits and connections out of it),
    # so every circuit can run there
    target = machine.target
    qubits = {q for q, cal in numbers.items() if cal["operational"] and all(cal[key] is not None for key in NEEDED)
              and q < target.num_qubits and (q,) in target["x"] and (q,) in target["measure"]}
    offered = {tuple(sorted(pair)) for pair in working_coupling_map(machine).get_edges()}
    return qubits, working_edges(cz, qubits, offered)


def calibrated_fez(numbers, cz, lengths, qubits, edges):
    # FakeFez with its noise numbers swapped for the calibration file's, so the noise simulator models the machine as it
    # was when the file was taken (FakeFez's own numbers are from February 2025). Unusable qubits keep FakeFez's numbers
    # but lose every connection, as does each connection outside edges: their CZ error is set to 1, which
    # working_coupling_map leaves out, so no placement or SWAP uses them
    backend = FakeFez()
    backend._set_props_dict_from_json()   # FakeFez's numbers, in the form IBM sends them
    props = backend._props_dict
    names = {"T1": "t1_us", "T2": "t2_us", "readout_error": "readout_error", "prob_meas0_prep1": "p0_given_1",
             "prob_meas1_prep0": "p1_given_0", "readout_length": "readout_length_ns"}
    for q in qubits:
        for entry in props["qubits"][q]:
            if numbers[q].get(names.get(entry["name"])) is not None:
                entry["value"] = numbers[q][names[entry["name"]]]
    for gate in props["gates"]:
        on, values = tuple(gate["qubits"]), {p["name"]: p for p in gate["parameters"]}
        if gate["gate"] in ("id", "rx", "sx", "x") and on[0] in qubits:
            # IBM's file has one error for all of a qubit's single-qubit gates (id, rx, sx and x share it)
            values["gate_error"]["value"] = numbers[on[0]]["x_error" if gate["gate"] == "x" else "sx_error"]
            values["gate_length"]["value"] = numbers[on[0]]["gate_length_ns"]
        elif gate["gate"] == "cz":
            pair = tuple(sorted(on))
            values["gate_error"]["value"] = cz[pair] if pair in edges else 1.0
            if pair in edges and pair in lengths:
                values["gate_length"]["value"] = lengths[pair]
    backend._target = None   # rebuilt from the new numbers the next time it is used
    return backend


def calibrated_simulator(numbers, cz, lengths, qubits, edges):
    # calibrated_fez's backend, its noise simulator, and each qubit's readout error as mapping_common.py's read_one
    # takes it. That uses both of the calibration file's readout errors, which differ (a 1 is read as 0 more often,
    # since the qubit can decay while it is read): [[P(read 0 | 0), P(read 1 | 0)], [P(read 0 | 1), P(read 1 | 1)]].
    # Qubits missing them keep the backend's own, the same both ways
    backend = calibrated_fez(numbers, cz, lengths, qubits, edges)
    readout = {q: [[1 - cal["p1_given_0"], cal["p1_given_0"]], [cal["p0_given_1"], 1 - cal["p0_given_1"]]]
               for q, cal in numbers.items() if cal["p1_given_0"] is not None and cal["p0_given_1"] is not None}
    return (backend, *noise_simulator(backend, readout))


# ---- The ranking, and the runs ----

def predict_all(gate_set, num_gates, seed, start_states, backend, sim, readout, qubits):
    # Every mapping's error on the noise simulator with the calibration's noise, worked out exactly as mapping_sweep.py
    # does (its own sweep, run on the calibrated backend): no correction on every usable qubit, and both codes on every
    # placement on 3 connected usable qubits. Returns each mapping's error from each starting state, {start: {option:
    # {mapping: error}}} (as mapping_pay_off.py reads them from a sweep), and {(option, mapping): the Fez qubit its
    # result is read out on}
    by_state, measured = {}, {}
    for r in sweep(gate_set, num_gates, seed, start_states, None, backend, sim, readout):
        if r["option"] == OPTIONS[0] and r["placement"][0] not in qubits:
            continue   # the calibration file is missing numbers for this qubit
        mapping = tuple(r["placement"])
        by_state.setdefault(r["start"], {}).setdefault(r["option"], {})[mapping] = r["error"]
        measured[r["option"], mapping] = r["measured_on"]
    return by_state, measured


def choose(compared, measured, head_to_head):
    # The mappings that run on the machine, {(option, mapping): [why]}: the top of each option's best and worst lists
    # (compared, mapping_pay_off.py's match-ups), and with head_to_head, no correction on the Fez qubit each of those
    # code placements is read out on, so the code can be compared with no correction on the very same qubit
    chosen = {}
    for name in OPTIONS:
        for kind in KINDS:
            for rank, (mapping, _) in enumerate(compared[name][kind], 1):
                chosen.setdefault((name, mapping), []).append(f"{kind} {rank}")
    if head_to_head:
        for code in CODES:
            for kind in KINDS:
                for mapping, _ in compared[code][kind]:
                    key = (OPTIONS[0], (measured[code, mapping],))
                    chosen.setdefault(key, []).append(f"same qubit as {short_name(code)} {mapping_text(mapping)}")
    return chosen


def build_runs(chosen, gate_set, num_gates, seed, start_states, backend, by_state):
    # One run per chosen mapping and starting state, in the order they go in the job: its circuit, transpiled for Fez
    # exactly as in the sweep (so the machine runs the very circuit whose error was predicted), and what's needed to
    # read its result. IBM runs a transpiled circuit as it is, on the Fez qubits in it, so qubits_used and measured_on
    # are the qubits it ran on. duration_us is how long the circuit takes with the calibration's gate lengths
    runs = []
    for option, mapping, bit, exact_p1, circuit in mapping_circuits(chosen, gate_set, num_gates, seed, start_states,
                                                                   backend):
        used, measured_on = physical_qubits(circuit)
        runs.append(dict(option=option, mapping=list(mapping), why=chosen[option, mapping], start=bit,
                         exact_p1=float(exact_p1), register="out" if option in CODES else "meas", qubits_used=used,
                         measured_on=measured_on, **circuit_stats(circuit, backend.target),
                         predicted=by_state[bit][option][mapping], circuit=circuit))
    return runs


def check_predictions(runs, sim, readout):
    # Each circuit that will run must have the predicted error the ranking used, since it is the same circuit. If the
    # transpiler ever placed one differently the second time, its own error is used instead
    rows = run_batch([(dict(exact_p1=r["exact_p1"]), r["circuit"]) for r in runs], sim, readout)
    off = max(abs(row["error"] - r["predicted"]) for row, r in zip(rows, runs))
    if off > 1e-9:
        print(f"Note: some circuits came out different from the ranking's (errors differ by up to {off:.1e}); "
              "using the errors of the circuits that run")
        for row, r in zip(rows, runs):
            r["predicted"] = row["error"]
    else:
        print(f"Checked: the circuits that will run have the errors the ranking used (largest difference {off:.1e})")


def per_mapping(runs):
    # The runs grouped by mapping, {(option, mapping): [one run per starting state]}
    grouped = {}
    for r in runs:
        grouped.setdefault((r["option"], tuple(r["mapping"])), []).append(r)
    return grouped


# ---- The job, and its files ----

def job_paths(backend_name, gate_set, num_gates, csv_dir=CSV_DIR, image_dir=IMAGE_DIR, report_dir=REPORT_DIR):
    # Where a job's files go, {"job", "results", "predicted", "ranks", "report", "image": path}, named after the
    # backend, the gate set and the number of gates (mapping_hardware_pay_off.py finds a job by them)
    name = f"mapping_hardware_{backend_name}_{gate_set}_{num_gates}"
    return {key: os.path.join(folder, name + suffix) for key, folder, suffix in (
        ("job", csv_dir, "_job.json"), ("results", csv_dir, ".csv"), ("predicted", csv_dir, "_predicted.csv"),
        ("ranks", csv_dir, "_ranks.csv"), ("report", report_dir, ".md"), ("image", image_dir, ".png"))}


def set_aside(paths):
    # Before a new job's files are written, the earlier job's are kept, renamed with its job ID. Its report and plot
    # are replaced, but can be made again from these: give them back their names and run with RESUME = True
    with open(paths["job"]) as f:
        old = json.load(f).get("job_id", "earlier")
    for key in ("job", "results", "predicted", "ranks"):
        if os.path.exists(paths[key]):
            stem, ext = os.path.splitext(paths[key])
            os.replace(paths[key], f"{stem}_{old}{ext}")
            print(f"Kept the earlier job's {os.path.basename(paths[key])} as {os.path.basename(stem)}_{old}{ext}")


def wait_for(job):
    # The job's result, once it finishes. None if it failed or was cancelled, or you stop waiting with Ctrl+C (the job
    # keeps going, and RESUME = True gets its results)
    print("Waiting for the results. You can stop the script (Ctrl+C) while it waits: the job keeps going, and running "
          "the script again with RESUME = True gets its results.")
    try:
        return job.result()
    except KeyboardInterrupt:
        print("\nStopped waiting. The job is still on IBM Quantum: set RESUME = True and run the script again to get "
              "its results.")
    except Exception as err:
        try:
            status = job.status()
        except Exception:
            status = "unknown"
        print(f"\nThe job ended without results (status {status}): {err}")
    return None


def billed_seconds(job, tries=6):
    # The QPU time IBM charged for the job, in seconds, once IBM has worked it out (it can take a little while after the
    # results come back); None if it hasn't by then
    for _ in range(tries):
        try:
            seconds = job.usage()
        except Exception:
            return None
        if seconds:
            return float(seconds)
        time.sleep(10)
    return None


def save_plan(path, plan, runs):
    # The job and everything needed to read its results and write the report later, without the circuits
    kept = [{k: v for k, v in r.items() if k not in ("circuit", "shots", "ones", "p1", "error", "error_sd")}
            for r in runs]
    write_text(path, json.dumps(dict(plan, runs=kept), indent=2))


def load_plan(path):
    with open(path) as f:
        plan = json.load(f)
    return plan, plan.pop("runs")


def saved_job(paths):
    # The job this script submitted last with these settings, from its files: (plan, runs, whether its results were
    # saved too). If they were, they are read into runs
    if not os.path.exists(paths["job"]):
        raise FileNotFoundError(f"{paths['job']} doesn't exist: mapping_hardware.py hasn't submitted a job with these "
                                "settings")
    plan, runs = load_plan(paths["job"])
    return plan, runs, load_results(paths["results"], plan, runs)


def plan_lists(plan):
    # The job's best and worst lists as mapping_pay_off.py's lists gives them, {option: {"best"/"worst": [(mapping,
    # error)]}} (the job file keeps each mapping as a list)
    return {name: {kind: [(tuple(m), e) for m, e in mine] for kind, mine in by_kind.items()}
            for name, by_kind in plan["lists"].items()}


def add_result(r, ones, shots):
    # A run's result: P(1), its error (how far P(1) is from the exact answer) and the error's standard deviation from
    # shot noise
    p1 = ones / shots
    r.update(shots=shots, ones=ones, p1=p1, error=abs(p1 - r["exact_p1"]), error_sd=math.sqrt(p1 * (1 - p1) / shots))


def read_results(runs, result):
    # Each run's result from the job, in the order the circuits were sent
    for r, pub in zip(runs, result):
        ones, zeros = prob_one(getattr(pub.data, r["register"]).get_counts())
        add_result(r, ones, ones + zeros)


def load_results(path, plan, runs):
    # The results an earlier run of this script saved for this job, so the report and plot can be made again without
    # asking IBM. False if there are none, or they are another job's
    if not os.path.exists(path):
        return False
    rows = read_csv(path)
    if len(rows) != len(runs) or any(row["job_id"] != plan["job_id"] or row["option"] != r["option"]
                                     or int(row["start"]) != r["start"] for row, r in zip(rows, runs)):
        return False
    for r, row in zip(runs, rows):
        add_result(r, int(row["ones"]), int(row["shots"]))
    print(f"Read the results of job {plan['job_id']} from {path}")
    return True


def hardware_rows(plan, runs):
    return [[plan["job_id"], plan["backend"], r["option"], *mapping_cells(r["mapping"]), "; ".join(r["why"]),
             r["start"], " ".join(map(str, r["qubits_used"])), r["measured_on"], r["shots"], r["ones"],
             round(r["p1"], 6), round(r["exact_p1"], 6), round(r["error"], 6), round(r["error_sd"], 6),
             round(r["predicted"], 6), r["gates"], r["two_qubit_gates"], r["depth"], r.get("duration_us", "")]
            for r in runs]


def predicted_rows(by_state, measured):
    return [[option, *mapping_cells(mapping), qubit, bit, round(by_state[bit][option][mapping], 6)]
            for (option, mapping), qubit in measured.items() for bit in sorted(by_state)]


# ---- What the runs show ----

def group(items):
    # The average predicted and measured error of some runs or mappings (each a dict with "predicted", "measured" and
    # "sd", the measured error's standard deviation), and the standard deviation of the measured average
    return dict(predicted=float(np.mean([e["predicted"] for e in items])),
                measured=float(np.mean([e["measured"] for e in items])),
                sd=math.sqrt(sum(e["sd"] ** 2 for e in items)) / len(items))


def averaged_runs(runs):
    # The runs averaged over the starting states, {(option, mapping): ...}: the predicted and measured errors, the
    # measured one's standard deviation from shot noise, each starting state's measured error, why it ran, and the Fez
    # qubits it ran on
    out = {}
    for key, mine in per_mapping(runs).items():
        out[key] = dict(**group([dict(predicted=r["predicted"], measured=r["error"], sd=r["error_sd"]) for r in mine]),
                        by_state={r["start"]: r["error"] for r in mine}, why=mine[0]["why"],
                        qubits_used=sorted({q for r in mine for q in r["qubits_used"]}),
                        measured_on=sorted({r["measured_on"] for r in mine}))
    return out


def difference(a, b):
    # a minus b, for two results of group() (or two mappings of averaged_runs())
    return dict(predicted=a["predicted"] - b["predicted"], measured=a["measured"] - b["measured"],
                sd=math.hypot(a["sd"], b["sd"]))


def split(summary, same, value):
    # mapping_sweep.py's split of the spread of the errors (spread_parts) over one code's placements and two options:
    # the code, and no correction on the qubit it is read out on. value: "predicted" or "measured". Returns each part's
    # share: the placement, the option, and the rest (the code's benefit changing from placement to placement)
    errors = np.array([[[summary[x["plain_key"]][value], summary[x["code_key"]][value]]] for x in same])
    shares = spread_parts(errors)   # errors[placement, 0, option]: its "qubits" part is the placement's
    return dict(placement=shares["qubits"] + shares["roles"], option=shares["option"], rest=shares["rest"])


def rank_correlation(summary, keys):
    return float(spearmanr([summary[k]["predicted"] for k in keys], [summary[k]["measured"] for k in keys]).statistic)


def analyze(plan, runs):
    # Everything the report and the plot show
    summary = averaged_runs(runs)
    compared = top_of(plan_lists(plan), plan["compare"])
    picked = {name: {kind: [(name, m) for m, _ in compared[name][kind]] for kind in KINDS} for name in OPTIONS}
    groups = {(name, kind): group([summary[k] for k in picked[name][kind]]) for name in OPTIONS for kind in KINDS}
    # How much picking the best mappings instead of the worst lowers each option's error
    mapping_effect = {name: difference(groups[name, "worst"], groups[name, "best"]) for name in OPTIONS}

    # mapping_pay_off.py's match-ups: no correction minus the code, so above 0 means the code has the lower error
    pairs, counts = {}, {}
    for matchup, plain_list, code_list in MATCHUPS:
        for code in CODES:
            mine = {(matchup, code_key, plain_key): difference(summary[plain_key], summary[code_key])
                    for code_key in picked[code][code_list] for plain_key in picked[OPTIONS[0]][plain_list]}
            pairs |= mine
            found = list(mine.values())
            counts[matchup, code] = dict(pairs=len(found), machine=sum(d["measured"] > 0 for d in found),
                                         clear=sum(d["measured"] > 2 * d["sd"] for d in found),
                                         simulator=sum(d["predicted"] > 0 for d in found))

    # Each code placement next to no correction on the qubit it is read out on (the head-to-head runs)
    same = []
    if plan["head_to_head"]:
        for code in CODES:
            for kind in KINDS:
                for code_key in picked[code][kind]:
                    qubit = summary[code_key]["measured_on"][0]
                    plain_key = (OPTIONS[0], (qubit,))
                    if plain_key in summary:
                        same.append(dict(code=code, kind=kind, placement=code_key[1], qubit=qubit, code_key=code_key,
                                         plain_key=plain_key, **difference(summary[plain_key], summary[code_key])))
    shares = {}
    for code in CODES:
        mine = [x for x in same if x["code"] == code]
        if len(mine) >= 2:
            shares[code] = {value: split(summary, mine, value) for value in ("predicted", "measured")}

    # How much using a code instead of no correction lowers the error, for each code's best and worst placements. With
    # the head-to-head runs it is against no correction on the very qubit each placement is read out on, so only the
    # code changes; without them, against no correction on qubits of the same quality (best with best, worst with
    # worst), as in the match-ups
    code_effect = {}
    for code in CODES:
        for kind in KINDS:
            mine = [x for x in same if x["code"] == code and x["kind"] == kind]
            plain_keys = [x["plain_key"] for x in mine] if mine else picked[OPTIONS[0]][kind]
            code_keys = [x["code_key"] for x in mine] if mine else picked[code][kind]
            code_effect[code, kind] = difference(group([summary[k] for k in plain_keys]),
                                                 group([summary[k] for k in code_keys]))

    listed = list(dict.fromkeys(key for name in OPTIONS for kind in KINDS for key in picked[name][kind]))
    by_option = {name: [k for k in summary if k[0] == name] for name in OPTIONS}
    return dict(summary=summary, picked=picked, groups=groups, mapping_effect=mapping_effect, code_effect=code_effect,
                same_qubits=bool(same), pairs=pairs, counts=counts, same=same, shares=shares, count=len(summary),
                circuits=len(runs), order=listed + sorted(set(summary) - set(listed)),
                rho=rank_correlation(summary, list(summary)),
                rho_by_option={name: rank_correlation(summary, keys) for name, keys in by_option.items()
                               if len(keys) >= 3},
                typical_sd=float(np.median([e["sd"] for e in summary.values()])))


def against_text(a):
    # What a code is compared with in code_effect
    return "no correction on the same qubits" if a["same_qubits"] else "no correction on qubits of the same quality"


def how_much(ratio):
    if ratio != ratio:   # not a number
        return "Can't tell"
    if ratio >= 1.33:
        return "More"
    if ratio >= 0.75:
        return "About as much"
    return "Less" if ratio >= 0.4 else "Much less"


def order_text(rho):
    if rho != rho:
        return "an order that can't be compared with"
    if rho >= 0.8:
        return "nearly the same order"
    if rho >= 0.5:
        return "a similar order"
    return "a loosely similar order" if rho >= 0.2 else "a different order"


def times_text(a, b):
    # Which of two sizes is bigger, and how many times bigger, e.g. ("the mapping", 3.2)
    return ("the mapping", a / b if b else float("inf")) if a >= b else ("the code", b / a if a else float("inf"))


def verdict(plan, a):
    # The answers to the two questions in a few lines, from the numbers in the sections below
    m = float(np.mean([abs(e["measured"]) for e in a["mapping_effect"].values()]))
    m_sim = float(np.mean([abs(e["predicted"]) for e in a["mapping_effect"].values()]))
    c = float(np.mean([abs(e["measured"]) for e in a["code_effect"].values()]))
    c_sim = float(np.mean([abs(e["predicted"]) for e in a["code_effect"].values()]))
    ratio = m / m_sim if m_sim else float("nan")
    more, times = times_text(m, c)
    more_sim, times_sim = times_text(m_sim, c_sim)
    crux = next(name for name, plain_list, code_list in MATCHUPS if (plain_list, code_list) == ("best", "worst"))
    pairs = sum(a["counts"][crux, code]["pairs"] for code in CODES)
    plain_wins = pairs - sum(a["counts"][crux, code]["machine"] for code in CODES)
    plain_wins_sim = pairs - sum(a["counts"][crux, code]["simulator"] for code in CODES)
    return [f"- **Do the mappings matter as much on {plan['backend']} as on the simulator? {how_much(ratio)}.** Going "
            f"from the worst to the best mappings lowered the error by {m:.3f} on the machine (averaged over the three "
            f"options), against {m_sim:.3f} on the simulator: {ratio:.0%} as much.",
            f"- The simulator put the {a['count']} mappings that ran in {order_text(a['rho'])} as the machine did "
            f"(rank correlation {a['rho']:.2f}, where 1 is the same order and 0 unrelated).",
            f"- **Picking good qubits or using a code?** On the machine, {more} mattered more: picking the mapping "
            f"changed the error by {m:.3f} on average, and using a code (against {against_text(a)}) by {c:.3f}, so "
            f"{more} mattered {times:.1f} times as much. On the simulator: {m_sim:.3f} and {c_sim:.3f} ({more_sim} "
            f"{times_sim:.1f} times as much).",
            f"- Good qubits with no correction against bad qubits with a code: no correction had the lower error in "
            f"{plain_wins} of {pairs} pairs on the machine, and in {plain_wins_sim} of {pairs} on the simulator."]


# ---- Printing ----

def print_plan(runs, shots, machine):
    print(f"\n{len(runs)} circuits to run on {machine.name}, {shots} shots each (the predicted error from each starting "
          "state):")
    print_table_header(f"  {'option':<22}{'mapping':<18}{'Fez qubits used':<20}{'read out on':>12}{'predicted':>18}"
                       "   why it runs")
    for (option, mapping), mine in per_mapping(runs).items():
        first = mine[0]
        predicted = " / ".join(f"{r['predicted']:.4f}" for r in mine)
        print(f"  {option:<22}{mapping_text(mapping):<18}{', '.join(map(str, first['qubits_used'])):<20}"
              f"{first['measured_on']:>12}{predicted:>18}   {'; '.join(first['why'])}")


# ---- The report ----

def gates_text(gate_set, num_gates):
    # "200 Y gates", or "200 gates of the repeat gate set"
    gates = GATE_SETS[gate_set][1]
    return f"{num_gates} {gates[0].upper()} gates" if len(gates) == 1 else f"{num_gates} gates of the {gate_set} gate set"


def errors_text(e):
    # A mapping's error on the machine, with the simulator's in brackets
    return f"{e['measured']:.3f} (sim {e['predicted']:.3f})"


def winner_text(d):
    # One match-up pair (no correction minus the code): which had the lower error on the machine and by how much, then
    # which the simulator predicted
    sim = "code" if d["predicted"] > 0 else "none"
    if abs(d["measured"]) < 2 * d["sd"]:
        return f"too close, {d['measured']:+.3f} (sim: {sim})"
    return f"{'code' if d['measured'] > 0 else 'none'}, {abs(d['measured']):.3f} lower (sim: {sim})"


def matchup_table(a, matchup, plain_list, code_list):
    s, plain_keys = a["summary"], a["picked"][OPTIONS[0]][plain_list]
    header = ["code", f"{code_list} placements"] + [f"vs {mapping_text(k[1])}: {errors_text(s[k])}"
                                                    for k in plain_keys]
    rows = [[short_name(code), f"{mapping_text(code_key[1])}: {errors_text(s[code_key])}"]
            + [winner_text(a["pairs"][matchup, code_key, plain_key]) for plain_key in plain_keys]
            for code in CODES for code_key in a["picked"][code][code_list]]
    return md_table(header, rows, "<<" + ">" * len(plain_keys))


def report(plan, a, image_path):
    # The results as Markdown. image_path is the plot's path from the report's folder
    s, states, compare = a["summary"], states_text(plan["start_states"]), plan["compare"]
    head = (", and no correction on the Fez qubit each of those code placements is read out on (the head-to-head "
            "runs)" if plan["head_to_head"] else "")
    out = [f"# Best and worst mappings on the real {plan['backend']}: {gates_text(plan['gate_set'], plan['num_gates'])}",
           "",
           f"Job `{plan['job_id']}`, submitted {plan['submitted']} (UTC): {a['circuits']} circuits of {plan['shots']} "
           f"shots each, every mapping starting once in each of {states}. The mappings are ranked by the error the "
           f"noise simulator predicts for them from the calibration file `{plan['calibration_file']}` (taken "
           f"{plan['calibration_taken'] or 'at an unknown time'}): mapping_sweep.py's simulator and circuits, with the "
           f"calibration's noise numbers instead of FakeFez's. The machine ran the top {compare} of each option's best "
           f"and worst lists{head}.", "",
           f"An error is the chance of reading the wrong answer, averaged over {states}. The machine's errors have shot "
           f"noise of about ±{a['typical_sd']:.3f} (one standard deviation), so smaller differences aren't clear.", ""]
    if plan["left_out"]:
        out += ["Left out of the ranking (numbers missing from the calibration file, or not offered by the machine): "
                f"Fez {', '.join(map(str, plan['left_out']))}.", ""]
    out += [f"![simulator vs machine]({image_path})", "", "## In short", ""] + verdict(plan, a) + [""]

    ranking = plan_lists(plan)
    for kind in KINDS:
        out += [f"## The {plan['top']} {kind} mappings of each option, as predicted", "",
                f"\"(ran)\" marks the top {compare}, which ran on the machine.", ""]
        out += lists_table(ranking, kind, "predicted", compare) + [""]

    out += ["## What the machine measured", "",
            "Every mapping that ran, with the Fez qubits its circuits used (routing can add one, through a SWAP) and the "
            "one its result was read out on.", ""]
    rows = [[short_name(key[0]), "; ".join(s[key]["why"]), mapping_text(key[1]),
             ", ".join(map(str, s[key]["qubits_used"])), "/".join(map(str, s[key]["measured_on"])),
             f"{s[key]['predicted']:.4f}", f"{s[key]['measured']:.4f} ± {s[key]['sd']:.4f}",
             " / ".join(f"{s[key]['by_state'][bit]:.4f}" for bit in plan["start_states"])] for key in a["order"]]
    # (no "|0>" in the header: a | would split the Markdown table's column)
    out += md_table(["option", "why it ran", "mapping", "ran on Fez qubits", "read out on", "simulator", "machine",
                     "machine, starting in " + " / ".join(map(str, plan["start_states"]))], rows, "<<<<>>>>")

    out += ["", "## Do the mappings matter as much on the machine?", "",
            f"Each option's top {compare} best and worst mappings, averaged, and the gap between them: how much picking "
            "the best mappings instead of the worst lowers the error.", ""]
    rows = []
    for name in OPTIONS:
        best, worst, gap = a["groups"][name, "best"], a["groups"][name, "worst"], a["mapping_effect"][name]
        ratio = f"{gap['measured'] / gap['predicted']:.0%}" if gap["predicted"] else "-"
        rows.append([short_name(name), f"{best['predicted']:.4f}", f"{best['measured']:.4f}",
                     f"{worst['predicted']:.4f}", f"{worst['measured']:.4f}", f"{gap['predicted']:.4f}",
                     f"{gap['measured']:.4f} ± {gap['sd']:.4f}", ratio])
    out += md_table(["option", "best: simulator", "best: machine", "worst: simulator", "worst: machine",
                     "gap: simulator", "gap: machine", "machine / simulator"], rows, "<>>>>>>>")
    by_option = ", ".join(f"{short_name(name)} {rho:.2f}" for name, rho in a["rho_by_option"].items())
    out += ["", f"- Rank correlation between the simulator's errors and the machine's, over all {a['count']} mappings "
                f"that ran: {a['rho']:.2f} (1 = the same order, 0 = unrelated). By option: {by_option}", ""]

    against = ("no correction on the very Fez qubit each of its placements is read out on (the head-to-head runs "
               "below), so only the code changes" if a["same_qubits"] else
               "no correction on qubits of the same quality, best with best and worst with worst, as in "
               "mapping_pay_off.py's match-ups")
    out += ["## Picking good qubits or using a code?", "",
            "How much each choice lowers the error (below 0: raises it). Picking the mapping is each option's gap from "
            f"the table above, with the option held fixed. Using a code compares each code's best and worst placements "
            f"with {against}.", ""]
    rows = [[f"best instead of worst mappings, {short_name(name)}", f"{e['predicted']:+.4f}",
             f"{e['measured']:+.4f} ± {e['sd']:.4f}"] for name, e in a["mapping_effect"].items()]
    rows += [[f"{short_name(code)} instead of no correction, {kind} placements", f"{e['predicted']:+.4f}",
              f"{e['measured']:+.4f} ± {e['sd']:.4f}"] for (code, kind), e in a["code_effect"].items()]
    out += md_table(["choice", "simulator", "machine"], rows, "<>>")
    out += ["", "### The match-ups", "",
            f"As in mapping_pay_off.py, each match-up pairs every one of the {compare} code placements with every one of "
            f"the {compare} no-correction qubits, here at {plan['num_gates']} gates. Each cell says which had the lower "
            "error on the machine and by how much (\"too close\" when the gap is under two standard deviations of shot "
            "noise), then which the simulator predicted. The headers give each mapping's error on the machine, with "
            "the simulator's in brackets.", ""]
    for matchup, plain_list, code_list in MATCHUPS:
        out += [f"#### {heading(matchup)}", ""] + matchup_table(a, matchup, plain_list, code_list)
        out.append("")
        for code in CODES:
            n = a["counts"][matchup, code]
            out.append(f"- {short_name(code)}: lower than no correction in {n['machine']} of {n['pairs']} pairs on the "
                       f"machine ({n['clear']} by more than two standard deviations), and in {n['simulator']} of "
                       f"{n['pairs']} on the simulator")
        out.append("")

    if a["same"]:
        out += ["### On the same qubits", "",
                "Each code placement next to no correction on the Fez qubit that placement is read out on, so both are "
                "read out by the same qubit: how much the code itself changes the error, with the qubits held fixed.", ""]
        rows = [[short_name(x["code"]), x["kind"], mapping_text(x["placement"]), f"Fez {x['qubit']}",
                 errors_text(s[x["code_key"]]), errors_text(s[x["plain_key"]]), f"{x['predicted']:+.4f}",
                 f"{x['measured']:+.4f} ± {x['sd']:.4f}"] for x in a["same"]]
        out += md_table(["code", "list", "placement", "read out on", "code: machine (sim)",
                         "no correction: machine (sim)", "the code lowers the error by: simulator", "machine"], rows,
                        "<<<<>>>>") + [""]
        for code in CODES:
            mine = [x for x in a["same"] if x["code"] == code]
            out.append(f"- {short_name(code)} lowered the error on {sum(x['measured'] > 0 for x in mine)} of "
                       f"{len(mine)} placements on the machine, and on {sum(x['predicted'] > 0 for x in mine)} of "
                       f"{len(mine)} on the simulator")
        if a["shares"]:
            out += ["", "The spread of these errors split as in mapping_sweep.py, for each code: which placement, the "
                        "code or no correction, and the rest (the code's benefit changing from placement to "
                        "placement). The placements are the ends of the ranking, so the placement's share is bigger "
                        "here than over all placements, for the simulator and the machine alike.", ""]
            rows = [[f"{short_name(code)}: {label}", f"{shares['predicted'][part]:.0%}",
                     f"{shares['measured'][part]:.0%}"] for code, shares in a["shares"].items()
                    for part, label in (("placement", "which placement"), ("option", "code or no correction"),
                                        ("rest", "the rest"))]
            out += md_table(["part of the spread", "simulator", "machine"], rows, "<>>")
        out.append("")

    out += ["## QPU time", ""]
    if plan["backend"].startswith("fake_"):
        out += ["Run on this computer's simulator (a fake backend), so it used no QPU time.", ""]
    else:
        used = plan.get("qpu_seconds_used")
        out += [f"IBM charged {used:.1f} s of QPU time for the job." if used else
                "IBM hadn't reported the job's QPU time when its results came back (see the Workloads page on IBM "
                "Quantum).", ""]

    out += ["## What this can't show", "",
            f"- One job, on one day. The mappings were ranked from a calibration taken {plan['calibration_age']} before "
            "the job was submitted, and the qubits drift between calibrations, so some of the machine's differences "
            "from the simulator may be drift rather than the simulator being wrong.",
            "- The best and worst mappings are the two ends of the ranking, so the gap between them is bigger than "
            "between typical mappings. That is so for the simulator and the machine alike, so comparing the two is "
            "fair, but it is a best case for how much picking the mapping matters.",
            "- The simulator's noise comes from the calibration numbers alone: it leaves out crosstalk between "
            "neighbouring qubits, leakage, noise on qubits waiting while others work, and drift during the day. Where "
            "the machine is worse than predicted, these are the likely reasons."]
    return "\n".join(out) + "\n"


# ---- The plot ----

def plot(plan, a, path):
    # Left: every mapping that ran, the simulator's error against the machine's. Right: how much each choice lowers the
    # error, picking the mapping against using a code, on the simulator and on the machine
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    plt = pyplot()
    fig, (left, right) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1, 1.2]})
    s = a["summary"]
    low, high = log_limits([v for e in s.values() for v in (e["predicted"], e["measured"])], pad=1.5)
    markers = {"best": "o", "worst": "^"}
    for key in a["order"]:
        e, color = s[key], OPTION_COLORS[key[0]]
        kind = next((k for k in KINDS if key in a["picked"][key[0]][k]), None)
        left.errorbar(max(e["predicted"], low), max(e["measured"], low), yerr=e["sd"], fmt=markers.get(kind, "s"),
                      ms=8 if kind else 6, mfc=color if kind else "white", mec=color, mew=1.4, ecolor=color,
                      elinewidth=1, zorder=3)
    left.plot([low, high], [low, high], "--", color=MUTED, lw=1, zorder=1)
    left.set_xscale("log")
    left.set_yscale("log")
    left.set_xlim(low, high)
    left.set_ylim(low, high)
    log_axis(left.xaxis)
    log_axis(left.yaxis)
    left.set_xlabel("error predicted by the simulator from the calibration", color=MUTED)
    left.set_ylabel(f"error measured on {plan['backend']}", color=MUTED)
    left.set_title("Every mapping that ran (bars: ±1 standard deviation of shot noise)", color=INK, fontsize=11,
                   loc="left")
    handles = [Line2D([], [], ls="", marker="o", ms=8, color=OPTION_COLORS[name]) for name in OPTIONS]
    labels = list(OPTIONS)
    shapes = [("o", "one of the best mappings"), ("^", "one of the worst mappings")]
    if a["same"]:
        shapes.append(("s", "no correction on a code's readout qubit"))
    handles += [Line2D([], [], ls="", marker=m, ms=8, mfc="white" if m == "s" else MUTED, mec=MUTED) for m, _ in shapes]
    labels += [label for _, label in shapes]
    handles.append(Line2D([], [], ls="--", color=MUTED, lw=1))
    labels.append("machine = simulator")
    left.legend(handles, labels, frameon=False, fontsize=8, loc="lower right")
    style(left)

    rows = [(f"best instead of worst\n{short_name(name)} mappings", name, a["mapping_effect"][name]) for name in OPTIONS]
    rows += [(f"{short_name(code)} instead of\nno correction, {kind} placements", code, a["code_effect"][code, kind])
             for code in CODES for kind in KINDS]
    y = np.arange(len(rows))[::-1].astype(float)
    height, ends = 0.38, [0.0]
    for yi, (_, name, e) in zip(y, rows):
        color = OPTION_COLORS[name]
        right.barh(yi + height / 2, e["predicted"], height * 0.92, color="white", edgecolor=color, lw=1.5, zorder=2)
        right.barh(yi - height / 2, e["measured"], height * 0.92, color=color, zorder=2)
        right.errorbar(e["measured"], yi - height / 2, xerr=e["sd"], fmt="none", ecolor=INK, elinewidth=1, capsize=2,
                       zorder=3)
        end = e["measured"] + math.copysign(e["sd"], e["measured"])
        right.annotate(f"{e['measured']:+.3f}", (end, yi - height / 2), xytext=(4 if end >= 0 else -4, 0),
                       textcoords="offset points", ha="left" if end >= 0 else "right", va="center", fontsize=8,
                       color=INK)
        ends += [e["predicted"], end]
    pad = 0.25 * ((max(ends) - min(ends)) or 1)
    right.set_xlim(min(ends) - pad, max(ends) + pad)
    right.axvline(0, color=MUTED, lw=0.8, zorder=1)
    right.axhline(y[len(OPTIONS)] + 0.5, color=GRID, lw=1.2)   # between the mapping rows and the code rows
    right.set_yticks(y, [label for label, _, _ in rows], fontsize=9, color=INK)
    right.set_xlabel("how much the choice lowers the error (below 0: raises it)", color=MUTED)
    right.set_title("Picking the mapping, or using a code", color=INK, fontsize=11, loc="left")
    right.legend([Patch(facecolor="white", edgecolor=MUTED, lw=1.5), Patch(facecolor=MUTED)],
                 ["simulator (predicted)", f"{plan['backend']} (measured, ±1 sd)"], frameon=False, fontsize=8,
                 loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    style(right, grid_axis="x")
    fig.suptitle(f"{plan['backend']}, {gates_text(plan['gate_set'], plan['num_gates'])}: the best and worst mappings of "
                 f"no correction and the Toffoli codes, simulator against machine\n(ranked from the calibration taken "
                 f"{plan['calibration_taken'] or 'at an unknown time'}; job {plan['job_id']}, {plan['shots']} shots per "
                 f"circuit, starting in {states_text(plan['start_states'])})", color=INK)
    save_plot(fig, path)   # tight_layout leaves room for the title itself
    plt.close(fig)


# ---- Running ----

def new_job(calibration_file, gate_set, num_gates, start_states, top, compare, head_to_head, shots, backend_name,
            account, seed, paths):
    # Ranks every mapping from the calibration, picks the runs and submits them to the machine as one job. Returns
    # (plan, runs, job, service), with service None on a fake backend
    print(f"Connecting to {backend_name}...")
    machine, service = get_backend(backend_name, account)
    numbers, cz, lengths, taken = read_calibration(calibration_file)
    print(f"Calibration file {os.path.basename(calibration_file)}, taken {age_text(taken)} ago")
    if taken is not None and (datetime.now(timezone.utc) - taken).total_seconds() > 24 * 3600:
        print("  Note: IBM recalibrates the machine every day and its qubits drift, so the ranking is best with a "
              "calibration file downloaded just before submitting (from ibm_fez's page on IBM Quantum)")
    qubits, edges = usable(numbers, cz, machine)
    left_out = sorted(set(range(len(numbers))) - qubits)
    print(f"Usable: {len(qubits)} qubits and {len(edges)} connections. Left out (numbers missing from the file, or not "
          f"offered by {machine.name}): {left_out or 'none'}")
    backend, sim, readout = calibrated_simulator(numbers, cz, lengths, qubits, edges)

    print(f"\nPredicting every mapping's error at {num_gates} gates from the calibration (this takes a few minutes):")
    by_state, measured = predict_all(gate_set, num_gates, seed, start_states, backend, sim, readout, qubits)
    picked = lists(ranked(average_states(by_state)), top)
    runs = build_runs(choose(top_of(picked, compare), measured, head_to_head), gate_set, num_gates, seed, start_states,
                      backend, by_state)
    check_predictions(runs, sim, readout)
    if service is not None and os.path.exists(paths["job"]):   # (a fake backend's files are just replaced)
        set_aside(paths)
    write_csv(paths["predicted"], PREDICTED_COLUMNS, predicted_rows(by_state, measured))
    write_csv(paths["ranks"], RANK_COLUMNS, rank_rows(picked))
    print_plan(runs, shots, machine)

    print(f"\nSubmitting {len(runs)} circuits x {shots} shots to {machine.name}"
          + (" (a fake backend, so it runs on this computer and uses no QPU time)" if service is None else ""))
    job = submit(runs, machine, shots)
    plan = dict(job_id=job.job_id(), backend=machine.name,
                submitted=datetime.now(timezone.utc).isoformat(timespec="seconds"), gate_set=gate_set,
                num_gates=num_gates, start_states=list(start_states), shots=shots, seed=seed, top=top, compare=compare,
                head_to_head=head_to_head, calibration_file=os.path.basename(calibration_file),
                calibration_taken=taken.strftime("%Y-%m-%d %H:%M UTC") if taken else None,
                calibration_age=age_text(taken), left_out=left_out,
                lists={name: {kind: [[list(m), e] for m, e in mine] for kind, mine in by_kind.items()}
                       for name, by_kind in picked.items()})
    print(f"Submitted job {plan['job_id']} at {plan['submitted']}")
    save_plan(paths["job"], plan, runs)
    return plan, runs, job, service


def collect(job, plan, runs, service, paths):
    # Waits for the job, reads its results into runs and saves them, and records the QPU time IBM charged for it.
    # False if there are no results
    result = wait_for(job)
    if result is None:
        return False
    read_results(runs, result)
    write_csv(paths["results"], HARDWARE_COLUMNS, hardware_rows(plan, runs))
    if service is not None:
        plan["qpu_seconds_used"] = used = billed_seconds(job)
        print(f"IBM charged {used:.1f} s of QPU time for the job" if used else
              "IBM hasn't reported the job's QPU time yet (see the Workloads page on IBM Quantum)")
    save_plan(paths["job"], plan, runs)
    return True


def run(calibration_file, gate_set="y", num_gates=200, start_states=(0, 1), top=10, compare=3, head_to_head=True,
        shots=2000, backend_name="ibm_fez", account=None, seed=3, resume=False, csv_dir=CSV_DIR, image_dir=IMAGE_DIR,
        report_dir=REPORT_DIR):
    start_states = check_test(gate_set, start_states)
    check_compare(compare, top)
    if backend_name not in ("ibm_fez", "fake_fez"):
        raise ValueError(f"this script is built for Fez (its calibration file and layout), so use \"ibm_fez\" or "
                         f"\"fake_fez\", not \"{backend_name}\"")
    paths = job_paths(backend_name, gate_set, num_gates, csv_dir, image_dir, report_dir)

    if resume and not backend_name.startswith("fake_"):
        # The results of the job submitted last, from its saved files or else from IBM, instead of a new job
        plan, runs, saved = saved_job(paths)
        if not saved:
            print(f"Getting the results of job {plan['job_id']} (submitted {plan['submitted']}) from IBM Quantum")
            _, service = get_backend(backend_name, account)
            if not collect(service.job(plan["job_id"]), plan, runs, service, paths):
                return
    else:
        plan, runs, job, service = new_job(calibration_file, gate_set, num_gates, start_states, top, compare,
                                           head_to_head, shots, backend_name, account, seed, paths)
        if not collect(job, plan, runs, service, paths):
            return

    analysis = analyze(plan, runs)
    save_report(paths["report"], report(plan, analysis, os.path.relpath(paths["image"], report_dir)))
    plot(plan, analysis, paths["image"])


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    # The ibm_fez calibration file the mappings are ranked from, downloaded from IBM Quantum (the time it was taken is
    # in its name). The machine drifts, so for the best ranking download a fresh one, save it in csvs/ and name it here
    CALIBRATION_FILE = os.path.join(CSV_DIR, "ibm_fez_calibrations_2026-11-13T16_27_59Z.csv")
    GATE_SET = "y"            # the test circuit (a key of compare_fez.py's GATE_SETS): "y" = only Y gates
    NUM_GATES = 200           # gates in the test circuit
    START_STATES = [0, 1]     # every mapping runs once from each; its error is the average over them
    TOP = 10                  # how many best and worst mappings of each option the report lists
    COMPARE = 3               # how many of each list run on the machine, as in mapping_pay_off.py's match-ups (1 to 4)
    HEAD_TO_HEAD = True       # also run no correction on the Fez qubit each code placement is read out on
    SHOTS = 2000              # shots per circuit (the first job, 44 circuits of 2000 shots, used 26 s of QPU time)
    BACKEND_NAME = "ibm_fez"  # "fake_fez" tries the whole script on your own machine, with no account or QPU time
    ACCOUNT = None            # only used if .env has no API key: name of a saved IBM account; None = default one
    SEED = 3                  # the transpiler seed, as in mapping_sweep.py and the hardware runs
    RESUME = False            # True gets the results of the job this script submitted last (its csvs/..._job.json)
                              # instead of submitting a new one, e.g. after you stopped waiting for it with Ctrl+C

    run(CALIBRATION_FILE, GATE_SET, NUM_GATES, start_states=START_STATES, top=TOP, compare=COMPARE,
        head_to_head=HEAD_TO_HEAD, shots=SHOTS, backend_name=BACKEND_NAME, account=ACCOUNT, seed=SEED, resume=RESUME)
