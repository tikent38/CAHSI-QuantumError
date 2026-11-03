# Gate counts where each code pays off

- Pays off: the first number of gates where a code beats no correction 5 times in a row, measured on the same qubit
- Pay-off cells: `even / odd` numbers of gates. `>N` means it still hadn't paid off when the sweep stopped at N. H rows have one number because those sweeps aren't split into even and odd
- Noise: ×10⁻³, written as `bit flip per X gate / phase flip per X gate / readout error` for each qubit. `2q` is the 2-qubit gate error on q0–q1, then q0–q2
- Qubits: the codes are the Toffoli versions, so bit-flip and phase-flip use only the 3 qubits listed. The result and the no-correction run are both measured on q2
- Source: the plot legends in `src/pay_off/images/` (5000 shots, seed 3). Noise is from `noise_levels` in `src/noisy/compare_backends.py`, on the fake backends in qiskit_ibm_runtime 0.50.0
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
