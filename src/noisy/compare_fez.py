# compare_fez.py
# Runs one 1-qubit test circuit on the Fez noise simulator with no correction and with each error-correction code,
# and prints how far each result is from the exact answer and how big each circuit is once it is on Fez.
# Change the experiment in the settings block at the bottom of the file
import os
import random
import sys

from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

from bit_flip_encoded import bit_flip_encoded
from bit_flip_toffoli import bit_flip_toffoli
from fez_common import (DEFAULT_ANCILLA_QUBITS, DEFAULT_DATA_QUBITS, DEFAULT_SHOR_ANCILLA_QUBITS,
                        DEFAULT_SHOR_DATA_QUBITS, physical_qubits, prob_one, working_coupling_map)
from phase_flip_encoded import phase_flip_encoded
from phase_flip_toffoli import phase_flip_toffoli
from shor_encoded import shor_encoded
from shor_toffoli import shor_toffoli

# The code for printing tables lives in src/output_tools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output_tools"))
from output_tools import print_table_header

ALL_GATES = ("x", "y", "z", "s", "t", "id")
XZ_GATES = ("x", "z")
REPEAT_GATES = ("x", "y", "z")

# Every error-correction code compare() can run, and the label printed for each. To add a code, add it here
CODES = {
    "bit-flip, if blocks": bit_flip_encoded,
    "bit-flip, Toffoli": bit_flip_toffoli,
    "phase-flip, if blocks": phase_flip_encoded,
    "phase-flip, Toffoli": phase_flip_toffoli,
    #"Shor, if blocks": shor_encoded,
    #"Shor, Toffoli": shor_toffoli,
}
# The codes compare() runs when it isn't told which. The Shor codes are left out: with 17 and 9 qubits they take most
# of the run time
DEFAULT_CODES = ("bit-flip, if blocks", "bit-flip, Toffoli", "phase-flip, if blocks", "phase-flip, Toffoli")


# ---- The test circuits ----

def random_circuit(num_gates, seed, gates):
    # num_gates gates picked at random from gates. The same seed always gives the same circuit
    rng = random.Random(seed)
    qc = QuantumCircuit(1)
    for _ in range(num_gates):
        getattr(qc, rng.choice(gates))(0)
    return qc


def repeating_circuit(num_gates, gates):
    # Not random: the gates in order, over and over, until there are num_gates of them (e.g. X, Y, Z, X, Y, Z, ...)
    qc = QuantumCircuit(1)
    for i in range(num_gates):
        getattr(qc, gates[i % len(gates)])(0)
    return qc


# Each gate_set option: whether its gates are picked at random or repeat in order, and the gates. To add a gate set,
# add it here
GATE_SETS = {
    "all": ("random", ALL_GATES),
    "xz": ("random", XZ_GATES),   # every code applies X and Z without decoding, so the qubit stays protected
    "repeat": ("repeating", REPEAT_GATES),
    "x": ("repeating", ("x",)),
    "y": ("repeating", ("y",)),
    "z": ("repeating", ("z",)),
}


# ---- Helpers ----

def test_circuit(gate_set, num_gates, seed, mirror):
    # The circuit compare() runs, before any code is applied. The seed also sets the transpiler and simulator seeds,
    # so it matters even for the gate sets that aren't random
    kind, gates = GATE_SETS[gate_set]
    circuit = random_circuit(num_gates, seed, gates) if kind == "random" else repeating_circuit(num_gates, gates)
    if mirror:
        circuit = mirrored(circuit)
    check_no_h(circuit)
    return circuit


def mirrored(circuit):
    # The circuit followed by its inverse, so the exact answer is always 0
    return circuit.compose(circuit.inverse())


def check_no_h(circuit):
    # H has no protected version in any of the codes (all would have to decode around it),
    # so circuits passed to compare() must not contain any
    if "h" in circuit.count_ops():
        raise ValueError(f"circuit contains {circuit.count_ops()['h']} H gate(s); compare() only supports circuits without H")


def encode_all(circuit, codes):
    # Each code's version of the circuit. A code that can't run this circuit raises ValueError (the Shor codes only
    # allow Pauli gates, so they can't run gate_set="all"); it is left out, and the reason kept to print
    encoded, skipped = {}, {}
    for name in codes:
        try:
            encoded[name] = CODES[name](circuit)
        except ValueError as err:
            skipped[name] = err
    return encoded, skipped


def code_layout(backend, data, ancillas, num_data, num_ancillas, code):
    # One code's layout, data + ancillas, after checking it has the right number of qubits,
    # uses each Fez qubit once, and only uses qubits Fez has
    layout = list(data) + list(ancillas)
    if len(data) != num_data or len(ancillas) != num_ancillas:
        raise ValueError(f"{code} codes need {num_data} data qubits and {num_ancillas} ancillas, "
                         f"got {len(data)} and {len(ancillas)}")
    if len(set(layout)) != len(layout):
        raise ValueError(f"{code} codes can only use each Fez qubit once, got {layout}")
    bad = [q for q in layout if not 0 <= q < backend.num_qubits]
    if bad:
        raise ValueError(f"Fez only has qubits 0-{backend.num_qubits - 1}, got {bad}")
    return layout


