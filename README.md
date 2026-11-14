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
    │   ├── fez_common.py             # shared: default Fez qubits and gates, the Y gate circuit, reading results, wiring
    │   ├── compare_fez.py            # runs a circuit unencoded and with each code, on Fez's noise
    │   └── compare_backends.py       # the same on any fake backend, built on compare_fez.py (pay_off/ uses this one)
    ├── theory_validation/            # the codes under noise set by hand, checked against the theory formulas
    │   ├── theory_validation.py      # X or Z errors alone: the codes' failure rates vs. the theory formulas
    │   ├── noise_sweep.py            # depolarizing and measurement noise of any strength, alone and together
    │   ├── csvs/
    │   └── images/
    ├── pay_off/                      # how many gates each code needs before it beats no correction
    │   ├── pay_off.py                # counts up on each backend and gate set in turn, one plot per gate set
    │   ├── pay_off_parallel.py       # the same with one process per backend and gate set
    │   ├── pay_off_h.py              # the same with an H gate every k gates
    │   ├── pay_off_report.py         # writes reports/pay_off_table.md from the pay_off_parallel.py results
    │   ├── pay_off_common.py         # shared: finding the pay-off points, printing, plots, CSV files
    │   ├── csvs/                     # pay_off.py and pay_off_h.py results, one folder per backend
    │   ├── images/
    │   ├── parallel_runs/            # pay_off_parallel.py results: csvs/, images/, logs/, jobs/
    │   └── reports/                  # pay_off_table.md: pay-off points, gate counts and depth by backend
    ├── qubit_mapping/                # Fez simulator only: which qubits a circuit runs on, against which code it uses
    │   ├── mapping_sweep.py          # no correction on every Fez qubit, the Toffoli codes on every placement
    │   ├── mapping_pay_off.py        # each option's best and worst mappings, and pay-off points between them
    │   ├── csvs/
    │   ├── images/
    │   └── reports/                  # mapping_sweep_<gate set>_<gates>.md and mapping_pay_off_<gate set>_<gates>.md
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
        ├── noise_common.py           # shared code: the Y gate circuit, and which calibration file and reading it
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
- **`src/noisy/`**: The codes built to protect any 1-qubit circuit, run on a noise simulator next to the same circuit with no correction.
- **`src/theory_validation/`**: Runs the codes under noise whose strength is set by hand, instead of a backend's fixed noise. Checks their failure rates against the theory formulas, and sweeps the strength of X, Z, depolarizing and measurement noise to see when a code helps.
- **`src/pay_off/`**: Runs `compare_backends.py` at many numbers of gates for the chosen backends and gate sets, and plots the error with no correction next to the Toffoli bit-flip and phase-flip codes, to show where each code starts paying off.
- **`src/qubit_mapping/`**: Simulator only: runs one test circuit with no correction on every Fez qubit, and with the Toffoli bit-flip and phase-flip codes on every way of placing their 3 qubits on connected Fez qubits. Shows how much of the difference in logical error comes from the mapping, and how much from the choice of code. Then lists each option's best and worst mappings, and finds when the codes pay off on good or bad qubits against no correction on good or bad qubits.
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
python src/theory_validation/theory_validation.py
```

Injects X or Z errors with probability p (from 0 to 0.5) at one step on each qubit, with perfect gates and readout, and compares the logical error rate with the formulas: `p` with no correction, `3p^2 - 2p^3` when the code fixes that error, and `3p(1-p)^2 + p^3` when it doesn't. Writes `src/theory_validation/csvs/theory_validation.csv` and `src/theory_validation/images/theory_validation.png`.

## Noise sweep

```bash
python src/theory_validation/noise_sweep.py
```

Runs the codes next to no correction under noise whose strength is set by hand, one kind of noise at a time and then both together. The whole thing takes about 3 minutes.

| Experiment | What's noisy | What it sweeps | Checked against |
|---|---|---|---|
| `depolarizing` | One `id` step on every qubit. Gates and measurements are perfect | p from 0 to 1 | A formula for every code |
| `measurement` | Every measurement. Gates are perfect | q from 0 to 0.5 | A formula for every code |
| `both` | Every gate except `rz`, and every measurement | p from 0.00001 to 0.03, 0 to 2000 `id` gates, and q of 0 and 0.01 | A formula for no correction only |

Every run starts in `|0>` and `|1>`, and in `|+>` and `|->`, since each code fixes one kind of flip and makes the other worse, and each kind of state only shows one of them. Results are reported for each kind of state and their average.

Where the results go:

- `src/theory_validation/csvs/noise_sweep_<experiment>.csv`: every result
- `src/theory_validation/images/noise_sweep_depolarizing.png` and `noise_sweep_measurement.png`: theory against simulation
- `src/theory_validation/images/noise_sweep_both_wins_readout_<q>.png`: where each code beats no correction
- `src/theory_validation/images/noise_sweep_both_lines_readout_<q>.png`: logical error against p

Two settings change the `both` results a lot:

```python
TWO_QUBIT_RATIO = 10    # how many times noisier a 2-qubit gate is than a 1-qubit gate
WIRED_LIKE_FEZ = True   # True = q_0 wired to q_1 and q_2 only (13 2-qubit gates), False = no SWAP needed (10)
```

The results, and how much those settings matter, are under "Noise Sweep" in [`notes/experiment_decisions.md`](notes/experiment_decisions.md).

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
- `python src/pay_off/pay_off_report.py` rebuilds `src/pay_off/reports/pay_off_table.md` from `parallel_runs/csvs/`: each code's pay-off points, with the transpiled gate count and depth at those points. It only transpiles, so it takes about 30 seconds.

The pay-off points come from each backend's full noise model at its fixed strength, on circuits that keep the qubit at 0 or 1, with one correction at the end. So they don't separate depolarizing from measurement noise, don't sweep the physical error rate, and don't count errors that only change the logical phase. `noise_sweep.py` tests those three. See "What the Results Can't Show" in [`notes/experiment_decisions.md`](notes/experiment_decisions.md).

## Qubit mapping sweep

```bash
python src/qubit_mapping/mapping_sweep.py
```

Runs one test circuit on the Fez noise simulator on every mapping, to see which changes the logical error more: which Fez qubits are used, or whether the circuit runs with no correction, the bit-flip code or the phase-flip code.

| Option | Its mappings |
|---|---|
| No correction | Each of Fez's 156 qubits |
| Bit-flip and phase-flip Toffoli codes | Every way of putting `q_0`, `q_1` and `q_2` on 3 connected Fez qubits: 226 lines of 3 qubits, each used 6 ways, so 1356 placements |

The settings, at the bottom of the file:

```python
GATE_SET = "y"          # the test circuit, as in compare_fez.py
NUM_GATES = 500         # gates in the test circuit
START_STATES = [0, 1]   # the states each run starts in; a mapping's error is the average over them
SEED = 3                # the transpiler seed, as in compare_fez.py
MAX_LINES = None        # a number runs only the first that many lines of 3 qubits, for a quick trial run
```

Notes:

- Each run is what `compare_fez.py` does with `DATA_QUBITS` set to that mapping, with one difference: the result is the exact chance of reading the wrong answer, with no shots. So small differences between mappings aren't lost in shot noise.
- Head to head on one placement, no correction is the run on the Fez qubit each code is measured on, as in `compare_fez.py`.
- Placements on 3 qubits that aren't connected are left out, since the transpiler would route them through other qubits.

Where the results go, with `<name>` standing for `mapping_sweep_<gate set>_<gates>`:

- `src/qubit_mapping/csvs/<name>.csv`: every run
- `src/qubit_mapping/csvs/<name>_placements.csv`: one line per placement, with the three options' errors side by side
- `src/qubit_mapping/reports/<name>.md`: the results as tables, which are also printed
- `src/qubit_mapping/images/<name>.png`: every mapping's error, one row of dots per option, with each option's median and the Fez default marked

The results for 500 Y gates are in [`src/qubit_mapping/reports/mapping_sweep_y_500.md`](src/qubit_mapping/reports/mapping_sweep_y_500.md). The choices behind the sweep are under "Qubit Mapping Sweep" in [`notes/experiment_decisions.md`](notes/experiment_decisions.md).

### Best and worst mappings, and when the codes pay off on them

```bash
python src/qubit_mapping/mapping_pay_off.py
```

Reads the sweep's `csvs/mapping_sweep_<gate set>_<gates>.csv` (so run `mapping_sweep.py` first, with the same seed) and lists the 10 best and 10 worst mappings of each option by their error in the sweep. Then it finds how many gates each code needs to pay off in four match-ups: the worst no-correction qubits against the codes' best placements, the best against the worst, best against best, and worst against worst. Each match-up pairs the top 3 of each list. It takes about 3 minutes.

```python
GATE_SET = "y"      # the sweep to use
NUM_GATES = 500     # (the ranking is by each mapping's error at this many gates)
TOP = 10            # how many best and worst mappings of each option to list
COMPARE = 3         # how many of each list go into the match-ups (1 to 4)
MAX_GATES = 1000    # stop counting here if a code still hasn't paid off, and where the plots end
SEED = 3            # the transpiler seed: must be the one the sweep was run with
```

- A code pays off where it starts beating no correction 5 times in a row, as in `pay_off.py`, counting in steps of 2. Unlike `pay_off.py`, no correction runs on the qubit it was picked for, not on the one the code is measured on.
- The errors are exact, as in the sweep. The lists are ranked by the average over starting in `|0>` and `|1>`, but the pay-off points are found for each starting state on its own: each cell of the report reads `|0> / |1>`, and `>1000` means it hadn't paid off by 1000 gates. There is one plot per starting state, on the same scale, with a marker on each code's line where it pays off and the gate counts written beside it. To get the errors at every number of gates quickly, each mapping is transpiled once with one gate, and its test gates are swapped for that gate's noisy channel to the right power. This matches running the full circuits on Aer to 1e-14, and the script checks its errors at the sweep's number of gates against the sweep before using them.
- Results: `csvs/mapping_pay_off_<gate set>_<gates>_ranks.csv` (the lists), `_points.csv` (every pay-off point, from each starting state), `_curves.csv` (every error at every number of gates, from each starting state), `reports/mapping_pay_off_<gate set>_<gates>.md`, and `images/mapping_pay_off_<gate set>_<gates>_start_0.png` and `_start_1.png`.

The results for 500 Y gates are in [`src/qubit_mapping/reports/mapping_pay_off_y_500.md`](src/qubit_mapping/reports/mapping_pay_off_y_500.md).

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

- `src/theory_validation/csvs/theory_validation.csv`
- `noise_sweep_both.csv`, `noise_sweep_depolarizing.csv` and `noise_sweep_measurement.csv` in `src/theory_validation/csvs/`
- `src/pay_off/reports/pay_off_table.md`
- `model_check.csv`, `model_check_cz.csv` and `y_gate_test_1000.csv` in `src/hardware_vs_simulator/csvs/`, and `src/hardware_vs_simulator/reports/good_qubits.md`
- `y_gate_noise_sources_1000.csv` and `y_gate_noise_sources_1000_properties.csv` in `src/simulator_noise_sources/csvs/`
- `pay_off.csv` and `pay_off_points.csv` for Repeat on Fez, in `src/pay_off/parallel_runs/jobs/repeat/fez/`

The rest of the pay-off runs weren't repeated from a clean clone, since they take hours. Other checks, in an existing environment with the same versions: X with an H every 50 gates on Fez matched `pay_off_h.csv`, and `pay_off_parallel.py` matched all 37,917 rows it shares with `pay_off.py`'s CSV files. numpy isn't pinned: the clean install picked 2.5.4 where the existing environment has 2.5.3, and its rows still matched the committed files.

These results won't come back the same from the current code and settings:

- `src/pay_off/images/<backend>/pay_off_z.png` and `src/pay_off/images/shor-fez/` reproduce with Aer's default simulation method, not the `method="statevector"` the code uses now. The Shor Repeat plot also used an older qubit layout.
- `src/pay_off/csvs/pay_off.csv` and `src/pay_off/csvs/pay_off_points.csv` are an older Washington run, measured on qubit 51. Washington is now measured on qubit 54.
- In `src/qubit_mapping/`, only the files named `mapping_sweep_y_500` come from the current script. `mapping_sweep_x.csv`, `mapping_sweep_y.csv`, `mapping_sweep_repeat.csv`, `mapping_sweep_id.csv` and `mapping_sweep_summary.csv`, and the plots with those names and `mapping_sweep_shares.png`, are from an earlier version of `mapping_sweep.py`. It ran each gate set at 0, 50, 100, 200, 500 and 1000 gates, with no correction on 154 of Fez's qubits.
- `src/real_hardware_runs/` ran on the real machine, whose noise changes over time.
