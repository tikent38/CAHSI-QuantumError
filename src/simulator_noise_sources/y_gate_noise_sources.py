# y_gate_noise_sources.py
# Runs NUM_GATES Y gates on every qubit of the Fez noise simulator and splits each qubit's error into its noise
# sources (readout, gate, T1, T2), each run on its own and then all together. Simulator only: every number comes from
# the FakeFez snapshot built into qiskit_ibm_runtime, nothing from a real ibm_fez calibration file
# (src/hardware_vs_simulator compares the simulator with one)
import csv
import math
import os
import random
import sys

from qiskit import transpile
from qiskit.quantum_info import average_gate_fidelity
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (NoiseModel, ReadoutError, amplitude_damping_error, depolarizing_error,
                              phase_damping_error, thermal_relaxation_error)
from qiskit_ibm_runtime.fake_provider import FakeFez

# The circuits and helpers live in src/noisy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
from compare_fez import prob_one, y_circuit

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images", "y_gate_noise_sources")

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

# On Fez a Y gate becomes RZ + X. RZ is done in software (it only changes how later pulses are timed), so it takes
# no time and has no error: X is the only gate in these circuits that picks up noise
NOISY_GATE = "x"
BASIS_GATES = ["cz", "id", "rz", "sx", "x"]


# ---- One noise model per noise source ----
# Each function returns a noise model with only that one source turned on, for every qubit in `qubits`. Running the
# circuit with each one on its own shows how much of a qubit's error comes from each source

def all_sources_noise(backend, qubits):
    # Every source together: Aer's full Fez noise model (readout, depolarizing gate error and T1/T2 relaxation).
    # This is what a Fez noise simulation normally uses
    return NoiseModel.from_backend(backend)


def readout_noise(backend, qubits):
    # Readout error: the measurement reports the wrong bit. It happens once, at the end, so it doesn't grow with the
    # number of gates. Fez lists one error rate per qubit, used for both 0 -> 1 and 1 -> 0
    noise = NoiseModel(basis_gates=BASIS_GATES)
    for q in qubits:
        p = backend.target["measure"][(q,)].error
        noise.add_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]), [q])
    return noise


def gate_noise(backend, qubits):
    # Depolarizing gate error: after each X gate the qubit gets a random X, Y or Z error. Stands in for every gate
    # imperfection that isn't T1/T2. X and Y errors flip the result; Z doesn't
    noise = NoiseModel(basis_gates=BASIS_GATES)
    for q in qubits:
        p = depolarizing_param(backend.target, q)
        if p > 0:
            noise.add_quantum_error(depolarizing_error(p, 1), NOISY_GATE, [q])
    return noise


def t1_noise(backend, qubits):
    # T1 (energy decay): during each X gate the qubit can fall from |1> to |0>. Only matters while the qubit is in |1>
    noise = NoiseModel(basis_gates=BASIS_GATES)
    for q in qubits:
        noise.add_quantum_error(amplitude_damping_error(t1_decay_chance(backend.target, q)), NOISY_GATE, [q])
    return noise


def t2_noise(backend, qubits):
    # T2 (dephasing): during each X gate the qubit loses phase information. Y gates only move the qubit between |0>
    # and |1>, which have no phase to lose, so this should do (almost) nothing here. 
    noise = NoiseModel(basis_gates=BASIS_GATES)
    for q in qubits:
        p = t2_dephasing_param(backend.target, q)
        if p > 0:
            noise.add_quantum_error(phase_damping_error(p), NOISY_GATE, [q])
    return noise


# Every source to run: key used in the CSV, label for printing and plots, and the function that builds its noise model
SOURCES = {
    "all": ("all sources together", all_sources_noise),
    "readout": ("readout", readout_noise),
    "gate": ("gate (depolarizing)", gate_noise),
    "t1": ("T1 (energy decay)", t1_noise),
    "t2": ("T2 (dephasing)", t2_noise),
}


SOURCE_COLORS = {"all": COLORS[0], "readout": COLORS[1], "gate": COLORS[2], "t1": COLORS[4], "t2": COLORS[6]}


BEST_COLOR = COLORS[3]


NUM_BEST = 5   # how many of the lowest-error qubits to highlight in the plots


# ---- Fez's listed numbers for one qubit ----

def gate_time(target, qubit):
    # How long one X gate takes on this qubit, in seconds. T1 and T2 noise grows with the time a gate takes
    return target[NOISY_GATE][(qubit,)].duration


def t1_t2(target, qubit):
    # The qubit's T1 and T2 in seconds.
    props = target.qubit_properties[qubit]
    return props.t1, min(props.t2, 2 * props.t1)


# calculate the chance a qubit decays from excited state to ground state depending on how long it takes to apply a given gate
def t1_decay_chance(target, qubit):
    # Chance the qubit decays from |1> to |0> during one X gate: 1 - e^(-time / T1)
    t1, _ = t1_t2(target, qubit)
    return 1 - math.exp(-gate_time(target, qubit) / t1)


#dephasing caused by enviromental noise and also chance of excited to ground state decay
def pure_dephasing_time(target, qubit):
    t1, t2 = t1_t2(target, qubit)
    rate = 1 / t2 - 1 / (2 * t1)
    return 1 / rate if rate > 0 else None


def t2_dephasing_param(target, qubit):
    # Phase damping parameter for one X gate: the qubit's phase coherence shrinks by e^(-time / T_phi), and phase
    # damping with parameter p shrinks it by sqrt(1 - p), so p = 1 - e^(-2 time / T_phi)
    t_phi = pure_dephasing_time(target, qubit)
    return 0.0 if t_phi is None else 1 - math.exp(-2 * gate_time(target, qubit) / t_phi)


def depolarizing_param(target, qubit):
    # The part of Fez's listed X gate error that T1 and T2 don't explain, as a depolarizing parameter. Fez's listed
    # error is measured on the hardware and includes T1/T2, so Aer only adds depolarizing noise for what is left over.
    # This is the same formula Aer uses (qiskit_aer.noise.device.models._device_depolarizing_error)
    listed = target[NOISY_GATE][(qubit,)].error
    t1, t2 = t1_t2(target, qubit)
    relax_fid = average_gate_fidelity(thermal_relaxation_error(t1, t2, gate_time(target, qubit)))
    if listed <= 1 - relax_fid:
        return 0.0
    dim = 2
    return dim * (listed - (1 - relax_fid)) / (dim * relax_fid - 1)


def qubit_properties(target, qubit):
    # Everything listed for the qubit, plus how strong each noise source is per X gate
    t1, t2 = t1_t2(target, qubit)
    return dict(readout_error=target["measure"][(qubit,)].error, x_gate_error=target[NOISY_GATE][(qubit,)].error,
                x_gate_time_ns=gate_time(target, qubit) * 1e9, t1_us=t1 * 1e6, t2_us=t2 * 1e6,
                t1_decay_per_gate=t1_decay_chance(target, qubit), t2_dephasing_per_gate=t2_dephasing_param(target, qubit),
                depolarizing_per_gate=depolarizing_param(target, qubit))


# ---- Other helpers ----

def best_qubits(rows):
    # The NUM_BEST qubits with the least error, all sources together. The same qubits are highlighted in every plot
    return {row["qubit"] for row in sorted(rows, key=lambda row: row["error"]["all"])[:NUM_BEST]}


def shot_noise(p1, shots):
    # Not a noise source on the qubit: P(1) is estimated from a limited number of shots, so it is only known to
    # within about this much (one standard error). Differences between qubits smaller than this are just luck
    return math.sqrt(p1 * (1 - p1) / shots)


# ---- CSV files, plots, and printing ----

def write_results_csv(rows, num_gates, start_bit, shots, ideal_p1, path):
    # One row per qubit: P(1), error and shot noise for every noise source
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["qubit", "y_gates", "start_bit", "shots", "no_noise_p1"]
                        + [f"{field}_{key}" for key in SOURCES for field in ("p1", "error", "shot_noise")])
        for row in rows:
            writer.writerow([row["qubit"], num_gates, start_bit, shots, round(ideal_p1, 6)]
                            + [round(row[field][key], 6) for key in SOURCES for field in ("p1", "error", "shot")])
    print(f"\nWrote results to {path}")


def write_properties_csv(rows, path):
    # One row per qubit: Fez's listed numbers and how strong each noise source is per X gate
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = list(rows[0]["props"])
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["qubit"] + fields)
        for row in rows:
            writer.writerow([row["qubit"]] + [row["props"][field] for field in fields])
    print(f"Wrote qubit properties to {path}")


