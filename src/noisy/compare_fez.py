import random

from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector
from qiskit.transpiler import CouplingMap
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

from bit_flip_encoded import bit_flip_encoded
from bit_flip_toffoli import bit_flip_toffoli
from phase_flip_encoded import phase_flip_encoded
from phase_flip_toffoli import phase_flip_toffoli
from shor_encoded import shor_encoded
from shor_toffoli import shor_toffoli

ALL_GATES = ("x", "y", "z", "s", "t", "id")
XZ_GATES = ("x", "z")
REPEAT_GATES = ("x", "y", "z")


def random_circuit(num_gates=100, seed=None, gate_set=ALL_GATES):
    # num_gates random 1-qubit gates picked from gate_set. The same seed always gives the same circuit
    rng = random.Random(seed)
    qc = QuantumCircuit(1)
    for _ in range(num_gates):
        getattr(qc, rng.choice(gate_set))(0)
    return qc


def random_all_gates(num_gates=100, seed=None):
    # Random circuit using every gate in ALL_GATES (X, Y, Z, S, T, id).
    return random_circuit(num_gates, seed, ALL_GATES)


def random_xz_gates(num_gates=100, seed=None):
    # Random circuit using only X and Z. Every code applies these without decoding,
    return random_circuit(num_gates, seed, XZ_GATES)


def repeated_gates(num_gates=100, seed=None):
    # Not random: X, Y, Z, X, Y, Z, ... until there are num_gates gates.
    # seed is ignored here (the circuit is always the same) but still sets the transpiler and simulator seeds
    qc = QuantumCircuit(1)
    for i in range(num_gates):
        getattr(qc, REPEAT_GATES[i % len(REPEAT_GATES)])(0)
    return qc


def x_gates(num_gates=100, seed=None):
    # Not random: num_gates X gates in a row. The exact answer is 1 if num_gates is odd, 0 if even.
    # seed is ignored here (the circuit is always the same) but still sets the transpiler and simulator seeds
    qc = QuantumCircuit(1)
    for _ in range(num_gates):
        qc.x(0)
    return qc


def y_circuit(bit, num_gates):
    # Prepare |bit>, then num_gates Y gates in a row. Used by src/real_hardware_runs, src/physical_qubit_comparison
    # and src/hardware_vs_simulator
    qc = QuantumCircuit(1)
    if bit:
        qc.x(0)
    for _ in range(num_gates):
        qc.y(0)
    return qc


# Which function builds the circuit for each gate_set option
CIRCUIT_FUNCTIONS = {"all": random_all_gates, "xz": random_xz_gates, "repeat": repeated_gates, "x": x_gates}
GATE_NAMES = {"all": ALL_GATES, "xz": XZ_GATES, "repeat": REPEAT_GATES, "x": ("x",)}

# The error-correction codes to compare, and the label printed for each
ENCODERS = {
    "bit-flip, if blocks": bit_flip_encoded,
    "bit-flip, Toffoli": bit_flip_toffoli,
    "phase-flip, if blocks": phase_flip_encoded,
    "phase-flip, Toffoli": phase_flip_toffoli,
    #"Shor, if blocks": shor_encoded,
    #"Shor, Toffoli": shor_toffoli,
}

# Default Fez qubits for each role
DEFAULT_DATA_QUBITS = (87, 88, 86)   # 87 is wired to both 88 and 86, so encoding/decoding need no SWAPs
DEFAULT_ANCILLA_QUBITS = (97, 108)

DEFAULT_SHOR_DATA_QUBITS = (87, 88, 85, 97, 108, 107, 86, 77, 84)
DEFAULT_SHOR_ANCILLA_QUBITS = (89, 109, 65, 83, 78, 90, 110, 118)


def mirrored(circuit):
    # The circuit followed by its inverse, so the exact answer is always 0
    return circuit.compose(circuit.inverse())


def check_no_h(circuit):
    # H has no protected version in any of the codes (all would have to decode around it),
    # so circuits passed to compare() must not contain any
    if "h" in circuit.count_ops():
        raise ValueError(f"circuit contains {circuit.count_ops()['h']} H gate(s); compare() only supports circuits without H")


