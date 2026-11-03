# Gate counts where each code pays off

- Pays off: the first number of gates where a code beats no correction 5 times in a row, measured on the same qubit
- Pay-off cells: `even / odd` numbers of logical gates (the test circuit's gates, before encoding). `>N` means it still hadn't paid off when the sweep stopped at N.
- Transpiled gates and depth: the code's whole circuit at that pay-off point, after transpiling to the backend, counted the way `print_sizes` in `src/noisy/compare_backends.py` does. Gates include `rz` and measurements, and leave out barriers. `—` means there was no pay-off to measure
- Noise: ×10⁻³, written as `bit flip per X gate / phase flip per X gate / readout error` for each qubit. `2q` is the 2-qubit gate error on q0–q1, then q0–q2
- Qubits: the codes are the Toffoli versions, so bit-flip and phase-flip use only the 3 qubits listed. The result and the no-correction run are both measured on q2
- Source: `src/pay_off/parallel_runs/csvs/` (`pay_off_parallel.py`, 1500 gates at most, 5000 shots, seed 3). Noise is from `noise_levels` in `src/noisy/compare_backends.py`, on the fake backends in qiskit_ibm_runtime 0.50.0
- Left out: runs with only Z gates, runs with H gates, and the Shor code. Backends are sorted roughly from earliest pay-off to latest

| Backend | Qubits q0, q1, q2 with noise | Gate sequence | Code | Pays off at, logical gates (even / odd) | Transpiled gates (even / odd) | Transpiled depth (even / odd) |
|---|---|---|---|---|---|---|
| **Fez** | **87**: 0.44 / 0.22 / 18.8; **88**: 0.22 / 0.22 / 4.39; **86**: 0.22 / 0.26 / 4.15; 2q: 2.28, 2.60 | X | Bit-flip | 48 / 155 | 237 / 558 | 118 / 225 |
|  |  |  | Phase-flip | 40 / 139 | 231 / 528 | 116 / 215 |
|  |  | Y | Bit-flip | 48 / 155 | 381 / 1023 | 166 / 380 |
|  |  |  | Phase-flip | 32 / 153 | 303 / 1029 | 140 / 382 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 60 / 277 | 333 / 1200 | 150 / 439 |
|  |  |  | Phase-flip | 42 / 223 | 279 / 1002 | 132 / 373 |
|  |  | ID | Bit-flip | 126 / 123 | 471 / 462 | 196 / 193 |
|  |  |  | Phase-flip | 160 / 169 | 591 / 618 | 236 / 245 |
| **Kingston** | **67**: 0.24 / 0.24 / 16.2; **57**: 0.15 / 0.13 / 4.76; **68**: 0.16 / 0.20 / 3.42; 2q: 2.26, 1.37 | X | Bit-flip | 96 / 129 | 381 / 480 | 166 / 199 |
|  |  |  | Phase-flip | 92 / 125 | 387 / 486 | 168 / 201 |
|  |  | Y | Bit-flip | 96 / 129 | 669 / 867 | 262 / 328 |
|  |  |  | Phase-flip | 106 / 127 | 747 / 873 | 288 / 330 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 144 / 181 | 669 / 816 | 262 / 311 |
|  |  |  | Phase-flip | 162 / 211 | 759 / 954 | 292 / 357 |
|  |  | ID | Bit-flip | 208 / 255 | 717 / 858 | 278 / 325 |
|  |  |  | Phase-flip | >1500 / 443 | — / 1440 | — / 519 |
| **Marrakesh** | **33**: 0.21 / 0.39 / 8.79; **34**: 0.23 / 0.21 / 5.13; **39**: 0.23 / 0.20 / 7.81; 2q: 2.38, 2.72 | X | Bit-flip | 116 / 129 | 441 / 480 | 186 / 199 |
|  |  |  | Phase-flip | 92 / 105 | 387 / 426 | 168 / 181 |
|  |  | Y | Bit-flip | 116 / 129 | 789 / 867 | 302 / 328 |
|  |  |  | Phase-flip | 128 / 127 | 879 / 873 | 332 / 330 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 162 / 193 | 741 / 864 | 286 / 327 |
|  |  |  | Phase-flip | 180 / 229 | 831 / 1026 | 316 / 381 |
|  |  | ID | Bit-flip | 172 / 173 | 609 / 612 | 242 / 243 |
|  |  |  | Phase-flip | 292 / 263 | 987 / 900 | 368 / 339 |
| **Torino** | **61**: 0.30 / 0.20 / 22.9; **60**: 0.17 / 0.17 / 6.10; **62**: 0.22 / 0.24 / 12.0; 2q: 2.72, 3.41 | X | Bit-flip | 118 / 147 | 447 / 534 | 188 / 217 |
|  |  |  | Phase-flip | 118 / 139 | 465 / 528 | 194 / 215 |
|  |  | Y | Bit-flip | 118 / 147 | 801 / 975 | 306 / 364 |
|  |  |  | Phase-flip | 116 / 149 | 807 / 1005 | 308 / 374 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 180 / 223 | 813 / 984 | 310 / 367 |
|  |  |  | Phase-flip | 174 / 229 | 807 / 1026 | 308 / 381 |
|  |  | ID | Bit-flip | 202 / 189 | 699 / 660 | 272 / 259 |
|  |  |  | Phase-flip | 262 / 251 | 897 / 864 | 338 / 327 |
| **Washington** | **64**: 0.36 / 0.35 / 12.4; **63**: 0.21 / 0.21 / 4.20; **54**: 0.25 / 0.23 / 12.4; 2q: 12.3, 8.71 | X | Bit-flip | 230 / 375 | 717 / 1152 | 255 / 400 |
|  |  |  | Phase-flip | 202 / 267 | 651 / 846 | 233 / 298 |
|  |  | Y | Bit-flip | 230 / 375 | 1407 / 2277 | 485 / 775 |
|  |  |  | Phase-flip | 224 / 373 | 1389 / 2283 | 479 / 777 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 408 / 565 | 1659 / 2286 | 569 / 778 |
|  |  |  | Phase-flip | 372 / 577 | 1533 / 2352 | 527 / 800 |
|  |  | ID | Bit-flip | 848 / 839 | 2571 / 2544 | 873 / 864 |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
| **Brisbane** | **104**: 0.25 / 0.25 / 16.4; **103**: 0.13 / 0.35 / 5.86; **105**: 0.23 / 0.36 / 8.79; 2q: 5.76, 9.69 | X | Bit-flip | 244 / 261 | 931 / 982 | 362 / 379 |
|  |  |  | Phase-flip | 182 / 219 | 763 / 874 | 306 / 343 |
|  |  | Y | Bit-flip | 244 / 261 | 1663 / 1765 | 606 / 640 |
|  |  |  | Phase-flip | 288 / 345 | 1945 / 2287 | 700 / 814 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 366 / 367 | 1663 / 1666 | 606 / 607 |
|  |  |  | Phase-flip | 426 / 505 | 1921 / 2236 | 692 / 797 |
|  |  | ID | Bit-flip | 1058 / 1087 | 3373 / 3460 | 1176 / 1205 |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
| **Kolkata** | **19**: 0.29 / 0.31 / 19.2; **20**: 0.17 / 0.14 / 7.30; **16**: 0.22 / 0.28 / 9.70; 2q: 9.09, 12.0 | X | Bit-flip | 314 / 375 | 969 / 1152 | 339 / 400 |
|  |  |  | Phase-flip | 262 / 309 | 831 / 972 | 293 / 340 |
|  |  | Y | Bit-flip | 314 / 375 | 1911 / 2277 | 653 / 775 |
|  |  |  | Phase-flip | 312 / 385 | 1917 / 2355 | 655 / 801 |
|  |  | Repeat (X, Y, Z) | Bit-flip | 474 / 565 | 1923 / 2286 | 657 / 778 |
|  |  |  | Phase-flip | 450 / 547 | 1845 / 2232 | 631 / 760 |
|  |  | ID | Bit-flip | 1010 / 1007 | 3057 / 3048 | 1035 / 1032 |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
| **Sherbrooke** | **100**: 0.34 / 0.26 / 13.4; **110**: 0.20 / 0.20 / 7.32; **101**: 0.11 / 0.40 / 3.66; 2q: 6.29, 7.67 | X | Bit-flip | >1500 / >1500 | — / — | — / — |
|  |  |  | Phase-flip | 444 / 449 | 1525 / 1540 | 556 / 561 |
|  |  | Y | Bit-flip | >1500 / >1500 | — / — | — / — |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
|  |  | Repeat (X, Y, Z) | Bit-flip | >1500 / >1500 | — / — | — / — |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
|  |  | ID | Bit-flip | >1500 / >1500 | — / — | — / — |
|  |  |  | Phase-flip | >1500 / >1500 | — / — | — / — |
