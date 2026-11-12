import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
import compare_fez  # Imports compare_fez.py module


def main():
    csv_filename = "csvs/benchmarking_experiments.csv"
    os.makedirs("csvs", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)

    headers = [
        "gate_set", "circuit_type", "num_gates", "shots", "random_seed",
        "noise_model", "error_metric"
    ]

    # Parameters to sweep
    gate_sets_to_test = ["x", "repeat", "xz"]
    gate_counts = [10, 50, 100, 500]
    shot_counts = 10000
    seeds = [3, 50, 100]
    ##gate_set = "repeat"

    # Error correction defined in compare_fez
    codes_to_test = [
        "bit-flip, if blocks",
        "bit-flip, Toffoli",
        "phase-flip, if blocks",
        "phase-flip, Toffoli"
    ]

    print("Running quantum benchmarking experiments across gate counts...")

    # Run benchmarks
    with open(csv_filename, mode="w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for g_set in gate_sets_to_test:
            for gates in gate_counts:
                for seed in seeds:
                    results_dict, _ = compare_fez.compare(
                        num_gates=gates,
                        shots=shot_counts,
                        seed=seed,
                        gate_set=g_set,
                        mirror=False,
                        codes=codes_to_test,
                        show=False
                    )

                # Iterate through results and write rows to CSV
                for run_name, error_val in results_dict.items():
                    row = {
                        "gate_set": g_set,  
                        "circuit_type": run_name,
                        "num_gates": gates,
                        "shots": shot_counts,
                        "random_seed": seed,
                        "noise_model": "FakeFez",
                        "error_metric": error_val
                    }
                    writer.writerow(row)
                    print(f"Recorded: {run_name:<35} | Gates: {gates:<3} | Seed: {seed:<3} | Error: {error_val:.4f}")

    print(f"\nBenchmark completed. All results saved to '{csv_filename}'.")

    # Read CSV
    df = pd.read_csv(csv_filename)
    df['error_metric'] = df['error_metric'].astype(float)
    df['num_gates'] = df['num_gates'].astype(int)

    # Group by circuit type and gate count to get mean error and standard deviation across seeds
    summary = df.groupby(['circuit_type', 'num_gates'])['error_metric'].agg(['mean', 'std']).reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))

    for c_type in summary['circuit_type'].unique():
        sub = summary[summary['circuit_type'] == c_type]
        ax.errorbar(
            sub['num_gates'],
            sub['mean'],
            yerr=sub['std'],
            label=c_type,
            marker='o',
            capsize=4,
            linewidth=2
        )

    ax.set_xlabel('Number of Gates (Circuit Depth)', fontsize=12)
    ax.set_ylabel('Error Metric |Observed P(1) - Exact P(1)|', fontsize=12)
    ax.set_title('Quantum Gate Depth & Error Correction Benchmarking on FakeFez', fontsize=14)
    ax.set_xscale('log')
    ax.grid(True, which="both", linestyle="--", alpha=0.6)
    ax.legend(fontsize=9)

    plt.tight_layout()
    output_png = 'outputs/error_correction_benchmark.png'
    plt.savefig(output_png, dpi=300)
    plt.show()

    print(f"Plot saved to '{output_png}'.")


if __name__ == "__main__":
    main()