def style(ax, muted="#52514e", grid="#e4e3df"):
    ax.grid(color=grid, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=muted)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, path):
    fig.tight_layout()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"Saved plot to {path}")


def plot(rows, num_gates, start_bit, shots, path):
    # Top: each qubit's error from the no-noise result, all sources together. Bottom: Fez's listed noise for each qubit
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ink, muted = "#0b0b0b", "#52514e"
    qubits = [row["qubit"] for row in rows]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(16, 8), sharex=True, gridspec_kw=dict(height_ratios=[3, 2]))

    errors = [row["error"]["all"] for row in rows]
    best = best_qubits(rows)
    top.bar(qubits, errors, width=0.8, color=[BEST_COLOR if q in best else SOURCE_COLORS["all"] for q in qubits])
    top.errorbar(qubits, errors, yerr=[row["shot"]["all"] for row in rows], fmt="none", ecolor=ink, elinewidth=0.6,
                 label="± shot noise (1 standard error)")
    for row in (row for row in rows if row["qubit"] in best):
        top.annotate(str(row["qubit"]), (row["qubit"], row["error"]["all"]), xytext=(0, 3), textcoords="offset points",
                     color=ink, fontsize=8, ha="center", va="bottom")
    mean = sum(errors) / len(errors)
    top.axhline(mean, color=muted, ls="--", lw=1, label=f"mean over all qubits ({mean:.4f})")
    # Add a legend entry for the 5 lowest-error qubits' bars
    handles, _ = top.get_legend_handles_labels()
    handles.append(Patch(color=BEST_COLOR, label=f"{NUM_BEST} qubits with the least error"))
    top.legend(handles=handles, frameon=False, fontsize=9, loc="upper left")
    # Name the worst few qubits so they are easy to find
    for row in sorted(rows, key=lambda row: row["error"]["all"])[-5:]:
        top.annotate(str(row["qubit"]), (row["qubit"], row["error"]["all"]), xytext=(0, 3), textcoords="offset points",
                     color=ink, fontsize=8, ha="center", va="bottom")
    top.set_title(f"{num_gates} Y gates starting in |{start_bit}> on every Fez qubit (Fez noise simulator, "
                  f"{shots} shots each)", color=ink)
    top.set_ylabel("error from no-noise result\n|P(1) - P(1) with no noise|", color=muted)

    bottom.plot(qubits, [row["props"]["readout_error"] for row in rows], "-o", color=SOURCE_COLORS["readout"], lw=1.5,
                ms=4, markeredgecolor="white", markeredgewidth=0.8, label="readout error")
    bottom.plot(qubits, [row["props"]["x_gate_error"] for row in rows], "-o", color=SOURCE_COLORS["gate"], lw=1.5,
                ms=4, markeredgecolor="white", markeredgewidth=0.8, label="X gate error (per gate, includes T1/T2)")
    # Mark the lowest-error qubits on both lines
    best_rows = [row for row in rows if row["qubit"] in best]
    for i, field in enumerate(("readout_error", "x_gate_error")):
        bottom.plot([row["qubit"] for row in best_rows], [row["props"][field] for row in best_rows], "o",
                    color=BEST_COLOR, ms=7, markeredgecolor=ink, markeredgewidth=0.8, zorder=3,
                    label=f"{NUM_BEST} qubits with the least error" if i == 0 else None)
    bottom.set_yscale("log")
    bottom.set_ylabel("Fez's listed noise", color=muted)
    bottom.set_xlabel("Fez qubit", color=muted)
    bottom.legend(frameon=False, fontsize=9, loc="upper left", ncol=3)

    for ax in (top, bottom):
        style(ax)
    bottom.set_xticks(range(0, max(qubits) + 1, 10))
    bottom.set_xlim(min(qubits) - 1, max(qubits) + 1)
    save(fig, path)


