# shor_code.py
# 9-qubit Shor code: protects one qubit from any single-qubit error (X, Z, or Y = both at once).
# It is the phase-flip code with each of its 3 qubits encoded again with the bit-flip code,
# giving 3 blocks of 3 qubits: q_0-q_2, q_3-q_5, q_6-q_8

# Follows the course's steps: check each block for bit flips, then check for phase flips with the
# course's simplified Z error detection. 
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

BLOCKS = (0, 3, 6) # first qubit of each block


def encode_block(qc, data, first):
    # Bit-flip code inside one block:  |+> -> |000> + |111>,  |-> -> |000> - |111>
    qc.cx(data[first], data[first + 1])
    qc.cx(data[first], data[first + 2])


def decode_block(qc, data, first):
    # Undo encode_block
    qc.cx(data[first], data[first + 2])
    qc.cx(data[first], data[first + 1])


def shor_code(state_prep, x_errors=None, z_errors=None):

    if state_prep.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {state_prep.num_qubits} qubits")

    data = QuantumRegister(9, "q") # our 9 qubits representing the 1 we are protecting
    anc = QuantumRegister(8, "a") # a_0-a_5: bit-flip checks (2 per block), a_6-a_7: phase-flip checks
    # one 2-bit bit-flip syndrome per block, and one 2-bit phase-flip syndrome
    bit_syndromes = [ClassicalRegister(2, f"b{block}") for block in range(3)]
    phase_syndrome = ClassicalRegister(2, "p")
    qc = QuantumCircuit(data, anc, *bit_syndromes, phase_syndrome) #make the QuantumCircuit

    # 1. Prepare the state we want to protect on q_0
    for inst in state_prep.data:
        qc.append(inst.operation, [data[0]])

    # 2. Encode, outer code first: the phase-flip code on q_0, q_3, q_6
    #    a|0> + b|1>  ->  a|+++> + b|--->
    qc.cx(data[0], data[3])
    qc.cx(data[0], data[6])

    qc.h([data[first] for first in BLOCKS])
    qc.barrier()
    #    then the bit-flip code inside each block
    for first in BLOCKS:
        encode_block(qc, data, first)
    qc.barrier()

    # Optional apply error X and Z gates to qubits (X and Z on the same qubit is a Y error)
    if x_errors is not None or z_errors is not None:
        for qbit in x_errors or []:
            qc.x(data[qbit])
        for qbit in z_errors or []:
            qc.z(data[qbit])
        qc.barrier()

    # 3. Bit-flip check: the bit-flip code's pairwise parities, done separately in each block
    for block, first in enumerate(BLOCKS):
        a0, a1 = anc[2 * block], anc[2 * block + 1]
        qc.cx(data[first], a0)
        qc.cx(data[first + 1], a0)
        qc.cx(data[first + 1], a1)
        qc.cx(data[first + 2], a1)
        qc.measure([a0, a1], bit_syndromes[block])
        qc.barrier()
    

    # 4. Phase-flip check, the course's simplified version
    qc.h([anc[6], anc[7]])
    for q in range(0, 6):
        qc.cx(anc[6], data[q])
    for q in range(3, 9):
        qc.cx(anc[7], data[q])
    qc.h([anc[6], anc[7]])
    qc.barrier()
    qc.measure([anc[6], anc[7]], phase_syndrome)
    qc.barrier()

    # 5. No correction gates in the circuit. The syndromes are only known after the circuit
    # runs, so print_correction() below reports which X and Z gates would fix the error, and the
    # measured out bit gets fixed afterwards in Python (see error_test.py)

    # 6. Decode back to q_0 (undo step 2 in reverse order) and measure it.
    out = ClassicalRegister(1, "out")
    qc.add_register(out)
    qc.barrier()
    for first in BLOCKS:
        decode_block(qc, data, first)
    qc.h([data[first] for first in BLOCKS])
    qc.cx(data[0], data[6])
    qc.cx(data[0], data[3])
    qc.measure(data[0], out[0])

    return qc


# Which qubit in a block each bit-flip syndrome (a_1 a_0 of that block) says flipped
BIT_SYNDROME_TO_QUBIT = {"00": None, "01": 0, "11": 1, "10": 2}

# Which block each phase-flip syndrome (a_7 a_6) says had its sign flipped
PHASE_SYNDROME_TO_BLOCK = {"00": None, "01": 0, "11": 1, "10": 2}


def print_correction(bit_syndromes, phase_syndrome):
    # bit_syndromes is the 3 measured bit-flip syndromes [b0, b1, b2], e.g. ["00", "11", "00"]
    # phase_syndrome is the measured "a_7 a_6" string, e.g. "01"
    corrections = []
    for block, syndrome in enumerate(bit_syndromes):
        qbit = BIT_SYNDROME_TO_QUBIT[syndrome]
        if qbit is not None:
            corrections.append(f"X gate to qubit q{3 * block + qbit}")
    block = PHASE_SYNDROME_TO_BLOCK[phase_syndrome]
    if block is not None:
        # Any qubit in the block works: a Z on any of them flips the sign of the whole block
        corrections.append(f"Z gate to any qubit in block {block} (q{3 * block}-q{3 * block + 2})")

    syndromes = f"bit syndromes (b2 b1 b0) {' '.join(reversed(bit_syndromes))}, phase syndrome {phase_syndrome}"
    if not corrections:
        print(f"  {syndromes} so no correction is needed")
    else:
        print(f"  {syndromes} so apply {' and '.join(corrections)} to correct error")
