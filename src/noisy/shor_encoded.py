# shor_encoded.py
# Turn any 1-qubit circuit into its 9-qubit Shor-code version:
# encode, apply the circuit's gates, measure the syndromes, and correct one X and one Z error.
# The Shor code is the phase-flip code with each of its 3 qubits encoded again with the bit-flip code,
# giving 3 blocks of 3 qubits: q_0-q_2, q_3-q_5, q_6-q_8

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Gates that work directly on the encoded state, without decoding:
#   logical X = Z on all 9 qubits: ZZZ turns each block's |000> + |111> into |000> - |111>
#               (|111> picks up (-1)^3 = -1), which swaps the encoded |0> and |1>
#   logical Z = X on all 9 qubits: XXX leaves each block's |000> + |111> alone and multiplies
#               |000> - |111> by -1, so the encoded |1> gets (-1)^3 = -1 and the encoded |0> is unchanged
#   logical Y = both (Y = iXZ, the i is only a global phase)
# Only these Pauli gates are allowed. Other gates (H, S, T, ...) have no version that works on
# the encoded state, so part of the code would have to be decoded around them. While decoded,
# a single error can become a logical error that the correction at the end can't fix
LOGICAL_GATES = {"id", "x", "y", "z"}
LOGICAL_X_QUBITS = range(9)
LOGICAL_Z_QUBITS = range(9)

BLOCKS = (0, 3, 6) # first qubit of each block


def encode_block(qc, data, first):
    # Bit-flip code inside one block:  |+> -> |000> + |111>,  |-> -> |000> - |111>
    qc.cx(data[first], data[first + 1])
    qc.cx(data[first], data[first + 2])


def decode_block(qc, data, first):
    # Undo encode_block
    qc.cx(data[first], data[first + 2])
    qc.cx(data[first], data[first + 1])


def encode(qc, data):
    # Outer code first: the phase-flip code on q_0, q_3, q_6:  a|0> + b|1>  ->  a|+++> + b|--->
    qc.cx(data[0], data[3])
    qc.cx(data[0], data[6])
    qc.h([data[first] for first in BLOCKS])
    # Then the bit-flip code inside each block
    for first in BLOCKS:
        encode_block(qc, data, first)


def decode(qc, data):
    # Undo encode in reverse order:  encoded state  ->  a|0> + b|1> on q_0
    for first in BLOCKS:
        decode_block(qc, data, first)
    qc.h([data[first] for first in BLOCKS])
    qc.cx(data[0], data[6])
    qc.cx(data[0], data[3])


def shor_encoded(circuit, measure=True):
    # Returns the Shor-code version of a 1-qubit circuit (no measurements in it, Pauli gates only).
    # measure=True also decodes and measures the result into the "out" register;
    # measure=False leaves the corrected state encoded
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(9, "q") # our 9 qubits representing the 1 we are protecting
    anc = QuantumRegister(8, "a") # a_0-a_5: bit-flip checks (2 per block), a_6-a_7: phase-flip checks
    # one 2-bit bit-flip syndrome per block, and one 2-bit phase-flip syndrome
    bit_syndromes = [ClassicalRegister(2, f"b{block}") for block in range(3)]
    phase_syndrome = ClassicalRegister(2, "p")
    qc = QuantumCircuit(data, anc, *bit_syndromes, phase_syndrome)

    # 1. Create the encoded |0>. All qubits start at |0>, so this is the encoded |0> (a=1, b=0);
    #    the gates in step 2 are what set a and b
    encode(qc, data)
    qc.barrier()

    # 2. Apply every gate from the passed in circuit to the encoded qubit
    for inst in circuit.data:
        gate = inst.operation
        if gate.name == "barrier":
            continue
        if gate.name == "measure":
            raise ValueError("leave measurements out of the circuit; use measure=True instead")
        if gate.name not in LOGICAL_GATES:
            raise ValueError(f"the Shor code only supports Pauli gates ({', '.join(sorted(LOGICAL_GATES))}), "
                             f"got '{gate.name}' (see LOGICAL_GATES)")

        # Apply the logical version (see LOGICAL_GATES above)
        if gate.name == "id":
            for q in data:
                qc.id(q)
        if gate.name in ("x", "y"):
            for q in LOGICAL_X_QUBITS:
                qc.z(data[q])
        if gate.name in ("z", "y"):
            for q in LOGICAL_Z_QUBITS:
                qc.x(data[q])
    qc.barrier()

    # 3. Bit-flip check: measure the pairwise parities inside each block, the same as bit_flip_encoded
    for block, first in enumerate(BLOCKS):
        a0, a1 = anc[2 * block], anc[2 * block + 1]
        qc.cx(data[first], a0)
        qc.cx(data[first + 1], a0)
        qc.cx(data[first + 1], a1)
        qc.cx(data[first + 2], a1)
        qc.measure([a0, a1], bit_syndromes[block])

    # 4. Flip back the qubit each block's syndrome points to
    # 1 = 01 -> first qubit flipped,  3 = 11 -> middle qubit flipped,  2 = 10 -> last qubit flipped,  0 = 00 -> no correction
    for block, first in enumerate(BLOCKS):
        with qc.switch(bit_syndromes[block]) as case:
            with case(1):
                qc.x(data[first])
            with case(3):
                qc.x(data[first + 1])
            with case(2):
                qc.x(data[first + 2])

    # 5. Phase-flip check, the course's simplified version (the same as noiseless/shor_code.py):
    #    compare the signs of neighbouring blocks.
    #   \
    qc.h([anc[6], anc[7]])
    for q in range(0, 6):
        qc.cx(anc[6], data[q])
    for q in range(3, 9):
        qc.cx(anc[7], data[q])
    qc.h([anc[6], anc[7]])
    qc.measure([anc[6], anc[7]], phase_syndrome)

    # 6. Fix the sign of the block the phase syndrome points to. A Z on any one qubit of a block
    #    flips the sign of the whole block, so use the block's first qubit
    # 1 = 01 -> block 0,  3 = 11 -> block 1,  2 = 10 -> block 2,  0 = 00 -> no correction
    with qc.switch(phase_syndrome) as case:
        with case(1):
            qc.z(data[0])
        with case(3):
            qc.z(data[3])
        with case(2):
            qc.z(data[6])

    # 7. (optional) Decode back to q_0 and measure it
    if measure:
        qc.barrier()
        decode(qc, data)
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc
