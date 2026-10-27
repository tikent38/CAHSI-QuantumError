# bit_flip_toffoli.py
# The same bit-flip code as bit_flip_encoded.py, but the error is corrected with a Toffoli (CCNOT) gate
# inside the circuit instead of measuring ancillas and using if blocks
# Only 3 qubits: after decoding, q_1 and q_2 hold the syndrome, so no separate ancillas are needed.
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Reuse the encoding and the gate handling from bit_flip_encoded.py, so the only difference is the correction
from bit_flip_encoded import apply_gates, decode, encode


def bit_flip_toffoli(circuit, measure=True):
    # Returns the bit-flip-code version of a 1-qubit circuit (no measurements in it), corrected with a Toffoli.
    # measure=True also measures the result into the "out" register;
    # measure=False leaves the corrected state decoded on q_0, with the syndrome left on q_1 and q_2.
    # Encoding makes a|000> + b|111>, and after decoding q_1 and q_2 are the syndrome:
    #   q_1 q_2 = 0 0 -> no flip,  1 0 -> q_1 flipped,  0 1 -> q_2 flipped,  1 1 -> q_0 flipped
    return toffoli_code(circuit, measure, encode, apply_gates, decode)


def toffoli_code(circuit, measure, encode, apply_gates, decode):
    # A 3-qubit code corrected with a Toffoli, built from that code's own encode, apply_gates and decode.
    # phase_flip_toffoli.py uses this too: decoding the phase-flip code turns a sign flip back into a bit flip,
    # so from there the correction is the same
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(3, "q")   # the 3 qubits that together hold the 1 qubit being protected
    qc = QuantumCircuit(data)

    # 1. Encode. All qubits start at |0>, so this makes the encoded |0> (a=1, b=0);
    #    the gates in step 2 are what set a and b
    encode(qc, data)
    qc.barrier()

    # 2. Apply every gate from the passed in circuit to the encoded qubit (the same as the if-block version)
    apply_gates(qc, data, circuit)
    qc.barrier()

    # 3. Decode. q_1 and q_2 are now the syndrome. A flip on q_1 or q_2 stays on that qubit and doesn't
    #    reach q_0, so only a flip on q_0 (q_1 q_2 = 1 1) needs fixing
    decode(qc, data)

    # 4. Flip q_0 back only when q_1 and q_2 are both 1. Does the same job as the measurement and
    #    if blocks in the if-block version, but inside the circuit, with no measurement
    qc.ccx(data[1], data[2], data[0])

    # 5. (optional) Measure q_0
    if measure:
        qc.barrier()
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc
