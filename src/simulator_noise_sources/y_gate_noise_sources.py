# y_gate_noise_sources.py
# Runs NUM_GATES Y gates on every qubit of the Fez noise simulator and splits each qubit's error into its noise
# sources (readout, gate, T1, T2), each run on its own and then all together.
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

# The circuits and helpers live in src/noisy, and the code for printing, CSV files and plots in src/output_tools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "noisy"))
sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
from fez_common import prob_one, y_circuit
from output_tools import (COLORS, INK, MUTED, label_above, print_table_header, pyplot, qubit_axis, save_plot, style,
                          write_csv)

# Output folders next to this file, so the results land in the same place from any working directory
CSV_DIR = os.path.join(HERE, "csvs")
IMAGE_DIR = os.path.join(HERE, "images", "y_gate_noise_sources")

# On Fez a Y gate becomes RZ + X. RZ is done in software (it only changes how later pulses are timed), so it takes
# no time and has no error: X is the only gate in these circuits that picks up noise
NOISY_GATE = "x"
BASIS_GATES = ["cz", "id", "rz", "sx", "x"]


# ---- One noise model per noise source ----
# Each function returns a noise model with only that one source turned on, for every qubit in `qubits`. Running the
# circuit with each one on its own shows how much of a qubit's error comes from each source. They all take
# (backend, qubits), so SOURCES can call any of them the same way

def all_sources_noise(backend, qubits):
    # Every source together: Aer's full Fez noise model (readout, depolarizing gate error and T1/T2 relaxation), which
    # is what a Fez noise simulation normally uses. It covers every qubit, so qubits isn't needed here
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
    # and |1>, which have no phase to lose, so this should do (almost) nothing here
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
BEST_COLOR = COLORS[3]   # the qubits with the least error
NUM_BEST = 5             # how many of the lowest-error qubits to list and highlight in the plots


# ---- Running the circuits ----

def measure_errors(backend, qubits, fez_circuits, ideal_p1, shots, seed):
    # Runs the circuits once per noise source, with only that source turned on. Returns one row per qubit: P(1),
    # error from the no-noise result and shot noise for every source, and the qubit's listed numbers
    rng = random.Random(seed)
    rows = [dict(qubit=q, p1={}, error={}, shot={}, props=qubit_properties(backend.target, q)) for q in qubits]
    for key, (_, build_noise) in SOURCES.items():
        # Every qubit's circuit goes to the simulator in one call. Each source gets its own seed from rng, so the
        # sources don't all see the same random numbers
        sim = AerSimulator(noise_model=build_noise(backend, qubits))
        counts = sim.run(fez_circuits, shots=shots, seed_simulator=rng.randrange(2**31)).result().get_counts()
        for row, c in zip(rows, counts):
            p1 = prob_one(c)[0] / shots
            row["p1"][key], row["error"][key], row["shot"][key] = p1, abs(p1 - ideal_p1), shot_noise(p1, shots)
    return rows


# ---- Fez's listed numbers for one qubit ----

def gate_time(target, qubit):
    # How long one X gate takes on this qubit, in seconds. T1 and T2 noise grows with the time a gate takes
    return target[NOISY_GATE][(qubit,)].duration


def t1_t2(target, qubit):
    # The qubit's T1 and T2 in seconds. T2 can't physically be more than 2 * T1, so it is capped there (Aer does the
    # same when it builds Fez's noise model)
    props = target.qubit_properties[qubit]
    return props.t1, min(props.t2, 2 * props.t1)


def t1_decay_chance(target, qubit):
    # Chance the qubit decays from |1> to |0> (excited to ground state) during one X gate: 1 - e^(-time / T1).
    # The longer the gate takes, the more likely the decay
    t1, _ = t1_t2(target, qubit)
    return 1 - math.exp(-gate_time(target, qubit) / t1)