def working_coupling_map(backend, max_error=0.5):
    # Fez's qubit wiring without the broken connections.
    edges = [pair for pair, props in backend.target["cz"].items()
             if props is None or props.error is None or props.error < max_error]
    return CouplingMap(edges)


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
    # Pick by hand which of Fez's physical qubits each circuit qubit runs on (the DEFAULT_ qubits above by default).
    # data = (Fez qubit for q_0, q_1, q_2), ancillas = (Fez qubit for a_0, a_1) of the bit-flip and phase-flip codes.
    # shor_data = (Fez qubit for q_0, ..., q_8), shor_ancillas = (Fez qubit for a_0, ..., a_7) of the Shor codes.
    # Every code puts its data qubits first and its ancillas after, so each layout is data + ancillas:
    # the Toffoli codes use only the data qubits, and no correction runs on data[0].
    # The two layouts can share Fez qubits, since every code runs on its own
    return {"bit/phase-flip": code_layout(backend, data, ancillas, 3, 2, "bit-flip and phase-flip"),
            "Shor": code_layout(backend, shor_data, shor_ancillas, 9, 8, "Shor")}


def prob_one(counts, register_index=0):
    # Fraction of shots where the measured result was 1.
    # For the encoded circuit the keys look like "out s" and "out" is the first group
    ones = sum(n for key, n in counts.items() if key.split()[register_index] == "1")
    return ones, sum(counts.values()) - ones


