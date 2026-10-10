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
│   ├── error_codes.md            # theory notes: repetition codes, bit-flip and phase-flip codes
│   └── research_papers.md        # links to related papers
├── src/
│   ├── installation_tests/       # check that Qiskit, Aer and the fake backends work
│   │   ├── qiskit_test.py
│   │   ├── aer_test.py
│   │   └── aer_noise_test.py
│   ├── noiseless/                # the 3-qubit codes with hand-placed errors, no noise
│   │   ├── bit_flip_code.py
│   │   ├── phase_flip_code.py
│   │   └── error_test.py
│   └── noisy/                    # the bit-flip code on IBM Fez noise vs. unencoded circuits
│       ├── bit_flip_encoded.py
│       └── compare_fez.py
├── .gitignore
└── README.md
```

All commands below are run from the repository’s main directory.

## `notes/`

### `notes/error_codes.md`

Background for the code in `src/`: the classical repetition code and its error rate $3p^2 - 2p^3$, the quantum bit-flip code and its syndrome table, and the phase-flip code (why the bit-flip code can’t catch phase flips, and how encoding in the $|\pm\rangle$ basis fixes that).

### `notes/research_papers.md`

Links to papers related to the project.

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

Runs both codes on input $|0\rangle$ with no error and with an error on each qubit, then prints the circuit, the syndrome, and the needed correction for each case. Because the circuits don’t correct themselves, it fixes the measured result in Python (`correct_bit_flip`).

```bash
python src/noiseless/error_test.py
```

Choose which code to test by commenting or uncommenting `test_bit_flip()` and `test_phase_flip()` at the bottom of the file.

## `src/noisy/`

The bit-flip code on a noisy Aer simulator, compared with running the same circuit unencoded.

### `bit_flip_encoded.py`

`bit_flip_encoded(circuit, measure=True)` takes any one-qubit circuit and returns its bit-flip-code version: encode into $a|000\rangle + b|111\rangle$, apply the circuit’s gates to the encoded qubit, measure the syndrome with the two ancillas, and apply an X to the flipped qubit. With `measure=True` it also decodes and measures the result into an `out` register. Run the returned circuit on any (noisy) `AerSimulator`.

How the circuit’s gates are applied to the encoded qubit:

- **X, Y, Z, `id`** are applied to all three data qubits, so the qubit stays protected.
- **H, S, T and other gates** are applied by decoding (2 CNOTs), running the gate on `q_0`, and re-encoding (2 CNOTs). The qubit is not protected during that gate, and each one adds 4 CNOTs.

There is a single syndrome check at the end, so it can correct at most one bit flip over the whole circuit.

```bash
python src/noisy/bit_flip_encoded.py   # prints an example encoded circuit
```

### `compare_fez.py`

Builds a random one-qubit circuit and runs it three ways: on a noiseless `AerSimulator`, on `AerSimulator` with IBM Fez noise, and on `AerSimulator` with Fez noise after `bit_flip_encoded`. It prints the counts for each, how far each is from the exact answer, and the size of each circuit after transpiling for Fez.

Set the experiment in the settings block at the bottom of the file, then run it:

```python
NUM_GATES = 100    # how many random gates in the circuit
SHOTS = 1000       # how many times each version of the circuit is run
SEED = None        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
GATE_SET = "all"   # "all" = X, Y, Z, H, S, T, id     "xz" = only X and Z
MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0
```

```bash
python src/noisy/compare_fez.py
```

From your own code, call `compare(num_gates, shots, seed, gate_set, mirror)`, or build circuits with `random_all_gates(num_gates, seed)` (X, Y, Z, H, S, T, id) or `random_xz_gates(num_gates, seed)` (X and Z only).

The seed used is printed, so any run can be repeated exactly. Both noisy runs are transpiled with `optimization_level=0` so the transpiler doesn’t merge the random gates away.

Results so far (seed 3, 100 gates, 1000 shots): on Fez noise the bit-flip code makes the result **worse** than no correction. With all gates it is 0.39 off from the exact answer versus 0.03 without correction, mostly from the CNOTs added around H/S/T gates. With only X and Z gates the gap shrinks (0.08 versus 0.02); the remaining cost comes from the encoding, the syndrome-check CNOTs, the SWAPs Fez’s qubit wiring needs, and measurement errors on the ancillas.
