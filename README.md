# CAHSI-QuantumError

A repository for the CAHSI project: **Reproducible Benchmarking of Small Quantum Error-Correction Circuits for Quantum Software Reliability**.

The project studies the three-qubit bit-flip and phase-flip codes and the nine-qubit Shor code in Qiskit: first on a noiseless simulator to check that they work, then on noisy simulators to see when error correction actually lowers the error rate compared with running a circuit unencoded.

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
│   ├── noiseless/                # the codes with hand-placed errors, no noise
│   │   ├── bit_flip_code.py
│   │   ├── phase_flip_code.py
│   │   ├── shor_code.py
│   │   └── error_test.py
│   └── noisy/                    # the codes on IBM Fez noise vs. unencoded circuits
│       ├── bit_flip_encoded.py
│       ├── phase_flip_encoded.py
│       ├── bit_flip_toffoli.py
│       ├── phase_flip_toffoli.py
│       ├── shor_encoded.py
│       └── compare_fez.py
├── .gitignore
└── README.md
```

All commands below are run from the repository’s main directory.

## `notes/`

### `notes/error_codes.md`

Background for the code in `src/`: the classical repetition code and its error rate $3p^2 - 2p^3$, the quantum bit-flip code and its syndrome table, and the phase-flip code (why the bit-flip code can’t catch phase flips, and how encoding in the $|\pm\rangle$ basis fixes that).

### `notes/research_papers.md`

Links to papers related to the project, grouped by topic: the bit-flip code, the phase-flip code, and the Toffoli-based correction (Reed et al. 2012).

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

It prints the measurement counts. Because the qubit is in an equal superposition, `0` and `1` should each occur about half the time.

### `aer_noise_test.py`

Applies 10 X gates to one qubit (they cancel, so the ideal answer is always `0`) and runs it 1,000 times with no noise and 1,000 times with the noise of IBM’s Fez device (`FakeFez`). It prints the counts and error rate for each run, plus the device’s error rates for the qubit used.

```bash
python src/installation_tests/aer_noise_test.py
```

## `src/noiseless/`

The codes with no noise. Errors are added by hand at a chosen point so you can check that each one is detected.

### `bit_flip_code.py`

`bit_flip_code(state_prep, error_qubits=None)` builds the bit-flip code circuit for a one-qubit input state: encode $a|0\rangle + b|1\rangle \to a|000\rangle + b|111\rangle$, apply an X error to each qubit in `error_qubits`, measure the two parity checks into the syndrome, then decode and measure. The circuit does not apply the correction itself; `print_correction(syndrome)` prints which X gate would fix the error.

### `phase_flip_code.py`

`phase_flip_code(state_prep, error_qubits=None)` is the same idea for phase flips: it encodes into $a|{+}{+}{+}\rangle + b|{-}{-}{-}\rangle$, applies Z errors, and measures the syndrome using phase kickback. `print_correction(syndrome)` prints which Z gate would fix the error.

### `shor_code.py`

`shor_code(state_prep, x_errors=None, z_errors=None)` builds the 9-qubit Shor code circuit, following the IBM course [Foundations of Quantum Error Correction: The 9-qubit Shor code](https://quantum.cloud.ibm.com/learning/en/courses/foundations-of-quantum-error-correction/correcting-quantum-errors/shor-code) (also Nielsen & Chuang §10.2). It is the phase-flip code with each of its three qubits encoded again with the bit-flip code, giving three blocks: `q_0`–`q_2`, `q_3`–`q_5`, `q_6`–`q_8`.

- **Encode:** the phase-flip code on `q_0`, `q_3`, `q_6`, then the bit-flip code inside each block, giving $|0\rangle \to (|000\rangle + |111\rangle)^{\otimes 3}/2\sqrt{2}$ and $|1\rangle \to (|000\rangle - |111\rangle)^{\otimes 3}/2\sqrt{2}$.
- **Errors:** an X on each qubit in `x_errors` and a Z on each qubit in `z_errors`. Putting the same qubit in both is a Y error.
- **Bit-flip check:** the bit-flip code’s two parity checks inside each block (ancillas `a_0`–`a_5`), measured into `b0`, `b1`, `b2`.
- **Phase-flip check:** two ancillas (`a_6`, `a_7`) measure X on all six qubits of blocks 0 and 1, and of blocks 1 and 2, using the same phase kickback as `phase_flip_code.py`, measured into `p`. This tells which block had its sign flipped, not which qubit. The course instead decodes each block, runs the phase-flip check on `q_0`, `q_3`, `q_6`, and re-encodes; both measure the same thing, and this version uses fewer gates.

The circuit does not apply the correction itself; `print_correction(bit_syndromes, phase_syndrome)` prints which X gate and which block’s Z gate would fix the error. It can fix one X and one Z error at once, on the same qubit or on different ones.

### `error_test.py`

Runs a code on input $|0\rangle$ with no error and with an error on each qubit (4,000 shots each), then prints the circuit, the syndrome, the probability of measuring `1`, and the needed correction for each case. For the Shor code it tests X, Z, and Y errors on qubits in each block, plus an X and a Z on different qubits. Because the circuits don’t correct themselves, it fixes the measured result in Python (`correct_bit_flip`, `correct_shor`).

```bash
python src/noiseless/error_test.py
```

Choose which code to test by commenting or uncommenting `test_bit_flip()`, `test_phase_flip()`, and `test_shor()` at the bottom of the file (currently only `test_phase_flip()` runs).

## `src/noisy/`

The bit-flip, phase-flip, and Shor codes on a noisy Aer simulator, compared with running the same circuit unencoded.

### `bit_flip_encoded.py`

`bit_flip_encoded(circuit, measure=True)` takes any one-qubit circuit and returns its bit-flip-code version: encode into $a|000\rangle + b|111\rangle$, apply the circuit’s gates to the encoded qubit, measure the syndrome with the two ancillas, and apply an X to the flipped qubit. With `measure=True` it also decodes and measures the result into an `out` register. Run the returned circuit on any (noisy) `AerSimulator`.

How the circuit’s gates are applied to the encoded qubit:

- **X, Y, Z, `id`** are applied to all three data qubits, so the qubit stays protected.
- **S, T, Sdg, Tdg, P, Rz** (gates that only add a phase to `1`) are applied to `q_0` only. That adds the phase to the $|111\rangle$ term once, which is exactly the encoded gate, so the qubit stays protected. Applying them to all three qubits would add the phase three times (S on all three acts like Sdg).
- **H and any other gate** is applied by decoding (2 CNOTs), running the gate on `q_0`, and re-encoding (2 CNOTs). The qubit is not protected during that gate, and each one adds 4 CNOTs. H has no protected version in the bit-flip code.

There is a single syndrome check at the end, so it can correct at most one bit flip over the whole circuit.

This file, `phase_flip_encoded.py`, and `shor_encoded.py` only define functions; running them directly prints nothing. To see an encoded circuit, run this from `src/noisy/`:

```python
from qiskit import QuantumCircuit
from bit_flip_encoded import bit_flip_encoded

