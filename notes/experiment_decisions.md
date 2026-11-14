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
- **`method="statevector"`:** in `compare_backends.py`, and so in the pay-off runs. Each shot runs on its own, with random errors picked for that shot. Left to itself, Aer would work out exact probabilities with a density matrix for circuits with no if blocks, and sample every shot from them. `compare_fez.py` still leaves this to Aer, so its numbers differ slightly at the same seed.

## Pay-Off Rule

- **5 wins in a row (`IN_A_ROW`):** so one lucky result from shot noise doesn't count. The pay-off point is the first number of gates in that run of wins.
- **5000 shots** per run, at every number of gates.
- **Limits:** up to 1500 gates in `pay_off.py` and `pay_off_parallel.py`, and 500 in `pay_off_h.py`.
- **Early stop:** a sweep stops once every code has paid off, or at the limit.
- **Transpiled size:** `circuit.size()` and `circuit.depth()`, as `print_sizes` reports them. Gates include `rz` and measurements, and leave out barriers. Many of the gates add no noise: at 48 X gates on Fez, 207 of the phase-flip code's 255 gates are `rz`.

## Theory Validation

`src/theory_validation/theory_validation.py` is the controlled test, where the formulas say exactly what to expect.

- **Noise:** an X or Z error with probability p on one `id` step, on every qubit. Nothing else is noisy.
- **Sweep:** 13 values of p from 0 to 0.5, with 10,000 shots per starting state and seed 3.
- **Starting states:** an error only shows up if it changes the state being measured. X errors flip `|0>` and `|1>`. Z errors only change their sign, so the runs that need to see a Z error start in `|+>` or `|->` and put an H before the measurement. The phase-flip code stores `|0>` as `|+++>`, so Z errors already flip it.
- **Result:** the largest gap between simulation and theory is 0.01, at 20,000 shots per point.

## Noise Sweep

`src/theory_validation/noise_sweep.py` sets the strength of the noise by hand, one kind of noise at a time and then both together.

### Setup

- **Depolarizing experiment:** depolarizing noise with parameter p on one `id` step on every qubit, with perfect gates and measurements. Aer gives each qubit X, Y or Z with chance p/4 each, so a bit flip (X or Y) with chance f = p/2, and a phase flip (Z or Y) with the same chance.
- **Measurement experiment:** each measurement reads the wrong bit with chance q, the same for 0 to 1 and 1 to 0, with perfect gates.
- **Both together:** depolarizing noise p on `id`, `sx` and `x`, `TWO_QUBIT_RATIO` × p on `cz`, and none on `rz`, plus measurement error q. This is the one where a code's own gates count against it.
- **Two kinds of state:** every run starts in `|0>` and `|1>`, and in `|+>` and `|->`. The average is over those two kinds of state, not every possible state.
- **Preparing and measuring:** the state is prepared on `q_0` before encoding, and the last H comes after the correction. So the `|+>`, `|->` runs pay for no extra decoding and encoding gates, and a wrong correction acts on `|+>` or `|->` rather than on 0 or 1.
- **Circuits:** in Fez's gates, with `optimization_level=0` and `sabre`, and `q_0` wired to `q_1` and `q_2` only, like Fez's 87, 88 and 86. That takes 13 2-qubit gates, the same as the pay-off runs.
- **Test circuit:** only `id` gates, so both codes run the same gates on all 3 qubits. An X gate would be noisy in the bit-flip code but only `rz` in the phase-flip code.
- **2-qubit gates 10 times noisier than 1-qubit gates:** this is an assumption, and it matters (see the results). Fez's numbers imply about 6, from `noise_levels` on each backend's table qubits, with 1-qubit p as bit flips plus phase flips per X gate, and 2-qubit p as 4/3 of the average 2-qubit gate error. That gives 6.1 on Fez, 6.5 on Kingston, 6.9 on Marrakesh, 9.3 on Torino, 18 on Sherbrooke, 20 on Brisbane, 26 on Washington and 30 on Kolkata.
- **Deciding a winner:** a code only wins or loses if its failure rate is more than 3 standard errors from no correction's. Otherwise it's too close to call.
- **Shots and seed:** 20,000 shots per starting state for the depolarizing and measurement experiments, and 100,000 for both together, with seed 3. Both together uses `method="density_matrix"`, which works out the exact probabilities and samples every shot from them, so more shots cost little.

