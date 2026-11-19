# mapping_sweep.py
import os
import time
from itertools import combinations, permutations

import numpy as np
from qiskit_ibm_runtime.fake_provider import FakeFez
from scipy.stats import spearmanr

# The code the mapping scripts share (importing it also puts src/noisy and src/output_tools on the import path)
from mapping_common import (CHUNK, CODES, CSV_DIR, IMAGE_DIR, OPTION_COLORS, OPTIONS, REPORT_DIR, check_test, log_axis,
                            log_limits, mapping_cells, mapping_text, md_table, noise_simulator, placed, run_batch,
                            save_report, short_name, states_text, test_versions)
from fez_common import DEFAULT_DATA_QUBITS, working_coupling_map
from output_tools import INK, MUTED, pyplot, save_plot, style, write_csv

# The 4 parts the spread of the errors is split into (see spread_parts): a short name and the label
PARTS = [
    ("qubits", "which 3 Fez qubits"),
    ("roles", "which qubit plays which role"),
    ("option", "which option"),
    ("rest", "the option gap changing by placement"),
]
MAPPING_PARTS = ("qubits", "roles")
RUN_COLUMNS = ["gate_set", "num_gates", "start", "option", "q0", "q1", "q2", "line", "q0_in_middle", "measured_on",
               "qubits_used", "gates", "two_qubit_gates", "depth", "exact_p1", "p_read_1", "error",
               "no_correction_error", "beats_no_correction"]
PLACEMENT_COLUMNS = ["line", "q0", "q1", "q2", "q0_in_middle", "measured_on", "no_correction_error", "bit_flip_error",
                     "phase_flip_error", "lowest"]


# ---- The mappings ----

def lines(backend, max_lines=None):
    # Every 3 connected Fez qubits, as (middle, end, end), over Fez's working connections (see fez_common.py).
    # max_lines keeps only the first that many, for a quick trial run
    wiring = working_coupling_map(backend)
    found = [(middle, a, b) for middle in sorted(wiring.physical_qubits)
             for a, b in combinations(sorted(set(wiring.neighbors(middle))), 2)]
    return found[:max_lines]


def placements(line):
    # The 6 placements on one line, as (Fez qubit for q_0, q_1, q_2): every choice of which qubit plays which role, the
    # 2 with q_0 in the middle first
    return list(permutations(line))


def sweep_name(gate_set, num_gates):
    # The sweep's files are named after it (mapping_pay_off.py reads its runs CSV file)
    return f"mapping_sweep_{gate_set}_{num_gates}"


# ---- Running ----

