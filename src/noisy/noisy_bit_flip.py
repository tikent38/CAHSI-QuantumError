# noisy_bit_flip.py
# Run any 1-qubit circuit with the 3-qubit bit-flip code on a noisy Aer simulator:
# encode, apply each gate from the circuit, measure the syndrome, correct the error,
# and compare against running the same circuit with no error correction.
# See notes/error_codes.md for the theory and syndrome table.
import math
import random

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, pauli_error

SHOTS = 1000

# Gates that work directly on the encoded state: applying the gate to all 3 data qubits
# does the same thing to a|000> + b|111> as the gate does to a|0> + b|1>
# (e.g. XXX turns a|000> + b|111> into a|111> + b|000>). These stay protected the whole time
LOGICAL_GATES = {"id", "x", "y", "z"}


def encode(qc, data):
    # a|0> + b|1> on q_0  ->  a|000> + b|111>
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])


def decode(qc, data):
    # a|000> + b|111>  ->  a|0> + b|1> on q_0
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])


def syndrome_check(qc, data, anc, syndrome, correct):
    # Measure the pairwise parities a_0 = q_0 xor q_1 and a_1 = q_1 xor q_2,
    # then (if correct is True) apply an X to the qubit the syndrome points to
    qc.reset(anc) # ancillas get reused every round, so start them back at |0>
    qc.cx(data[0], anc[0])
    qc.cx(data[1], anc[0])
    qc.cx(data[1], anc[1])
    qc.cx(data[2], anc[1])
    qc.measure(anc, syndrome)

    if correct:
        # 1 = 01 -> q_0 flipped,  3 = 11 -> q_1 flipped,  2 = 10 -> q_2 flipped,  0 = 00 -> no correction
        with qc.switch(syndrome) as case:
            with case(1):
                qc.x(data[0])
            with case(3):
                qc.x(data[1])
            with case(2):
                qc.x(data[2])


def bit_flip_circuit(circuit, correct=True):
    # Build the error-corrected version of a 1-qubit circuit. After every gate the syndrome
    # is measured (and the error corrected), so errors get fixed before they can pile up
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(3, "q") # our 3 qubits representing the 1 we are protecting
    anc = QuantumRegister(2, "a")
    qc = QuantumCircuit(data, anc)

    # 1. Encode |0> -> |000> (nothing to do; all qubits start at |0>)

    # 2. Apply each gate from the original circuit, then check for errors
    gates = [inst.operation for inst in circuit.data if inst.operation.name != "barrier"]
    for i, gate in enumerate(gates):
        if gate.name == "measure":
            raise ValueError("leave measurements out of the circuit; the result is measured at the end")

        if gate.name in LOGICAL_GATES:
            # Protected: apply the gate to all 3 data qubits
            for q in data:
                qc.append(gate, [q])
        else:
            # Gates like H, S, T have no simple encoded version: decode, apply to q_0, re-encode.
            # The qubit is NOT protected while this gate runs
            decode(qc, data)
            qc.append(gate, [data[0]])
            encode(qc, data)

        syndrome = ClassicalRegister(2, f"s{i}") # one syndrome register per check
        qc.add_register(syndrome)
        syndrome_check(qc, data, anc, syndrome, correct)
        qc.barrier()

    # 3. Decode back to q_0 and measure it
    decode(qc, data)
    out = ClassicalRegister(1, "out")
    qc.add_register(out)
    qc.measure(data[0], out[0])
    return qc


def run_encoded(circuit, noise_model, correct=True, shots=SHOTS):
    # Run the circuit with the bit-flip code. Returns counts of the final answer, e.g. {"0": 990, "1": 10}
    qc = bit_flip_circuit(circuit, correct)
    counts = AerSimulator(noise_model=noise_model).run(qc, shots=shots).result().get_counts()

    # "out" was added last, so it's the first group in each key: "out s_n ... s_0"
    result = {"0": 0, "1": 0}
    for key, n in counts.items():
        result[key.split()[0]] += n
    return result