### Results

- **Checks against theory:** with no noise, every code gives the exact answer. 2 of the 714 points with a formula are more than 3 standard errors from it, about what chance predicts.
- **Depolarizing noise alone:** each code helps one kind of state and hurts the other. At p = 0.1, no correction fails 0.05 of the time, and a code fails about 0.007 on `|0>`, `|1>` and 0.136 on `|+>`, `|->`, which averages to 0.071. Averaged, a code is worse than no correction by f(1 - f)(1/2 - f) for every f between 0 and 1/2. The bit-flip and phase-flip codes behave the same, and so do the Toffoli and if-block versions.
- **Measurement noise alone:** Toffoli codes only measure the result, after correcting, so they fail exactly as often as no correction (q). If-block codes also read a syndrome, and a misread one "fixes" a healthy qubit. That nearly doubles the error on `|0>`, `|1>` (2q - 3q² + 2q³, or 0.093 at q = 0.05), and doesn't change `|+>`, `|->` (q).
- **Both together, on `|+>`, `|->` and on average:** no code beats no correction at any point, at any ratio tried.
- **Both together, on `|0>`, `|1>`:** a code needs enough gates to pay for itself, and low enough noise that it isn't overwhelmed. At the default settings:

| `id` gates | Where a code beats no correction |
|------------|----------------------------------|
| 0 to 50    | nowhere |
| 100        | nowhere: too close to call up to p = 0.0001, and it loses above that |
| 200        | up to p = 0.001, and it loses at p = 0.003 and 0.01 |
| 500        | up to p = 0.003 (by only 1 to 2% at that point), then too close to call |
| 1000, 2000 | up to p = 0.001, then too close to call, with both near 0.5 |

- **Measurement error added to both together:** an error of 0.01 adds up to about 0.01 to both no correction and the code, so it hardly moves where a code wins. It only hides the smallest differences in shot noise.
- **What sets the number of gates:** mostly how noisy the code's own 2-qubit gates are. The first number of gates tried where the bit-flip code wins on `|0>`, `|1>`:

| Settings | First win | Up to p |
|----------|-----------|---------|
| 2-qubit gates 5 times noisier | 100 gates | 0.001 |
| 2-qubit gates 10 times noisier | 200 gates | 0.001 |
| 2-qubit gates 10 times noisier, no SWAP (10 2-qubit gates) | 100 gates | 0.0003 |
| 2-qubit gates 20 times noisier | 500 gates | 0.001 |

- **Next to the pay-off table:** the backends with the lower ratios (Fez, Kingston, Marrakesh, Torino) pay off earlier on ID, at 123 to 255 gates for the bit-flip code, and the ones with the higher ratios (Washington, Brisbane, Kolkata, Sherbrooke) at 839 to 1087 gates or never. That's the same direction, but it isn't proof: those backends also differ in T1/T2 and gate times.

## Qubit Mapping Sweep

`src/qubit_mapping/mapping_sweep.py` asks which changes the logical error more on Fez: which qubits a circuit runs on (the mapping), or whether it runs with no correction, the bit-flip code or the phase-flip code (the option).

### Setup

- **Test circuit:** 500 Y gates. Both codes apply a Y as a Y on all 3 qubits, so they run the same gates in between.
- **Mappings for no correction:** each of Fez's 156 qubits.
- **Mappings for the codes:** every way of putting `q_0`, `q_1` and `q_2` on 3 connected Fez qubits. Fez's wiring has no triangles, so 3 connected qubits are always a line, and each of the 226 lines can be used 6 ways. Only the 2 with `q_0` in the middle encode and decode without SWAPs, like the defaults (87, 88, 86).
- **Left out:** placements on 3 qubits that aren't connected. The transpiler would route them through other qubits, so the run would no longer be on the 3 qubits it was given, and there are about 3.7 million of them.
- **Starting states:** every run starts in `|0>` and in `|1>`, and a mapping's error is the average of the two. `|0>` alone would favour the bit-flip code: it stores `|0>` as `|000>`, which can't decay (T1 only takes `|1>` to `|0>`), while the phase-flip code stores it as `|+++>`, which can.
- **The same runs as `compare_fez.py`:** the same codes, transpiler settings and Fez noise, with seed 3, as if `DATA_QUBITS` were set to each mapping in turn.
- **Exact results:** `method="density_matrix"` gives the exact chance that the measured qubit is 1, and the readout error is added with the simulator's own numbers. With no shots, small differences between mappings aren't lost in shot noise.
- **Head to head:** on one placement, no correction is the run on the Fez qubit each code is measured on, so all three are read out by the same qubit.
- **Mapping against option:** the spread of the errors of all three options on every placement (their summed squared distance from their average) is split into 4 parts that add up to it, the way an analysis of variance does: which 3 qubits, which qubit plays which role, which option, and the gap between the options changing from placement to placement. The first two together are the mapping.

