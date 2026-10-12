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


# Which function builds the circuit for each gate_set option
CIRCUIT_FUNCTIONS = {"all": random_all_gates, "xz": random_xz_gates, "repeat": repeated_gates}
GATE_NAMES = {"all": ALL_GATES, "xz": XZ_GATES, "repeat": REPEAT_GATES}

# The error-correction codes to compare, and the label printed for each
ENCODERS = {
    "bit-flip, if blocks": bit_flip_encoded,
    "bit-flip, Toffoli": bit_flip_toffoli,
    "phase-flip, if blocks": phase_flip_encoded,
    "phase-flip, Toffoli": phase_flip_toffoli,
    "Shor, if blocks": shor_encoded,
    "Shor, Toffoli": shor_toffoli,
}


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


def prob_one(counts, register_index=0):
    # Fraction of shots where the measured result was 1.
    # For the encoded circuit the keys look like "out s" and "out" is the first group
    ones = sum(n for key, n in counts.items() if key.split()[register_index] == "1")
    return ones, sum(counts.values()) - ones


def compare(num_gates=1000, shots=1000, seed=None, gate_set="all", mirror=False, encoders=ENCODERS):
    # gate_set: "all" uses random_all_gates, "xz" uses random_xz_gates, "repeat" uses repeated_gates

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

    # Pick Fez's physical qubits once, for the encoded circuit with the most qubits, and start every
    # run on those same qubits. Otherwise each circuit is placed separately and can land on better or
    # worse qubits, which shows up as a difference between the codes. Every code puts its data qubits first
    # (q_0, q_1, q_2, ...) and its ancillas after, so all codes share q_0-q_2's qubits and no correction
    # gets q_0's qubit. 
    # With the Shor code included, the largest circuit is the 17-qubit Shor code, so the
    # bit-flip and phase-flip ancillas land on Shor's q_3 and q_4.

    # generate the qubit layout so its shared between all runs
    largest = max(encoded.values(), key=lambda qc: qc.num_qubits)
    layout = transpile(largest, layout_method="sabre", **options).layout.initial_index_layout(filter_ancillas=True)

    # build a dict with the fez circuits
    fez_circuits = {"no correction": transpile(plain, initial_layout=layout[:1], **options)}
    for name, qc in encoded.items():
        fez_circuits[name] = transpile(qc, initial_layout=layout[:qc.num_qubits], **options)
    #run the circuits
    runs = [("no noise", ideal_sim.run(plain, shots=shots).result().get_counts())]
    for name, fez_circuit in fez_circuits.items():
        counts = noisy_sim.run(fez_circuit, shots=shots, seed_simulator=seed).result().get_counts()
        runs.append((f"Fez noise, {name}", counts))
    #print the results
    kind = "Repeating circuit" if gate_set == "repeat" else "Random circuit"
    print(f"{kind}: {num_gates} gates from {', '.join(GATE_NAMES[gate_set])}  (seed {seed}"
          f"{', mirrored' if mirror else ''})")
    print(f"Shots per run: {shots}")
    print(f"Fez qubits:    {layout}  (in order q_0, q_1, q_2, ... of the largest circuit)")
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
    NUM_GATES = 300    # how many random gates in the circuit
    SHOTS = 1000       # how many times each version of the circuit is run
    SEED = 3        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
    GATE_SET = "repeat"  # "all" = X, Y, Z, S, T, id     "xz" = only X and Z     "repeat" = X, Y, Z in order, over and over
    MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0

    compare(num_gates=NUM_GATES, shots=SHOTS, seed=SEED, gate_set=GATE_SET, mirror=MIRROR)
