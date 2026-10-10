# aer_noise_test.py
# Needs qiskit-ibm-runtime for the fake backends: pip install qiskit-ibm-runtime
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez

# Create a 1-qubit, 1-classical-bit circuit with 10 X gates.
# 10 flips cancel out, so with no noise the qubit always ends up back at 0
qc = QuantumCircuit(1, 1)
for _ in range(10):
    qc.x(0)
qc.measure(0, 0)

# Simulator with the noise of a real IBM device (error rates from its calibration data)
backend = FakeFez()
noisy_simulator = AerSimulator.from_backend(backend)

# Convert the circuit to the device's gates and put it on physical qubit 0.
# optimization_level=0 keeps all 10 X gates (otherwise the transpiler sees they cancel and removes them)
noisy_qc = transpile(qc, noisy_simulator, optimization_level=0, initial_layout=[0])

# Run the circuit 1,000 times with and without noise
ideal_counts = AerSimulator().run(qc, shots=1000).result().get_counts()
noisy_counts = noisy_simulator.run(noisy_qc, shots=1000).result().get_counts()

print(qc.draw())

# Results for each run: how many shots gave 0 and 1
print(f"\n{'run':<20}{'0':>8}{'1':>8}{'error rate':>14}")
print("-" * 50)
for name, counts in [("no noise", ideal_counts), (f"{backend.name} noise", noisy_counts)]:
    zeros, ones = counts.get("0", 0), counts.get("1", 0)
    # The right answer is always 0, so every 1 is an error
    print(f"{name:<20}{zeros:>8}{ones:>8}{ones / (zeros + ones):>13.1%}")

# The device's own error rates for the qubit the circuit ran on (from its calibration data)
x_error = backend.target["x"][(0,)].error
readout_error = backend.target["measure"][(0,)].error
print(f"\n{backend.name} qubit 0 error rates:")
print(f"  each X gate:      {x_error:.4%}   (x 10 gates = about {10 * x_error:.2%})")
print(f"  measurement:      {readout_error:.4%}")
