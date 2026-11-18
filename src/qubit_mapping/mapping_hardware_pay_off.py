# mapping_hardware_pay_off.py
# mapping_pay_off.py's plots for a job mapping_hardware.py ran on the real ibm_fez: one plot per starting state, with a
# panel for each of the four match-ups (worst no correction vs best codes, best vs worst, best vs best, worst vs worst),
# on the mappings that ran. The machine ran at one number of gates only (200 by default), so it gives one point per
# mapping instead of a line, and no pay-off points. Each panel shows:
#   left   the error the noise simulator predicts at every number of gates, with the noise of the calibration file the
#          job was ranked from (mapping_pay_off.py's lines, on mapping_hardware.py's calibrated simulator)
#   right  each mapping at the job's number of gates: the simulator's error (hollow dot) and the machine's (filled dot,
#          with one standard deviation of shot noise), joined by a line in the mapping's line style
import os

# The code the mapping scripts share, mapping_pay_off.py's match-ups, lines and plot panels, and mapping_hardware.py's
# job files and calibrated simulator
from mapping_common import CSV_DIR, IMAGE_DIR, OPTION_COLORS, OPTIONS, REPORT_DIR, log_limits, mapping_text, states_text
from mapping_pay_off import (KINDS, MATCHUPS, check_compare, curves, error_panel, gate_counts, in_matchups,
                             matchup_legend, matchup_lines, state_plots, top_of, write_curves)
from mapping_hardware import (calibrated_simulator, gates_text, job_paths, plan_lists, read_calibration, saved_job,
                              working_edges)
from output_tools import INK, pyplot, save_plot, style, write_text

PANEL_WIDTHS = (3, 1.2)  # each panel's two parts: the lines, and the job's number of gates
DODGE = 0.25            # on the right of a panel, how far apart an option's 1st, 2nd, ... mapping sit
STRIP_LABELS = ("no corr.", "bit-flip", "phase-flip")   # the options, under the right of each panel


# ---- The job and its simulator ----

def load_job(paths):
    # The job's plan and runs, with the machine's results. paths: mapping_hardware.py's job_paths
    plan, runs, saved = saved_job(paths)
    if not saved:
        raise FileNotFoundError(f"{paths['results']} doesn't hold the results of job {plan['job_id']}: run "
                                "mapping_hardware.py with RESUME = True to get them")
    return plan, runs


def rebuilt_simulator(plan, csv_dir):
    # The calibrated simulator the job was ranked with (mapping_hardware.py's calibrated_simulator), rebuilt from its
    # calibration file without connecting to IBM: the same qubits, and every connection between them whose CZ error
    # is below mapping_hardware.py's MAX_CZ_ERROR. mapping_hardware.py also left out any connection the machine itself
    # didn't offer, which only the machine knew; if that changes a circuit here, check_simulator stops the script
    path = os.path.join(csv_dir, plan["calibration_file"])
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} doesn't exist: job {plan['job_id']} was ranked from it, so it is needed to "
                                "draw the simulator's lines")
    numbers, cz, lengths, _ = read_calibration(path)
    qubits = set(range(len(numbers))) - set(plan["left_out"])
    return calibrated_simulator(numbers, cz, lengths, qubits, working_edges(cz, qubits))


def check_simulator(by_state, runs, ns, num_gates, calibration_file):
    # Each mapping's error here at the job's number of gates must be the one the job predicted for the circuit that ran
    # (for the first ibm_fez job they agree to 1e-8; with the connections wrong, one circuit was off by 0.9)
    i, off = ns.index(num_gates), {}
    for r in runs:
        key = (r["option"], tuple(r["mapping"]))
        if key in by_state[r["start"]]:   # (the head-to-head runs aren't in the match-ups)
            off[key + (r["start"],)] = abs(by_state[r["start"]][key][i] - r["predicted"])
    worst = max(off, key=off.get)
    if off[worst] > 1e-6:
        option, mapping, bit = worst
        raise RuntimeError(f"{option} on {mapping_text(mapping)} from |{bit}>: the simulator rebuilt from "
                           f"{calibration_file} is off by {off[worst]:.1e} from the job's prediction at {num_gates} "
                           "gates, so its lines wouldn't be the circuits that ran. The machine may have left out a "
                           "connection the calibration file lists")
    print(f"Checked against the job's predictions at {num_gates} gates: largest difference {off[worst]:.1e}")