### Results

From `src/qubit_mapping/reports/mapping_sweep_y_500.md`:

- **The mapping matters more than the option:** the mapping accounts for 54% of the spread and the option for 8%. The other 38% is the gap between the options changing from placement to placement.
- **Each option over all its mappings:**

| Option | Best | Median | Worst |
|--------|------|--------|-------|
| No correction | 0.0295 | 0.0980 | 0.4590 |
| Bit-flip code | 0.0293 | 0.0623 | 0.2691 |
| Phase-flip code | 0.0347 | 0.0874 | 0.3498 |

- **Head to head:** the bit-flip code has the lowest error of the three on 990 of the 1356 placements, no correction on 303, and the phase-flip code on 63. The bit-flip code beats no correction on 1052 placements, and the phase-flip code on 740.
- **The Fez defaults (87, 88, 86):** 0.0650 for the bit-flip code and 0.0549 for the phase-flip code, lower than 45% and 92% of their placements. No correction on qubit 86, where both are measured, is 0.1036.

## What the Results Can't Show

- **In the pay-off runs, depolarizing and measurement noise on their own.** The pay-off runs only see these inside each backend's full noise model, together with T1/T2, so their effects can't be separated. `noise_sweep.py` tests each on its own, with the codes. `y_gate_noise_sources.py` does too, but only on unencoded Y gates, at Fez's fixed strengths.
- **In the pay-off runs, an error rate.** The pay-off runs vary the number of gates at each backend's fixed noise. The 8 backends aren't a controlled sweep, especially with qubits picked to resemble Fez's. So the pay-off table says when a code helps in numbers of gates, not in error rates. `noise_sweep.py` and `theory_validation.py` do vary the error rate.
- **In the pay-off runs, errors that only change the logical phase.** Without H gates the qubit stays at 0 or 1, so only logical bit flips show up in the result. Each code's weak spot never counts: Z errors for the bit-flip code and X errors for the phase-flip code. The `|+>`, `|->` runs in `noise_sweep.py` show how much that can matter: under that noise, a code never beats no correction on them. So the pay-off points may look better than they would for a circuit using superpositions. The H runs also expose this, and most of them never paid off, though each H also adds decoding and encoding gates, so those runs can't separate the two effects.
- **In the noise sweep, a real machine's noise.** Its noise is depolarizing only, the same on every qubit, with no T1/T2, and its test circuit only waits. Its numbers show the shape of the answer, not a prediction for any backend.
- **In the mapping sweep, which qubits to use on the real machine.** It runs on the Fez simulator, and a qubit's numbers there can be far from the real `ibm_fez`'s today: `model_check.py` finds only 13 of the 156 qubits within 2x in all six areas it compares. It's also one test circuit, at one transpiler seed. So it shows how much the mapping can matter, not which mapping is best on the machine.
- **Repeated correction.** Every run corrects once, at the end. Correcting during a long circuit isn't tested.
- **Whether a pay-off lasts.** Pay-off sweeps stop once every code has paid off, so most can't show what happens at more gates.
- **How much the pay-off results vary.** Each pay-off experiment uses one seed and has no error bars.

## Reading the Pay-Off Table

For rows in `src/pay_off/reports/pay_off_table.md` that are easy to misread:

- **Kingston ID, phase-flip odd (443):** probably shot noise. The odd sweep stopped at 451, right after its 5 wins, while the even sweep ran to 1500 and won 0 of the 250 points above 1000 gates.
- **Sherbrooke ID (all `>1500`):** there's almost nothing for a code to beat, so this doesn't mean the codes do badly at waiting in general. Aer's `id` noise on qubit 101 is only relaxation, which leaves `|0>` alone, so with no correction the error stays between 0.0014 and 0.0074 for all 1500 gates, around its 0.004 readout error.