example = QuantumCircuit(1)
example.x(0)
example.s(0)
print(bit_flip_encoded(example).draw(fold=-1))
```

### `phase_flip_encoded.py`

`phase_flip_encoded(circuit, measure=True)` is the bit-flip code done in the $|\pm\rangle$ basis instead of the $|0\rangle, |1\rangle$ basis, following the structure of the IBM course [Foundations of Quantum Error Correction: Repetition codes](https://quantum.cloud.ibm.com/learning/en/courses/foundations-of-quantum-error-correction/correcting-quantum-errors/repetition-codes) (also Nielsen & Chuang §10.1.2):

- **Encode:** encode exactly as for the bit-flip code, then H on every qubit: $a|0\rangle + b|1\rangle \to a|{+}{+}{+}\rangle + b|{-}{-}{-}\rangle$.
- **Gates:** each gate the bit-flip code applies, conjugated by H. Logical X is ZZZ, logical Z is XXX, logical Y is YYY; S, T, Sdg, Tdg, P and Rz are applied to `q_0` as H, gate, H (no decoding). H still has no encoded version, so it is applied by decoding and re-encoding.
- **Detect:** the course’s simplified phase-flip check: the two ancillas start in $|+\rangle$ (H), act as CNOT controls onto the data qubits so each qubit’s sign kicks back onto them (phase kickback), then H and measure. This measures $X_1X_2$ and $X_2X_3$, i.e. whether neighbouring qubits have the same sign. It gives the same result as putting H on the data qubits around the bit-flip check, with fewer gates.
- **Recover:** the bit-flip X correction conjugated by H, which is a Z on the qubit the syndrome points to.

This code does not detect X errors. In this encoding a single X on any qubit acts as a logical phase flip, which doesn’t change a `0`/`1` measurement unless the circuit later rotates the qubit (e.g. with H).

### `bit_flip_toffoli.py` and `phase_flip_toffoli.py`

`bit_flip_toffoli(circuit, measure=True)` and `phase_flip_toffoli(circuit, measure=True)` are the same two codes, with the same encoding and the same handling of each gate, but they correct the error the way [Reed et al. (2012)](https://doi.org/10.1038/nature10786) do: with a Toffoli (CCNOT) gate inside the circuit instead of measuring ancillas and using if blocks.

- **No ancillas:** the circuit uses only the 3 data qubits.
- **Decode first:** after decoding, `q_1` and `q_2` hold the syndrome. A flip on `q_1` or `q_2` stays on that qubit and doesn’t reach `q_0`. A flip on `q_0` sets both `q_1` and `q_2` to 1.
- **Correct:** a Toffoli controlled by `q_1` and `q_2` flips `q_0` back. Nothing is measured until the final result.

For the phase-flip code, decoding undoes the H gates, which turns a sign flip back into a bit flip, so the same Toffoli fixes it.

With `measure=False` the corrected qubit is left decoded on `q_0` and the syndrome stays on `q_1` and `q_2`. Unlike the if-block versions, these qubits would need to be reset before another round of correction.

How the two ways of correcting differ:

- **False corrections.** In the if-block versions, a flip on `q_0` gives syndrome `01`, where only one ancilla is set, so any single error that sets `a_0` by mistake (a readout error, a bad syndrome CNOT, or a flip on the ancilla itself) makes the if blocks apply an X or Z to a `q_0` that was fine. The Toffoli only flips `q_0` when `q_1` and `q_2` are both 1, so a false correction needs two errors at once.
- **Measurements.** The if-block versions measure both ancillas as well as the output. The Toffoli versions measure only `q_0`.
- **Cost of the Toffoli.** On Fez the Toffoli becomes about 6 two-qubit gates plus SWAPs, since three qubits can’t all be connected to each other on Fez’s qubit wiring.

### `shor_encoded.py`

`shor_encoded(circuit, measure=True)` is the Shor code from `noiseless/shor_code.py` (same encoding and checks) built the same way as `bit_flip_encoded`: it applies the circuit’s gates to the encoded qubit, measures the syndromes, and corrects with if blocks (`qc.switch`). It uses 9 data qubits and 8 ancillas.

How the circuit’s gates are applied to the encoded qubit:

- **X** is Z on one qubit of each block (`q_0`, `q_3`, `q_6`), **Z** is X on every qubit of one block (`q_0`, `q_1`, `q_2`), **Y** is both, and **`id`** goes on all nine qubits. The qubit stays protected.
- **S, T, Sdg, Tdg, P, Rz** are applied by decoding block 0 only (2 CNOTs), applying H, the gate, H to `q_0` as in `phase_flip_encoded`, and re-encoding block 0 (2 CNOTs). Blocks 1 and 2 stay encoded, but block 0 is not fully protected during the gate.
- **H and any other gate** is applied by fully decoding (8 CNOTs), running the gate on `q_0`, and re-encoding (8 CNOTs). The qubit is not protected during that gate.

After the gates, it runs the bit-flip check and applies an X to the flipped qubit in each block, then runs the phase-flip check and applies a Z to the first qubit of the flagged block. As with the other codes, there is a single round of checks at the end.

### `compare_fez.py`

Builds a one-qubit circuit and runs it seven ways: on a noiseless `AerSimulator`, and on `AerSimulator` with IBM Fez noise with no correction and with each of the five encoders:

| Label | Function | How the error is corrected |
|---|---|---|
| bit-flip, if blocks | `bit_flip_encoded` | measure the ancillas, then X with `qc.switch` |
| bit-flip, Toffoli | `bit_flip_toffoli` | decode, then a Toffoli flips `q_0` back |
| phase-flip, if blocks | `phase_flip_encoded` | measure the ancillas, then Z with `qc.switch` |
| phase-flip, Toffoli | `phase_flip_toffoli` | decode, then a Toffoli flips `q_0` back |
| Shor, if blocks | `shor_encoded` | measure the ancillas, then X in each block and Z on one block with `qc.switch` |

It prints the counts for each, how far each is from the exact answer, and the size of each circuit after transpiling for Fez.

Circuits must not contain H gates; `compare()` raises a `ValueError` if they do. H has no protected version in any of the codes, so all of them would have to decode around it.

Set the experiment in the settings block at the bottom of the file, then run it:

```python
NUM_GATES = 3000     # how many random gates in the circuit
SHOTS = 1000         # how many times each version of the circuit is run
SEED = 3             # a number (e.g. 3) gives the same circuit every time; None picks a new random one
GATE_SET = "repeat"  # "all" = X, Y, Z, S, T, id     "xz" = only X and Z     "repeat" = X, Y, Z, S, T in order, over and over
MIRROR = False       # True adds the circuit's inverse, so the exact answer is always 0
```

```bash
python src/noisy/compare_fez.py
```

From your own code, call `compare(num_gates, shots, seed, gate_set, mirror, encoders)`, where `encoders` is a `{label: function}` dict of the codes to run (all five above by default), or build circuits with `random_all_gates(num_gates, seed)` (X, Y, Z, S, T, id), `random_xz_gates(num_gates, seed)` (X and Z only), or `repeated_gates(num_gates)` (X, Y, Z, S, T repeated in order, not random). With `"repeat"` the seed doesn’t change the circuit, but it still sets the transpiler’s qubit placement and the simulator’s randomness.

The seed used is printed, so any run can be repeated exactly. All noisy runs are transpiled with `optimization_level=0` so the transpiler doesn’t merge the random gates away.

Every run starts on the same physical qubits of Fez, which are printed as `Fez qubits`. The transpiler picks them once for the largest encoded circuit (the 17-qubit Shor code), and each run reuses them. Every code puts its data qubits first, so all codes share `q_0`–`q_2`’s qubits and no correction gets `q_0`’s qubit; the 3-qubit codes’ ancillas land on the Shor code’s `q_3` and `q_4`. Without this, each circuit would be placed separately and could land on better or worse qubits, which would look like a difference between the codes. Routing can still add different SWAPs to each circuit, so qubits can move after the start.

A few of Fez’s CZ connections have an error rate of 1.0, so a gate sent through one of them always fails. The transpiler doesn’t look at error rates when it places and routes circuits, so `compare()` transpiles with Fez’s wiring minus those connections (`working_coupling_map`). Otherwise a circuit routed through one of them would come out close to 50/50. The noise from all of Fez’s other gates and qubits is still applied when the circuits run.

The Shor code’s circuit is much larger than the others (17 qubits and many more gates), so it takes most of the run time. Simulation time grows with `NUM_GATES` × `SHOTS`; to compare only some of the codes, pass `encoders` to `compare()`.