def plot_sources(rows, num_gates, start_bit, shots, path):
    # One panel per noise source: each qubit's error with only that source turned on (the top panel has them all).
    # Each panel has its own y scale, so small sources are still readable: compare them using the means in the titles.
    # The qubits with the least error (all sources together) are highlighted in every panel
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ink, muted = "#0b0b0b", "#52514e"
    qubits = [row["qubit"] for row in rows]
    best = best_qubits(rows)

    fig, axes = plt.subplots(len(SOURCES), 1, figsize=(16, 3 * len(SOURCES)), sharex=True)
    for ax, (key, (label, _)) in zip(axes, SOURCES.items()):
        errors = [row["error"][key] for row in rows]
        mean = sum(errors) / len(errors)
        ax.bar(qubits, errors, width=0.8, color=[BEST_COLOR if q in best else SOURCE_COLORS[key] for q in qubits])
        ax.errorbar(qubits, errors, yerr=[row["shot"][key] for row in rows], fmt="none", ecolor=ink, elinewidth=0.6)
        for row in (row for row in rows if row["qubit"] in best):
            ax.annotate(str(row["qubit"]), (row["qubit"], row["error"][key] + row["shot"][key]), xytext=(0, 2),
                        textcoords="offset points", color=ink, fontsize=8, ha="center", va="bottom")
        ax.axhline(mean, color=muted, ls="--", lw=1)
        ax.set_title(f"{label}: mean error {mean:.4f}", color=ink, fontsize=10, loc="left")
        ax.set_ylabel("error", color=muted)
        ax.set_ylim(bottom=0)
        style(ax)
    axes[0].legend(handles=[Patch(color=BEST_COLOR, label=f"{NUM_BEST} qubits with the least error, all sources together")],
                   frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(f"{num_gates} Y gates starting in |{start_bit}>: error from each noise source on its own "
                 f"({shots} shots each, black lines = ± shot noise, each panel has its own y scale)", color=ink)
    axes[-1].set_xlabel("Fez qubit", color=muted)
    axes[-1].set_xticks(range(0, max(qubits) + 1, 10))
    axes[-1].set_xlim(min(qubits) - 1, max(qubits) + 1)
    save(fig, path)


def plot_coherence(rows, path):
    # Fez's listed T1 and T2 for every qubit. Longer is better: the qubit holds its state for longer
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted = "#0b0b0b", "#52514e"
    qubits = [row["qubit"] for row in rows]

    fig, ax = plt.subplots(figsize=(16, 4.5))
    for key, field, label in (("t1", "t1_us", "T1 (energy decay time)"), ("t2", "t2_us", "T2 (dephasing time)")):
        ax.plot(qubits, [row["props"][field] for row in rows], "-o", color=SOURCE_COLORS[key], lw=1.5, ms=4,
                markeredgecolor="white", markeredgewidth=0.8, label=label)
    ax.set_title("Fez's listed T1 and T2 for every qubit (longer is better)", color=ink)
    ax.set_ylabel("time (µs)", color=muted)
    ax.set_xlabel("Fez qubit", color=muted)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    style(ax)
    ax.set_xticks(range(0, max(qubits) + 1, 10))
    ax.set_xlim(min(qubits) - 1, max(qubits) + 1)
    save(fig, path)


def run(num_gates, shots=1000, seed=3, start_bit=0, qubits=None, csv_file=None, properties_csv_file=None,
        plot_file=None, sources_plot_file=None, coherence_plot_file=None):
    backend = FakeFez()
    ideal_sim = AerSimulator()   # no noise at all: gives what would be measured without noise
    if qubits is None:
        qubits = list(range(backend.num_qubits))
    rng = random.Random(seed)

    # Prepare |start_bit>, then num_gates Y gates, then measure
    qc = y_circuit(start_bit, num_gates)
    qc.measure_all()

    # The same circuit placed on each Fez qubit in turn. optimization_level=0 keeps every Y gate: otherwise the
    # transpiler would cancel them in pairs
    fez_circuits = [transpile(qc, backend, initial_layout=[q], optimization_level=0, seed_transpiler=seed)
                    for q in qubits]

    ideal_p1 = prob_one(ideal_sim.run(qc, shots=shots, seed_simulator=seed).result().get_counts())[0] / shots

    print(f"{num_gates} Y gates starting in |{start_bit}>, on {len(qubits)} Fez qubits, {shots} shots each")
    print(f"Fez gates per qubit: {dict(fez_circuits[0].count_ops())}")
    print(f"No noise:   P(1) = {ideal_p1:.4f}")
    print("Each noise source is run on its own, then all together. error = |P(1) - P(1) with no noise|\n")

    rows = [dict(qubit=q, p1={}, error={}, shot={}, props=qubit_properties(backend.target, q)) for q in qubits]
    for key, (label, build_noise) in SOURCES.items():
        sim = AerSimulator(noise_model=build_noise(backend, qubits))
        counts = sim.run(fez_circuits, shots=shots, seed_simulator=rng.randrange(2**31)).result().get_counts()
        for row, c in zip(rows, counts):
            p1 = prob_one(c)[0] / shots
            row["p1"][key], row["error"][key], row["shot"][key] = p1, abs(p1 - ideal_p1), shot_noise(p1, shots)

    width = 22
    print(f"{'qubit':>6}" + "".join(f"{label:>{width}}" for label, _ in SOURCES.values()) + f"{'shot noise (all)':>18}")
    print("-" * (6 + width * len(SOURCES) + 18))
    for row in rows:
        print(f"{row['qubit']:>6}" + "".join(f"{row['error'][key]:>{width}.4f}" for key in SOURCES)
              + f"{'±' + format(row['shot']['all'], '.4f'):>18}")

    print("\nMean error over all qubits:")
    for key, (label, _) in SOURCES.items():
        print(f"  {label:<22}{sum(row['error'][key] for row in rows) / len(rows):.4f}")
    print(f"  {'shot noise (all)':<22}±{sum(row['shot']['all'] for row in rows) / len(rows):.4f}")

    ranked = sorted(rows, key=lambda row: row["error"]["all"])
    print(f"\n5 qubits with the least error, |P(1) - P(1) with no noise|, all sources together "
          f"(no noise P(1) = {ideal_p1:.4f}):")
    print(f"{'rank':>6}{'qubit':>7}" + "".join(f"{label:>{width}}" for label, _ in SOURCES.values()))
    for rank, row in enumerate(ranked[:5], 1):
        print(f"{rank:>6}{row['qubit']:>7}" + "".join(f"{row['error'][key]:>{width}.4f}" for key in SOURCES))
    print("\nWorst qubits: " + ", ".join(f"{row['qubit']} ({row['error']['all']:.4f})" for row in ranked[::-1][:5]))

    if csv_file:
        write_results_csv(rows, num_gates, start_bit, shots, ideal_p1, csv_file)
    if properties_csv_file:
        write_properties_csv(rows, properties_csv_file)
    if plot_file:
        plot(rows, num_gates, start_bit, shots, plot_file)
    if sources_plot_file:
        plot_sources(rows, num_gates, start_bit, shots, sources_plot_file)
    if coherence_plot_file:
        plot_coherence(rows, coherence_plot_file)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 1000     # how many Y gates in a row on each qubit
    SHOTS = 1000         # how many times the circuit is run on each qubit, for every noise source
    SEED = 3             # sets the simulator's randomness (same SEED = same results)
    START_BIT = 0        # start each qubit in |0> or |1>
    QUBITS = None        # list of Fez qubits to test, e.g. [0, 1, 2]; None tests all 156
    # Output files; None skips any of them
    NAME = f"y_gate_noise_sources_{NUM_GATES}"
    CSV_FILE = os.path.join(CSV_DIR, f"{NAME}.csv")                        # error from every source, per qubit
    PROPERTIES_CSV_FILE = os.path.join(CSV_DIR, f"{NAME}_properties.csv")  # Fez's listed numbers, per qubit
    PLOT_FILE = os.path.join(IMAGE_DIR, f"{NAME}.png")                     # all sources together + listed noise
    SOURCES_PLOT_FILE = os.path.join(IMAGE_DIR, f"{NAME}_sources.png")     # one panel per noise source
    COHERENCE_PLOT_FILE = os.path.join(IMAGE_DIR, f"{NAME}_coherence.png") # T1 and T2 per qubit

    run(NUM_GATES, shots=SHOTS, seed=SEED, start_bit=START_BIT, qubits=QUBITS, csv_file=CSV_FILE,
        properties_csv_file=PROPERTIES_CSV_FILE, plot_file=PLOT_FILE, sources_plot_file=SOURCES_PLOT_FILE,
        coherence_plot_file=COHERENCE_PLOT_FILE)