def pure_dephasing_time(target, qubit):
    # T2 counts every way the qubit loses its phase, including the phase lost when it decays (T1). This is the time
    # for the rest, the pure dephasing caused by noise in the qubit's surroundings: 1/T_phi = 1/T2 - 1/(2 T1).
    # Using it (not T2) for the T2 run means the T1 and T2 runs don't both count the same decay.
    # None if T1 explains all of T2
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
    # Everything listed for the qubit, plus how strong each noise source is per X gate. T2 is the listed value: the
    # 2 * T1 cap (see t1_t2) only goes into the noise
    props = target.qubit_properties[qubit]
    return dict(readout_error=target["measure"][(qubit,)].error, x_gate_error=target[NOISY_GATE][(qubit,)].error,
                x_gate_time_ns=gate_time(target, qubit) * 1e9, t1_us=props.t1 * 1e6, t2_us=props.t2 * 1e6,
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


# ---- Printing, CSV files and plots ----

def print_summary(rows, ideal_p1):
    # Every qubit's error from each source, the mean error per source, and the best and worst qubits
    labels = "".join(f"{label:>22}" for label, _ in SOURCES.values())

    def errors(row):
        # One qubit's error from every source, lined up under labels
        return "".join(f"{row['error'][key]:>22.4f}" for key in SOURCES)

    print_table_header(f"{'qubit':>6}{labels}{'shot noise (all)':>18}")
    for row in rows:
        shot = f"±{row['shot']['all']:.4f}"
        print(f"{row['qubit']:>6}{errors(row)}{shot:>18}")

    print("\nMean error over all qubits:")
    for key, (label, _) in SOURCES.items():
        print(f"  {label:<22}{sum(row['error'][key] for row in rows) / len(rows):.4f}")
    print(f"  {'shot noise (all)':<22}±{sum(row['shot']['all'] for row in rows) / len(rows):.4f}")

    ranked = sorted(rows, key=lambda row: row["error"]["all"])
    print(f"\n{NUM_BEST} qubits with the least error, |P(1) - P(1) with no noise|, all sources together "
          f"(no noise P(1) = {ideal_p1:.4f}):")
    print(f"{'rank':>6}{'qubit':>7}{labels}")
    for rank, row in enumerate(ranked[:NUM_BEST], 1):
        print(f"{rank:>6}{row['qubit']:>7}{errors(row)}")
    print("\nWorst qubits: " + ", ".join(f"{row['qubit']} ({row['error']['all']:.4f})" for row in ranked[::-1][:5]))
    print()


def write_results_csv(rows, num_gates, start_bit, shots, ideal_p1, path):
    # One row per qubit: P(1), error and shot noise for every noise source
    header = ["qubit", "y_gates", "start_bit", "shots", "no_noise_p1"]
    header += [f"{field}_{key}" for key in SOURCES for field in ("p1", "error", "shot_noise")]
    lines = [[row["qubit"], num_gates, start_bit, shots, round(ideal_p1, 6)]
             + [round(row[field][key], 6) for key in SOURCES for field in ("p1", "error", "shot")] for row in rows]
    write_csv(path, header, lines)


def write_properties_csv(rows, path):
    # One row per qubit: Fez's listed numbers and how strong each noise source is per X gate
    fields = list(rows[0]["props"])
    write_csv(path, ["qubit"] + fields, [[row["qubit"]] + [row["props"][field] for field in fields] for row in rows])


def plot(rows, num_gates, start_bit, shots, path):
    # Top: each qubit's error from the no-noise result, all sources together. Bottom: Fez's listed noise for each qubit
    plt = pyplot()
    from matplotlib.patches import Patch

    qubits = [row["qubit"] for row in rows]
    best = best_qubits(rows)
    best_rows = [row for row in rows if row["qubit"] in best]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(16, 8), sharex=True, gridspec_kw=dict(height_ratios=[3, 2]))

    errors = [row["error"]["all"] for row in rows]
    top.bar(qubits, errors, width=0.8, color=[BEST_COLOR if q in best else SOURCE_COLORS["all"] for q in qubits])
    top.errorbar(qubits, errors, yerr=[row["shot"]["all"] for row in rows], fmt="none", ecolor=INK, elinewidth=0.6,
                 label="± shot noise (1 standard error)")
    # Number the lowest-error qubits, and the worst few so they are easy to find
    for row in best_rows + sorted(rows, key=lambda row: row["error"]["all"])[-5:]:
        label_above(top, str(row["qubit"]), row["qubit"], row["error"]["all"])
    mean = sum(errors) / len(errors)
    top.axhline(mean, color=MUTED, ls="--", lw=1, label=f"mean over all qubits ({mean:.4f})")
    # Add a legend entry for the NUM_BEST lowest-error qubits' bars
    handles, _ = top.get_legend_handles_labels()
    handles.append(Patch(color=BEST_COLOR, label=f"{NUM_BEST} qubits with the least error"))
    top.legend(handles=handles, frameon=False, fontsize=9, loc="upper left")
    top.set_title(f"{num_gates} Y gates starting in |{start_bit}> on every Fez qubit (Fez noise simulator, "
                  f"{shots} shots each)", color=INK)
    top.set_ylabel("error from no-noise result\n|P(1) - P(1) with no noise|", color=MUTED)

    bottom.plot(qubits, [row["props"]["readout_error"] for row in rows], "-o", color=SOURCE_COLORS["readout"], lw=1.5,
                ms=4, markeredgecolor="white", markeredgewidth=0.8, label="readout error")
    bottom.plot(qubits, [row["props"]["x_gate_error"] for row in rows], "-o", color=SOURCE_COLORS["gate"], lw=1.5,
                ms=4, markeredgecolor="white", markeredgewidth=0.8, label="X gate error (per gate, includes T1/T2)")
    # Mark the lowest-error qubits on both lines
    for i, field in enumerate(("readout_error", "x_gate_error")):
        bottom.plot([row["qubit"] for row in best_rows], [row["props"][field] for row in best_rows], "o",
                    color=BEST_COLOR, ms=7, markeredgecolor=INK, markeredgewidth=0.8, zorder=3,
                    label=f"{NUM_BEST} qubits with the least error" if i == 0 else None)
    bottom.set_yscale("log")
    bottom.set_ylabel("Fez's listed noise", color=MUTED)
    bottom.legend(frameon=False, fontsize=9, loc="upper left", ncol=3)

    for ax in (top, bottom):
        style(ax)
    qubit_axis(bottom, qubits)
    save_plot(fig, path)


