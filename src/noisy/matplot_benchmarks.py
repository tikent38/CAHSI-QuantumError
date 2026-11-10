import os
import matplotlib.pyplot as plt
import pandas as pd


def plot_benchmark_results(
    csv_filename="csvs/benchmarking_experiments.csv",
    output_image="csvs/benchmark_plot.png",
):
    if not os.path.exists(csv_filename):
        print(f"Error: File '{csv_filename}' not found. Run benchmarking first.")
        return

    # Load CSV data into a Pandas DataFrame
    df = pd.read_csv(csv_filename)

    # Convert numeric columns explicitly to numeric data types
    df["num_gates"] = pd.to_numeric(df["num_gates"])
    df["error_metric"] = pd.to_numeric(df["error_metric"])

    # Calculate mean error and standard deviation
    aggregated = (
        df.groupby(["circuit_type", "num_gates"])["error_metric"]
        .agg(["mean", "std"])
        .reset_index()
    )

    # Create the Matplotlib visual plot
    plt.figure(figsize=(10, 6), dpi=300)

    # Define markers and line styles for each circuit type
    styles = {
        "unencoded": {"color": "#e74c3c", "marker": "o", "ls": "--"},
        "bit-flip, if blocks": {"color": "#2ecc71", "marker": "s", "ls": "-"},
        "phase-flip, if blocks": {"color": "#3498db", "marker": "^", "ls": "-"},
    }

    unique_circuits = aggregated["circuit_type"].unique()

    for c_type in unique_circuits:
        data = aggregated[aggregated["circuit_type"] == c_type]

        style = styles.get(
            c_type, {"color": "#8e44ad", "marker": "D", "ls": "-"}
        )

        plt.plot(
            data["num_gates"],
            data["mean"],
            label=c_type,
            color=style["color"],
            marker=style["marker"],
            linestyle=style["ls"],
            linewidth=2,
            markersize=7,
        )

        # Plot error bars if standard deviation exists
        if data["std"].notnull().any():
            plt.fill_between(
                data["num_gates"],
                data["mean"] - data["std"],
                data["mean"] + data["std"],
                color=style["color"],
                alpha=0.15,
            )

    # 4. Format plot axes, title, grid, and legend
    plt.title(
        "Quantum Error Metric vs. Circuit Gate Length (FakeFez)",
        fontsize=14,
        pad=15,
    )
    plt.xlabel("Number of Gates (Circuit Depth)", fontsize=12)
    plt.ylabel("Error Metric |P(1)_observed - P(1)_ideal|", fontsize=12)

    gate_ticks = sorted(df["num_gates"].unique())
    plt.xticks(gate_ticks, labels=[str(g) for g in gate_ticks])

    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(title="Circuit Type", loc="upper left", frameon=True)
    plt.tight_layout()

    # 5. Save chart and display plot window
    plt.savefig(output_image, dpi=300)
    print(f"✅ Plot successfully saved to '{output_image}'.")
    plt.show()


if __name__ == "__main__":
    plot_benchmark_results()