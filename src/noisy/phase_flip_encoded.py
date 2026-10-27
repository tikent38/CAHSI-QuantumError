# phase_flip_encoded.py
# Turn any 1-qubit circuit into its 3-qubit phase-flip-code version:
# encode, apply the circuit's gates, measure the syndrome, and correct the phase-flipped qubit.
# This is the bit-flip code done in the |+>, |-> basis: every step is the bit-flip version with H around it
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit.library import XGate, ZGate

# Gates that work directly on the encoded state: applying the gate's H-conjugated version to all
# 3 data qubits does the same thing to a|+++> + b|---> as the gate does to a|0> + b|1>
# (e.g. ZZZ turns a|+++> + b|---> into a|---> + b|+++>, so logical X = ZZZ)
LOGICAL_GATES = {"id", "x", "y", "z"}

# H-conjugated versions of the LOGICAL_GATES that change: H X H = Z and H Z H = X.
# The rest stay the same (H Y H = -Y, which is the same gate up to a global phase)
H_SWAPPED = {"x": ZGate(), "z": XGate()}

# Gates that only add a phase to |1> (S, T, their inverses, and other phase rotations).
# In the bit-flip code these go on q_0 only; here they go on q_0 only wrapped in H,
# which adds the phase to the |---> term once: a|+++> + b|--->  ->  a|+++> + e^(i*phase) b|--->
PHASE_GATES = {"s", "sdg", "t", "tdg", "p", "rz"}


def phase_flip_encoded(circuit, measure=True):
    # Returns the phase-flip-code version of a 1-qubit circuit (no measurements in it).
    # measure=True also decodes and measures the result into the "out" register;
    # measure=False leaves the corrected state encoded as a|+++> + b|--->
    if circuit.num_qubits != 1:
        raise ValueError(f"expected a 1-qubit circuit, got {circuit.num_qubits} qubits")

    data = QuantumRegister(3, "q")         # the 3 qubits that together hold the 1 qubit being protected
    anc = QuantumRegister(2, "a")
    syndrome = ClassicalRegister(2, "s")   # which qubit (if any) had its sign flipped
    qc = QuantumCircuit(data, anc, syndrome)

    # 1. Create a|+++> + b|--->. All qubits start at |0>, so this is |+++> (a=1, b=0);
    #    the gates in step 2 are what set a and b
    encode(qc, data)
    qc.barrier()

    # 2. Apply every gate from the passed in circuit to the encoded qubit
    apply_gates(qc, data, circuit)
    qc.barrier()

    # 3. Error detection: the simplified phase-flip check (IBM Foundations of QEC, "Repetition codes").
    #    It measures X1X2 and X2X3: whether qubits 0 and 1 (and 1 and 2) have the same sign.
    #    The ancillas start in |+> and act as CNOT controls onto the data qubits, so each data
    #    qubit's sign kicks back onto the ancilla (phase kickback). H then turns |+>/|-> into 0/1.
    #    Same result as putting H on the data qubits around the bit-flip check, with fewer gates
    qc.h(anc)
    qc.cx(anc[0], data[0])
    qc.cx(anc[0], data[1])
    qc.cx(anc[1], data[1])
    qc.cx(anc[1], data[2])
    qc.h(anc)
    qc.measure(anc, syndrome)

    # 4. Recovery: the bit-flip code's X correction conjugated by H, which is H X H = Z
    # 1 = 01 -> q_0 sign flipped,  3 = 11 -> q_1 sign flipped,  2 = 10 -> q_2 sign flipped,  0 = 00 -> no correction
    with qc.switch(syndrome) as case:
        with case(1):
            qc.z(data[0])
        with case(3):
            qc.z(data[1])
        with case(2):
            qc.z(data[2])

    # 5. (optional) Decode back to q_0 and measure it
    if measure:
        qc.barrier()
        decode(qc, data)
        out = ClassicalRegister(1, "out")
        qc.add_register(out)
        qc.measure(data[0], out[0])

    return qc


def apply_gates(qc, data, circuit):
    # Step 2: every gate from circuit (a 1-qubit circuit with no measurements), applied to the encoded qubit on data.
    # phase_flip_toffoli.py uses this too, so the two versions of the code only differ in how they correct
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
            # Apply H, the gate, H to q_0 only (see PHASE_GATES above)
            qc.h(data[0])
            qc.append(gate, [data[0]])
            qc.h(data[0])
        else:
            # Gates like H have no encoded version in this code: decode, apply to q_0, re-encode.
            # The qubit is NOT protected while this gate runs
            decode(qc, data)
            qc.append(gate, [data[0]])
            encode(qc, data)


def encode(qc, data):
    # Step 1: encode exactly as for the bit-flip code:  a|0> + b|1>  ->  a|000> + b|111>
    # Step 2: H on every qubit to move to the +/- basis:  ->  a|+++> + b|--->
    qc.cx(data[0], data[1])
    qc.cx(data[0], data[2])
    qc.h(data)


def decode(qc, data):
    # Undo encode:  a|+++> + b|--->  ->  a|0> + b|1> on q_0
    qc.h(data)
    qc.cx(data[0], data[2])
    qc.cx(data[0], data[1])
