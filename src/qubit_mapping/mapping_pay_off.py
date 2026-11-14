# mapping_pay_off.py
# Uses one mapping sweep (mapping_sweep.py's runs CSV file, so run that first) to list each option's TOP best and worst
# mappings: the Fez qubits to run no correction on, and the placements (Fez qubits for q_0, q_1, q_2) to run the
# bit-flip and phase-flip Toffoli codes on. Then finds how many gates each code needs to pay off against no correction
# when each runs on a mapping picked from those lists, in four match-ups:
#   worst no correction vs best codes    no correction on its worst qubits, the codes on their best placements
#   best no correction vs worst codes    the other way round
#   best no correction vs best codes
#   worst no correction vs worst codes
# Each match-up takes COMPARE mappings from each list and pairs every code placement with every no-correction qubit.
# Every pay-off point is found for each starting state on its own. Writes the lists and the pay-off points to CSV files
# and a report (also printed), and plots the errors, one plot per starting state, with a marker where each code pays off.
#
# The ranking: a mapping's error is the sweep's, at the sweep's number of gates, averaged over its starting states, so
# "best" means lowest error there. The sweep only places the codes on 3 connected Fez qubits (see mapping_sweep.py).
#
# The pay-off point is counted the way pay_off.py counts it: the first number of gates where the code starts beating no
# correction IN_A_ROW times in a row, counting up from 0 in steps of pay_off.py's STEPS for the gate set, up to
# max_gates. Two things differ from pay_off.py:
#   - no correction runs on the Fez qubit it was picked for, not on the qubit the code is measured on, since comparing
#     good and bad qubits is the point here
#   - the errors are exact, as in mapping_sweep.py (the exact chance of reading 1, with the readout error added), so
#     there is no shot noise, and the pay-off point is found for each of the sweep's starting states
#
# Why the errors at every number of gates are quick to get: the test gates each act on one qubit, so the transpiler
# routes a circuit the same way however many there are, and n of them on one Fez qubit act as that qubit's noisy
# channel for one gate (the gate followed by its Fez error, the way Aer applies it) n times over. So each mapping is
# transpiled once with one round of the gate set's gates, and for each number of gates that section of the circuit is
# swapped for its channel to the matching power, which Aer runs along with the rest of the circuit and its noise.
# Checked against running the full circuits on Aer (the same to 1e-14), and the script checks its own errors at the
# sweep's number of gates against the sweep's CSV file before using them
import os
import sys

import numpy as np
from qiskit.quantum_info import Kraus, Operator, Statevector, SuperOp
from qiskit_aer import AerSimulator
from qiskit_aer.noise.device import basic_device_gate_errors, basic_device_readout_errors
from qiskit_ibm_runtime.fake_provider import FakeFez

# The sweep's code (and through it the codes and Fez helpers in src/noisy and the output code in src/output_tools),
# and the pay-off rules in src/pay_off
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pay_off"))
from mapping_sweep import (CHUNK, CODES, CSV_DIR, IMAGE_DIR, OPTION_COLORS, OPTIONS, REPORT_DIR, log_axis,
                           mapping_text, md_table, run_batch, short_name, states_text, test_versions)
from compare_fez import GATE_SETS, on_fez, test_circuit
from output_tools import INK, MUTED, pyplot, read_csv, save_plot, style, write_csv, write_text
from pay_off import STEPS
from pay_off_common import IN_A_ROW

# The four match-ups: (name, which list no correction's qubits come from, which list the codes' placements come from)
MATCHUPS = [
    ("worst no correction vs best codes", "worst", "best"),
    ("best no correction vs worst codes", "best", "worst"),
    ("best no correction vs best codes", "best", "best"),
    ("worst no correction vs worst codes", "worst", "worst"),
]
# In the plot, each option keeps its color, and its 1st, 2nd, ... mapping in a match-up gets these line styles
LINE_STYLES = ["-", "--", ":", "-."]
RANK_COLUMNS = ["option", "list", "rank", "q0", "q1", "q2", "error"]
POINT_COLUMNS = ["matchup", "start", "code", "q0", "q1", "q2", "code_error", "no_correction_qubit",
                 "no_correction_error", "pays_off_at_gates"]
