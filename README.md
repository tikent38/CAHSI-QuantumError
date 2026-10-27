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
│   ├── error_codes.md                # theory notes on repetition, bit-flip and phase-flip codes
│   └── research_papers.md            # links to related papers
└── src/
    ├── installation_tests/           # check that Qiskit, Aer and the fake backends work
    │   ├── qiskit_test.py
    │   ├── aer_test.py
    │   └── aer_noise_test.py
    ├── noiseless/                    # the codes with hand-placed errors, no noise
    │   ├── bit_flip_code.py
    │   ├── phase_flip_code.py
    │   ├── shor_code.py
    │   └── error_test.py             # runs a code with an error on each qubit
    ├── noisy/                        # the codes on IBM Fez noise vs. unencoded circuits
    │   ├── bit_flip_encoded.py       # bit-flip code, corrected with if blocks
    │   ├── bit_flip_toffoli.py       # bit-flip code, corrected with a Toffoli (Reed et al. 2012)
    │   ├── phase_flip_encoded.py
    │   ├── phase_flip_toffoli.py
    │   ├── shor_encoded.py
    │   ├── shor_toffoli.py
    │   ├── fez_common.py             # shared: the Y gate circuit, reading results, default Fez qubits
    │   ├── compare_fez.py            # runs a circuit unencoded and with each code
    │   ├── theory_validation.py      # the codes' failure rates vs. the theory formulas
    │   ├── csvs/
    │   └── images/
    ├── pay_off/                      # how many gates each code needs before it beats no correction
    │   ├── pay_off.py                # runs compare_fez.py at many numbers of gates, one plot per gate set
    │   ├── csvs/
    │   └── images/
    ├── output_tools/                 # shared by every script that writes files
    │   └── output_tools.py           # plot colors and style, plot and printing helpers, CSV and text files
    ├── real_hardware_runs/           # the bit-flip and phase-flip codes on the real ibm_fez
    │   ├── hardware_common.py        # shared code: connecting to IBM, running the jobs, plots
    │   ├── bit_flip_hardware.py      # one bit-flip run
    │   ├── phase_flip_hardware.py    # one phase-flip run
    │   ├── y_sweep_hardware.py       # both codes at several numbers of Y gates
    │   ├── csvs/                     # results and job IDs (single_runs/ and sweep/)
    │   └── images/
    ├── simulator_noise_sources/      # Fez simulator only: each qubit's error split into its noise sources
    │   ├── y_gate_noise_sources.py
    │   ├── csvs/
    │   └── images/
    └── hardware_vs_simulator/        # how well the Fez simulator matches a real ibm_fez calibration
        ├── noise_common.py           # shared code: the Y gate circuit and reading the calibration file
        ├── model_check.py            # the simulator's noise numbers vs. the calibration, per qubit
        ├── y_gate_test.py            # Y gate circuit error: runs the three below and compares them
        ├── simulator_predicted.py    # calculated from the simulator's noise model
        ├── simulator_measured.py     # from running the circuit on the simulator
        ├── calibration_predicted.py  # calculated from the calibration file
        ├── csvs/                     # results, and the ibm_fez calibration file
        ├── images/
        └── reports/                  # good_qubits.md: qubits where the simulator matches the real machine
```

What each directory is for:

- **`notes/`**: Background reading for the project: the theory behind the repetition, bit-flip and phase-flip codes, and links to related papers.
- **`src/installation_tests/`**: Small scripts that confirm Qiskit, Aer and the fake IBM backends are installed and working. Run these first on a new machine.
- **`src/noiseless/`**: The bit-flip, phase-flip and Shor codes on a perfect simulator, with errors placed by hand. Shows that each code detects every single error and reports the right correction.
- **`src/noisy/`**: The codes built to protect any 1-qubit circuit, run on the IBM Fez noise simulator next to the same circuit with no correction. Also checks the codes' failure rates against the theory formulas.
- **`src/pay_off/`**: Runs `compare_fez.py` at many numbers of gates for the chosen gate sets, and plots the error with no correction next to the Toffoli bit-flip and phase-flip codes, to show where each code starts paying off.
- **`src/output_tools/`**: Shared code every script uses for printing tables, writing CSV and text files, and drawing and saving plots, so they all look the same.
- **`src/real_hardware_runs/`**: Runs the bit-flip and phase-flip codes on the real ibm_fez through IBM Quantum, next to the same circuits on the simulator. Saves every result and job ID.
- **`src/simulator_noise_sources/`**: Simulator only: splits each Fez qubit's error into its sources (readout, gate, T1, T2) to show which ones matter most.
- **`src/hardware_vs_simulator/`**: Checks how well the Fez simulator matches a real ibm_fez calibration file, qubit by qubit. Lists the qubits where the two agree, so experiments can run on the ones the simulator models best.

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
