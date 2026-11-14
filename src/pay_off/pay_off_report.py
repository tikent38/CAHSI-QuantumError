# pay_off_report.py
# Writes reports/pay_off_table.md from the results of pay_off_parallel.py: for each backend, the qubits it ran on and
# their noise, and for each gate set and code, how many gates the code needs to pay off, with the size of its transpiled
# circuit at that point. Nothing is simulated here: the pay-off points are read from the CSV files, and only the
# transpiling is done again. Change what is reported in the settings block at the bottom of the file
import os

import qiskit_ibm_runtime

from pay_off_common import HERE, IN_A_ROW, backend_folder
from compare_backends import backend_label, default_qubits, get_backend, noise_levels, on_backend, set_layout
from compare_fez import encode_all, test_circuit   # in src/noisy, which importing pay_off_common puts on the path
from output_tools import read_csv, write_text      # in src/output_tools, the same

PARITIES = ("even", "odd")
TABLE_HEADER = ["Backend", "Qubits q0, q1, q2 with noise", "Gate sequence", "Code",
                "Pays off at, logical gates (even / odd)", "Transpiled gates (even / odd)",
                "Transpiled depth (even / odd)"]


# ---- The numbers in the table ----

def read_points(results_dir, backend, pick):
    # This backend's pay-off points, {(gate set, code, parity): number of gates, or None if it never paid off}, and its
    # {(shots, seed)}
    rows = read_csv(os.path.join(backend_folder(results_dir, backend, pick), "pay_off_points.csv"))
    points = {(r["gate_set"], r["code"], r["parity"]): int(r["pays_off_at_gates"]) if r["pays_off_at_gates"] else None
              for r in rows}
    return points, {(r["shots"], r["seed"]) for r in rows}


def transpiled_size(backend, gate_set, num_gates, code, seed, pick):
    # (gates, depth) of code's circuit on backend, at num_gates gates of gate_set, transpiled the way
    # compare_backends.py does it and counted the way it prints them (compare_fez.py's print_sizes). None if it never
    # paid off
    if num_gates is None:
        return None
    circuit = test_circuit(gate_set, num_gates, seed, False)
    plain = circuit.copy()
    plain.measure_all()
    encoded, skipped = encode_all(circuit, [code])
    circuits, _ = on_backend(plain, encoded, skipped, backend, set_layout(backend, pick=pick), seed)
    return circuits[code].size(), circuits[code].depth()


# ---- The text in the table ----

def small(error):
    # A gate error, as x 10^-3
    return f"{error * 1e3:.2f}"


def big(error):
    # A readout or 2-qubit gate error, as x 10^-3, which can be 10 or more
    error *= 1e3
    return f"{error:.1f}" if error >= 10 else f"{error:.2f}"


def noise_text(name, data):
    # Each data qubit's noise, then the 2-qubit gate error on q0-q1 and q0-q2
    levels, links = noise_levels(name)
    qubits = "; ".join(f"**{q}**: {small(levels[q][0])} / {small(levels[q][1])} / {big(levels[q][2])}" for q in data)
    return f"{qubits}; 2q: " + ", ".join(big(links[tuple(sorted((data[0], q)))]) for q in data[1:])


def table_row(cells):
    return "| " + " | ".join(cells) + " |"


def backend_rows(name, points, seed, gate_sets, codes, max_gates, pick):
    # The table's rows for one backend. The backend and each gate set are only named on their first row
    backend = get_backend(name)
    first_cells = [f"**{backend_label(backend)}**", noise_text(name, default_qubits(backend, pick)["data"])]
    rows = []
    for gate_set, gate_label in gate_sets.items():
        gate_cell = gate_label
        for code, code_label in codes.items():
            found = [points[gate_set, code, parity] for parity in PARITIES]
            sizes = [transpiled_size(backend, gate_set, n, code, seed, pick) for n in found]
            rows.append(table_row([first_cells[0], first_cells[1], gate_cell, code_label,
                                   " / ".join(f">{max_gates}" if n is None else str(n) for n in found),
                                   " / ".join("—" if s is None else str(s[0]) for s in sizes),
                                   " / ".join("—" if s is None else str(s[1]) for s in sizes)]))
            first_cells, gate_cell = ["", ""], ""
    return rows


