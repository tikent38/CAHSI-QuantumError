# qec_runner.py
# Run any 1-qubit circuit with 3-qubit error correction (bit-flip or phase-flip code),
# with a syndrome check + correction after every gate, and compare it to running the
# same circuit unencoded. See notes/error_codes.md for the theory and syndrome tables.
import random

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error, pauli_error

SHOTS = 4000

# 1-qubit gates the noise models add errors to
ONE_QUBIT_GATES = ["id", "x", "y", "z", "h", "s", "sdg", "t", "tdg", "rx", "ry", "rz", "sx"]

# Gates with a simple logical version: applying the gate to all 3 data qubits acts
# on the encoded state the same way the gate acts on one qubit (logical X = XXX, logical Z = ZZZ
# for both codes, because of the extra H in the phase-flip encoding below)
LOGICAL_GATES = {
    "bit_flip":   {"id": "id", "x": "x", "z": "z"},
    "phase_flip": {"id": "id", "x": "x", "z": "z"},
}


def encode(qc, data, code):
    # Bit flip:   a|0> + b|1>  ->  a|000> + b|111>
    # Phase flip: a|+> + b|->  ->  a|+++> + b|--->
    # The phase-flip version adds an H on q_0 before the encoding from the notes. Without it,
    # a code failure (ZZZ) acts as a logical bit flip, so it couldn't be compared fairly with an
    # unencoded qubit, where Z noise causes phase flips. With it, a failure is a logical phase flip
    if code == "phase_flip":
        qc.h(data[0])
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])
    if code == "phase_flip":
        qc.h(data)


def decode(qc, data, code):
    # Undo encode, leaving the logical state on q_0
    if code == "phase_flip":
        qc.h(data)
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])
    if code == "phase_flip":
        qc.h(data[0])


def syndrome_check(qc, data, anc, syndrome, code):
    # Measure the pairwise parities into syndrome, then apply the correction gate.
    # Ancillas are reset first so they can be reused every round
    qc.reset(anc)
    if code == "bit_flip":
        qc.cx(data[0], anc[0])
        qc.cx(data[1], anc[0])
        qc.cx(data[1], anc[1])
        qc.cx(data[2], anc[1])
    else:
        # Parities in the +/- basis using phase kickback (see notes)
        qc.h(anc)
        qc.cx(anc[0], data[0])
        qc.cx(anc[0], data[1])
        qc.cx(anc[1], data[1])
        qc.cx(anc[1], data[2])
        qc.h(anc)
    qc.measure(anc, syndrome)

    # 1 = 01 -> q_0 flipped,  3 = 11 -> q_1 flipped,  2 = 10 -> q_2 flipped,  0 = 00 -> no correction
    with qc.switch(syndrome) as case:
        for value, qbit in [(1, 0), (3, 1), (2, 2)]:
            with case(value):
                if code == "bit_flip":
                    qc.x(data[qbit])
                else:
                    qc.z(data[qbit])


def build_encoded_circuit(circuit, code="bit_flip"):
    # Build the error-corrected version of a 1-qubit circuit:
    # encode |0>, run each gate on the encoded qubits followed by a syndrome check,
    # then decode and measure the logical qubit into "out"
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")
    if code not in LOGICAL_GATES:
        raise ValueError(f"code must be 'bit_flip' or 'phase_flip', got {code!r}")

    data = QuantumRegister(3, "q")
    anc = QuantumRegister(2, "a")
    qc = QuantumCircuit(data, anc)

    encode(qc, data, code)
    qc.barrier()

    gates = [inst for inst in circuit.data if inst.operation.name != "barrier"]
    for i, inst in enumerate(gates):
        op = inst.operation
        if op.name == "measure":
            raise ValueError("leave measurements out of the circuit; the logical qubit is measured at the end")

        logical = LOGICAL_GATES[code].get(op.name)
        if logical is not None:
            # Protected: apply the logical version to all 3 data qubits
            for q in data:
                getattr(qc, logical)(q)
        else:
            # No simple logical version (e.g. H, Ry): decode, apply to q_0, re-encode.
            # The qubit is NOT protected while this gate runs
            decode(qc, data, code)
            qc.append(op, [data[0]])
            encode(qc, data, code)

        syndrome = ClassicalRegister(2, f"s{i}")
        qc.add_register(syndrome)
        syndrome_check(qc, data, anc, syndrome, code)
        qc.barrier()

    if not gates:
        # Empty circuit: still do one check so the code does something
        syndrome = ClassicalRegister(2, "s0")
        qc.add_register(syndrome)
        syndrome_check(qc, data, anc, syndrome, code)
        qc.barrier()

    decode(qc, data, code)
    out = ClassicalRegister(1, "out")
    qc.add_register(out)
    qc.measure(data[0], out[0])
    return qc


