# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.



## Getting started

Follow these steps if you are cloning this project and installing Qiskit for the first time.
Also I am on a Mac OS so these are the steps that work for me but if you are on windows
let me know and I can help search for the windows' workflow steps


### 1. Clone the repository

```bash
git clone https://github.com/tikent38/CAHSI-QuantumError.git
cd CAHSI-QuantumError
```

### 2. Create a virtual environment

A virtual environment keeps this project’s packages separate from other Python projects on your computer.

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

```bash
source .venv/bin/activate
```

When it is active, your terminal prompt should begin with `(.venv)`.

### 4. Install Qiskit and Aer

```bash
python -m pip install --upgrade pip
python -m pip install qiskit qiskit-aer
```

### 5. Verify the installation

Run both scripts from the repository’s main directory:

```bash
python Qiskit/test_qiskit.py
python Qiskit/aer-test.py
```

The first command should print the installed Qiskit version and a circuit. The second should print measurement counts containing both `0` and `1`.

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