def sweep(gate_set, num_gates, seed, start_states, max_lines, backend, sim, readout):
    # No correction on every Fez qubit, then both codes on every placement, from every starting state. Returns one row
    # per run. Each code's row also gets no correction's error on the Fez qubit that code was measured on
    versions = test_versions(gate_set, num_gates, seed, start_states)
    test = dict(gate_set=gate_set, num_gates=num_gates)
    start = time.time()
    batch = []
    for q in range(backend.num_qubits):
        for bit, (exact_p1, plain, encoded) in versions.items():
            qc = placed([OPTIONS[0]], (q,), plain, encoded, backend, seed)[OPTIONS[0]]
            batch.append((test | dict(start=bit, option=OPTIONS[0], line=None, placement=(q,), exact_p1=exact_p1), qc))
    plain_rows = run_batch(batch, sim, readout)
    print(f"No correction on all {backend.num_qubits} Fez qubits: {len(plain_rows)} runs done "
          f"({(time.time() - start) / 60:.1f} min)", flush=True)

    todo = [(line, placement) for line in lines(backend, max_lines) for placement in placements(line)]
    per_chunk = max(1, CHUNK // (len(CODES) * len(start_states)))
    total = len(CODES) * len(start_states) * len(todo)
    rows, start = [], time.time()
    for i in range(0, len(todo), per_chunk):
        batch = []
        for line, placement in todo[i:i + per_chunk]:
            for bit, (exact_p1, plain, encoded) in versions.items():
                circuits = placed(CODES, placement, plain, encoded, backend, seed)
                batch += [(test | dict(start=bit, option=name, line=line, placement=placement, exact_p1=exact_p1),
                           circuits[name]) for name in CODES]
        rows += run_batch(batch, sim, readout)
        elapsed = time.time() - start
        left = elapsed / len(rows) * (total - len(rows))
        print(f"Codes: {len(rows)} of {total} runs done ({elapsed / 60:.1f} min, about {left / 60:.1f} min left)",
              flush=True)

    on_qubit = {(r["start"], r["measured_on"]): r["error"] for r in plain_rows}
    for r in rows:
        r["no_correction_error"] = on_qubit[r["start"], r["measured_on"]]
    return plain_rows + rows


# ---- What the runs show ----

def averaged(rows):
    # The runs averaged over the starting states: {(option, placement): error}, with placement (q,) for no correction
    # and (q_0, q_1, q_2) for the codes. Also {(code, placement): no correction's error on the Fez qubit that code was
    # measured on}, and {placement: the Fez qubits the codes were measured on}
    errors, beside, measured = {}, {}, {}
    for r in rows:
        key = (r["option"], r["placement"])
        errors.setdefault(key, []).append(r["error"])
        if r["option"] in CODES:
            beside.setdefault(key, []).append(r["no_correction_error"])
            measured.setdefault(r["placement"], set()).add(r["measured_on"])
    return ({key: float(np.mean(v)) for key, v in errors.items()},
            {key: float(np.mean(v)) for key, v in beside.items()}, measured)


def spread_parts(errors):
    # Splits the spread of errors[t, o, c] (option c on placement o of line t, see summarize), its summed squared
    # distance from its average, into the parts of PARTS: the lines' averages around the overall average, each
    # placement's average around its line's, each option's average around the overall average, and what's left, which
    # is the gaps between the options changing from placement to placement. Every line has the same number of
    # placements and every placement all three options, so the parts don't overlap and add up to the whole spread
    # exactly. Returns each part's share of the whole, {short name: share}
    mean = errors.mean()
    qubits = errors.mean(axis=(1, 2), keepdims=True) - mean
    roles = errors.mean(axis=2, keepdims=True) - mean - qubits
    option = errors.mean(axis=(0, 1), keepdims=True) - mean
    rest = errors - mean - qubits - roles - option
    total = ((errors - mean) ** 2).sum()
    return {key: float((np.broadcast_to(part, errors.shape) ** 2).sum() / total)
            for (key, _), part in zip(PARTS, (qubits, roles, option, rest))}


def mapping_share(shares):
    return sum(shares[key] for key in MAPPING_PARTS)


def summarize(rows, gate_set, num_gates, start_states):
    # Everything the report and the plot show
    average, beside, measured = averaged(rows)
    found = list(dict.fromkeys(r["line"] for r in rows if r["option"] in CODES))
    placed = [(line, p) for line in found for p in placements(line)]
    # errors[t, o, c]: option c's error on placement o of line t, with no correction on the Fez qubit the codes were
    # measured on (the two codes' qubits averaged, should routing ever end them on different qubits)
    errors = np.array([[np.mean([beside[c, p] for c in CODES])] + [average[c, p] for c in CODES]
                       for _, p in placed]).reshape(len(found), -1, len(OPTIONS))
    middle = np.array([p[0] == line[0] for line, p in placed]).reshape(len(found), -1)
    flat = errors.reshape(-1, len(OPTIONS))

    # Each option over all its mappings. No correction's Fez default is the qubit the codes are measured on in the
    # default placement, as in compare_fez.py
    on_default = sorted(measured.get(DEFAULT_DATA_QUBITS, []))
    defaults = {OPTIONS[0]: tuple(on_default[:1]) or None} | {name: DEFAULT_DATA_QUBITS for name in CODES}
    options = {}
    for name in OPTIONS:
        mine = {p: e for (option, p), e in average.items() if option == name}
        on, e = list(mine), np.array(list(mine.values()))
        default = mine.get(defaults[name])
        options[name] = dict(
            errors=e, count=len(e), best=float(e.min()), best_on=on[int(e.argmin())], median=float(np.median(e)),
            worst=float(e.max()), worst_on=on[int(e.argmax())], default=default, default_on=defaults[name],
            default_beats=None if default is None else float((e > default).mean()),
            median_from={bit: float(np.median([r["error"] for r in rows if r["start"] == bit and r["option"] == name]))
                         for bit in start_states})

    lowest = flat.argmin(axis=1)
    gap = flat[:, 2] - flat[:, 1]   # phase-flip minus bit-flip, on the same placement
    return dict(
        gate_set=gate_set, num_gates=num_gates, start_states=start_states, lines=len(found), placements=len(placed),
        placed=placed, measured=[measured[p] for _, p in placed], errors=errors, options=options,
        wins={name: int((lowest == i).sum()) for i, name in enumerate(OPTIONS)},
        beats={name: sum(average[name, p] < beside[name, p] for _, p in placed) for name in CODES},
        gap=dict(median=float(np.median(gap)), low=float(np.percentile(gap, 25)), high=float(np.percentile(gap, 75)),
                 bit_flip_lower=int((gap > 0).sum())),
        switch=float(np.median(flat.max(axis=1) - flat.min(axis=1))),
        rank={(a, b): float(spearmanr(flat[:, i], flat[:, j]).statistic)
              for (i, a), (j, b) in combinations(enumerate(OPTIONS), 2)},
        shares=spread_parts(errors),
        # The same split over only the placements with q_0 in the middle, the ones a person would pick by hand
        middle_shares=spread_parts(errors[middle].reshape(len(found), -1, len(OPTIONS))),
        split=sum(len(qubits) > 1 for qubits in measured.values()),
        detours=sum(r["qubits_used"] > 3 for r in rows if r["option"] in CODES),
    )


# ---- CSV files and the report ----

def line_text(line):
    # A line's qubits in wiring order, end-middle-end
    return f"{line[1]}-{line[0]}-{line[2]}"


def run_row(r):
    # One run as a line of the runs CSV file
    coded = r["option"] in CODES
    return [r["gate_set"], r["num_gates"], r["start"], r["option"], *mapping_cells(r["placement"]),
            line_text(r["line"]) if coded else "", r["placement"][0] == r["line"][0] if coded else "",
            r["measured_on"], r["qubits_used"], r["gates"], r["two_qubit_gates"], r["depth"], round(r["exact_p1"], 6),
            round(r["p_read_1"], 6), round(r["error"], 6), round(r["no_correction_error"], 6) if coded else "",
            r["error"] < r["no_correction_error"] if coded else ""]


def placement_rows(s):
    # One line of the placements CSV file per placement: the three options' errors side by side, averaged over the
    # starting states, and which is lowest
    return [[line_text(line), *p, p[0] == line[0], "/".join(map(str, sorted(qubits))),
             *(round(float(e), 6) for e in errors), OPTIONS[int(errors.argmin())]]
            for (line, p), qubits, errors in zip(s["placed"], s["measured"], s["errors"].reshape(-1, len(OPTIONS)))]


def report(s, plot_path):
    # The results as Markdown: each option over all its mappings, the options head to head on each placement, and
    # where the spread of the errors comes from. plot_path is the plot's path from the report's folder
    n, opts = s["placements"], s["options"]
    out = [f"# Qubit mapping sweep on Fez: {s['gate_set']} gate set, {s['num_gates']} gates", "",
           "From the Fez noise simulator, as the exact chance of reading the wrong answer (no shots). Each error is "
           f"averaged over starting in {states_text(s['start_states'])}.", "",
           f"- **no correction** on each of Fez's {opts[OPTIONS[0]]['count']} qubits",
           f"- **the bit-flip and phase-flip Toffoli codes** on {n} placements: every way of putting q_0, q_1 and q_2 "
           f"on 3 connected Fez qubits ({s['lines']} lines x 6 choices of roles)", "",
           f"![every mapping's logical error]({plot_path})", "",
           "## Each option over all its mappings", ""]
    rows = []
    for name, o in opts.items():
        default = ("not in this run" if o["default"] is None else
                   f"{o['default']:.4f} on {mapping_text(o['default_on'])}, lower than {o['default_beats']:.0%} of "
                   "mappings")
        rows.append([name, o["count"], f"{o['best']:.4f}", f"{o['median']:.4f}", f"{o['worst']:.4f}",
                     mapping_text(o["best_on"]), mapping_text(o["worst_on"]), default])
    out += md_table(["option", "mappings", "best", "median", "worst", "best on", "worst on", "Fez default"], rows,
                    "<>>>><<<")
    out += ["", "Median error over all mappings, by starting state:", ""]
    medians = [[bit] + [f"{opts[name]['median_from'][bit]:.4f}" for name in OPTIONS] for bit in s["start_states"]]
    out += md_table(["starting state"] + [short_name(name) for name in OPTIONS], medians, "<" + ">" * len(OPTIONS))

    g = s["gap"]
    moves = ", ".join(f"{short_name(name)} {o['median'] - o['best']:.4f}" for name, o in opts.items())
    ranks = ", ".join(f"{short_name(a)} vs {short_name(b)} {r:.2f}" for (a, b), r in s["rank"].items())
    out += ["", "## Head to head on the same placement", "",
            "No correction is the run on the Fez qubit each code is measured on, as in compare_fez.py, so all three "
            "are read out by the same qubit.", ""]
    out += md_table(["option", "lowest of the three on", "beats no correction on"],
                    [[name, f"{s['wins'][name]} of {n} placements", f"{s['beats'][name]} of {n}" if name in CODES
                      else "-"] for name in OPTIONS], "<>>")
    out += ["",
            f"- Bit-flip is lower than phase-flip on {g['bit_flip_lower']} of {n} placements. Phase-flip minus "
            f"bit-flip: median {g['median']:+.4f}, middle half {g['low']:+.4f} to {g['high']:+.4f}",
            "- Typical change from switching the option on one placement (the median gap between its best and worst "
            f"option): {s['switch']:.4f}",
            f"- Change from moving each option from its median mapping to its best: {moves}",
            f"- Do the options put the placements in the same order? Rank correlation {ranks} (1 = the same order, "
            "0 = unrelated)"]
    if s["split"]:
        out.append(f"- Note: on {s['split']} placements the two codes ended up measured on different Fez qubits; no "
                   "correction's error there is the average over the two")
    if s["detours"]:
        out.append(f"- Note: {s['detours']} code runs were routed through a 4th Fez qubit (see qubits_used in the "
                   "runs CSV file)")

    mapping, option = mapping_share(s["shares"]), s["shares"]["option"]
    both = [("all placements", s["shares"]), ("q_0 in the middle only", s["middle_shares"])]
    out += ["", "## Which matters more: the mapping or the option", "",
            "The spread of the errors of all three options on every placement (their summed squared distance from "
            "their average), split into 4 parts that add up to it. The second column leaves out the placements that "
            "need SWAPs to encode.", ""]
    rows = [[label] + [f"{shares[key]:.1%}" for _, shares in both] for key, label in PARTS]
    rows.append(["the mapping (the first two together)"] + [f"{mapping_share(shares):.1%}" for _, shares in both])
    out += md_table(["part of the spread"] + [name for name, _ in both], rows, "<>>")
    out += ["", f"**{'The mapping' if mapping > option else 'The option'} matters more here:** the mapping accounts "
                f"for {mapping:.0%} of the spread and the option for {option:.0%}."]
    return "\n".join(out) + "\n"


# ---- The plot ----

def strip_panel(ax, s, limits):
    # Every mapping's error, one row per option and one dot per mapping (a Fez qubit for no correction, a placement for
    # the codes), spread up and down a little so they don't hide each other. Rows wider than the gaps between them mean
    # the mapping matters more than the option. The black tick is each option's median, the ring the Fez default
    rng = np.random.default_rng(0)   # the same spread every run
    for i, name in enumerate(OPTIONS):
        o, y = s["options"][name], len(OPTIONS) - 1 - i   # the first option on top
        ax.scatter(o["errors"], y + rng.uniform(-0.28, 0.28, o["count"]), s=10, color=OPTION_COLORS[name], alpha=0.45,
                   edgecolors="white", linewidths=0.3, zorder=2)
        ax.plot([o["median"]] * 2, [y - 0.36, y + 0.36], color=INK, lw=2, zorder=3)
        ax.annotate(f"median {o['median']:.3f}", (o["median"], y + 0.36), xytext=(0, 2), textcoords="offset points",
                    ha="center", va="bottom", color=INK, fontsize=8)
        if o["default"] is not None:
            ax.scatter([o["default"]], [y], s=80, facecolors="none", edgecolors=INK, linewidths=1.6, zorder=4)
    ax.set_yticks(range(len(OPTIONS)))
    ax.set_yticklabels([f"{name}\n{s['options'][name]['count']} {'Fez qubits' if name == OPTIONS[0] else 'placements'}"
                        for name in OPTIONS][::-1], color=INK)
    ax.set_ylim(-0.6, len(OPTIONS) - 0.4)
    ax.set_xscale("log")
    ax.set_xlim(*limits)
    log_axis(ax.xaxis)
    ax.set_xlabel("logical error", color=MUTED)
    style(ax, grid_axis="x")


def top_matter(fig, title, handles, labels):
    # The figure's title and its legend above the panels. Returns the share of the figure's height they take, for
    # save_plot to keep free. Both are left out of save_plot's layout, which would otherwise leave room for the title a
    # second time
    height = fig.get_figheight()
    below_title = 0.15 + 0.24 * (title.count("\n") + 1)   # inches from the top of the figure to under the title
    title = fig.suptitle(title, color=INK, y=1 - 0.1 / height, va="top")
    legend = fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False, fontsize=9,
                        bbox_to_anchor=(0.5, 1 - below_title / height))
    for item in (title, legend):
        item.set_in_layout(False)
    return (below_title + 0.42) / height