CURVE_COLUMNS = ["option", "q0", "q1", "q2", "start", "gates", "error"]


# ---- The sweep's results ----

def sweep_path(gate_set, num_gates, csv_dir):
    return os.path.join(csv_dir, f"mapping_sweep_{gate_set}_{num_gates}.csv")


def load_sweep(gate_set, num_gates, csv_dir):
    # Each mapping's error in the sweep, averaged over the starting states: {option: {mapping: error}}, with mapping
    # (q,) for no correction and (q_0, q_1, q_2) for the codes. Also the starting states, and each mapping's error from
    # each of them: {start: {option: {mapping: error}}}
    path = sweep_path(gate_set, num_gates, csv_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} doesn't exist: run mapping_sweep.py with GATE_SET = \"{gate_set}\" and "
                                f"NUM_GATES = {num_gates} first")
    by_state = {}
    for r in read_csv(path):
        mapping = tuple(int(r[k]) for k in ("q0", "q1", "q2") if r[k] != "")
        by_state.setdefault(int(r["start"]), {}).setdefault(r["option"], {})[mapping] = float(r["error"])
    start_states = tuple(sorted(by_state))
    average = {name: {m: float(np.mean([by_state[bit][name][m] for bit in start_states]))
                      for m in by_state[start_states[0]][name]} for name in OPTIONS}
    return average, start_states, by_state


def ranked(errors):
    # Each option's mappings, lowest error first: {option: [(mapping, error)]}
    return {name: sorted(mine.items(), key=lambda item: (item[1], item[0])) for name, mine in errors.items()}


def lists(ranks, n):
    # Each option's n best (lowest error first) and n worst (highest error first): {option: {"best"/"worst": [...]}}
    return {name: {"best": mine[:n], "worst": mine[::-1][:n]} for name, mine in ranks.items()}


# ---- Errors at every number of gates ----

def gate_channel(instructions, qubit, gate_errors):
    # The channel (a SuperOp matrix) of instructions on one Fez qubit, each gate followed by its error on that qubit,
    # as Aer's noise model applies it
    channel = SuperOp(np.eye(4))
    for inst in instructions:
        step = SuperOp(Operator(inst.operation))
        error = gate_errors.get((inst.operation.name, (qubit,)))
        if error is not None:
            step = step.compose(error.to_quantumchannel())
        channel = channel.compose(step)
    return channel.data


def gate_section(circuit, coded, bit):
    # Where a transpiled circuit's test gates are, as (first index, index after the last), and the gates by Fez qubit,
    # {qubit: [instructions]}. The codes put a barrier on each side of them. With no correction they run from the start
    # (after the X that prepares |1>) up to the barrier measure_all puts before the measurement
    barriers = [i for i, inst in enumerate(circuit.data) if inst.operation.name == "barrier"]
    first, stop = (barriers[0] + 1, barriers[1]) if coded else (bit, barriers[0])
    gates = {}
    for inst in circuit.data[first:stop]:
        if len(inst.qubits) != 1:
            raise ValueError(f"expected only 1-qubit test gates between indices {first} and {stop}, got "
                             f"'{inst.operation.name}' on {len(inst.qubits)} qubits")
        gates.setdefault(circuit.find_bit(inst.qubits[0]).index, []).append(inst)
    return first, stop, gates


def with_channels(circuit, first, stop, channels):
    # The circuit with its test gates swapped for {qubit: channel matrix}, each added as one instruction
    out = circuit.copy_empty_like()
    for inst in circuit.data[:first]:
        out.append(inst)
    for qubit, matrix in channels.items():
        out.append(Kraus(SuperOp(matrix)), [qubit])
    for inst in circuit.data[stop:]:
        out.append(inst)
    return out


def exact_answers(gate_set, period, seed, bit, rounds):
    # The exact chance of 1 after 0, 1, 2, ... rounds of the gate set's gates (period gates each), starting in |bit>
    one_round = Operator(test_circuit(gate_set, period, seed, False))
    state, answers = Statevector.from_int(bit, 2), []
    for _ in range(rounds + 1):
        answers.append(float(state.probabilities()[1]))
        state = state.evolve(one_round)
    return answers


