# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.

The project studies the three-qubit bit-flip and phase-flip codes and the nine-qubit Shor code in Qiskit: first on a noiseless simulator to check that they work, then with injected errors, on the noise simulators of IBM machines, and on the real `ibm_fez`, to see when error correction actually lowers the error rate compared with running a circuit unencoded.

## Getting started

These steps are for macOS. If you're on Windows, let me know and I can help find the equivalent steps.

```bash
git clone https://github.com/tikent38/CAHSI-QuantumError.git
cd CAHSI-QuantumError

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install qiskit==2.5.2 qiskit-aer==0.17.2 qiskit-ibm-runtime==0.50.0 matplotlib==3.11.2 pylatexenc==2.11
```

These are the versions behind the committed results, on Python 3.14.7. Keep them if you want the same numbers: the fake backends' noise data ships inside `qiskit-ibm-runtime`, so another version can change the noise.

`qiskit-ibm-runtime` provides the fake IBM backends (such as `FakeFez`) used for realistic device noise, and connects to the real machines. `matplotlib` draws the plots, and `pylatexenc` is only needed to draw circuits as images.

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
│   ├── error_codes.md                # the codes: theory, how they're built, the Toffoli correction
│   ├── experiment_decisions.md       # the choices behind the experiments, and what the results can't show
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
    ├── noisy/                        # the codes on noise simulators vs. unencoded circuits
    │   ├── bit_flip_encoded.py       # bit-flip code, corrected with if blocks
    │   ├── bit_flip_toffoli.py       # bit-flip code, corrected with a Toffoli (Reed et al. 2012)
    │   ├── phase_flip_encoded.py
    │   ├── phase_flip_toffoli.py
    │   ├── shor_encoded.py
    │   ├── shor_toffoli.py
    │   ├── fez_common.py             # shared: the Y gate circuit, reading results, default Fez qubits
    │   ├── compare_fez.py            # runs a circuit unencoded and with each code, on Fez's noise
    │   ├── compare_backends.py       # the same on any fake backend (pay_off/ uses this one)
    │   ├── theory_validation.py      # the codes' failure rates vs. the theory formulas
    │   ├── csvs/
    │   └── images/
    ├── pay_off/                      # how many gates each code needs before it beats no correction
    │   ├── pay_off.py                # counts up on each backend and gate set in turn, one plot per gate set
    │   ├── pay_off_parallel.py       # the same with one process per backend and gate set
    │   ├── pay_off_h.py              # the same with an H gate every k gates
    │   ├── pay_off_common.py         # shared: finding the pay-off points, printing, plots, CSV files
    │   ├── csvs/                     # pay_off.py and pay_off_h.py results, one folder per backend
    │   ├── images/
    │   ├── parallel_runs/            # pay_off_parallel.py results: csvs/, images/, logs/, jobs/
    │   └── reports/                  # pay_off_table.md: pay-off points, gate counts and depth by backend
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

- **`notes/`**: Background for the project: the theory behind the codes and how they're built, the decisions behind the experiments, and links to related papers.
- **`src/installation_tests/`**: Small scripts that confirm Qiskit, Aer and the fake IBM backends are installed and working. Run these first on a new machine.
- **`src/noiseless/`**: The bit-flip, phase-flip and Shor codes on a perfect simulator, with errors placed by hand. Shows that each code detects every single error and reports the right correction.
- **`src/noisy/`**: The codes built to protect any 1-qubit circuit, run on a noise simulator next to the same circuit with no correction. Also checks the codes' failure rates against the theory formulas.
- **`src/pay_off/`**: Runs `compare_backends.py` at many numbers of gates for the chosen backends and gate sets, and plots the error with no correction next to the Toffoli bit-flip and phase-flip codes, to show where each code starts paying off.
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
python src/noisy/compare_backends.py
```

`compare_fez.py` builds a one-qubit test circuit and runs it on a noiseless simulator, then on a simulator with IBM Fez noise, with no correction and with each code. It prints the counts, the distance from the exact answer, and the transpiled circuit size for each. `compare_backends.py` does the same on any of the 68 fake backends.

Set the experiment in the settings block at the bottom of each file:

```python
NUM_GATES = 100    # how many gates in the circuit
SHOTS = 1000       # how many times each version of the circuit is run
SEED = None        # a number (e.g. 3) gives the same circuit every time; None picks a new random one
GATE_SET = "x"     # which test circuit (see below)
MIRROR = False     # True adds the circuit's inverse, so the exact answer is always 0
CODES_TO_RUN = ["bit-flip, if blocks", "bit-flip, Toffoli", "phase-flip, if blocks", "phase-flip, Toffoli"]

# compare_backends.py only
BACKEND = "fez"            # which fake backend to run on
PICK_QUBITS = "like fez"   # "like fez" = the qubits whose noise is closest to the Fez defaults', "best" = the least noisy
```

| `GATE_SET` | Test circuit |
|---|---|
| `"all"` | random X, Y, Z, S, T, id |
| `"xz"` | random X and Z |
| `"repeat"` | X, Y, Z in order, over and over |
| `"x"`, `"y"`, `"z"`, `"id"` | only that gate. Z is done in software, so it adds no noise, and id is only waiting |

Notes:

- `compare_fez.py` can't run circuits with H gates, since none of the codes has a protected version of H. `compare_backends.py` can be handed one through `compare(circuit=...)`: the bit-flip and phase-flip codes decode around each H, which leaves the qubit unprotected for that moment.
- All runs start on the same physical qubits, and no correction runs on the qubit each code is measured on, so differences come from the codes and not from qubit placement.
- Connections with an error rate of 0.5 or more are left out when routing. Fake backends list broken connections at 1.0.
- A code a backend can't run is skipped, and the reason is printed.
- The Shor codes (17 qubits with if blocks, 9 with Toffoli gates) are left out by default, since they take most of the run time, and they only run Pauli gates. Run time grows with `NUM_GATES` × `SHOTS`.
- `compare_fez.py` leaves the simulation method to Aer, and `compare_backends.py` always runs each shot on its own (`method="statevector"`), so at the same seed their numbers differ slightly.
- `compare_backends.py` prints a warning about `fake_nighthawk` when it loads the list of backends. You can ignore it unless you run on that backend.

## Theory validation

```bash
python src/noisy/theory_validation.py
```

Injects X or Z errors with probability p (from 0 to 0.5) at one step on each qubit, with perfect gates and readout, and compares the logical error rate with the formulas: `p` with no correction, `3p^2 - 2p^3` when the code fixes that error, and `3p(1-p)^2 + p^3` when it doesn't. Writes `src/noisy/csvs/theory_validation.csv` and `src/noisy/images/theory_validation.png`.

## Pay-off experiments

```bash
python src/pay_off/pay_off_parallel.py
python src/pay_off/pay_off.py
python src/pay_off/pay_off_h.py
```

These count up through numbers of gates, at even and odd numbers separately, until each code beats no correction 5 times in a row. That first number of gates is the code's pay-off point.

| Script | What it runs | Where the results go |
|---|---|---|
| `pay_off_parallel.py` | Each backend and gate set in its settings, as its own process. Set up for the full results: X, Y, Repeat and ID on 8 backends | `src/pay_off/parallel_runs/` |
| `pay_off.py` | The same experiment, one after another | `src/pay_off/csvs/<backend>/` and `src/pay_off/images/<backend>/` |
| `pay_off_h.py` | The same with an H gate every k gates. Set up for Fez | `pay_off_h.csv`, `pay_off_h_points.csv` and `pay_off_h_<gate set>_every_<k>.png` in those same folders |

The settings behind the full results, in `pay_off_parallel.py`:

```python
BACKENDS_TO_RUN = ["fez", "kingston", "marrakesh", "torino", "washington", "brisbane", "kolkata", "sherbrooke"]
GATE_SETS_TO_RUN = ["x", "y", "repeat", "id"]
JOBS_AT_ONCE = 10          # how many processes run at the same time
MAX_GATES = 1500           # stop counting here if a code still hasn't paid off
SHOTS = 5000               # shots per run, at every number of gates
SEED = 3                   # fixes the test circuit, the transpiler and the simulator
PICK_QUBITS = "like fez"   # "like fez" or "best"
```

Notes:

- The full run took about 6.5 hours on a 12-core M2 Max. Most jobs took 10 to 40 minutes. The slowest took up to 5.6 hours, since a code that never pays off counts all the way to `MAX_GATES`. To keep the Mac from sleeping, start it with `caffeinate -i python src/pay_off/pay_off_parallel.py`, and keep the lid open.
- `pay_off_parallel.py` skips jobs that already finished, so a stopped run picks up where it left off. Their results are committed, so delete `src/pay_off/parallel_runs/jobs` to run them again.
- `pay_off.py` overwrites a backend's CSV files with only the gate sets of that run. That's why `src/pay_off/csvs/` is incomplete: Kingston, Washington and Kolkata only have ID and Repeat there, and Brisbane only has ID. `src/pay_off/parallel_runs/csvs/` has all of them.
- `src/pay_off/reports/pay_off_table.md` reports each code's pay-off points with the transpiled gate count and depth at those points. No script in this repository generates it: the pay-off points are from `parallel_runs/csvs/`, and the sizes are from transpiling each code at its pay-off point with seed 3, counted the way `print_sizes` in `compare_backends.py` does.

The pay-off points come from each backend's full noise model at its fixed strength, on circuits that keep the qubit at 0 or 1, with one correction at the end. So they don't separate depolarizing from measurement noise, don't sweep the physical error rate, and don't count errors that only change the logical phase. See "What the results can't show" in [`notes/experiment_decisions.md`](notes/experiment_decisions.md).

## Real hardware runs

```bash
python src/real_hardware_runs/bit_flip_hardware.py
python src/real_hardware_runs/phase_flip_hardware.py
python src/real_hardware_runs/y_sweep_hardware.py
```

These submit jobs to IBM Quantum on your account. To connect, put an API key in a `.env` file in the main directory, which git ignores. Without one, they use your saved IBM account (`ACCOUNT` in the settings).

```text
QISKIT_IBM_TOKEN=your API key
QISKIT_IBM_INSTANCE=your IBM Quantum instance
```

Set `BACKEND_NAME = "fake_fez"` to try a script on your own machine, with no account. Each run saves its results as a CSV file, with a `_job.json` file holding the job ID and settings, in `src/real_hardware_runs/csvs/`.

## Checking the simulator

```bash
python src/simulator_noise_sources/y_gate_noise_sources.py
python src/hardware_vs_simulator/model_check.py
python src/hardware_vs_simulator/y_gate_test.py
```

- `y_gate_noise_sources.py` runs Y gates on every Fez qubit with each noise source turned on by itself (readout, depolarizing gate error, T1, T2), then all together.
- `model_check.py` compares every number the Fez simulator's noise is built from with a real `ibm_fez` calibration file, and writes `src/hardware_vs_simulator/reports/good_qubits.md`.
- `y_gate_test.py` works out a Y gate circuit's error three ways: calculated from the simulator's noise model, measured by running the simulator, and calculated from the calibration file.

## Reproducing results

Each experiment's settings are in a block at the bottom of its script, and its results are written next to the script, from any working directory. The committed results use `SEED = 3`. The `SEED = None` in `compare_fez.py` and `compare_backends.py` picks a new one each run.

Rerunning a script overwrites its committed results. CSV files come back with Windows line endings, so `git status` can list them as modified when no number changed. To check, use `git diff` (which hides this if `core.autocrlf` is `input`) or compare the rows.

Checked on 2026-11-03 from a clean clone with the versions above. Every row of these matched the committed files:

- `src/noisy/csvs/theory_validation.csv`
- `model_check.csv`, `model_check_cz.csv` and `y_gate_test_1000.csv` in `src/hardware_vs_simulator/csvs/`, and `src/hardware_vs_simulator/reports/good_qubits.md`
- `y_gate_noise_sources_1000.csv` and `y_gate_noise_sources_1000_properties.csv` in `src/simulator_noise_sources/csvs/`
- `pay_off.csv` and `pay_off_points.csv` for Repeat on Fez, in `src/pay_off/parallel_runs/jobs/repeat/fez/`

The rest of the pay-off runs weren't repeated from a clean clone, since they take hours. Other checks, in an existing environment with the same versions: X with an H every 50 gates on Fez matched `pay_off_h.csv`, and `pay_off_parallel.py` matched all 37,917 rows it shares with `pay_off.py`'s CSV files. numpy isn't pinned: the clean install picked 2.5.4 where the existing environment has 2.5.3, and its rows still matched the committed files.

These results won't come back the same from the current code and settings:

- `src/pay_off/images/<backend>/pay_off_z.png` and `src/pay_off/images/shor-fez/` reproduce with Aer's default simulation method, not the `method="statevector"` the code uses now. The Shor Repeat plot also used an older qubit layout.
- `src/pay_off/csvs/pay_off.csv` and `src/pay_off/csvs/pay_off_points.csv` are an older Washington run, measured on qubit 51. Washington is now measured on qubit 54.
- `src/real_hardware_runs/` ran on the real machine, whose noise changes over time.