def set_layout(backend, data=DEFAULT_DATA_QUBITS, ancillas=DEFAULT_ANCILLA_QUBITS,
               shor_data=DEFAULT_SHOR_DATA_QUBITS, shor_ancillas=DEFAULT_SHOR_ANCILLA_QUBITS):
    # Pick by hand which of Fez's physical qubits each circuit qubit runs on (fez_common.py's DEFAULT_ qubits by
    # default). data = (Fez qubit for q_0, q_1, q_2), ancillas = (Fez qubit for a_0, a_1) of the bit-flip and
    # phase-flip codes. shor_data = (Fez qubit for q_0, ..., q_8), shor_ancillas = (Fez qubit for a_0, ..., a_7) of
    # the Shor codes. Every code puts its data qubits first and its ancillas after, so each layout is data + ancillas:
    # the Toffoli codes use only the data qubits.
    # The two layouts can share Fez qubits, since every code runs on its own
    return {"bit/phase-flip": code_layout(backend, data, ancillas, 3, 2, "bit-flip and phase-flip"),
            "Shor": code_layout(backend, shor_data, shor_ancillas, 9, 8, "Shor")}


def on_fez(plain, encoded, backend, layouts, seed):
    # Every circuit converted to Fez's gates (cz, rz, sx, x) and placed on Fez's qubits.
    # optimization_level=0 keeps every gate: otherwise the transpiler would merge the test gates into one or two.
    # Fez's gates and wiring are passed in directly, instead of the backend, so the wiring can leave out Fez's broken
    # connections (see working_coupling_map). Every code starts on the same Fez qubits (layouts), so differences
    # between the codes don't come from landing on better or worse qubits.
    # Routing moves a code's qubits around with SWAPs, so its result is often measured on a different Fez qubit than
    # the one q_0 started on. As in the hardware runs, no correction runs on the qubit each code is measured on, so both
    # are read out on the same physical qubit (with no codes, it runs on q_0's qubit).
    # Returns the circuits, {run: circuit}, and the no-correction run each code is compared with, {code: run}
    options = dict(optimization_level=0, routing_method="sabre", seed_transpiler=seed,
                   basis_gates=list(backend.target.operation_names), coupling_map=working_coupling_map(backend))
    coded = {}
    for name, qc in encoded.items():
        layout = layouts["Shor" if name.startswith("Shor") else "bit/phase-flip"]
        coded[name] = transpile(qc, initial_layout=layout[:qc.num_qubits], **options)
    measured_on = {name: physical_qubits(qc)[1] for name, qc in coded.items()}
    plain_for = {name: f"no correction (Fez {q})" for name, q in measured_on.items()}
    circuits = {f"no correction (Fez {q})": transpile(plain, initial_layout=[q], **options)
                for q in dict.fromkeys(measured_on.values()) or [layouts["bit/phase-flip"][0]]}
    circuits.update(coded)
    return circuits, plain_for


def run_all(plain, circuits, backend, shots, seed):
    # [(name, counts)]: the test circuit on a perfect simulator, then every Fez circuit on the Fez noise simulator
    runs = [("no noise", AerSimulator().run(plain, shots=shots).result().get_counts())]
    noisy_sim = AerSimulator.from_backend(backend)
    for name, circuit in circuits.items():
        counts = noisy_sim.run(circuit, shots=shots, seed_simulator=seed).result().get_counts()
        runs.append((f"Fez noise, {name}", counts))
    return runs


# ---- Printing ----

def print_setup(gate_set, num_gates, seed, mirror, shots, layouts, exact_p1, skipped, plain_for):
    kind, gates = GATE_SETS[gate_set]
    print(f"{kind.capitalize()} circuit: {num_gates} gates from {', '.join(gates)}  (seed {seed}"
          f"{', mirrored' if mirror else ''})")
    print(f"Shots per run: {shots}")
    small, shor = layouts["bit/phase-flip"], layouts["Shor"]
    print(f"Fez qubits:    bit/phase-flip data {small[:3]}, ancillas {small[3:]}")
    print(f"               Shor data {shor[:9]}, ancillas {shor[9:]}")
    print("Compared with:  " + ",  ".join(f"{name} -> {run}" for name, run in plain_for.items())
          + "  (no correction runs on the qubit each code is measured on)")
    print(f"Exact answer:  P(0) = {1 - exact_p1:.4f}   P(1) = {exact_p1:.4f}")
    for name, err in skipped.items():
        print(f"Skipped {name}: {err}")
    print()


def print_results(runs, shots, exact_p1):
    # Column widths grow to fit the longest run name
    run_width = max(28, max(len(name) for name, _ in runs) + 2)
    print(f"{'run':<{run_width}}{'0':>7}{'1':>7}{'P(1)':>10}{'off from exact':>17}")
    print("-" * (run_width + 41))
    for name, counts in runs:
        ones, zeros = prob_one(counts)
        p1 = ones / shots
        print(f"{name:<{run_width}}{zeros:>7}{ones:>7}{p1:>10.4f}{abs(p1 - exact_p1):>17.4f}")


def print_sizes(circuits, exact_p1):
    # Each transpiled circuit's size: gates (barriers left out, measurements counted), two-qubit gates, depth, and how
    # many of each gate
    print("\nTranspiled circuits on Fez:")
    size_width = max(22, max(len(name) for name in circuits) + 2)
    print_table_header(f"  {'run':<{size_width}}{'gates':>8}{'2-qubit':>9}{'depth':>8}   gate counts")
    for name, circuit in circuits.items():
        counts = " ".join(f"{gate}:{n}" for gate, n in circuit.count_ops().items() if gate != "barrier")
        print(f"  {name:<{size_width}}{circuit.size():>8}{circuit.num_nonlocal_gates():>9}{circuit.depth():>8}"
              f"   {counts}")
    if 0.35 < exact_p1 < 0.65:
        print("\nNote: the exact answer is close to 50/50, and noise tends to push results toward 50/50,")
        print("so noise is hard to see here. Try another SEED or set MIRROR = True (exact answer is then always 0).")


def compare(num_gates=1000, shots=1000, seed=None, gate_set="all", mirror=False, codes=DEFAULT_CODES,
            data_qubits=DEFAULT_DATA_QUBITS, ancilla_qubits=DEFAULT_ANCILLA_QUBITS,
            shor_data_qubits=DEFAULT_SHOR_DATA_QUBITS, shor_ancilla_qubits=DEFAULT_SHOR_ANCILLA_QUBITS, show=True):
    # gate_set: which test circuit (a key of GATE_SETS). codes: which codes to compare (keys of CODES).
    # data_qubits / ancilla_qubits: Fez qubits for the bit-flip and phase-flip codes' q_0-q_2 / a_0-a_1
    # shor_data_qubits / shor_ancilla_qubits: Fez qubits for the Shor codes' q_0-q_8 / a_0-a_7 (see set_layout)
    # show=False skips the printing. Returns each run's error, {run: |P(1) - exact P(1)|}, e.g. for
    # "Fez noise, no correction (Fez 86)" and "Fez noise, bit-flip, Toffoli", and the no-correction run each code is
    # compared with, e.g. {"bit-flip, Toffoli": "no correction (Fez 86)"} (src/pay_off/pay_off.py uses both)
    if seed is None:
        seed = random.randrange(10**6)
    circuit = test_circuit(gate_set, num_gates, seed, mirror)
    exact_p1 = Statevector(circuit).probabilities()[1]   # the exact answer, straight from the state: no shots or noise
    plain = circuit.copy()
    plain.measure_all()   # the codes add their own measurement
    encoded, skipped = encode_all(circuit, codes)

    backend = FakeFez()
    layouts = set_layout(backend, data_qubits, ancilla_qubits, shor_data_qubits, shor_ancilla_qubits)
    circuits, plain_for = on_fez(plain, encoded, backend, layouts, seed)
    runs = run_all(plain, circuits, backend, shots, seed)

    if show:
        print_setup(gate_set, num_gates, seed, mirror, shots, layouts, exact_p1, skipped, plain_for)
        print_results(runs, shots, exact_p1)
        print_sizes(circuits, exact_p1)
    return {name: abs(prob_one(counts)[0] / shots - exact_p1) for name, counts in runs}, plain_for


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 100    # how many gates in the circuit
    SHOTS = 1000       # how many times each version of the circuit is run
    SEED = None        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
    GATE_SET = "x"     # "all" = random X, Y, Z, S, T, id     "xz" = random X and Z     "repeat" = X, Y, Z in order,
                       # over and over     "x", "y", "z" = only that gate (Z is done in software on Fez, so it adds no
                       # noise)
    MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0
    # Which codes to compare (keys of CODES). Add "Shor, if blocks" and "Shor, Toffoli" to include the Shor codes,
    # which are much slower and only run Pauli gates (not GATE_SET = "all")
    CODES_TO_RUN = ["bit-flip, if blocks", "bit-flip, Toffoli", "phase-flip, if blocks", "phase-flip, Toffoli"]

    # Which Fez qubits to run on (see set_layout). The defaults are in fez_common.py
    DATA_QUBITS = DEFAULT_DATA_QUBITS                  # bit/phase-flip data q_0, q_1, q_2
    ANCILLA_QUBITS = DEFAULT_ANCILLA_QUBITS            # bit/phase-flip ancilla a_0, a_1 (only the if-block codes use these)
    SHOR_DATA_QUBITS = DEFAULT_SHOR_DATA_QUBITS        # Shor data q_0, ..., q_8
    SHOR_ANCILLA_QUBITS = DEFAULT_SHOR_ANCILLA_QUBITS  # Shor ancilla a_0, ..., a_7 (only "Shor, if blocks" uses these)

    compare(num_gates=NUM_GATES, shots=SHOTS, seed=SEED, gate_set=GATE_SET, mirror=MIRROR, codes=CODES_TO_RUN,
            data_qubits=DATA_QUBITS, ancilla_qubits=ANCILLA_QUBITS,
            shor_data_qubits=SHOR_DATA_QUBITS, shor_ancilla_qubits=SHOR_ANCILLA_QUBITS)
