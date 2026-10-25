# model_check.py
# Every number the Fez simulator's noise is built from (T1, T2, readout and gate errors, CZ errors), next to the same
# number from a real ibm_fez calibration file, for every qubit. Writes CSV files, a plot with the qubits that are far
# off labelled, and good_qubits.md: the qubits where the simulator matches the real machine
import math
import os
import statistics
import textwrap

from qiskit_aer.noise.device import basic_device_readout_errors
from qiskit_ibm_runtime.fake_provider import FakeFez

from noise_common import (COLORS, CSV_DIR, FAIL_COLOR, IMAGE_DIR, load_calibration, ratio, save, style,
                          write_rows)

# Output folder for good_qubits.md, next to this file
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

PASS_COLOR = COLORS[0]   # points within DIFFERENCE_FACTOR

# The simulator and the real machine "differ" on a number if one is more than this many times the other
DIFFERENCE_FACTOR = 2

# Numbers compared, and the label printed for each
MODEL_QUANTITIES = {
    "t1_us": "T1 (µs)",
    "t2_us": "T2 (µs)",
    "p1_given_0": "readout P(1 | prepared 0)",
    "p0_given_1": "readout P(0 | prepared 1)",
    "readout_error": "readout error (average)",
    "sx_error": "sx gate error",
    "x_error": "X gate error",
    "gate_length_ns": "single-qubit gate length (ns)",
    "readout_length_ns": "readout length (ns)",
}

MODEL_PLOT_PANELS = ["p1_given_0", "p0_given_1", "t1_us", "t2_us", "sx_error"]   # the numbers in the plot

# The six areas of the plot, and the label used for each in the good qubit lists
AREAS = {"p1_given_0": "readout P(1|0)", "p0_given_1": "readout P(0|1)", "t1_us": "T1", "t2_us": "T2",
         "sx_error": "sx error", "cz": "CZ"}
FIVE_AREAS = ["p1_given_0", "p0_given_1", "t1_us", "sx_error", "cz"]   # every area except T2


# ---- The six plots ----
# Each plot is real calibration (y) vs the simulator (x). Points more than DIFFERENCE_FACTOR apart are red diamonds,
# and the label_limit furthest off are labelled