def run_with_code(circuit, code="bit_flip", noise_model=None, shots=SHOTS):
    # Run the circuit with error correction. Returns counts of the logical output, e.g. {"0": 3990, "1": 10}
    qc = build_encoded_circuit(circuit, code)
    counts = AerSimulator(noise_model=noise_model).run(qc, shots=shots).result().get_counts()

    # "out" was added last, so it's the first group in each key: "out s_n ... s_0"
    logical = {"0": 0, "1": 0}
    for key, n in counts.items():
        logical[key.split()[0]] += n
    return logical


def run_unencoded(circuit, noise_model=None, shots=SHOTS):
    # Baseline: run the circuit on a single qubit with the same noise, no error correction
    qc = circuit.copy()
    qc.measure_all()
    counts = AerSimulator(noise_model=noise_model).run(qc, shots=shots).result().get_counts()
    return {"0": counts.get("0", 0), "1": counts.get("1", 0)}


def logical_error_rate(circuit, counts):
    # Fraction of shots that gave the wrong answer. Needs a circuit whose ideal
    # (noise-free) output is always 0 or always 1, so "wrong" is well defined
    probs = Statevector(circuit).probabilities()
    if max(probs) < 1 - 1e-9:
        raise ValueError("logical_error_rate needs a circuit whose ideal output is always 0 or always 1")
    expected = "0" if probs[0] > 0.5 else "1"
    wrong = "1" if expected == "0" else "0"
    return counts[wrong] / sum(counts.values())


def make_noise_model(kind, p):
    # kind: "bit_flip", "phase_flip", "depolarizing", or "measurement"; p is the physical error rate.
    # Gate noise is added after every 1-qubit gate (each qubit of a CNOT gets its own error)
    noise = NoiseModel()
    if kind == "measurement":
        noise.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
        return noise

    if kind == "bit_flip":
        error_1q = pauli_error([("X", p), ("I", 1 - p)])
        error_2q = error_1q.tensor(error_1q)
    elif kind == "phase_flip":
        error_1q = pauli_error([("Z", p), ("I", 1 - p)])
        error_2q = error_1q.tensor(error_1q)
    elif kind == "depolarizing":
        error_1q = depolarizing_error(p, 1)
        error_2q = depolarizing_error(p, 2)
    else:
        raise ValueError(f"unknown noise kind {kind!r}")

    noise.add_all_qubit_quantum_error(error_1q, ONE_QUBIT_GATES)
    noise.add_all_qubit_quantum_error(error_2q, ["cx"])
    return noise


def idle_only_noise(kind, p):
    # Noise only on id gates (errors while the qubit waits), none on the code's own gates
    pauli = "X" if kind == "bit_flip" else "Z"
    noise = NoiseModel()
    noise.add_all_qubit_quantum_error(pauli_error([(pauli, p), ("I", 1 - p)]), ["id"])
    return noise


def random_circuit(n_gates, gate_set=("x", "z", "h", "s", "t"), idle_steps=0, seed=None):
    # n_gates random gates from gate_set on 1 qubit, each followed by idle_steps id gates
    # (time spent waiting, where idle noise can hit). Pass a seed to get the same circuit every time
    rng = random.Random(seed)
    qc = QuantumCircuit(1)
    for _ in range(n_gates):
        getattr(qc, rng.choice(gate_set))(0)
        for _ in range(idle_steps):
            qc.id(0)
    return qc


def mirror(circuit):
    # The circuit followed by its inverse. The ideal output is always 0,
    # so every 1 that gets measured is an error, whatever gates were picked
    return circuit.compose(circuit.inverse())


def run_experiment(circuit, noise_model, code="bit_flip", shots=SHOTS):
    # Run the circuit unencoded and with error correction under the same noise.
    # Returns (unencoded error rate, encoded error rate)
    unencoded = logical_error_rate(circuit, run_unencoded(circuit, noise_model, shots))
    encoded = logical_error_rate(circuit, run_with_code(circuit, code, noise_model, shots))
    return unencoded, encoded


if __name__ == "__main__":
    SHOTS_PER_RUN = 1000
    P_VALUES = [0.001, 0.01, 0.05, 0.1]

    # A random 5-gate circuit with 2 idle steps after each gate, mirrored so the ideal output is always 0
    circuit = mirror(random_circuit(5, idle_steps=2, seed=1))
    print("Random circuit (mirrored):\n")
    print(circuit.draw(fold=-1))

    for label, make_noise in [("noise on every gate", make_noise_model),
                              ("idle-only noise", idle_only_noise)]:
        print(f"\nBit-flip code vs unencoded, bit_flip {label}  ({SHOTS_PER_RUN} shots each)")
        print(f"  {'p':>6}{'unencoded':>12}{'encoded':>12}   result")
        for p in P_VALUES:
            unencoded, encoded = run_experiment(circuit, make_noise("bit_flip", p), "bit_flip", SHOTS_PER_RUN)
            if encoded < unencoded:
                result = "code helps"
            elif encoded > unencoded:
                result = "code makes it worse"
            else:
                result = "no difference"
            print(f"  {p:>6}{unencoded:>12.3f}{encoded:>12.3f}   {result}")
