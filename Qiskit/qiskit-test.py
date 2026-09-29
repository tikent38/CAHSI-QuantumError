# test_qiskit.py
import qiskit
from qiskit import QuantumCircuit

print("Qiskit version:", qiskit.__version__)

# Make a 1-qubit circuit: put it into superposition, then measure it
qc = QuantumCircuit(1, 1)
qc.h(0)
qc.measure(0, 0)

print("\nCircuit:")
print(qc.draw())
print("\nQiskit is installed and imported successfully!")