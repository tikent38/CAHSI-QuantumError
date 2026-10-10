# aer_test.py
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

# Create a 1-qubit, 1-classical-bit circuit
qc = QuantumCircuit(1, 1)
qc.h(0)           # Put qubit 0 into superposition
qc.measure(0, 0)  # Measure it into classical bit 0

# Run the circuit 1,000 times using Aer
simulator = AerSimulator()
job = simulator.run(qc, shots=1000)
result = job.result()

# Show how often each measurement occurred
counts = result.get_counts()
print("Measurement counts:", counts)