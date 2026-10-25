# Qubits where the simulator matches the real ibm_fez

- Simulator: FakeFez, calibrated 2025-02-26 15:16:25-05:00
- Real machine: `ibm_fez_calibrations_2026-10-24T18_48_15Z.csv`
- "Matches" means within 2x. CZ matches if every CZ connection the qubit has does
- 156 qubits checked

## All six areas (13 qubits)

readout P(1\|0), readout P(0\|1), T1, T2, sx error, CZ

- 8
- 9
- 25
- 47
- 73
- 79
- 83
- 106
- 109
- 122
- 123
- 129
- 131

## All five areas except T2 (14 qubits)

readout P(1\|0), readout P(0\|1), T1, sx error, CZ

- 8
- 9
- 25
- 47
- 73
- 79
- 83
- 106
- 109
- 120
- 122
- 123
- 129
- 131

## Four of those five (53 qubits)

Matches in every area but the one shown. Qubits matching all five are in the list above

- 2 (off: readout P(1\|0))
- 10 (off: readout P(0\|1))
- 12 (off: CZ)
- 17 (off: readout P(0\|1))
- 18 (off: readout P(1\|0))
- 22 (off: readout P(1\|0))
- 24 (off: readout P(1\|0))
- 26 (off: CZ)
- 29 (off: CZ)
- 33 (off: readout P(1\|0))
- 34 (off: sx error)
- 36 (off: readout P(0\|1))
- 37 (off: readout P(1\|0))
- 40 (off: readout P(0\|1))
- 41 (off: CZ)
- 44 (off: readout P(0\|1))
- 45 (off: sx error)
- 48 (off: CZ)
- 50 (off: readout P(0\|1))
- 63 (off: readout P(0\|1))
- 65 (off: readout P(1\|0))
- 66 (off: readout P(0\|1))
- 69 (off: CZ)
- 70 (off: readout P(1\|0))
- 76 (off: sx error)
- 77 (off: readout P(1\|0))
- 85 (off: readout P(1\|0))
- 86 (off: readout P(0\|1))
- 91 (off: readout P(1\|0))
- 99 (off: CZ)
- 101 (off: CZ)
- 104 (off: CZ)
- 107 (off: readout P(0\|1))
- 110 (off: readout P(1\|0))
- 113 (off: CZ)
- 117 (off: CZ)
- 118 (off: readout P(0\|1))
- 124 (off: readout P(1\|0))
- 130 (off: readout P(1\|0))
- 133 (off: readout P(1\|0))
- 135 (off: CZ)
- 137 (off: sx error)
- 138 (off: readout P(0\|1))
- 139 (off: readout P(0\|1))
- 140 (off: readout P(0\|1))
- 142 (off: readout P(1\|0))
- 143 (off: CZ)
- 145 (off: readout P(1\|0))
- 146 (off: readout P(1\|0))
- 150 (off: T1)
- 151 (off: readout P(1\|0))
- 153 (off: CZ)
- 155 (off: readout P(0\|1))
