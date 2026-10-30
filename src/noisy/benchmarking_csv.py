import warnings

# Silence Qiskit transpiler UserWarnings and general warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import csv
import os
from qiskit import transpile
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime.fake_provider import FakeFez
# Import Tim's compare_fez
import compare_fez


def run_experiment(circuit_type, num_gates, shots, seed, backend, ideal_sim):

    gate_set = getattr(compare_fez, "GATE_SET", "x")
    circuit_fn = compare_fez.CIRCUIT_FUNCTIONS.get(
        gate_set, compare_fez.x_gates
    )

    base_qc = circuit_fn(num_gates, seed)

    if getattr(compare_fez, "MIRROR", False):
        base_qc = compare_fez.mirrored(base_qc)

    # Resolve encoder mapping dynamically from compare_fez
    encoders = compare_fez.ENCODERS.copy()

    if circuit_type == "unencoded":
        qc = base_qc.copy()
        qc.measure_all()
    else:
        encoder_fn = encoders[circuit_type]
        qc = encoder_fn(base_qc)

    # Transpiling parameters matching Tim's exact Fez setup
    transpile_options = dict(
        optimization_level=0,
        routing_method="sabre",
        seed_transpiler=seed,
        basis_gates=list(backend.target.operation_names),
        coupling_map=compare_fez.working_coupling_map(backend),
    )

    # 1. Ideal run
    t_ideal = transpile(qc, ideal_sim, optimization_level=0)
    ideal_counts = (
        ideal_sim.run(t_ideal, shots=shots, seed_simulator=seed)
        .result()
        .get_counts()
    )

    # 2. Noisy run
    t_noisy = transpile(qc, backend, **transpile_options)
    noisy_sim = AerSimulator.from_backend(backend)
    noisy_counts = (
        noisy_sim.run(t_noisy, shots=shots, seed_simulator=seed)
        .result()
        .get_counts()
    )

    # Extract output bit probabilities using Tim's syndrome parser
    ones_ideal, total_ideal = compare_fez.prob_one(ideal_counts)
    ideal_p1 = ones_ideal / total_ideal
    ideal_p0 = 1.0 - ideal_p1

    ones_noisy, total_noisy = compare_fez.prob_one(noisy_counts)
    observed_p1 = ones_noisy / total_noisy
    observed_p0 = 1.0 - observed_p1

    # Tim's output-probability difference error metric
    error_metric = abs(observed_p1 - ideal_p1)

    return {
        "circuit_type": circuit_type,
        "num_gates": num_gates,
        "shots": shots,
        "random_seed": seed,
        "noise_model": "FakeFez",
        "ideal_p0": f"{ideal_p0:.4f}",
        "ideal_p1": f"{ideal_p1:.4f}",
        "observed_p0": f"{observed_p0:.4f}",
        "observed_p1": f"{observed_p1:.4f}",
        "error_metric": f"{error_metric:.4f}",
    }


def main():
    csv_filename = "csvs/benchmarking_experiments.csv"
    headers = [
        "circuit_type",
        "num_gates",
        "shots",
        "random_seed",
        "noise_model",
        "ideal_p0",
        "ideal_p1",
        "observed_p0",
        "observed_p1",
        "error_metric",
    ]

    backend = FakeFez()
    ideal_sim = AerSimulator()

    # Tested circuit types matching compare_fez encoder keys
    circuit_types = ["unencoded"] + [
        k for k in compare_fez.ENCODERS.keys() if "if blocks" in k
    ]
    gate_counts = [10, 50, 100, 500]  # different circuit lengths
    shot_counts = [10000]  # 10,000 simulations
    seeds = [3, 50, 100]  #(At least 3 seeds)

    file_exists = os.path.isfile(csv_filename)

    with open(csv_filename, mode="a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if not file_exists:
            writer.writeheader()

        for c_type in circuit_types:
            for gates in gate_counts:
                for shots in shot_counts:
                    for seed in seeds:
                        res = run_experiment(
                            c_type, gates, shots, seed, backend, ideal_sim
                        )
                        writer.writerow(res)
                        print(f"Recorded: {res['circuit_type']:<22} | Gates: {res['num_gates']:<3} | Seed: {res['random_seed']:<3} | Error: {res['error_metric']}")

    print(f"\n Benchmark completed. All results saved to '{csv_filename}'.")


if __name__ == "__main__":
    main()