def plot_p1_given_0(ax, qubits, model, label_limit):
    scatter_panel(ax, MODEL_QUANTITIES["p1_given_0"], "simulator", "real ibm_fez",
                  qubit_series(qubits, model, "p1_given_0"), band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_p0_given_1(ax, qubits, model, label_limit):
    scatter_panel(ax, MODEL_QUANTITIES["p0_given_1"], "simulator", "real ibm_fez",
                  qubit_series(qubits, model, "p0_given_1"), band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_t1(ax, qubits, model, label_limit):
    scatter_panel(ax, MODEL_QUANTITIES["t1_us"], "simulator (µs)", "real ibm_fez (µs)",
                  qubit_series(qubits, model, "t1_us"), band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_t2(ax, qubits, model, label_limit):
    scatter_panel(ax, MODEL_QUANTITIES["t2_us"], "simulator (µs)", "real ibm_fez (µs)",
                  qubit_series(qubits, model, "t2_us"), band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_sx_error(ax, qubits, model, label_limit):
    scatter_panel(ax, MODEL_QUANTITIES["sx_error"], "simulator", "real ibm_fez",
                  qubit_series(qubits, model, "sx_error"), band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_cz(ax, cz, label_limit):
    # One point per CZ connection on both sides, labelled with the pair
    connections = [row for row in cz if row["status"] == "both"]
    scatter_panel(ax, "CZ error (per connection)", "simulator", "real ibm_fez",
                  split_series(connections, lambda row: row["sim"], lambda row: row["real"],
                               lambda row: f"{row['pair'][0]}–{row['pair'][1]}"),
                  band=DIFFERENCE_FACTOR, label_limit=label_limit)


def plot_model_check(qubits, model, cz, path, label_limit=8):
    # All six plots in one image, in a 2 x 3 grid
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(18, 11.6))
    plot_p1_given_0(axes[0][0], qubits, model, label_limit)
    plot_p0_given_1(axes[0][1], qubits, model, label_limit)
    plot_t1(axes[0][2], qubits, model, label_limit)
    plot_t2(axes[1][0], qubits, model, label_limit)
    plot_sx_error(axes[1][1], qubits, model, label_limit)
    plot_cz(axes[1][2], cz, label_limit)
    fig.suptitle(f"Model check: Fez simulator (FakeFez) vs real ibm_fez calibration "
                 f"(the {label_limit} furthest off in each plot are labelled)", color="#0b0b0b")
    save(fig, path)


# ---- Helpers: drawing a plot ----

def scatter_panel(ax, title, xlabel, ylabel, series, band=None, label_limit=8):
    # One log-log scatter plot on ax, with a dashed y = x line: points on the line agree.
    # series: list of (label, color, xs, ys, y errors or None, qubits or None).
    # band: also draw dotted lines at y = band * x and y = x / band. Series given qubits get the label_limit points
    # furthest from y = x labelled with their qubit number
    from matplotlib.ticker import NullFormatter

    ink, muted = "#0b0b0b", "#52514e"
    values = []
    for label, color, xs, ys, yerr, *names in series:
        if not xs:
            continue
        # Points that are far off are bigger diamonds, so they stand out by shape as well as color
        marker, size = ("D", 7) if color == FAIL_COLOR else ("o", 5)
        ax.errorbar(xs, ys, yerr=yerr, fmt=marker, color=color, ms=size, mec="white", mew=0.8, elinewidth=0.8,
                    label=f"{label} ({len(xs)})", zorder=3 if color == FAIL_COLOR else 2)
        values += [v for v in xs + ys if v > 0]
        if names and names[0]:
            points = sorted(zip(names[0], xs, ys), key=lambda p: -abs(math.log(p[2] / p[1])))
            for q, x, y in points[:label_limit]:
                ax.annotate(str(q), (x, y), xytext=(5, 2), textcoords="offset points", color=ink, fontsize=7)
    low, high = min(values) / 1.3, max(values) * 1.3
    ax.plot([low, high], [low, high], "--", color=muted, lw=1, label="y = x")
    if band:
        ax.plot([low, high], [low * band, high * band], ":", color=muted, lw=1, label=f"{band}x off")
        ax.plot([low, high], [low / band, high / band], ":", color=muted, lw=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    # Only label the powers of 10: the in-between labels overlap on short axes
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_title(title, color=ink, fontsize=10)
    ax.set_xlabel(xlabel, color=muted)
    ax.set_ylabel(ylabel, color=muted)
    # Legend below the plot, so it never covers points
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    style(ax)


def split_series(items, sim, real, name):
    # Plot series for scatter_panel: the items within DIFFERENCE_FACTOR, then the ones further off (labelled with
    # name). sim, real and name read one item's simulator value, real value and label
    items = [i for i in items if real(i) and sim(i)]
    out = []
    for off in (False, True):
        group = [i for i in items if differs(real(i) / sim(i)) == off]
        out.append((f"more than {DIFFERENCE_FACTOR}x off" if off else f"within {DIFFERENCE_FACTOR}x",
                    FAIL_COLOR if off else PASS_COLOR, [sim(i) for i in group], [real(i) for i in group], None,
                    [name(i) for i in group] if off else None))
    return out


def qubit_series(qubits, model, key):
    # split_series for one per-qubit number, labelled with the qubit
    return split_series(qubits, lambda q: model[q][key][0], lambda q: model[q][key][1], str)


# ---- Helpers: the simulator's numbers ----

def simulator_model(backend, qubits):
    # The numbers FakeFez lists for each qubit, which the simulator builds its noise from
    target = backend.target
    readout = {q[0]: error.probabilities for q, error in basic_device_readout_errors(target=target)}
    return {q: dict(t1_us=target.qubit_properties[q].t1 * 1e6, t2_us=target.qubit_properties[q].t2 * 1e6,
                    p1_given_0=readout[q][0][1], p0_given_1=readout[q][1][0],
                    readout_error=target["measure"][(q,)].error, sx_error=target["sx"][(q,)].error,
                    x_error=target["x"][(q,)].error, gate_length_ns=target["sx"][(q,)].duration * 1e9,
                    readout_length_ns=target["measure"][(q,)].duration * 1e9)
            for q in qubits}


def simulator_cz(backend):
    # CZ error for every connected pair of qubits, keyed (smaller qubit, larger qubit). Fez lists both directions
    # with the same error, so one is kept
    return {tuple(sorted(pair)): props.error for pair, props in backend.target["cz"].items()}


# ---- Helpers: comparing ----

def differs(r):
    # True if real / simulator is more than DIFFERENCE_FACTOR either way
    return r is not None and (r > DIFFERENCE_FACTOR or r < 1 / DIFFERENCE_FACTOR)


def compare_models(sim, real, qubits):
    # For every qubit and number: (simulator, real, real / simulator)
    return {q: {key: (sim[q][key], real.get(q, {}).get(key), ratio(real.get(q, {}).get(key), sim[q][key]))
                for key in MODEL_QUANTITIES} for q in qubits}


def compare_cz(sim_cz, real_cz, qubits):
    # Every CZ connection between the qubits checked, on either side. A simulator error of 0.5 or more means the
    # connection is broken in the simulator (FakeFez lists broken ones with an error of 1.0); a connection missing
    # from the calibration file isn't available on the real machine today
    rows = []
    for pair in sorted(set(sim_cz) | set(real_cz)):
        if pair[0] not in qubits or pair[1] not in qubits:
            continue
        s, r = sim_cz.get(pair), real_cz.get(pair)
        if s is not None and s >= 0.5:
            status = "broken in simulator" + ("" if r is None else ", works on real machine")
        elif s is None:
            status = "only on real machine"
        elif r is None:
            status = "missing on real machine"
        else:
            status = "both"
        rows.append(dict(pair=pair, sim=s, real=r, ratio=ratio(r, s) if status == "both" else None, status=status))
    return rows


def biggest_differences(qubits, model, key, limit=None):
    # The qubits whose real value is more than DIFFERENCE_FACTOR from the simulator's, furthest first, as
    # (qubit, simulator, real, real / simulator). limit=None keeps all of them
    rows = [(q, *model[q][key]) for q in qubits if differs(model[q][key][2])]
    return sorted(rows, key=lambda row: -abs(math.log(row[3])))[:limit]


def far_off_list(rows):
    # "103 (146x), 141 (43x), ..." from biggest_differences rows
    return ", ".join(f"{q} ({rat:.2g}x)" for q, _, _, rat in rows)


def far_off_cz(cz):
    # CZ connections on both sides that are more than DIFFERENCE_FACTOR apart, furthest first
    return sorted((row for row in cz if row["status"] == "both" and differs(row["ratio"])),
                  key=lambda row: -abs(math.log(row["ratio"])))


def cz_off_list(rows):
    return ", ".join(f"{row['pair'][0]}–{row['pair'][1]} ({row['ratio']:.2g}x)" for row in rows)


def area_matches(qubits, model, cz, real):
    # For every qubit: which areas the simulator matches the real machine in (within DIFFERENCE_FACTOR). CZ matches if
    # every CZ connection the qubit has on both sides does. A missing number, or no CZ connection to compare, counts
    # as not matching. Qubits IBM marks as not operational are left out completely
    connections = {}
    for row in cz:
        if row["status"] == "both":
            for q in row["pair"]:
                connections.setdefault(q, []).append(row)
    matches = {}
    for q in qubits:
        if real.get(q, {}).get("operational") is False:
            continue
        matches[q] = {key: model[q][key][2] is not None and not differs(model[q][key][2]) for key in MODEL_PLOT_PANELS}
        matches[q]["cz"] = bool(connections.get(q)) and not any(differs(row["ratio"]) for row in connections[q])
    return matches


def good_qubit_lists(matches):
    # The three lists in the good qubit file: all six areas match; all five areas except T2 match; and exactly four
    # of those five match, with the one that doesn't
    all_six = [q for q, m in matches.items() if all(m.values())]
    all_five = [q for q, m in matches.items() if all(m[key] for key in FIVE_AREAS)]
    four_of_five = [(q, next(key for key in FIVE_AREAS if not m[key])) for q, m in matches.items()
                    if sum(m[key] for key in FIVE_AREAS) == len(FIVE_AREAS) - 1]
    return all_six, all_five, four_of_five


# ---- Helpers: output files ----

def write_model_csv(qubits, model, real, path):
    # One row per qubit: for every number, the simulator's value, the real value, real / simulator, and whether
    # they differ by more than DIFFERENCE_FACTOR
    header = ["qubit", "operational_on_real_machine", "real_init_error"]
    header += [f"{key}_{field}" for key in MODEL_QUANTITIES for field in ("simulator", "real", "real_over_sim",
                                                                          "differs")]
    rows = []
    for q in qubits:
        row = [q, real.get(q, {}).get("operational"), real.get(q, {}).get("init_error")]
        for key in MODEL_QUANTITIES:
            s, r, rat = model[q][key]
            row += [s, r, rat, differs(rat)]
        rows.append(row)
    write_rows(path, header, rows)


def write_cz_csv(cz, path):
    write_rows(path, ["qubit_a", "qubit_b", "simulator_cz_error", "real_cz_error", "real_over_sim", "differs",
                      "status"],
               [[row["pair"][0], row["pair"][1], row["sim"], row["real"], row["ratio"], differs(row["ratio"]),
                 row["status"]] for row in cz])


def md(text):
    # Text for the good qubits Markdown file: | would otherwise be read as a table
    return text.replace("|", "\\|")


def write_good_qubits(path, lists, qubits, sim_date, calibration_file):
    # The good qubit lists, rewritten every run
    all_six, all_five, four_of_five = lists
    five_names = ", ".join(md(AREAS[key]) for key in FIVE_AREAS)
    lines = ["# Qubits where the simulator matches the real ibm_fez", "",
             f"- Simulator: FakeFez, calibrated {sim_date}",
             f"- Real machine: `{os.path.basename(calibration_file)}`",
             f"- \"Matches\" means within {DIFFERENCE_FACTOR}x. CZ matches if every CZ connection the qubit has does",
             f"- {len(qubits)} qubits checked", "",
             f"## All six areas ({len(all_six)} qubits)", "",
             f"{', '.join(md(AREAS[key]) for key in AREAS)}", ""]
    lines += [f"- {q}" for q in all_six] or ["- none"]
    lines += ["", f"## All five areas except T2 ({len(all_five)} qubits)", "", five_names, ""]
    lines += [f"- {q}" for q in all_five] or ["- none"]
    lines += ["", f"## Four of those five ({len(four_of_five)} qubits)", "",
              "Matches in every area but the one shown. Qubits matching all five are in the list above", ""]
    lines += [f"- {q} (off: {md(AREAS[key])})" for q, key in four_of_five] or ["- none"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote good qubit lists to {path}")


# ---- Printing ----

def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, digits=4):
    # A number for printing: None becomes "—", everything else 4 significant figures
    return "—" if value is None else f"{value:.{digits}g}"


def run(qubits=None, calibration_file=None, model_csv_file=None, cz_csv_file=None, good_qubits_file=None,
        plot_file=None):
    backend = FakeFez()
    if qubits is None:
        qubits = list(range(backend.num_qubits))
    sim_date = backend.properties().last_update_date
    real, real_cz = load_calibration(calibration_file, qubits)
    model = compare_models(simulator_model(backend, qubits), real, qubits)
    cz = compare_cz(simulator_cz(backend), real_cz, qubits)

    print(f"Simulator: FakeFez, calibrated {sim_date}")
    print(f"Real:      {os.path.basename(calibration_file)}\n")
    print(f"Simulator model vs real calibration (differs = more than {DIFFERENCE_FACTOR}x apart)")
    print(f"  {'number':<32}{'median sim':>12}{'median real':>13}{'median real/sim':>17}{'differs':>9}")
    for key, label in MODEL_QUANTITIES.items():
        ratios = [model[q][key][2] for q in qubits]
        print(f"  {label:<32}{fmt(median(model[q][key][0] for q in qubits)):>12}"
              f"{fmt(median(model[q][key][1] for q in qubits)):>13}{fmt(median(ratios), 3):>17}"
              f"{sum(differs(r) for r in ratios):>9}")
    both = [row for row in cz if row["status"] == "both"]
    print(f"  {'CZ error (per connection)':<32}{fmt(median(row['sim'] for row in both)):>12}"
          f"{fmt(median(row['real'] for row in both)):>13}{fmt(median(row['ratio'] for row in both), 3):>17}"
          f"{sum(differs(row['ratio']) for row in both):>9}")
    print(f"\n  Qubits more than {DIFFERENCE_FACTOR}x off in the plot, furthest first (real / sim):")
    for key in MODEL_PLOT_PANELS:
        rows = biggest_differences(qubits, model, key)
        print(textwrap.fill(f"{MODEL_QUANTITIES[key]} ({len(rows)}): {far_off_list(rows) or 'none'}", width=118,
                            initial_indent="  - ", subsequent_indent="      "))
    cz_off = far_off_cz(cz)
    print(textwrap.fill(f"CZ error ({len(cz_off)} connections): {cz_off_list(cz_off) or 'none'}", width=118,
                        initial_indent="  - ", subsequent_indent="      "))
    good_lists = good_qubit_lists(area_matches(qubits, model, cz, real))
    all_six, all_five, four_of_five = good_lists
    print()
    for title, text in ((f"Within {DIFFERENCE_FACTOR}x in all six areas ({len(all_six)} qubits)",
                         ", ".join(map(str, all_six))),
                        (f"Within {DIFFERENCE_FACTOR}x in all five areas except T2 ({len(all_five)} qubits)",
                         ", ".join(map(str, all_five))),
                        (f"Within {DIFFERENCE_FACTOR}x in four of those five ({len(four_of_five)} qubits, area off "
                         f"in brackets)", ", ".join(f"{q} ({AREAS[key]})" for q, key in four_of_five))):
        print(textwrap.fill(f"{title}: {text or 'none'}", width=118, initial_indent="  ", subsequent_indent="    "))
    print()

    if model_csv_file:
        write_model_csv(qubits, model, real, model_csv_file)
    if cz_csv_file:
        write_cz_csv(cz, cz_csv_file)
    if plot_file:
        plot_model_check(qubits, model, cz, plot_file)
    if good_qubits_file:
        write_good_qubits(good_qubits_file, good_lists, qubits, sim_date, calibration_file)


if __name__ == "__main__":
    # ---- Settings: change these to run a different comparison ----
    QUBITS = None              # list of Fez qubits to check, e.g. [0, 1, 2]; None checks all 156
    # Real calibration file downloaded from IBM Quantum
    CALIBRATION_FILE = os.path.join(CSV_DIR, "ibm_fez_calibrations_2026-10-24T18_48_15Z.csv")
    # Output files; None skips any of them
    MODEL_CSV_FILE = os.path.join(CSV_DIR, "model_check.csv")          # simulator vs real, per qubit
    CZ_CSV_FILE = os.path.join(CSV_DIR, "model_check_cz.csv")          # simulator vs real, per CZ connection
    GOOD_QUBITS_FILE = os.path.join(REPORT_DIR, "good_qubits.md")      # qubits where the simulator matches
    PLOT_FILE = os.path.join(IMAGE_DIR, "model_check.png")

    run(qubits=QUBITS, calibration_file=CALIBRATION_FILE, model_csv_file=MODEL_CSV_FILE, cz_csv_file=CZ_CSV_FILE,
        good_qubits_file=GOOD_QUBITS_FILE, plot_file=PLOT_FILE)
