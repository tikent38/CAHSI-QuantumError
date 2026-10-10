# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.

The project studies the three-qubit bit-flip and phase-flip codes in Qiskit: first on a noiseless simulator to check that they work, then on noisy simulators to see when error correction actually lowers the error rate compared with running a circuit unencoded.

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

### 4. Install the packages

```bash
python -m pip install --upgrade pip
python -m pip install qiskit qiskit-aer
python -m pip install matplotlib pylatexenc
python -m pip install qiskit-ibm-runtime
```

- `matplotlib` and `pylatexenc` are only needed to draw circuits as images (`qc.draw("mpl")`).
- `qiskit-ibm-runtime` provides the fake IBM backends (such as `FakeFez`) used for realistic device noise.

### 5. Verify the installation

Run these from the repository’s main directory:

```bash
python src/installation_tests/qiskit_test.py
python src/installation_tests/aer_test.py
python src/installation_tests/aer_noise_test.py
```

The first prints the installed Qiskit version and a circuit. The second prints measurement counts containing both `0` and `1`. The third runs a circuit with simulated IBM device noise and prints how many shots came out wrong.

## Project structure

```text
CAHSI-QuantumError/
├── notes/
│   └── error_codes.md            # theory notes: repetition codes, bit-flip and phase-flip codes
├── src/
│   ├── installation_tests/       # check that Qiskit, Aer and the fake backends work
│   │   ├── qiskit_test.py
│   │   ├── aer_test.py
│   │   └── aer_noise_test.py
│   ├── noiseless/                # the 3-qubit codes with hand-placed errors, no noise
│   │   ├── bit_flip_code.py
│   │   ├── phase_flip_code.py
│   │   └── error_test.py
│   └── noisy/                    # the codes on a noisy simulator vs. unencoded circuits
│       ├── noisy_bit_flip.py
│       └── qec_runner.py
└── README.md
```

All commands below are run from the repository’s main directory.

## `notes/`

### `notes/error_codes.md`

Background for the code in `src/`: the classical repetition code and its error rate $3p^2 - 2p^3$, the quantum bit-flip code and its syndrome table, and the phase-flip code (why the bit-flip code can’t catch phase flips, and how encoding in the $|\pm\rangle$ basis fixes that).

## `src/installation_tests/`

Small scripts that check the setup is working.

### `qiskit_test.py`

Prints the installed Qiskit version, builds a one-qubit circuit with a Hadamard (`H`) gate and a measurement, and prints the circuit. If it runs without an error, Qiskit is installed correctly.

```bash
python src/installation_tests/qiskit_test.py
```

### `aer_test.py`

Runs the same one-qubit superposition circuit 1,000 times on `AerSimulator`.

```bash
python src/installation_tests/aer_test.py
```

Expected output resembles:

```text
Measurement counts: {'0': 496, '1': 504}
```

The exact counts vary, but `0` and `1` should each occur about half the time.

### `aer_noise_test.py`

Applies 10 X gates to one qubit (they cancel, so the ideal answer is always `0`) and runs it 1,000 times with no noise and 1,000 times with the noise of IBM’s Fez device (`FakeFez`). It prints the counts and error rate for each run, plus the device’s error rates for the qubit used.

```bash
python src/installation_tests/aer_noise_test.py
```

Expected output resembles:

```text
run                        0       1    error rate
--------------------------------------------------
no noise                1000       0         0.0%
fake_fez noise           983      17         1.7%
```

## `src/noiseless/`

The three-qubit codes with no noise. Errors are added by hand at a chosen point so you can check that each one is detected.

### `bit_flip_code.py`

`bit_flip_code(state_prep, error_qubits=None)` builds the bit-flip code circuit for a one-qubit input state: encode $a|0\rangle + b|1\rangle \to a|000\rangle + b|111\rangle$, apply an X error to each qubit in `error_qubits`, measure the two parity checks into the syndrome, then decode and measure. The circuit does not apply the correction itself; `print_correction(syndrome)` prints which X gate would fix the error.

### `phase_flip_code.py`

`phase_flip_code(state_prep, error_qubits=None)` is the same idea for phase flips: it encodes into $a|{+}{+}{+}\rangle + b|{-}{-}{-}\rangle$, applies Z errors, and measures the syndrome using phase kickback. `print_correction(syndrome)` prints which Z gate would fix the error.

### `error_test.py`

Runs both codes with no error and with an error on each qubit, then prints the circuit, the syndrome, and the needed correction for each case. Because the circuits don’t correct themselves, it fixes the measured result in Python (`correct_bit_flip`).

```bash
python src/noiseless/error_test.py
```

Choose which code to test by commenting or uncommenting `test_bit_flip()` and `test_phase_flip()` at the bottom of the file.

## `src/noisy/`

The codes on a noisy Aer simulator, compared with running the same circuit unencoded.

### `noisy_bit_flip.py`

`run_encoded(circuit, noise_model, correct=True)` runs any one-qubit circuit with the bit-flip code. X, Y, Z and idle (`id`) gates are applied to all three encoded qubits; other gates (H, S, T, …) are applied by decoding, running the gate, and re-encoding. After every gate the syndrome is measured and the X correction is applied.

Running the file compares three versions of random circuits (unencoded, encoded with detection only, and encoded with correction) under bit-flip noise on idle steps only and on every gate:

```bash
python src/noisy/noisy_bit_flip.py
```

This takes about a minute. So far: the code clearly helps when only idle time is noisy, but makes things worse when its own gates are as noisy as everything else.

### `qec_runner.py`

An earlier, more general version of the same experiment that supports both the bit-flip and phase-flip codes (`run_with_code(circuit, code="bit_flip" | "phase_flip", ...)`) and builds bit-flip, phase-flip, depolarizing and measurement noise models (`make_noise_model`).

```bash
python src/noisy/qec_runner.py
```
