# fez_common.py
# Small pieces shared by the experiments on Fez, simulated and real, and by the same experiments on other backends:
# the default Fez qubits, Fez's gates, the Y gate circuit, reading results, and a backend's wiring without its broken
# connections
from qiskit import QuantumCircuit
from qiskit.transpiler import CouplingMap, Target

# Default Fez qubits for each role, used by compare_fez.py and the hardware runs so they all run on the same qubits.
# 87 is wired to both 88 and 86, so the bit-flip and phase-flip codes encode and decode without SWAPs. The Toffoli
# still needs one SWAP, and with the transpiler seed set to 3 the Toffoli codes' result ends up measured on 86 (as in
# the hardware sweeps)
DEFAULT_DATA_QUBITS = (87, 88, 86)                                  # q_0, q_1, q_2 of the bit-flip and phase-flip codes
DEFAULT_ANCILLA_QUBITS = (97, 108)                                  # their a_0, a_1 (only the if-block codes use them)
# Chosen for "Shor, Toffoli": its outer phase-flip code (q_0, q_3, q_6) is on the same Fez qubits as the bit-flip and
# phase-flip codes (87, 86, 88), each block's other two qubits run along Fez's wiring from its first one, and with the
# transpiler seed set to 3 its result is measured on 86, like the bit-flip and phase-flip Toffoli codes
DEFAULT_SHOR_DATA_QUBITS = (87, 97, 107, 86, 85, 84, 88, 89, 90)    # q_0, ..., q_8 of the Shor codes
DEFAULT_SHOR_ANCILLA_QUBITS = (108, 109, 78, 91, 77, 83, 110, 118)  # their a_0, ..., a_7 (only "Shor, if blocks")

# The gates Fez runs: every circuit is rewritten in these before it goes on the machine. rz is done in software (it
# only changes how later pulses are timed), so it takes no time and has no error. For the noise models and circuits
# built by hand (noise_sweep.py, y_gate_noise_sources.py)
FEZ_BASIS_GATES = ["cz", "id", "rz", "sx", "x"]


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
    # error of 1.0, and routing through one would ruin the circuit. Only for backends whose 2-qubit gate is CZ, like
    # Fez (compare_fez.py and mapping_sweep.py use it). working_target does the same on any backend
    edges = [pair for pair, props in backend.target["cz"].items()
             if props is None or props.error is None or props.error < max_error]
    return CouplingMap(edges)


def working_target(backend, max_error=0.5):
    # The backend's target (its gates, connections and error rates) without connections whose error is max_error or
    # more: fake backends list a broken connection with an error of 1.0, and routing through one would ruin the
    # circuit. Real machines already leave out their faulty qubits and connections. Works whatever the backend's
    # 2-qubit gate is, so compare_backends.py and the hardware runs transpile with it
    target = backend.target
    kept = Target(num_qubits=target.num_qubits, dt=target.dt, granularity=target.granularity,
                  min_length=target.min_length, pulse_alignment=target.pulse_alignment,
                  acquire_alignment=target.acquire_alignment, qubit_properties=target.qubit_properties,
                  concurrent_measurements=target.concurrent_measurements)
    for name in target.operation_names:
        props = target[name]
        if props is None or list(props) == [None]:
            props = None   # available on every qubit (e.g. if_else, barrier)
        else:
            props = {qargs: p for qargs, p in props.items()
                     if len(qargs) < 2 or p is None or p.error is None or p.error < max_error}
        kept.add_instruction(target.operation_from_name(name), props, name=name)
    return kept


def physical_qubits(circuit):
    # The physical qubits a transpiled circuit actually uses (routing can add qubits through SWAPs), and the one its
    # result is measured on (the "out" register for the codes, "meas" for no correction)
    touched = sorted({circuit.find_bit(q).index for inst in circuit.data if inst.operation.name != "barrier"
                      for q in inst.qubits})
    measured = [circuit.find_bit(inst.qubits[0]).index for inst in circuit.data if inst.operation.name == "measure"
                and circuit.find_bit(inst.clbits[0]).registers[0][0].name in ("out", "meas")]
    return touched, measured[0]