def plot(s, path):
    # Every mapping's error, one row of dots per option (see strip_panel)
    from matplotlib.lines import Line2D
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11, 6.5))
    strip_panel(ax, s, log_limits(np.concatenate([o["errors"] for o in s["options"].values()])))
    handles = [Line2D([], [], ls="", marker="o", ms=7, color=OPTION_COLORS[name]) for name in OPTIONS]
    handles += [Line2D([], [], ls="", marker="|", ms=12, mew=2, color=INK),
                Line2D([], [], ls="", marker="o", ms=9, mfc="none", mec=INK, mew=1.6)]
    labels = list(OPTIONS) + ["median", f"Fez default {DEFAULT_DATA_QUBITS}"]
    title = (f"Fez, {s['gate_set']} gate set, {s['num_gates']} gates: every mapping of no correction and of the "
             f"bit-flip and phase-flip Toffoli codes\n(errors from the Fez noise simulator, averaged over starting in "
             f"{states_text(s['start_states'])})")
    top = top_matter(fig, title, handles, labels)
    save_plot(fig, path, rect=(0, 0, 1, 1 - top))
    plt.close(fig)


def run(gate_set="y", num_gates=500, start_states=(0, 1), seed=3, max_lines=None, csv_dir=CSV_DIR,
        image_dir=IMAGE_DIR, report_dir=REPORT_DIR):
    start_states = check_test(gate_set, start_states)
    backend = FakeFez()
    sim, readout = noise_simulator(backend)
    found = lines(backend, max_lines)
    print(f"{gate_set} gate set, {num_gates} gates, starting in {states_text(start_states)}: no correction on all "
          f"{backend.num_qubits} Fez qubits, and both Toffoli codes on {6 * len(found)} placements ({len(found)} lines "
          f"of 3 connected Fez qubits)\n")

    start = time.time()
    rows = sweep(gate_set, num_gates, seed, start_states, max_lines, backend, sim, readout)
    print(f"All {len(rows)} runs done in {(time.time() - start) / 60:.1f} min\n")
    summary = summarize(rows, gate_set, num_gates, start_states)
    name = sweep_name(gate_set, num_gates)
    image = os.path.join(image_dir, f"{name}.png")
    write_csv(os.path.join(csv_dir, f"{name}.csv"), RUN_COLUMNS, [run_row(r) for r in rows])
    write_csv(os.path.join(csv_dir, f"{name}_placements.csv"), PLACEMENT_COLUMNS, placement_rows(summary))
    save_report(os.path.join(report_dir, f"{name}.md"), report(summary, os.path.relpath(image, report_dir)))
    plot(summary, image)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    GATE_SET = "y"          # the test circuit (a key of compare_fez.py's GATE_SETS): "y" = only Y gates
    NUM_GATES = 500         # gates in the test circuit
    START_STATES = [0, 1]   # the states each run starts in; a mapping's error is the average over them
    SEED = 3                # the transpiler seed, as in compare_fez.py (3 puts the defaults' result on Fez 86, as in
                            # the hardware runs). It only changes the test circuit itself for the random gate sets
    MAX_LINES = None        # None runs every line of 3 qubits (226); a number runs only the first that many, for a
                            # quick trial run before the full one

    run(GATE_SET, NUM_GATES, start_states=START_STATES, seed=SEED, max_lines=MAX_LINES)
