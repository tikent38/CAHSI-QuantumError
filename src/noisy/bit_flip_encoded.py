# bit_flip_encoded.py
# Turn any 1-qubit circuit into its 3-qubit bit-flip-code version:
# encode, apply the circuit's gates, measure the syndrome, and correct the flipped qubit.
# See notes/error_codes.md for the theory and syndrome table.
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

# Gates that work directly on the encoded state: applying the gate to all 3 data qubits
# does the same thing to a|000> + b|111> as the gate does to a|0> + b|1>
# (e.g. XXX turns a|000> + b|111> into a|111> + b|000>)
LOGICAL_GATES = {"id", "x", "y", "z"}


def encode(qc, data):
    # a|0> + b|1> on q_0  ->  a|000> + b|111>
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])


def decode(qc, data):
    # a|000> + b|111>  ->  a|0> + b|1> on q_0
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])


def bit_flip_encoded(circuit, measure=True):
    # Returns the bit-flip-code version of a 1-qubit circuit (no measurements in it).
    # measure=True also decodes and measures the result into the "out" register;
    # measure=False leaves the corrected state encoded as a|000> + b|111>
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(3, "q") # our 3 qubits representing the 1 we are protecting
    anc = QuantumRegister(2, "a")
    syndrome = ClassicalRegister(2, "s") #used to calculate what (if any) qbits need to be flipped
    qc = QuantumCircuit(data, anc, syndrome)

    # 1. Create a|000> + b|111>. All qubits start at |0>, so this is |000> (a=1, b=0);
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

        if gate.name in LOGICAL_GATES:
            # Apply the gate to all 3 data qubits
            for q in data:
                qc.append(gate, [q])
        else:
            # Gates like H, S, T have no simple encoded version: decode, apply to q_0, re-encode.
            # The qubit is NOT protected while this gate runs
            decode(qc, data)
            qc.append(gate, [data[0]])
            encode(qc, data)
    qc.barrier()

    # 3. Measure the pairwise parities into the ancillas to find which (if any) qubit flipped
    qc.cx(data[0], anc[0])
    qc.cx(data[1], anc[0])
    qc.cx(data[1], anc[1])
    qc.cx(data[2], anc[1])
    qc.measure(anc, syndrome)

    # 4. Flip back the qubit the syndrome points to
    # 1 = 01 -> q_0 flipped,  3 = 11 -> q_1 flipped,  2 = 10 -> q_2 flipped,  0 = 00 -> no correction
    with qc.switch(syndrome) as case:
        with case(1):
            qc.x(data[0])
        with case(3):
            qc.x(data[1])
        with case(2):
            qc.x(data[2])

    # 5. (optional) Decode back to q_0 and measure it
    if measure:
        qc.barrier()
        decode(qc, data)
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc


if __name__ == "__main__":
    # Example: H then 2 idle steps
    example = QuantumCircuit(1)
    example.h(0)
    example.id(0)
    example.id(0)
    print(bit_flip_encoded(example).draw(fold=-1))
