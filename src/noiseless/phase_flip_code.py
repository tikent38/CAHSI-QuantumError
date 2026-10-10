# phase_flip_code.py
# 3-qubit phase-flip code: protects one qubit from a single Z (phase-flip) error.
# Encodes in the |+>/|-> basis, where a phase flip acts like a bit flip.
# See notes/error_codes.md for the theory and syndrome table.
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister


def phase_flip_code(state_prep, error_qubits=None):

  
    data = QuantumRegister(3, "q") # our 3 qubits representing the 1 we are protecting
    anc = QuantumRegister(2, "a")
    syndrome = ClassicalRegister(2, "s") #used to calculate what (if any) qbits need to be flipped
    qc = QuantumCircuit(data, anc, syndrome) #make the QuantumCircuit

    # 1. Prepare the state we want to protect on q_0
    for inst in state_prep.data:
        qc.append(inst.operation, [data[0]])

    # 2. Encode: a|0> + b|1>  ->  a|000> + b|111>  ->  a|+++> + b|--->
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])
    qc.h(data)
    qc.barrier()

    # Optional apply error Z gates to qubits
    if error_qubits is not None:
        for qbit in error_qubits:
            qc.z(data[qbit])
        qc.barrier()

    # 3. Encode pairwise parities (in the +/- basis) into the ancillas:
    #    ancillas start in |+> and control CNOTs onto the data qubits, so each
    #    data qubit's phase kicks back onto the ancilla. H then turns |+>/|-> into 0/1
    qc.h(anc)
    qc.cx(anc[0], data[0])
    qc.cx(anc[0], data[1])
    qc.cx(anc[1], data[1])
    qc.cx(anc[1], data[2])
    qc.h(anc)
    qc.barrier()

    qc.measure(anc, syndrome)

    # 4. Decode back to q_0 (undo the H gates, then the CNOTs) and measure it
    # No correction is done in the circuit. The H gates turn a phase flip back into
    # a bit flip, so just like the bit-flip code, a flip on q_1 or q_2 doesn't reach q_0
    # but a flip on q_0 (syndrome 01) flips the output. That gets fixed afterwards in
    # Python (see error_test.py)
    out = ClassicalRegister(1, "out")
    qc.add_register(out)
    qc.barrier()
    qc.h(data)
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])
    qc.measure(data[0], out[0])

    return qc


# Which data qubit each syndrome (a_1 a_0) says flipped
SYNDROME_TO_QUBIT = {"00": None, "01": 0, "11": 1, "10": 2}


def print_correction(syndrome):
    # syndrome is the measured "a_1 a_0" string, e.g. "01"
    qbit = SYNDROME_TO_QUBIT[syndrome]
    if qbit is None:
        print(f"  syndrome is {syndrome} so no correction is needed")
    else:
        print(f"  syndrome is {syndrome} so apply Z gate to qubit q{qbit} to correct error")
