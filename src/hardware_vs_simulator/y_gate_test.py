# y_gate_test.py
# A circuit of Y gates on every Fez qubit. Runs the three ways of working out its error and compares them:
#   - simulator predicted (simulator_predicted.py): calculated exactly from the simulator's own noise model, no shots
#   - simulator measured (simulator_measured.py): actually running the circuit on the simulator
#   - calibration predicted (calibration_predicted.py): calculated exactly the same way, but with noise built from a
#     real ibm_fez calibration file
# Predicted vs measured on the simulator checks that the simulator does what its model says. Simulator vs calibration
# predicted shows how different the real machine should be today
import os
import statistics

from qiskit_ibm_runtime.fake_provider import FakeFez

from calibration_predicted import calibration_predicted, check_gate_channel
from noise_common import COLORS, CSV_DIR, FAIL_COLOR, IMAGE_DIR, ideal_result, ratio, save, style, write_rows
from simulator_measured import simulator_measured
from simulator_predicted import simulator_predicted

# Simulator measured "agrees" with simulator predicted if it is within this many standard errors (shot noise) of it.
# With 3, about 1 in 370 qubits still lands outside by chance even when the simulator is working
TOLERANCE_SIGMAS = 3


def agrees(measured, sigma, expected):
    # True if the measurement is within TOLERANCE_SIGMAS standard errors of the expected value, None if it couldn't
    # be measured
    if measured is None or sigma is None or expected is None:
        return None
    return bool(abs(measured - expected) <= TOLERANCE_SIGMAS * sigma)


def write_y_csv(qubits, results, num_gates, start_bit, shots, path):
    write_rows(path, ["qubit", "y_gates", "start_bit", "no_noise_result", "shots", "simulator_predicted_error",
                      "simulator_measured_error", "shot_noise", "measured_agrees_with_predicted",
                      "calibration_predicted_error", "calibration_over_simulator"],
               [[q, num_gates, start_bit, ideal_result(num_gates, start_bit), shots, results[q]["sim_predicted"],
                 results[q]["sim_measured"], results[q]["shot_noise"], results[q]["agrees"],
                 results[q]["cal_predicted"], ratio(results[q]["cal_predicted"], results[q]["sim_predicted"])]
                for q in qubits])


def plot_y_test(qubits, results, num_gates, start_bit, shots, path):
    # Top: simulator predicted vs measured, for every qubit (checks the simulator). Bottom: simulator predicted vs
    # calibration predicted (shows how the real machine differs). Log scale: the errors span a wide range
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted = "#0b0b0b", "#52514e"
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(16, 9), sharex=True)
    predicted = [results[q]["sim_predicted"] for q in qubits]
    for ax in (top, bottom):
        ax.plot(qubits, predicted, "-", color=COLORS[0], lw=1.5, label="simulator predicted (from its model)")

    ok = [q for q in qubits if results[q]["agrees"]]
    off = [q for q in qubits if results[q]["agrees"] is False]
    # Agreeing points in dark gray, the rest as bigger red diamonds, so they stand out by shape as well as color
    for qs, color, marker, size, label in ((ok, muted, "o", 4, "simulator measured (agrees)"),
                                           (off, FAIL_COLOR, "D", 7,
                                            f"simulator measured (off by > {TOLERANCE_SIGMAS}σ)")):
        if qs:
            top.errorbar(qs, [results[q]["sim_measured"] for q in qs], yerr=[results[q]["shot_noise"] for q in qs],
                         fmt=marker, color=color, ms=size, mec="white", mew=0.6, elinewidth=0.8,
                         label=f"{label} ({len(qs)})", zorder=3)
    top.set_title(f"Simulator check: {num_gates} Y gates starting in |{start_bit}>, predicted vs measured "
                  f"({shots} shots, bars = ± shot noise)", color=ink, fontsize=10, loc="left")

    cal = [q for q in qubits if results[q]["cal_predicted"] is not None]
    bottom.plot(cal, [results[q]["cal_predicted"] for q in cal], "o", color=COLORS[2], ms=4, mec="white", mew=0.6,
                label="calibration predicted (real machine today)")
    bottom.set_title("Real machine check: what the simulator predicts vs what today's calibration predicts",
                     color=ink, fontsize=10, loc="left")
    bottom.set_xlabel("Fez qubit", color=muted)
    bottom.set_xticks(range(0, max(qubits) + 1, 10))
    bottom.set_xlim(min(qubits) - 1, max(qubits) + 1)
    for ax in (top, bottom):
        ax.set_yscale("log")
        ax.set_ylabel("error (chance of a wrong result)", color=muted)
        ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=3)
        style(ax)
    save(fig, path)


def run(qubits=None, num_gates=150, start_bit=0, shots=10000, seed=3, calibration_file=None, csv_file=None,
        plot_file=None):
    backend = FakeFez()
    if qubits is None:
        qubits = list(range(backend.num_qubits))

    print(f"Simulator: FakeFez, calibrated {backend.properties().last_update_date}")
    print(f"Real:      {os.path.basename(calibration_file)}\n")
    print(f"{num_gates} Y gates starting in |{start_bit}> on every qubit, {shots} shots")
    predicted = simulator_predicted(backend, qubits, num_gates, start_bit)
    measured = simulator_measured(backend, qubits, num_gates, start_bit, shots, seed)
    cal = calibration_predicted(calibration_file, qubits, num_gates, start_bit)
    results = {q: dict(sim_predicted=predicted[q], sim_measured=measured[q][0], shot_noise=measured[q][1],
                       agrees=agrees(measured[q][0], measured[q][1], predicted[q]), cal_predicted=cal[q])
               for q in qubits}

    checked = [r["agrees"] for r in results.values() if r["agrees"] is not None]
    print(f"  simulator measured vs simulator predicted: {sum(checked)}/{len(checked)} agree within "
          f"{TOLERANCE_SIGMAS} standard errors")
    print(f"  mean error: simulator predicted {statistics.mean(predicted.values()):.4f}, "
          f"simulator measured {statistics.mean(e for e, _ in measured.values()):.4f}, "
          f"calibration predicted {statistics.mean(e for e in cal.values() if e is not None):.4f}")
    print(f"  calibration noise built the same way as Aer's (largest difference on FakeFez's numbers: "
          f"{check_gate_channel(backend, qubits):.1e})\n")

    if csv_file:
        write_y_csv(qubits, results, num_gates, start_bit, shots, csv_file)
    if plot_file:
        plot_y_test(qubits, results, num_gates, start_bit, shots, plot_file)


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    QUBITS = None              # list of Fez qubits to test, e.g. [0, 1, 2]; None tests all 156
    NUM_GATES = 1000           # how many Y gates in a row on each qubit
    START_BIT = 0              # start each qubit in |0> or |1>
    SHOTS = 10000              # shots per qubit
    SEED = 3                   # sets the simulator's randomness (same SEED = same results)
    # Real calibration file downloaded from IBM Quantum
    CALIBRATION_FILE = os.path.join(CSV_DIR, "ibm_fez_calibrations_2026-10-24T18_48_15Z.csv")
    # Output files; None skips any of them
    CSV_FILE = os.path.join(CSV_DIR, f"y_gate_test_{NUM_GATES}.csv")
    PLOT_FILE = os.path.join(IMAGE_DIR, f"y_gate_test_{NUM_GATES}.png")

    run(qubits=QUBITS, num_gates=NUM_GATES, start_bit=START_BIT, shots=SHOTS, seed=SEED,
        calibration_file=CALIBRATION_FILE, csv_file=CSV_FILE, plot_file=PLOT_FILE)