def run_unencoded(circuit, noise_model, shots=SHOTS):
    # Run the original circuit on 1 qubit with the same noise and no error correction
    qc = circuit.copy()
    qc.measure_all()
    counts = AerSimulator(noise_model=noise_model).run(qc, shots=shots).result().get_counts()
    return {"0": counts.get("0", 0), "1": counts.get("1", 0)}


def random_circuit(n_gates, gate_set=("x", "z", "h", "s", "t"), idle_steps=0, seed=None):
    # n_gates random 1-qubit gates, each followed by idle_steps id gates (time spent waiting).
    # Mirrored: the gates are followed by their inverse, so the ideal output is always 0
    # and every 1 that gets measured is an error, whatever gates were picked
    rng = random.Random(seed)
    qc = QuantumCircuit(1)
    for _ in range(n_gates):
        getattr(qc, rng.choice(gate_set))(0)
        for _ in range(idle_steps):
            qc.id(0)
    return qc.compose(qc.inverse())


def bit_flip_noise(p, every_gate=True):
    # Each gate has probability p of being followed by an X (bit flip) on each qubit it touches.
    # every_gate=False only puts noise on id gates (errors while the qubit waits), so the
    # error-correction gates themselves are perfect
    flip = pauli_error([("X", p), ("I", 1 - p)])
    noise = NoiseModel()
    if every_gate:
        noise.add_all_qubit_quantum_error(flip, ["id", "x", "y", "z", "h", "s", "sdg", "t", "tdg"])
        noise.add_all_qubit_quantum_error(flip.tensor(flip), ["cx"])
    else:
        noise.add_all_qubit_quantum_error(flip, ["id"])
    return noise


def error_rate(counts):
    # The circuits are mirrored, so the right answer is always 0
    return counts["1"] / (counts["0"] + counts["1"])


def compare(p_values, every_gate, n_circuits=5, n_gates=5, idle_steps=2):
    # Run n_circuits random circuits each way at every p and print the average error rates
    where = "every gate" if every_gate else "idle steps only"
    print(f"\nBit-flip noise on {where}  ({n_circuits} random circuits x {SHOTS} shots each way)")
    print(f"  {'p':>6}{'unencoded':>14}{'detect only':>14}{'corrected':>14}   does correction help?")
    print("  " + "-" * 76)
    total_shots = n_circuits * SHOTS
    for p in p_values:
        noise = bit_flip_noise(p, every_gate)
        rates = [0.0, 0.0, 0.0]
        for seed in range(n_circuits):
            circuit = random_circuit(n_gates, idle_steps=idle_steps, seed=seed)
            rates[0] += error_rate(run_unencoded(circuit, noise)) / n_circuits
            rates[1] += error_rate(run_encoded(circuit, noise, correct=False)) / n_circuits
            rates[2] += error_rate(run_encoded(circuit, noise, correct=True)) / n_circuits

        # Differences smaller than ~2 standard errors could just be shot noise
        unencoded, corrected = rates[0], rates[2]
        margin = 2 * math.sqrt((unencoded * (1 - unencoded) + corrected * (1 - corrected)) / total_shots)
        if corrected < unencoded - margin:
            verdict = "yes, fewer errors than unencoded"
        elif corrected > unencoded + margin:
            verdict = "no, MORE errors than unencoded"
        else:
            verdict = "no clear difference"
        print(f"  {p:>6}" + "".join(f"{r:>14.3f}" for r in rates) + f"   {verdict}")


if __name__ == "__main__":
    example = random_circuit(3, idle_steps=1, seed=0)
    print("Example random circuit (mirrored, ideal output is always 0):\n")
    print(example.draw(fold=-1))
    print("\nIts bit-flip-code version:\n")
    print(bit_flip_circuit(example).draw(fold=-1))

    P_VALUES = [0.001, 0.005, 0.01, 0.05, 0.1]
    compare(P_VALUES, every_gate=False)
    compare(P_VALUES, every_gate=True)
