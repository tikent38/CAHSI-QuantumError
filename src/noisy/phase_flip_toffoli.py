# phase_flip_toffoli.py
# The same phase-flip code as phase_flip_encoded.py, but the error is corrected with a Toffoli (CCNOT) gate
# inside the circuit instead of measuring ancillas and using if blocks
# (Reed et al. 2012, "Realization of three-qubit quantum error correction with superconducting circuits", Fig. 4a).
# Only 3 qubits: decoding undoes the H gates, which turns a phase flip back into a bit flip,
# so from there the correction is exactly the one in bit_flip_toffoli.py.
# See notes/error_codes.md for the theory and syndrome table.
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Reuse the encoding and gate sets from phase_flip_encoded.py so the only difference is the correction
from phase_flip_encoded import LOGICAL_GATES, H_SWAPPED, PHASE_GATES, encode, decode


def phase_flip_toffoli(circuit, measure=True):
    # Returns the phase-flip-code version of a 1-qubit circuit (no measurements in it), corrected with a Toffoli.
    # measure=True also measures the result into the "out" register;
    # measure=False leaves the corrected state decoded on q_0, with the syndrome left on q_1 and q_2
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(3, "q") # our 3 qubits representing the 1 we are protecting
    qc = QuantumCircuit(data)

    # 1. Create a|+++> + b|--->. All qubits start at |0>, so this is |+++> (a=1, b=0);
    #    the gates in step 2 are what set a and b
    encode(qc, data)
    qc.barrier()

    # 2. Apply every gate from the passed in circuit to the encoded qubit (same as phase_flip_encoded)
    for inst in circuit.data:
        gate = inst.operation
        if gate.name == "barrier":
            continue
        if gate.name == "measure":
            raise ValueError("leave measurements out of the circuit; use measure=True instead")

        if gate.name in LOGICAL_GATES:
            # Apply the H-conjugated gate to all 3 data qubits (e.g. X -> ZZZ)
            gate = H_SWAPPED.get(gate.name, gate)
            for q in data:
                qc.append(gate, [q])
        elif gate.name in PHASE_GATES:
            # Apply H, the gate, H to q_0 only (see PHASE_GATES in phase_flip_encoded.py)
            qc.h(data[0])
            qc.append(gate, [data[0]])
            qc.h(data[0])
        else:
            # Gates like H have no encoded version in this code: decode, apply to q_0, re-encode.
            # The qubit is NOT protected while this gate runs
            decode(qc, data)
            qc.append(gate, [data[0]])
            encode(qc, data)
    qc.barrier()

    # 3. Decode. The H gates turn a sign flip into a bit flip, so q_1 and q_2 are now the syndrome:
    #    q_1 q_2 = 0 0 -> no flip,  1 0 -> q_1 sign flipped,  0 1 -> q_2 sign flipped,  1 1 -> q_0 sign flipped
    #    Only a flip on q_0 reaches the decoded qubit, so only that one needs fixing
    decode(qc, data)

    # 4. Flip q_0 back only when q_1 and q_2 are both 1 (same as bit_flip_toffoli)
    qc.ccx(data[1], data[2], data[0])

    # 5. (optional) Measure q_0
    if measure:
        qc.barrier()
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc
