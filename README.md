# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.

## Project structure

```text
CAHSI-QuantumError/
├── Qiskit/
│   ├── test_qiskit.py
│   └── aer-test.py
└── README.md
```

## Qiskit

The `Qiskit/` directory contains small scripts to verify that Qiskit and its Aer simulator are installed and working.

Install the required packages:

```bash
pip install qiskit qiskit-aer
```

### `Qiskit/test_qiskit.py`

Verifies that the base Qiskit package imports correctly. It:

- Prints the installed Qiskit version.
- Creates a one-qubit circuit.
- Applies a Hadamard (`H`) gate, placing the qubit in an equal superposition of `0` and `1`.
- Adds a measurement instruction and prints the circuit.

Run it from the repository’s main directory:

```bash
python Qiskit/test_qiskit.py
```

If it prints a version number and the circuit without an error, Qiskit is installed correctly.

### `Qiskit/aer-test.py`

Verifies that Qiskit Aer can simulate a quantum circuit. It creates the same one-qubit superposition circuit and runs it 1,000 times using `AerSimulator`.

Run it from the repository’s main directory:

```bash
python Qiskit/aer-test.py
```

Expected output resembles:

```text
Measurement counts: {'0': 496, '1': 504}
```

The exact counts will vary, but both `0` and `1` should occur about half the time. This confirms that Aer is simulating the quantum measurement correctly.