def plot_sources(rows, num_gates, start_bit, shots, path):
    # One panel per noise source: each qubit's error with only that source turned on (the top panel has them all).
    # Each panel has its own y scale, so small sources are still readable: compare them using the means in the titles.
    # The qubits with the least error (all sources together) are highlighted in every panel
    plt = pyplot()
    from matplotlib.patches import Patch

    qubits = [row["qubit"] for row in rows]
    best = best_qubits(rows)

    fig, axes = plt.subplots(len(SOURCES), 1, figsize=(16, 3 * len(SOURCES)), sharex=True)
    for ax, (key, (label, _)) in zip(axes, SOURCES.items()):
        errors = [row["error"][key] for row in rows]
        mean = sum(errors) / len(errors)
        ax.bar(qubits, errors, width=0.8, color=[BEST_COLOR if q in best else SOURCE_COLORS[key] for q in qubits])
        ax.errorbar(qubits, errors, yerr=[row["shot"][key] for row in rows], fmt="none", ecolor=INK, elinewidth=0.6)
        for row in (row for row in rows if row["qubit"] in best):
            label_above(ax, str(row["qubit"]), row["qubit"], row["error"][key] + row["shot"][key], gap=2)
        ax.axhline(mean, color=MUTED, ls="--", lw=1)
        ax.set_title(f"{label}: mean error {mean:.4f}", color=INK, fontsize=10, loc="left")
        ax.set_ylabel("error", color=MUTED)
        ax.set_ylim(bottom=0)
        style(ax)
    axes[0].legend(handles=[Patch(color=BEST_COLOR, label=f"{NUM_BEST} qubits with the least error, all sources together")],
                   frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(f"{num_gates} Y gates starting in |{start_bit}>: error from each noise source on its own "
                 f"({shots} shots each, black lines = ± shot noise, each panel has its own y scale)", color=INK)
    qubit_axis(axes[-1], qubits)
    save_plot(fig, path)


def plot_coherence(rows, path):
    # Fez's listed T1 and T2 for every qubit. Longer is better: the qubit holds its state for longer
    plt = pyplot()
    qubits = [row["qubit"] for row in rows]

    fig, ax = plt.subplots(figsize=(16, 4.5))
    for key, field, label in (("t1", "t1_us", "T1 (energy decay time)"), ("t2", "t2_us", "T2 (dephasing time)")):
        ax.plot(qubits, [row["props"][field] for row in rows], "-o", color=SOURCE_COLORS[key], lw=1.5, ms=4,
                markeredgecolor="white", markeredgewidth=0.8, label=label)
    ax.set_title("Fez's listed T1 and T2 for every qubit (longer is better)", color=INK)
    ax.set_ylabel("time (µs)", color=MUTED)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    style(ax)
    qubit_axis(ax, qubits)
    save_plot(fig, path)


def run(num_gates, shots=1000, seed=3, start_bit=0, qubits=None, csv_file=None, properties_csv_file=None,
        plot_file=None, sources_plot_file=None, coherence_plot_file=None):
    backend = FakeFez()
    ideal_sim = AerSimulator()   # no noise at all: gives what would be measured without noise
    if qubits is None:
        qubits = list(range(backend.num_qubits))

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

    rows = measure_errors(backend, qubits, fez_circuits, ideal_p1, shots, seed)
    print_summary(rows, ideal_p1)

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
