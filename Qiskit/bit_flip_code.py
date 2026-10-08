# bit_flip_code.py
# 3-qubit bit-flip code: protects one qubit from a single X (bit-flip) error.
# See notes/Error_Codes.MD for the theory and syndrome table.
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator


def bit_flip_code(state_prep, error_qubits=None):

    if state_prep.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {state_prep.num_qubits} qubits")

    data = QuantumRegister(3, "q") # our 3 qubits representing the 1 we are protecting
    anc = QuantumRegister(2, "a") 
    syndrome = ClassicalRegister(2, "s") #used to calculate what (if any) qbits need to be flipped
    qc = QuantumCircuit(data, anc, syndrome) #make the QunatumCircuit



    # 1. Prepare the state we want to protect on q_0
    for inst in state_prep.data:
        qc.append(inst.operation, [data[0]])

    # 2. Encode: a|0> + b|1>  ->  a|000> + b|111>
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])
    qc.barrier()

    # Optional apply error X gates to qubits
    if error_qubits is not None:
        for qbit in error_qubits:
            qc.x(data[qbit])
        qc.barrier()

    # 3. Encode pairwise parities into the ancillas
    qc.cx(data[0], anc[0])
    qc.cx(data[1], anc[0])
    qc.cx(data[1], anc[1])
    qc.cx(data[2], anc[1])

    qc.measure(anc, syndrome)

    # 4. Determine which qbit flipped
    # 1 = 01 -> q_0 flipped,  3 = 11 -> q_1 flipped,  2 = 10 -> q_2 flipped
    with qc.if_test((syndrome, 1)):
        qc.x(data[0])
    with qc.if_test((syndrome, 3)):
        qc.x(data[1])
    with qc.if_test((syndrome, 2)):
        qc.x(data[2])

    # 5. Decode back to q_0 and measure it
    
    out = ClassicalRegister(1, "out")
    qc.add_register(out)
    qc.barrier()
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])
    qc.measure(data[0], out[0])

    return qc