def compare(num_gates=1000, shots=1000, seed=None, gate_set="all", mirror=False, encoders=ENCODERS,
            data_qubits=DEFAULT_DATA_QUBITS, ancilla_qubits=DEFAULT_ANCILLA_QUBITS,
            shor_data_qubits=DEFAULT_SHOR_DATA_QUBITS, shor_ancilla_qubits=DEFAULT_SHOR_ANCILLA_QUBITS):
    # gate_set: "all" uses random_all_gates, "xz" uses random_xz_gates, "repeat" uses repeated_gates
    # data_qubits / ancilla_qubits: Fez qubits for the bit-flip and phase-flip codes' q_0-q_2 / a_0-a_1
    # shor_data_qubits / shor_ancilla_qubits: Fez qubits for the Shor codes' q_0-q_8 / a_0-a_7 (see set_layout)

    if seed is None:
        seed = random.randrange(10**6)
    circuit = CIRCUIT_FUNCTIONS[gate_set](num_gates, seed)
    if mirror:
        circuit = mirrored(circuit)
    check_no_h(circuit)

    # Exact answer straight from the state vector (no shots, no noise)
    exact_p1 = Statevector(circuit).probabilities()[1]

    backend = FakeFez()
    noisy_sim = AerSimulator.from_backend(backend)
    ideal_sim = AerSimulator()

    # Add the measurement to the plain circuit; the encoders add their own
    plain = circuit.copy()
    plain.measure_all()

    # Convert every circuit to Fez's gates (cz, rz, sx, x) and fit it onto Fez's qubits.
    # optimization_level=0 keeps every gate: otherwise the transpiler would merge the random
    # gates into one or two
    # Fez's gates and wiring are passed in directly, instead of the backend, so the wiring can leave out
    # Fez's broken connections (see working_coupling_map). The noise comes from noisy_sim when the circuits run
    options = dict(optimization_level=0, routing_method="sabre", seed_transpiler=seed,
                   basis_gates=list(backend.target.operation_names), coupling_map=working_coupling_map(backend))
    # A code that can't run this circuit raises ValueError (the Shor codes only allow Pauli gates,
    # so they are skipped for gate_set="all"); leave it out of the comparison and print why
    encoded, skipped = {}, {}
    for name, encoder in encoders.items():
        try:
            encoded[name] = encoder(circuit)
        except ValueError as err:
            skipped[name] = err

    # Start every run on the same Fez qubits. Otherwise each circuit is placed separately and can land on
    # better or worse qubits, which shows up as a difference between the codes. Every code puts its data
    # qubits first (q_0, q_1, q_2) and its ancillas after, so all codes share q_0-q_2's qubits and
    # no correction gets q_0's qubit.
    # The Shor codes get their own layout, since they have 9 data qubits and 8 ancillas
    layouts = set_layout(backend, data_qubits, ancilla_qubits, shor_data_qubits, shor_ancilla_qubits)

    # build a dict with the fez circuits
    fez_circuits = {"no correction": transpile(plain, initial_layout=layouts["bit/phase-flip"][:1], **options)}
    for name, qc in encoded.items():
        layout = layouts["Shor" if name.startswith("Shor") else "bit/phase-flip"]
        fez_circuits[name] = transpile(qc, initial_layout=layout[:qc.num_qubits], **options)
    #run the circuits
    runs = [("no noise", ideal_sim.run(plain, shots=shots).result().get_counts())]
    for name, fez_circuit in fez_circuits.items():
        counts = noisy_sim.run(fez_circuit, shots=shots, seed_simulator=seed).result().get_counts()
        runs.append((f"Fez noise, {name}", counts))
    #print the results
    kind = "Repeating circuit" if gate_set in ("repeat", "x") else "Random circuit"
    print(f"{kind}: {num_gates} gates from {', '.join(GATE_NAMES[gate_set])}  (seed {seed}"
          f"{', mirrored' if mirror else ''})")
    print(f"Shots per run: {shots}")
    small, shor = layouts["bit/phase-flip"], layouts["Shor"]
    print(f"Fez qubits:    bit/phase-flip data {small[:3]}, ancillas {small[3:]}  (no correction runs on {small[0]})")
    print(f"               Shor data {shor[:9]}, ancillas {shor[9:]}")
    print(f"Exact answer:  P(0) = {1 - exact_p1:.4f}   P(1) = {exact_p1:.4f}")
    for name, err in skipped.items():
        print(f"Skipped {name}: {err}")
    print()

    # Column widths grow to fit the longest run name
    run_width = max(28, max(len(name) for name, _ in runs) + 2)
    print(f"{'run':<{run_width}}{'0':>7}{'1':>7}{'P(1)':>10}{'off from exact':>17}")
    print("-" * (run_width + 41))
    for name, counts in runs:
        ones, zeros = prob_one(counts)
        p1 = ones / shots
        print(f"{name:<{run_width}}{zeros:>7}{ones:>7}{p1:>10.4f}{abs(p1 - exact_p1):>17.4f}")

    print("\nCircuit size on Fez:")
    size_width = max(18, max(len(name) for name in fez_circuits) + 2)
    for name, fez_circuit in fez_circuits.items():
        print(f"  {name:<{size_width}}{fez_circuit.size():>7} gates, depth {fez_circuit.depth()}")
    if 0.35 < exact_p1 < 0.65:
        print("\nNote: the exact answer is close to 50/50, and noise tends to push results toward 50/50,")
        print("so noise is hard to see here. Try another SEED or set MIRROR = True (exact answer is then always 0).")


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 100    # how many random gates in the circuit
    SHOTS = 1000       # how many times each version of the circuit is run
    SEED = None      # a number (e.g. 3) gives the same circuit every time; None picks a new random one
    GATE_SET = "x"     # "all" = X, Y, Z, S, T, id     "xz" = only X and Z     "repeat" = X, Y, Z in order, over and over
                       # "x" = only X gates, NUM_GATES of them
    MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0

    # Which Fez qubits to run on (compare passes these to set_layout). The defaults are the DEFAULT_ qubits at the top
    DATA_QUBITS = DEFAULT_DATA_QUBITS                  # bit/phase-flip data q_0, q_1, q_2 (q_0 is also the no-correction qubit)
    ANCILLA_QUBITS = DEFAULT_ANCILLA_QUBITS            # bit/phase-flip ancilla a_0, a_1 (only the if-block codes use these)
    SHOR_DATA_QUBITS = DEFAULT_SHOR_DATA_QUBITS        # Shor data q_0, ..., q_8
    SHOR_ANCILLA_QUBITS = DEFAULT_SHOR_ANCILLA_QUBITS  # Shor ancilla a_0, ..., a_7 (only "Shor, if blocks" uses these)

    compare(num_gates=NUM_GATES, shots=SHOTS, seed=SEED, gate_set=GATE_SET, mirror=MIRROR,
            data_qubits=DATA_QUBITS, ancilla_qubits=ANCILLA_QUBITS,
            shor_data_qubits=SHOR_DATA_QUBITS, shor_ancilla_qubits=SHOR_ANCILLA_QUBITS)
