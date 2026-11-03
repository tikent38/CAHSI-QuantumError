# Experimental Decisions

The choices behind the experiments in `src/`, why they were made, and what the results can't show. The [README](../README.md) says how to run everything, and [error_codes.md](error_codes.md) says how the codes are built. The numbers here are the settings behind the committed results. Each script's settings block is where to change them.

## Test Circuits

Every experiment protects one qubit running a simple 1-qubit circuit, so the code is the only thing being compared.

| Gate set | Circuit | Notes |
|----------|---------|-------|
| `x`, `y` | that gate, over and over | Each gate flips the answer. On Fez a Y gate becomes RZ + X |
| `repeat` | X, Y, Z in order, over and over | The answer cycles every 3 gates |
| `id`     | id, over and over | Only waiting: id does nothing, but each one gets the backend's noise. The answer is always 0 |
| `z`      | Z, over and over | Done in software, so it adds no noise. Left out of the pay-off table |
| `all`, `xz` | random gates | For single runs in `compare_fez.py` and `compare_backends.py`. `xz` is also used between the H gates in `pay_off_h.py` |

- **Error:** `|P(1) - exact P(1)|`, with the exact answer from the circuit's state, with no shots or noise. Without H gates the qubit stays at 0 or 1 (up to a phase), so this is the chance of reading the wrong answer.
- **Even and odd:** X and Y gates give 0 after an even number of gates and 1 after an odd number, and the codes do worse when the answer is 1. So `pay_off.py` counts up through each separately.
- **Steps:** each step keeps the exact answer the same: 2 gates for X, Y and ID, and 6 for Repeat, since 6 is a whole number of its cycles and also keeps even or odd. `pay_off_h.py` steps by 10, and adds up to 2 gates at the end to bring the answer back to 0.

## The Codes

- **Toffoli versions:** the pay-off and real hardware runs use them. They take 3 qubits, with no ancillas and only one measurement.
- **One correction, at the end of the circuit:** errors build up for the whole circuit, and two flipped qubits are too many to fix. The cost in 2-qubit gates doesn't grow with the number of test gates: it was 13 on all 8 backends for both codes, at every number of X gates checked (0, 1, 48, 49 and 300).

## Putting Circuits on a Machine

- **`optimization_level=0`:** keeps every gate. Otherwise the transpiler would merge the test gates into one or two.
- **Routing:** `sabre`, with the seed set. Connections with an error of 0.5 or more are left out, since fake backends list broken connections at 1.0.
- **Same starting qubits for every code:** so differences between the codes don't come from landing on better or worse qubits.
- **No correction on the same qubit as the code's result:** routing often moves the result to another qubit, so no correction runs on the qubit the code is measured on. Both are read out on the same physical qubit.
- **Fez's qubits (87, 88, 86):** 87 is wired to both 88 and 86, so the codes encode and decode without SWAPs. Defaults are in `src/noisy/fez_common.py`.
- **Other backends:** `pick="like fez"` takes the qubits whose noise is closest to Fez's defaults, wired the same way. The pay-off table uses this. `pick="best"` takes the backend's least noisy qubits instead, with results in a `best/` folder.
- **Real hardware:** the same qubits and transpiler settings as the simulations, so the two can be compared.

## Simulation

- **Noise model:** `AerSimulator.from_backend`, which builds noise from the backend's listed calibration: depolarizing gate error, T1/T2 relaxation and readout error. `rz` is done in software, with no time or error.
- **`method="statevector"`:** in `compare_backends.py`, and so in the pay-off runs. Each shot runs on its own, with random errors picked for that shot. Left to itself, Aer would work out exact probabilities with a density matrix for circuits with no if blocks, and sample every shot from them. `compare_fez.py` still leaves this to Aer, so its numbers differ slightly at the same seed.x

## Pay-Off Rule

- **5 wins in a row (`IN_A_ROW`):** so one lucky result from shot noise doesn't count. The pay-off point is the first number of gates in that run of wins.
- **5000 shots** per run, at every number of gates.
- **Limits:** up to 1500 gates in `pay_off.py` and `pay_off_parallel.py`, and 500 in `pay_off_h.py`.
- **Early stop:** a sweep stops once every code has paid off, or at the limit.
- **Transpiled size:** `circuit.size()` and `circuit.depth()`, as `print_sizes` reports them. Gates include `rz` and measurements, and leave out barriers. Many of the gates add no noise: at 48 X gates on Fez, 207 of the phase-flip code's 255 gates are `rz`.

## Theory Validation

`src/noisy/theory_validation.py` is the controlled test, where the formulas say exactly what to expect.

- **Noise:** an X or Z error with probability p on one `id` step, on every qubit. Nothing else is noisy.
- **Sweep:** 13 values of p from 0 to 0.5, with 10,000 shots per starting state and seed 3.
- **Starting states:** an error only shows up if it changes the state being measured. X errors flip `|0>` and `|1>`. Z errors only change their sign, so the runs that need to see a Z error start in `|+>` or `|->` and put an H before the measurement. The phase-flip code stores `|0>` as `|+++>`, so Z errors already flip it.
- **Result:** the largest gap between simulation and theory is 0.01, at 20,000 shots per point.

## What the Results Can't Show

- **Depolarizing and measurement noise on their own.** The codes only see these inside each backend's full noise model, together with T1/T2, so their effects can't be separated. `y_gate_noise_sources.py` does separate them, but only on unencoded Y gates, at Fez's fixed strengths.
- **A sweep of the physical error rate with realistic noise.** Only `theory_validation.py` varies the error rate, and only for X and Z errors with perfect gates and readout, so a code's own gates can't hurt it. The pay-off runs vary the number of gates at each backend's fixed noise. The 8 backends aren't a controlled sweep, especially with qubits picked to resemble Fez's. So the pay-off table says when a code helps in numbers of gates, not in error rates.
- **Errors that only change the logical phase.** Without H gates the qubit stays at 0 or 1, so only logical bit flips show up in the result. Each code's weak spot never counts: Z errors for the bit-flip code and X errors for the phase-flip code. `theory_validation.py` shows those errors make a code worse than no correction, so the pay-off points may look better than they would for a circuit using superpositions. The H runs do expose this, and most of them never paid off, though each H also adds decoding and encoding gates, so those runs can't separate the two effects.
- **Repeated correction.** Every run corrects once, at the end. Correcting during a long circuit isn't tested.
- **Whether a pay-off lasts.** Sweeps stop once every code has paid off, so most can't show what happens at more gates.
- **How much results vary.** Each experiment uses one seed and has no error bars.

## Reading the Pay-Off Table

For rows in `src/pay_off/reports/pay_off_table.md` that are easy to misread:

- **Kingston ID, phase-flip odd (443):** probably shot noise. The odd sweep stopped at 451, right after its 5 wins, while the even sweep ran to 1500 and won 0 of the 250 points above 1000 gates.
- **Sherbrooke ID (all `>1500`):** there's almost nothing for a code to beat, so this doesn't mean the codes do badly at waiting in general. Aer's `id` noise on qubit 101 is only relaxation, which leaves `|0>` alone, so with no correction the error stays between 0.0014 and 0.0074 for all 1500 gates, around its 0.004 readout error.