def machine_errors(runs):
    # What the machine measured: {start: {(option, mapping): (error, its standard deviation from shot noise)}}
    out = {}
    for r in runs:
        out.setdefault(r["start"], {})[r["option"], tuple(r["mapping"])] = (r["error"], r["error_sd"])
    return out


# ---- The report and the plots ----

def report(plan, max_gates, image_paths, main_report):
    # A short Markdown page with the plots. image_paths: {start: that plot's path from the report's folder};
    # main_report: mapping_hardware.py's report's path from the report's folder
    machine, num_gates = plan["backend"], plan["num_gates"]
    out = [f"# The match-ups on the real {machine}: {gates_text(plan['gate_set'], num_gates)}", "",
           f"mapping_pay_off.py's plots for job `{plan['job_id']}` (mapping_hardware.py, {plan['shots']} shots per "
           f"circuit), with the best and worst mappings that ran on {machine}. Each match-up pairs the top "
           f"{plan['compare']} of each list, as in mapping_pay_off.py. The full results, with the match-up tables, are "
           f"in [{os.path.basename(main_report)}]({main_report}).", "",
           f"- **Lines:** the error the noise simulator predicts at every number of gates from 0 to {max_gates}, with "
           f"the noise of the calibration file the job was ranked from (taken {plan['calibration_taken']}).",
           f"- **Right of each panel, at {num_gates} gates:** each mapping's predicted error (hollow dot) and the error "
           f"{machine} measured (filled dot, with one standard deviation of shot noise), joined by a line in the "
           "mapping's line style. Each option's dots go 1st, 2nd, 3rd on its list from left to right.",
           f"- {machine} ran at {num_gates} gates only, so it gives one point per mapping, not a line, and there are no "
           "pay-off points from it.", ""]
    for bit, path in image_paths.items():
        out += [f"![the match-ups on {machine}, starting in |{bit}>]({path})", ""]
    return "\n".join(out)


def plot(plan, compared, found, measured, ns, bit, limits, path):
    # One panel per match-up, starting in |bit>: the simulator's error against the number of gates for each mapping in
    # it, and beside that, each mapping at the job's number of gates on the simulator and on the machine. found:
    # {(option, mapping): errors} from |bit>; measured: {(option, mapping): (error, sd)} from |bit>. Each option keeps
    # its color, and its 1st, 2nd, ... mapping in the match-up gets mapping_pay_off.py's line styles
    from matplotlib.lines import Line2D
    plt = pyplot()
    machine, num_gates = plan["backend"], plan["num_gates"]
    at = ns.index(num_gates)
    fig = plt.figure(figsize=(16, 12.5))
    cells = fig.add_gridspec(2, 2)
    first = None
    for n, (matchup, plain_list, code_list) in enumerate(MATCHUPS):
        row, column = divmod(n, 2)
        parts = cells[row, column].subgridspec(1, 2, width_ratios=PANEL_WIDTHS, wspace=0.05)
        ax = fig.add_subplot(parts[0], sharex=first, sharey=first)
        strip = fig.add_subplot(parts[1], sharey=ax)
        first = first or ax
        for name, i, count, mapping, ls in matchup_lines(compared, plain_list, code_list):
            color, errors = OPTION_COLORS[name], found[name, mapping]
            error, sd = measured[name, mapping]
            label = f"{mapping_text(mapping)} ({errors[at]:.3f} → {error:.3f})"
            ax.plot(ns, errors, ls, color=color, lw=2, label=label)
            ax.plot(num_gates, errors[at], "o", ms=6, mfc="white", mec=color, mew=1.4, zorder=4)
            spot = OPTIONS.index(name) + (i - (count - 1) / 2) * DODGE
            strip.plot([spot, spot], [errors[at], error], ls, color=color, lw=1.4, zorder=2)
            strip.plot(spot, errors[at], "o", ms=6, mfc="white", mec=color, mew=1.4, zorder=3)
            strip.errorbar(spot, error, yerr=sd, fmt="o", ms=6.5, color=color, mec="white", mew=0.8, elinewidth=1,
                           capsize=2, zorder=4)
        strip.set_xlim(-0.5, len(OPTIONS) - 0.5)
        strip.set_xticks(range(len(OPTIONS)), STRIP_LABELS, fontsize=8)
        strip.tick_params(labelleft=False)
        strip.set_title(f"at {num_gates} gates", color=INK, fontsize=10, loc="left")
        style(strip, grid_axis="y")
        # The panel's legend is centred under both its parts
        left, right = ax.get_position(), strip.get_position()
        legend_title = f"mapping (error at {num_gates} gates from |{bit}>: simulator → {machine})"
        error_panel(ax, matchup, ns, limits, legend_title, row, column, legend_x=(right.x1 - left.x0) / 2 / left.width)

    title = (f"{machine}, {gates_text(plan['gate_set'], num_gates)}, starting in |{bit}>: the best and worst mappings "
             f"of each option, simulator against machine\n(lines and hollow dots: the noise simulator, with the "
             f"calibration taken {plan['calibration_taken']}, which ranked the lists; filled dots: what job "
             f"{plan['job_id']} measured)")
    hollow = Line2D([], [], ls="", marker="o", ms=6, mfc="white", mec=INK, mew=1.4)
    filled = Line2D([], [], ls="", marker="o", ms=6.5, color=INK)
    matchup_legend(fig, title, len(compared[OPTIONS[0]][KINDS[0]]),
                   [(hollow, f"simulator at {num_gates} gates"), (filled, f"{machine} at {num_gates} gates (±1 sd)")],
                   0.95)
    # tight_layout leaves room for the title itself, so rect only keeps the legend's row free
    save_plot(fig, path, rect=(0, 0, 1, 0.975))
    plt.close(fig)


