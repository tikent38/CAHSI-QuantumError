# compare_fez.py
# Build a random 1-qubit circuit (no H gates) and run it four ways:
#   1. on a noiseless AerSimulator (the exact answer)
#   2. on AerSimulator with IBM Fez's noise, no error correction
#   3. on AerSimulator with IBM Fez's noise, after passing it through bit_flip_encoded
#   4. on AerSimulator with IBM Fez's noise, after passing it through phase_flip_encoded
# then print the results so no correction, bit-flip correction and phase-flip correction can be compared.
#
# Change the settings at the bottom of this file (under __main__), then run:
#   python src/noisy/compare_fez.py
import random

from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

from bit_flip_encoded import bit_flip_encoded
from phase_flip_encoded import phase_flip_encoded

ALL_GATES = ("x", "y", "z", "s", "t", "id")
XZ_GATES = ("x", "z")


def random_circuit(num_gates=100, seed=None, gate_set=ALL_GATES):
    # num_gates random 1-qubit gates picked from gate_set. The same seed always gives the same circuit
    rng = random.Random(seed)
    qc = QuantumCircuit(1)
    for _ in range(num_gates):
        getattr(qc, rng.choice(gate_set))(0)
    return qc


def random_all_gates(num_gates=100, seed=None):
    # Random circuit using every gate in ALL_GATES (X, Y, Z, S, T, id).
    # Both codes apply all of these without decoding, so no extra CNOTs
    return random_circuit(num_gates, seed, ALL_GATES)


def random_xz_gates(num_gates=100, seed=None):
    # Random circuit using only X and Z. Both codes apply these to all 3 qubits,
    # so no extra CNOTs. The exact answer is always 0 or 1, never in between
    return random_circuit(num_gates, seed, XZ_GATES)


# Which function builds the circuit for each gate_set option
CIRCUIT_FUNCTIONS = {"all": random_all_gates, "xz": random_xz_gates}
GATE_NAMES = {"all": ALL_GATES, "xz": XZ_GATES}

# The error-correction codes to compare, and the label printed for each
ENCODERS = {"bit-flip code": bit_flip_encoded, "phase-flip code": phase_flip_encoded}


def mirrored(circuit):
    # The circuit followed by its inverse, so the exact answer is always 0
    return circuit.compose(circuit.inverse())


def check_no_h(circuit):
    # H has no protected version in either code (both would have to decode around it),
    # so circuits passed to compare() must not contain any
    if "h" in circuit.count_ops():
        raise ValueError(f"circuit contains {circuit.count_ops()['h']} H gate(s); compare() only supports circuits without H")


def prob_one(counts, register_index=0):
    # Fraction of shots where the measured result was 1.
    # For the encoded circuit the keys look like "out s" and "out" is the first group
    ones = sum(n for key, n in counts.items() if key.split()[register_index] == "1")
    return ones, sum(counts.values()) - ones


def compare(num_gates=1000, shots=1000, seed=None, gate_set="all", mirror=False):
    # gate_set: "all" uses random_all_gates, "xz" uses random_xz_gates
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
    # gates into one or two, and the comparison would hide the noise from the extra gates
    options = dict(optimization_level=0, layout_method="sabre", routing_method="sabre", seed_transpiler=seed)
    # build a dict with the fez circuits
    fez_circuits = {"no correction": transpile(plain, noisy_sim, **options)}
    for name, encoder in ENCODERS.items():
        fez_circuits[name] = transpile(encoder(circuit), noisy_sim, **options)
    #run the circuits
    runs = [("no noise", ideal_sim.run(plain, shots=shots).result().get_counts())]
    for name, fez_circuit in fez_circuits.items():
        counts = noisy_sim.run(fez_circuit, shots=shots, seed_simulator=seed).result().get_counts()
        runs.append((f"Fez noise, {name}", counts))
    #print the results
    print(f"Random circuit: {num_gates} gates from {', '.join(GATE_NAMES[gate_set])}  (seed {seed}"
          f"{', mirrored' if mirror else ''})")
    print(f"Shots per run: {shots}")
    print(f"Exact answer:  P(0) = {1 - exact_p1:.4f}   P(1) = {exact_p1:.4f}\n")

    print(f"{'run':<28}{'0':>7}{'1':>7}{'P(1)':>10}{'off from exact':>17}")
    print("-" * 69)
    for name, counts in runs:
        ones, zeros = prob_one(counts)
        p1 = ones / shots
        print(f"{name:<28}{zeros:>7}{ones:>7}{p1:>10.4f}{abs(p1 - exact_p1):>17.4f}")

    print("\nCircuit size on Fez:")
    for name, fez_circuit in fez_circuits.items():
        print(f"  {name:<18}{fez_circuit.size():>7} gates, depth {fez_circuit.depth()}")
    if 0.35 < exact_p1 < 0.65:
        print("\nNote: the exact answer is close to 50/50, and noise tends to push results toward 50/50,")
        print("so noise is hard to see here. Try another SEED or set MIRROR = True (exact answer is then always 0).")


if __name__ == "__main__":
    # ---- Settings: change these to run a different experiment ----
    NUM_GATES = 300    # how many random gates in the circuit
    SHOTS = 1000       # how many times each version of the circuit is run
    SEED = 3        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
    GATE_SET = "all"   # "all" = X, Y, Z, S, T, id     "xz" = only X and Z
    MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0

    compare(num_gates=NUM_GATES, shots=SHOTS, seed=SEED, gate_set=GATE_SET, mirror=MIRROR)
