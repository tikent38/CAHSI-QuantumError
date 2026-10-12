# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.

The project studies the three-qubit bit-flip and phase-flip codes and the nine-qubit Shor code in Qiskit: first on a noiseless simulator to check that they work, then on noisy simulators to see when error correction actually lowers the error rate compared with running a circuit unencoded.

## Getting started

These steps are for macOS. If you're on Windows, let me know and I can help find the equivalent steps.

```bash
git clone https://github.com/tikent38/CAHSI-QuantumError.git
cd CAHSI-QuantumError

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install qiskit qiskit-aer qiskit-ibm-runtime matplotlib pylatexenc
```

`qiskit-ibm-runtime` provides the fake IBM backends (such as `FakeFez`) used for realistic device noise. `matplotlib` and `pylatexenc` are only needed to draw circuits as images.

Check the installation (all commands are run from the repository's main directory):

```bash
python src/installation_tests/qiskit_test.py
python src/installation_tests/aer_test.py
python src/installation_tests/aer_noise_test.py
```

## Project structure

```text
CAHSI-QuantumError/
├── notes/
│   ├── error_codes.md            # theory notes on repetition, bit-flip and phase-flip codes
│   └── research_papers.md        # links to related papers
└── src/
    ├── installation_tests/       # check that Qiskit, Aer and the fake backends work
    ├── noiseless/                # the codes with hand-placed errors, no noise
    │   ├── bit_flip_code.py
    │   ├── phase_flip_code.py
    │   ├── shor_code.py
    │   └── error_test.py         # runs a code with an error on each qubit
    └── noisy/                    # the codes on IBM Fez noise vs. unencoded circuits
        ├── bit_flip_encoded.py   # bit-flip code, corrected with if blocks
        ├── bit_flip_toffoli.py   # bit-flip code, corrected with a Toffoli (Reed et al. 2012)
        ├── phase_flip_encoded.py
        ├── phase_flip_toffoli.py
        ├── shor_encoded.py
        └── compare_fez.py        # runs a circuit unencoded and with each code
```

## Noiseless tests

```bash
python src/noiseless/error_test.py
```

Runs a code with no error and with an error on each qubit, and prints the syndrome and needed correction for each case. Choose which code to test by uncommenting `test_bit_flip()`, `test_phase_flip()`, or `test_shor()` at the bottom of the file.

## Noisy comparison

```bash
python src/noisy/compare_fez.py
```

Builds a random one-qubit circuit and runs it on a noiseless simulator, on a simulator with IBM Fez noise with no correction, and with each of the five encoders. It prints the counts, the distance from the exact answer, and the transpiled circuit size for each.

Set the experiment in the settings block at the bottom of the file:

```python
NUM_GATES = 3000     # how many random gates in the circuit
SHOTS = 1000         # how many times each version of the circuit is run
SEED = 3             # a number gives the same circuit every time; None picks a new random one
GATE_SET = "repeat"  # "all" = X, Y, Z, S, T, id   "xz" = only X and Z   "repeat" = X, Y, Z, S, T in order
MIRROR = False       # True adds the circuit's inverse, so the exact answer is always 0
```

Notes:

- Circuits can't contain H gates, since none of the codes has a protected version of H.
- All runs start on the same physical Fez qubits, so differences come from the codes and not from qubit placement.
- Fez connections with an error rate of 1.0 are left out when routing.
- The Shor code (17 qubits) takes most of the run time. Run time grows with `NUM_GATES` × `SHOTS`.