# ---- Running ----

def run(gate_set="y", num_gates=200, backend_name="ibm_fez", max_gates=None, csv_dir=CSV_DIR, image_dir=IMAGE_DIR,
        report_dir=REPORT_DIR):
    # gate_set, num_gates and backend_name pick the job, as mapping_hardware.py names its files. max_gates: where the
    # simulator's lines end (twice num_gates if None)
    paths = job_paths(backend_name, gate_set, num_gates, csv_dir, image_dir, report_dir)
    plan, runs = load_job(paths)
    max_gates = max_gates or 2 * num_gates
    ns, step = gate_counts(gate_set, max_gates)
    if num_gates not in ns:
        raise ValueError(f"the lines go from 0 to {max_gates} gates in steps of {step}, so they miss the job's "
                         f"{num_gates}")
    check_compare(plan["compare"], plan["top"])

    compared = top_of(plan_lists(plan), plan["compare"])
    mappings = in_matchups(compared)
    start_states = tuple(plan["start_states"])
    backend, sim, readout = rebuilt_simulator(plan, csv_dir)
    print(f"Job {plan['job_id']}: the simulator's errors of the {len(mappings)} mappings in the match-ups at 0 to "
          f"{max_gates} gates in steps of {step}, starting in {states_text(start_states)}")
    by_state = curves(mappings, gate_set, start_states, plan["seed"], ns, backend, sim, readout)
    check_simulator(by_state, runs, ns, num_gates, plan["calibration_file"])
    measured = machine_errors(runs)

    name = f"mapping_hardware_pay_off_{backend_name}_{gate_set}_{num_gates}"
    images, links = state_plots(name, start_states, image_dir, report_dir)
    write_curves(os.path.join(csv_dir, f"{name}_curves.csv"), by_state, ns)
    write_text(os.path.join(report_dir, f"{name}.md"),
               report(plan, max_gates, links, os.path.relpath(paths["report"], report_dir)))
    # Both plots share one scale, so they can be compared
    every = [e for mine in by_state.values() for errors in mine.values() for e in errors]
    for bit in start_states:
        for key in mappings:
            error, sd = measured[bit][key]
            every += [error - sd, error + sd]
    # (the top may go a little past 1, so an error near 1 isn't drawn on the frame)
    limits = log_limits(every, top=None)
    for bit, path in images.items():
        plot(plan, compared, by_state[bit], measured[bit], ns, bit, limits, path)


if __name__ == "__main__":
    # ---- Settings: which mapping_hardware.py job to plot, csvs/mapping_hardware_<BACKEND_NAME>_<GATE_SET>_<NUM_GATES>
    GATE_SET = "y"            # as in mapping_hardware.py
    NUM_GATES = 200
    BACKEND_NAME = "ibm_fez"
    MAX_GATES = 400           # where the simulator's lines end

    run(GATE_SET, NUM_GATES, BACKEND_NAME, max_gates=MAX_GATES)
