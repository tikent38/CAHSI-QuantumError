# CAHSI-QuantumError
A repository for working on the Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability CAHSI project.

#Qiskit/
In order to run the files in this director, install qiskit using the following command:
pip install qiskit qiskit-aer

test_qiskit.py
This script verifies that the base Qiskit package imports correctly. It:
- prints the installed Qiskit version;
- creates a one-qubit circuit;
- applies a Hadamard (H) gate, placing the qubit in an equal superposition of 0 and 1;
- adds a measurement instruction and prints the circuit.
Run it with:
python test_qiskit.py
If it prints a version number and the circuit without an error, Qiskit is installed correctly.

aer_test.py
This script verifies that Qiskit Aer can simulate a circuit. It creates the same one-qubit superposition circuit, then runs it 1,000 times using AerSimulator.
Run it with:
python aer_test.py
Expected output resembles:
Measurement counts: {'0': 496, '1': 504}
The counts will not be exactly the same on every run, but both 0 and 1 should occur close to half the time. This confirms Aer is simulating the quantum measurement correctly.