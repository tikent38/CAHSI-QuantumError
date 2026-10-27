# shor_toffoli.py
# The same Shor code as shor_encoded.py, but the errors are corrected with Toffoli (CCNOT) gates
# inside the circuit instead of measuring ancillas and using if blocks.
# Only 9 qubits: decoding each block leaves its syndrome on the block's last two qubits, and decoding
# the outer phase-flip code leaves its syndrome on q_3 and q_6, so no separate ancillas are needed.
# This is the bit_flip_toffoli.py correction inside each block, then the phase_flip_toffoli.py
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Reuse the encoding and the gate handling from shor_encoded.py, so the only difference is the correction
from shor_encoded import BLOCKS, apply_gates, decode_block, encode


def shor_toffoli(circuit, measure=True):
    # Returns the Shor-code version of a 1-qubit circuit (no measurements in it, Pauli gates only),
    # corrected with Toffolis.
    # measure=True also measures the result into the "out" register;
    # measure=False leaves the corrected state decoded on q_0, with the syndromes left on q_1-q_8
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(9, "q")   # the 9 qubits that together hold the 1 qubit being protected
    qc = QuantumCircuit(data)

    # 1. Create the encoded |0>. All qubits start at |0>, so this is the encoded |0> (a=1, b=0);
    #    the gates in step 2 are what set a and b
    encode(qc, data)
    qc.barrier()

    # 2. Apply every gate from the passed in circuit to the encoded qubit (same as shor_encoded)
    apply_gates(qc, data, circuit)
    qc.barrier()

    # 3. Decode each block and fix its bit flip, the same as bit_flip_toffoli:
    #    after decoding, the block's last two qubits are its syndrome, and only a flip on the
    #    block's first qubit reaches the decoded value, so flip it back when both are 1
    for first in BLOCKS:
        decode_block(qc, data, first)
        qc.ccx(data[first + 1], data[first + 2], data[first])

    # 4. Decode the outer phase-flip code and fix its sign flip, the same as phase_flip_toffoli:
    #    the H gates turn a block's sign flip into a bit flip on that block's first qubit,
    #    so q_3 and q_6 are now the syndrome and only a flip on q_0 needs fixing
    qc.h([data[first] for first in BLOCKS])
    qc.cx(data[0], data[6])
    qc.cx(data[0], data[3])
    qc.ccx(data[3], data[6], data[0])

    # 5. (optional) Measure q_0
    if measure:
        qc.barrier()
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc
