# fez_common.py
# Small pieces shared by the experiments on Fez, simulated and real: the Y gate circuit, reading results, Fez's
# wiring, and the default Fez qubits. 
from qiskit import QuantumCircuit
from qiskit.transpiler import CouplingMap

# Default Fez qubits for each role, used by compare_fez.py and the hardware runs so they all run on the same qubits.
# 87 is wired to both 88 and 86, so the bit-flip and phase-flip codes encode and decode without SWAPs. The Toffoli
# still needs one SWAP, and with the transpiler seed set to 3 the Toffoli codes' result ends up measured on 86 (as in
# the hardware sweeps)
DEFAULT_DATA_QUBITS = (87, 88, 86)                                  # q_0, q_1, q_2 of the bit-flip and phase-flip codes
DEFAULT_ANCILLA_QUBITS = (97, 108)                                  # their a_0, a_1 (only the if-block codes use them)
DEFAULT_SHOR_DATA_QUBITS = (87, 88, 85, 97, 108, 107, 86, 77, 84)   # q_0, ..., q_8 of the Shor codes
DEFAULT_SHOR_ANCILLA_QUBITS = (89, 109, 65, 83, 78, 90, 110, 118)   # their a_0, ..., a_7 (only "Shor, if blocks")


def y_circuit(bit, num_gates):
    # Prepare |bit>, then num_gates Y gates in a row. Each Y flips the qubit, so with no noise it reads
    # (bit + num_gates) % 2
    qc = QuantumCircuit(1)
    if bit:
        qc.x(0)
    for _ in range(num_gates):
        qc.y(0)
    return qc


def prob_one(counts, register_index=0):
    # How many shots read 1 and how many read 0, as (ones, zeros). When a circuit has more than one classical
    # register the keys look like "out s", one group per register; register_index picks the group, and the codes'
    # "out" register is the first one
    ones = sum(n for key, n in counts.items() if key.split()[register_index] == "1")
    return ones, sum(counts.values()) - ones


def working_coupling_map(backend, max_error=0.5):
    # The backend's qubit wiring without its broken connections: fake backends list a broken connection with a CZ
    # error of 1.0, and routing through one would ruin the circuit
    edges = [pair for pair, props in backend.target["cz"].items()
             if props is None or props.error is None or props.error < max_error]
    return CouplingMap(edges)


def physical_qubits(circuit):
    # The physical qubits a transpiled circuit actually uses (routing can add qubits through SWAPs), and the one its
    # result is measured on (the "out" register for the codes, "meas" for no correction)
    touched = sorted({circuit.find_bit(q).index for inst in circuit.data if inst.operation.name != "barrier"
                      for q in inst.qubits})
    measured = [circuit.find_bit(inst.qubits[0]).index for inst in circuit.data if inst.operation.name == "measure"
                and circuit.find_bit(inst.clbits[0]).registers[0][0].name in ("out", "meas")]
    return touched, measured[0]