def notes_text(max_gates, shots, seed):
    # What the report says above its table
    return [
        f"- Pays off: the first number of gates where a code beats no correction {IN_A_ROW} times in a row, measured "
        "on the same qubit",
        "- Pay-off cells: `even / odd` numbers of logical gates (the test circuit's gates, before encoding). `>N` "
        "means it still hadn't paid off when the sweep stopped at N.",
        "- Transpiled gates and depth: the code's whole circuit at that pay-off point, after transpiling to the "
        "backend, counted the way `print_sizes` in `src/noisy/compare_fez.py` does. Gates include `rz` and "
        "measurements, and leave out barriers. `—` means there was no pay-off to measure",
        "- Noise: ×10⁻³, written as `bit flip per X gate / phase flip per X gate / readout error` for each qubit. "
        "`2q` is the 2-qubit gate error on q0–q1, then q0–q2",
        "- Qubits: the codes are the Toffoli versions, so bit-flip and phase-flip use only the 3 qubits listed. The "
        "result and the no-correction run are both measured on q2",
        f"- Source: `src/pay_off/parallel_runs/csvs/` (`pay_off_parallel.py`, {max_gates} gates at most, {shots} "
        f"shots, seed {seed}), put together by `src/pay_off/pay_off_report.py`. Noise is from `noise_levels` in "
        f"`src/noisy/compare_backends.py`, on the fake backends in qiskit_ibm_runtime {qiskit_ibm_runtime.__version__}",
        "- Left out: runs with only Z gates, runs with H gates, and the Shor code. Backends are sorted roughly from "
        "earliest pay-off to latest",
    ]


# ---- Running ----

def run(backends, gate_sets, codes, results_dir, max_gates, pick, report_file):
    # Writes the report. gate_sets and codes: {key in the CSV files: name in the table}
    points = {}
    settings = set()
    for name in backends:
        points[name], found = read_points(results_dir, name, pick)
        settings |= found
    if len(settings) != 1:   # the report names one number of shots and one seed, so they have to be the same throughout
        raise ValueError(f"the results don't all have the same shots and seed: {sorted(settings)}")
    shots, seed = settings.pop()

    lines = ["# Gate counts where each code pays off", ""] + notes_text(max_gates, shots, seed) + [""]
    lines += [table_row(TABLE_HEADER), table_row(["---"] * len(TABLE_HEADER)).replace(" ", "")]
    for name in backends:
        lines += backend_rows(name, points[name], int(seed), gate_sets, codes, max_gates, pick)
        print(f"done: {name}", flush=True)
    write_text(report_file, "\n".join(lines) + "\n")


if __name__ == "__main__":
    # ---- Settings: change these to report something else ----
    # In this order in the table: roughly earliest pay-off to latest
    BACKENDS = ["fez", "kingston", "marrakesh", "torino", "washington", "brisbane", "kolkata", "sherbrooke"]
    GATE_SETS = {"x": "X", "y": "Y", "repeat": "Repeat (X, Y, Z)", "id": "ID"}   # gate set: its name in the table
    CODES = {"bit-flip, Toffoli": "Bit-flip", "phase-flip, Toffoli": "Phase-flip"}   # code: its name in the table
    RESULTS_DIR = os.path.join(HERE, "parallel_runs", "csvs")   # where pay_off_parallel.py merges its results
    MAX_GATES = 1500           # the MAX_GATES those results ran with: what the table's ">1500" means
    PICK_QUBITS = "like fez"   # the PICK_QUBITS those results ran with
    REPORT_FILE = os.path.join(HERE, "reports", "pay_off_table.md")

    run(BACKENDS, GATE_SETS, CODES, RESULTS_DIR, MAX_GATES, PICK_QUBITS, REPORT_FILE)