def curves(mappings, gate_set, start_states, seed, ns, backend, sim, readout):
    # Each mapping's error at every number of gates in ns, from each starting state: {start: {(option, mapping): array
    # of errors}}. mappings: [(option, mapping)]
    period = len(GATE_SETS[gate_set][1])
    gate_errors = {(name, tuple(q)): e for name, q, e in basic_device_gate_errors(target=backend.target)}
    versions = test_versions(gate_set, period, seed, start_states)   # one round of gates
    exact = {bit: exact_answers(gate_set, period, seed, bit, ns[-1] // period) for bit in start_states}
    batch = []
    for option, mapping in mappings:
        for bit, (_, plain, encoded) in versions.items():
            coded = option in CODES
            circuits, _ = on_fez(plain, {option: encoded[option]} if coded else {}, backend,
                                 {"bit/phase-flip": list(mapping)}, seed)
            circuit = circuits[option] if coded else next(iter(circuits.values()))
            first, stop, gates = gate_section(circuit, coded, bit)
            one = {q: gate_channel(insts, q, gate_errors) for q, insts in gates.items()}
            for n in ns:
                channels = {q: np.linalg.matrix_power(c, n // period) for q, c in one.items()}
                # num_gates, not gates: run_batch adds the circuit's size as "gates"
                batch.append((dict(option=option, mapping=mapping, num_gates=n, start=bit,
                                   exact_p1=exact[bit][n // period]), with_channels(circuit, first, stop, channels)))
    errors = {bit: {} for bit in start_states}
    for i in range(0, len(batch), CHUNK):
        for r in run_batch(batch[i:i + CHUNK], sim, readout):
            errors[r["start"]].setdefault((r["option"], r["mapping"]), {})[r["num_gates"]] = r["error"]
    return {bit: {key: np.array([by_n[n] for n in ns]) for key, by_n in mine.items()} for bit, mine in errors.items()}


def check_against_sweep(found, errors, ns, num_gates):
    # The errors here at the sweep's number of gates must be the sweep's own (its CSV file rounds them to 6 decimals),
    # or something differs from the sweep, such as the seed
    if num_gates not in ns:
        print(f"Note: {num_gates} gates isn't among the numbers of gates counted, so the errors weren't checked against "
              "the sweep")
        return
    i = ns.index(num_gates)
    off = {key: abs(e[i] - errors[key[0]][key[1]]) for key, e in found.items()}
    worst = max(off, key=off.get)
    if off[worst] > 1e-5:
        raise RuntimeError(f"{worst[0]} on {mapping_text(worst[1])}: {found[worst][i]:.6f} here but "
                           f"{errors[worst[0]][worst[1]]:.6f} in the sweep at {num_gates} gates; was the sweep run "
                           "with the same seed?")
    print(f"Checked against the sweep at {num_gates} gates: largest difference {off[worst]:.1e}")


# ---- Pay-off points ----

def pay_off_point(code, plain, ns):
    # The first number of gates where code's error starts being lower than plain's IN_A_ROW times in a row, or None
    streak = 0
    for i, n in enumerate(ns):
        streak = streak + 1 if code[i] < plain[i] else 0
        if streak == IN_A_ROW:
            return ns[i - IN_A_ROW + 1]
    return None


def matchups(picked, by_state, ns):
    # Every pay-off point: one row per match-up, code placement, no-correction qubit and starting state. by_state:
    # {start: {(option, mapping): errors}}
    points = []
    for matchup, plain_list, code_list in MATCHUPS:
        for code in CODES:
            for placement, code_error in picked[code][code_list]:
                for (qubit,), plain_error in picked[OPTIONS[0]][plain_list]:
                    for bit, found in by_state.items():
                        points.append(dict(matchup=matchup, start=bit, code=code, placement=placement,
                                           code_error=code_error, qubit=qubit, plain_error=plain_error,
                                           pays_off_at=pay_off_point(found[code, placement],
                                                                     found[OPTIONS[0], (qubit,)], ns)))
    return points


# ---- CSV files and the report ----

def rank_rows(picked):
    return [[name, kind, i, *mapping, *[""] * (3 - len(mapping)), round(error, 6)]
            for name, by_kind in picked.items() for kind, mine in by_kind.items()
            for i, (mapping, error) in enumerate(mine, 1)]


def point_rows(points):
    return [[p["matchup"], p["start"], p["code"], *p["placement"], round(p["code_error"], 6), p["qubit"],
             round(p["plain_error"], 6), "" if p["pays_off_at"] is None else p["pays_off_at"]] for p in points]


def curve_rows(by_state, ns):
    return [[option, *mapping, *[""] * (3 - len(mapping)), bit, n, round(float(e), 6)]
            for bit, found in by_state.items() for (option, mapping), errors in found.items() for n, e in zip(ns, errors)]


def pay_off_text(n, max_gates):
    # As in pay_off_table.md: ">N" when it still hadn't paid off at N gates
    return f">{max_gates}" if n is None else str(n)


def range_text(numbers):
    return f"{min(numbers)}" if min(numbers) == max(numbers) else f"{min(numbers)} to {max(numbers)}"


def report(picked, compared, points, gate_set, num_gates, start_states, top, max_gates, step, plot_paths):
    # The lists (picked) and the pay-off points of the mappings in the match-ups (compared, the top of each list) as
    # Markdown. plot_paths: {start: that starting state's plot's path from the report's folder}
    compare = len(compared[OPTIONS[0]]["best"])
    states = states_text(start_states)
    out = [f"# Best and worst mappings on Fez, and when the codes pay off: {gate_set} gate set", "",
           f"From `csvs/mapping_sweep_{gate_set}_{num_gates}.csv` (mapping_sweep.py): the exact error at {num_gates} "
           f"gates on the Fez noise simulator, averaged over starting in {states}. The codes' placements are q_0, q_1, "
           "q_2 on 3 connected Fez qubits.", ""]
    for kind in ("best", "worst"):
        out += [f"## The {top} {kind} mappings of each option", ""]
        header = ["rank"] + [h for name in OPTIONS for h in (short_name(name), "error")]
        rows = [[i + 1] + [cell for name in OPTIONS for cell in
                           (mapping_text(picked[name][kind][i][0]), f"{picked[name][kind][i][1]:.4f}")]
                for i in range(top)]
        out += md_table(header, rows, ">" + "<>" * len(OPTIONS)) + [""]

    out += ["## When the codes pay off", "",
            f"Each match-up pairs every one of the {compare} code placements with every one of the {compare} no-correction "
            f"qubits, taken from the top of the lists above. A code pays off at the first number of gates where its "
            f"error starts being lower than no correction's {IN_A_ROW} times in a row (as in pay_off.py), counting "
            f"from 0 in steps of {step} up to {max_gates}. Here no correction runs on its own qubit, not on the one the "
            f"code is measured on. Errors are exact, and each starting state is counted on its own: each cell is the "
            f"pay-off point starting in {' / '.join(f'|{bit}>' for bit in start_states)} (>{max_gates}: it hadn't paid "
            f"off by {max_gates} gates). The number in brackets is each mapping's error at {num_gates} gates, averaged "
            f"over starting in {states} (what the lists are ranked by).", "",
            "One plot per starting state, with a marker where each code pays off:", ""]
    for bit, path in plot_paths.items():
        out += [f"![error vs number of gates in each match-up, starting in |{bit}>]({path})", ""]
    for matchup, plain_list, code_list in MATCHUPS:
        mine = [p for p in points if p["matchup"] == matchup]
        qubits = list(dict.fromkeys((p["qubit"], p["plain_error"]) for p in mine))
        out += [f"### {matchup[0].upper() + matchup[1:]}", ""]
        rows = []
        for code in CODES:
            for placement, code_error in compared[code][code_list]:
                cells = {(p["qubit"], p["start"]): p["pays_off_at"] for p in mine
                         if p["code"] == code and p["placement"] == placement}
                rows.append([short_name(code), f"{mapping_text(placement)} ({code_error:.4f})"]
                            + [" / ".join(pay_off_text(cells[q, bit], max_gates) for bit in start_states)
                               for q, _ in qubits])
        header = ["code", f"{code_list} placements"] + [f"vs Fez {q} ({e:.4f})" for q, e in qubits]
        out += md_table(header, rows, "<<" + ">" * len(qubits)) + [""]
        for code in CODES:
            parts = []
            for bit in start_states:
                found = [p["pays_off_at"] for p in mine if p["code"] == code and p["start"] == bit]
                paid = [n for n in found if n is not None]
                parts.append(f"{len(paid)} of {len(found)} pairs from |{bit}>"
                             + (f" ({range_text(paid)} gates)" if paid else ""))
            out.append(f"- {short_name(code)}: pays off in " + " and ".join(parts))
        out.append("")
    return "\n".join(out)


# ---- The plot ----

def clusters(marks, ax, reach=14):
    # Groups marks [(gates, error, ...)] that sit within reach pixels of each other on ax, so each group gets one label
    to_pixels = ax.transData.transform
    groups = []
    for mark in sorted(marks):
        x, y = to_pixels((mark[0], mark[1]))
        for group in groups:
            if any(np.hypot(x - gx, y - gy) <= reach for gx, gy in group["pixels"]):
                group["marks"].append(mark)
                group["pixels"].append((x, y))
                break
        else:
            groups.append(dict(marks=[mark], pixels=[(x, y)]))
    return [g["marks"] for g in groups]


def label_pay_offs(ax, marks):
    # One marker per pay-off point, [(gates, error, code)], on the code's line, and one label per group of markers that
    # sit together, with the gates where they pay off. Each label goes in the nearest spot to its group that is inside
    # the panel and clear of the labels and markers already placed, or, if there is none, the spot inside the panel
    # that overlaps the fewest of them
    from matplotlib.text import Text
    renderer = ax.figure.canvas.get_renderer()
    for gates, error, code in marks:
        ax.scatter([gates], [error], s=40, color=OPTION_COLORS[code], edgecolors="white", linewidths=1.2, zorder=5)
    inside = ax.get_window_extent(renderer)
    taken = [ax.transData.transform((gates, error)) for gates, error, _ in marks]
    boxes = []
    # Offsets in points: to the right, left, above and below, then further out
    spots = [(sx * dx * d, sy * dy * d) for d in (8, 16, 26, 38, 52, 68, 86, 106, 130) for dx, dy in
             ((1, 0.5), (0.3, 1), (0, 1)) for sx in ((1, -1) if dx else (1,)) for sy in (1, -1)]
    for code in CODES:
        for group in clusters([m for m in marks if m[2] == code], ax):
            text = f"{short_name(code)} {range_text([m[0] for m in group])}".replace(" to ", "–")
            x, y = group[0][0], group[0][1]
            best = None
            for dx, dy in spots:
                label = ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=7.5, color=INK,
                                    ha="center" if dx == 0 else "left" if dx > 0 else "right",
                                    va="bottom" if dy > 0 else "top", zorder=6,
                                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
                                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6, shrinkA=0, shrinkB=4))
                # The text alone: the annotation's own extent takes in its leader line, which reaches the marker
                label.update_positions(renderer)
                box = Text.get_window_extent(label, renderer).expanded(1.06, 1.15)
                outside = not (inside.contains(box.x0, box.y0) and inside.contains(box.x1, box.y1))
                clashes = sum(box.overlaps(b) for b in boxes) + sum(box.contains(px, py) for px, py in taken)
                score = 1000 * outside + clashes
                if best is None or score < best[0]:
                    if best is not None:
                        best[1].remove()
                    best = (score, label, box)
                else:
                    label.remove()
                if score == 0:
                    break
            best[1].set_in_layout(False)
            boxes.append(best[2])


def plot(picked, found, state_errors, points, ns, gate_set, num_gates, bit, start_states, limits, path):
    # One panel per match-up: the error of each mapping in it against the number of gates, starting in |bit>, with a
    # marker where each code pays off against each no-correction qubit. found: {(option, mapping): errors} from that
    # state; state_errors: {option: {mapping: error}}, the sweep's errors from it at num_gates; points: the pay-off
    # points from that state. Each option keeps its color; its 1st, 2nd, ... mapping in the match-up (ranked by the
    # average over the starting states) get the line styles of LINE_STYLES
    from matplotlib.lines import Line2D
    plt = pyplot()
    fig, axes = plt.subplots(2, 2, figsize=(15, 12), sharex=True, sharey=True)
    for ax, (matchup, plain_list, code_list) in zip(axes.flat, MATCHUPS):
        for name in OPTIONS:
            kind = plain_list if name == OPTIONS[0] else code_list
            for (mapping, _), ls in zip(picked[name][kind], LINE_STYLES):
                ax.plot(ns, found[name, mapping], ls, color=OPTION_COLORS[name], lw=2,
                        label=f"{mapping_text(mapping)} ({state_errors[name][mapping]:.3f})")
        ax.set_yscale("log")
        ax.set_ylim(*limits)
        ax.set_xlim(ns[0], ns[-1])
        log_axis(ax.yaxis)
        ax.set_title(matchup[0].upper() + matchup[1:], color=INK, fontsize=11, loc="left")
        # One legend column per option, in the order of OPTIONS
        ax.legend(ncol=len(OPTIONS), frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1),
                  title=f"mapping (error at {num_gates} gates from |{bit}>)", title_fontsize=8)
        style(ax)
    for ax in axes[1]:
        ax.set_xlabel("number of gates", color=MUTED)
    for ax in axes[:, 0]:
        ax.set_ylabel("logical error", color=MUTED)
    for ax in axes[0]:
        ax.tick_params(labelbottom=True)
    handles = [Line2D([], [], color=OPTION_COLORS[name], lw=2) for name in OPTIONS]
    handles += [Line2D([], [], ls=ls, color=INK, lw=2) for ls in LINE_STYLES[:len(picked[OPTIONS[0]]["best"])]]
    handles.append(Line2D([], [], ls="", marker="o", ms=7, color=MUTED, mec="white", mew=1.2))
    labels = list(OPTIONS) + [f"{i} on its list" for i in ("1st", "2nd", "3rd", "4th")[:len(handles) - len(OPTIONS) - 1]]
    labels.append(f"code pays off ({IN_A_ROW} wins in a row), at the gates written")
    fig.suptitle(f"Fez, {gate_set} gate set, starting in |{bit}>: error vs number of gates for the best and worst "
                 f"mappings of each option\n(exact errors from the Fez noise simulator; the lists are ranked by the "
                 f"average over {states_text(start_states)} at {num_gates} gates)", color=INK)
    fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False, fontsize=9,
               bbox_to_anchor=(0.5, 0.945))
    # The markers and their labels go on once the panels are in their final places, so labels can be kept apart
    rect = (0, 0, 1, 0.93)
    fig.tight_layout(rect=rect)
    fig.canvas.draw()
    for ax, (matchup, *_) in zip(axes.flat, MATCHUPS):
        marks = [(p["pays_off_at"], float(found[p["code"], p["placement"]][ns.index(p["pays_off_at"])]), p["code"])
                 for p in points if p["matchup"] == matchup and p["pays_off_at"] is not None]
        if marks:
            label_pay_offs(ax, marks)
        else:
            ax.text(0.98, 0.03, f"neither code pays off by {ns[-1]} gates", transform=ax.transAxes, ha="right",
                    va="bottom", color=MUTED, fontsize=9)
    save_plot(fig, path, rect=rect)
    plt.close(fig)


# ---- Running ----

def run(gate_set="y", num_gates=500, top=10, compare=3, max_gates=1000, seed=3, csv_dir=CSV_DIR, image_dir=IMAGE_DIR,
        report_dir=REPORT_DIR):
    # gate_set and num_gates pick the sweep (it must have been run with the same seed). top: how many best and worst
    # mappings to list. compare: how many of each list go into the match-ups (1 to 4). max_gates: where to stop
    # counting when a code hasn't paid off, and where the plots end
    kind, gates = GATE_SETS[gate_set]
    if kind != "repeating":
        raise ValueError(f"gate set '{gate_set}' is random, so its gates can't be counted up by repeating one round; "
                         "use a repeating one (x, y, z, id, repeat)")
    step = STEPS.get(gate_set, 20)
    if step % len(gates):
        raise ValueError(f"the step ({step}) must be a whole number of rounds of {len(gates)} gates")
    if not 1 <= compare <= min(top, len(LINE_STYLES)):
        raise ValueError(f"compare must be from 1 to {min(top, len(LINE_STYLES))}, got {compare}")
    errors, start_states, sweep_by_state = load_sweep(gate_set, num_gates, csv_dir)
    picked = lists(ranked(errors), top)
    for name in OPTIONS:
        if len(errors[name]) < 2 * top:
            print(f"Note: {name} has only {len(errors[name])} mappings, so its best and worst lists overlap")

    backend = FakeFez()
    sim = AerSimulator.from_backend(backend, method="density_matrix", max_parallel_experiments=0)
    readout = {qargs[0]: err.probabilities for qargs, err in basic_device_readout_errors(target=backend.target)}
    ns = list(range(0, max_gates + 1, step))
    mappings = list(dict.fromkeys((name, m) for name in OPTIONS for by_kind in ("best", "worst")
                                  for m, _ in picked[name][by_kind][:compare]))
    print(f"{gate_set} gate set: errors of {len(mappings)} mappings at 0 to {max_gates} gates in steps of {step}, "
          f"starting in {states_text(start_states)}\n")
    by_state = curves(mappings, gate_set, start_states, seed, ns, backend, sim, readout)
    found = {key: np.mean([by_state[bit][key] for bit in start_states], axis=0) for key in by_state[start_states[0]]}
    check_against_sweep(found, errors, ns, num_gates)

    compared = {name: {k: mine[:compare] for k, mine in by_kind.items()} for name, by_kind in picked.items()}
    points = matchups(compared, by_state, ns)
    name = f"mapping_pay_off_{gate_set}_{num_gates}"
    images = {bit: os.path.join(image_dir, f"{name}_start_{bit}.png") for bit in start_states}
    write_csv(os.path.join(csv_dir, f"{name}_ranks.csv"), RANK_COLUMNS, rank_rows(picked))
    write_csv(os.path.join(csv_dir, f"{name}_points.csv"), POINT_COLUMNS, point_rows(points))
    write_csv(os.path.join(csv_dir, f"{name}_curves.csv"), CURVE_COLUMNS, curve_rows(by_state, ns))
    text = report(picked, compared, points, gate_set, num_gates, start_states, top, max_gates, step,
                  {bit: os.path.relpath(path, report_dir) for bit, path in images.items()})
    print("\n" + text)
    write_text(os.path.join(report_dir, f"{name}.md"), text)
    # Both plots share one scale, so they can be compared
    every = np.concatenate([e for mine in by_state.values() for e in mine.values()])
    limits = (max(every[every > 0].min() / 1.3, 1e-4), min(every.max() * 1.3, 1))
    for bit, path in images.items():
        plot(compared, by_state[bit], sweep_by_state[bit], [p for p in points if p["start"] == bit], ns, gate_set,
             num_gates, bit, start_states, limits, path)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    GATE_SET = "y"      # the sweep to use: csvs/mapping_sweep_<GATE_SET>_<NUM_GATES>.csv from mapping_sweep.py
    NUM_GATES = 500     # (the ranking is by each mapping's error at this many gates)
    TOP = 10            # how many best and worst mappings of each option to list
    COMPARE = 3         # how many of the best and worst of each option go into the match-ups (1 to 4)
    MAX_GATES = 1000    # stop counting here if a code still hasn't paid off, and where the plots end
    SEED = 3            # the transpiler seed: must be the one the sweep was run with

    run(GATE_SET, NUM_GATES, top=TOP, compare=COMPARE, max_gates=MAX_GATES, seed=SEED)
