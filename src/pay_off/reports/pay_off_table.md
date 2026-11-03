# Gate counts where each code pays off

- Pays off: the first number of gates where a code beats no correction 5 times in a row, measured on the same qubit
- Pay-off cells: `even / odd` numbers of logical gates (the test circuit's gates, before encoding). `>N` means it still hadn't paid off when the sweep stopped at N. H rows have one number because those sweeps aren't split into even and odd
- Transpiled gates and depth: the code's whole circuit at that pay-off point, after transpiling to the backend, counted the way `print_sizes` in `src/noisy/compare_backends.py` does. Gates include `rz` and measurements, and leave out barriers. `—` means there was no pay-off to measure
- Noise: ×10⁻³, written as `bit flip per X gate / phase flip per X gate / readout error` for each qubit. `2q` is the 2-qubit gate error on q0–q1, then q0–q2
- Qubits: the codes are the Toffoli versions, so bit-flip and phase-flip use only the 3 qubits listed. The result and the no-correction run are both measured on q2
- Source: X, Y, Repeat and ID on every backend are from `src/pay_off/parallel_runs/csvs/` (`pay_off_parallel.py`, 1500 gates at most, 5000 shots, seed 3). H rows are from `src/pay_off/csvs/fez/pay_off_h_points.csv`. Shor rows are from the plot legends in `src/pay_off/images/`. Noise is from `noise_levels` in `src/noisy/compare_backends.py`, on the fake backends in qiskit_ibm_runtime 0.50.0
- Left out: runs with only Z gates. Backends are sorted roughly from earliest pay-off to latest

| Backend | Qubits q0, q1, q2 with noise | Gate sequence | Bit-flip (even / odd) | Phase-flip (even / odd) | Shor (even / odd) |
|---|---|---|---|---|---|
| **Fez** | **87**: 0.44 / 0.22 / 18.8; **88**: 0.22 / 0.22 / 4.39; **86**: 0.22 / 0.26 / 4.15; 2q: 2.28, 2.60 | X | 48 / 155 | 40 / 139 | |
| | | Y | 48 / 155 | 32 / 153 | |
| | | Repeat (X, Y, Z) | 60 / 277 | 42 / 223 | |
| | | ID | 126 / 123 | 160 / 169 | |
| **Kingston** | **67**: 0.24 / 0.24 / 16.2; **57**: 0.15 / 0.13 / 4.76; **68**: 0.16 / 0.20 / 3.42; 2q: 2.26, 1.37 | X | 96 / 129 | 92 / 125 | |
| | | Y | 96 / 129 | 106 / 127 | |
| | | Repeat (X, Y, Z) | 144 / 181 | 162 / 211 | |
| | | ID | 208 / 255 | >1500 / 443 | |
| **Marrakesh** | **33**: 0.21 / 0.39 / 8.79; **34**: 0.23 / 0.21 / 5.13; **39**: 0.23 / 0.20 / 7.81; 2q: 2.38, 2.72 | X | 116 / 129 | 92 / 105 | |
| | | Y | 116 / 129 | 128 / 127 | |
| | | Repeat (X, Y, Z) | 162 / 193 | 180 / 229 | |
| | | ID | 172 / 173 | 292 / 263 | |
| **Torino** | **61**: 0.30 / 0.20 / 22.9; **60**: 0.17 / 0.17 / 6.10; **62**: 0.22 / 0.24 / 12.0; 2q: 2.72, 3.41 | X | 118 / 147 | 118 / 139 | |
| | | Y | 118 / 147 | 116 / 149 | |
| | | Repeat (X, Y, Z) | 180 / 223 | 174 / 229 | |
| | | ID | 202 / 189 | 262 / 251 | |
| **Washington** | **64**: 0.36 / 0.35 / 12.4; **63**: 0.21 / 0.21 / 4.20; **54**: 0.25 / 0.23 / 12.4; 2q: 12.3, 8.71 | X | 230 / 375 | 202 / 267 | |
| | | Y | 230 / 375 | 224 / 373 | |
| | | Repeat (X, Y, Z) | 408 / 565 | 372 / 577 | |
| | | ID | 848 / 839 | >1500 / >1500 | |
| **Brisbane** | **104**: 0.25 / 0.25 / 16.4; **103**: 0.13 / 0.35 / 5.86; **105**: 0.23 / 0.36 / 8.79; 2q: 5.76, 9.69 | X | 244 / 261 | 182 / 219 | |
| | | Y | 244 / 261 | 288 / 345 | |
| | | Repeat (X, Y, Z) | 366 / 367 | 426 / 505 | |
| | | ID | 1058 / 1087 | >1500 / >1500 | |
| **Kolkata** | **19**: 0.29 / 0.31 / 19.2; **20**: 0.17 / 0.14 / 7.30; **16**: 0.22 / 0.28 / 9.70; 2q: 9.09, 12.0 | X | 314 / 375 | 262 / 309 | |
| | | Y | 314 / 375 | 312 / 385 | |
| | | Repeat (X, Y, Z) | 474 / 565 | 450 / 547 | |
| | | ID | 1010 / 1007 | >1500 / >1500 | |
| **Sherbrooke** | **100**: 0.34 / 0.26 / 13.4; **110**: 0.20 / 0.20 / 7.32; **101**: 0.11 / 0.40 / 3.66; 2q: 6.29, 7.67 | X | >1500 / >1500 | 444 / 449 | |
| | | Y | >1500 / >1500 | >1500 / >1500 | |
| | | Repeat (X, Y, Z) | >1500 / >1500 | >1500 / >1500 | |
| | | ID | >1500 / >1500 | >1500 / >1500 | |
| **Fez, with H gates** | Same qubits and noise as Fez above | X, no H | 40 | 40 | |
| | | X, H every 100 (stopped before first H) | 40 | 40 | |
| | | X, H every 50 | >500 | 130 | |
| | | X, H every 26, 10, 5 | >500 | >500 | |
| | | Y, no H | 40 | 40 | |
| | | Y, H every 100 (stopped before first H) | 40 | 40 | |
| | | Y, H every 50, 26, 10, 5 | >500 | >500 | |
| | | Repeat, no H | 40 | 40 | |
| | | Repeat, H every 100 (stopped before first H) | 40 | 40 | |
| | | Repeat, H every 50, 26, 10, 5 | >500 | >500 | |
| | | Random X, Z, no H | 110 | 110 | |
| | | Random X, Z, H every 100, 50, 26, 10, 5 | >500 | >500 | |
| | | ID, no H | 100 | 130 | |
| | | ID, H every 100, 50, 26, 10, 5 | >500 | >500 | |
| | | Z, H every 100, 50, 26, 10, 5 | >500 | >500 | |
| **Fez, Shor code** | **87**: 0.44 / 0.22 / 18.8; **97**: 0.31 / 0.29 / 4.15; **107**: 0.11 / 0.52 / 7.32; **86**: 0.22 / 0.26 / 4.15; **85**: 0.08 / 0.53 / 12.7; **84**: 0.23 / 0.24 / 2.44; **88**: 0.22 / 0.22 / 4.39; **89**: 0.09 / 0.16 / 16.8; **90**: 0.24 / 0.24 / 2.69; 2q range: 2.28–4.73; measured on 86 | X | | | ≤500 / ≤501 |
| | | Y | | | >5000 / >5000 |
| **Fez, Shor code, older layout** | **87**: 0.44 / 0.22 / 18.8; **88**: 0.22 / 0.22 / 4.39; **85**: 0.08 / 0.53 / 12.7; **97**: 0.31 / 0.29 / 4.15; **108**: 0.24 / 0.27 / 4.64; **107**: 0.11 / 0.52 / 7.32; **86**: 0.22 / 0.26 / 4.15; **77**: 0.09 / 0.25 / 8.54; **84**: 0.23 / 0.24 / 2.44; 2q range: 2.28–4.73; measured on 77 | Repeat (X, Y, Z) | | | >3000 / >3000 |

## Rows to read with care

- H every 100 on X, Y and Repeat: these sweeps stopped at 80 gates, before the first H at gate 100, so the 40s are really no-H results. The Random X, Z and ID runs did reach their H gates, and they never paid off
- Kingston ID, phase-flip odd (443): probably shot noise. The odd sweep stopped at 451, right after its 5 wins, while the even sweep ran to 1500 and won 0 of the 251 points past 1000 gates. Sweeps stop once both codes have paid off, so most rows can't show whether a pay-off lasts
- Sherbrooke ID: no correction barely degrades, so there's almost nothing for a code to beat. Aer's `id` noise on qubit 101 is only relaxation, which leaves `|0>` alone, so the error stays near its 0.004 readout error for all 1500 gates
- Shor rows: not directly comparable with the other rows. The sweeps started at 500 gates, so `≤500` is only an upper bound. The X and Repeat plots reproduce with Aer's default simulation method, not the per-shot statevector the other rows use
- Step sizes: counts move in steps of 2 for X, Y and ID, 6 for Repeat, and 10 for the H rows. That's why X with no H shows 40 where plain X shows 48
