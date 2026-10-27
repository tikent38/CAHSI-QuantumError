# output_tools.py
# Shared code for what the scripts in this repo print and the files they write: the plot colors and look, small
# pieces that repeat across plots and printed tables, saving plots, and writing and reading CSV and text files. Each
# plot and printed table itself stays in its own script, since every one is different.
# To use it from a script in another folder of src/:
#     sys.path.insert(0, os.path.join(HERE, "..", "output_tools"))
#     from output_tools import COLORS, INK, MUTED, pyplot, read_csv, save_plot, style, write_csv, write_text
import csv
import os
import textwrap

# Colors for the series in a plot, used in this order
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
# INK for titles and values, MUTED for axis labels and ticks, GRID for grid lines
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
DPI = 150   # resolution of every saved plot


# ---- Plots ----

def pyplot():
    # matplotlib's pyplot, set to draw straight into files (no plot windows open). Imported only when a plot is made,
    # so scripts that don't plot don't pay for loading matplotlib
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def style(ax, grid_axis="both"):
    # The look every plot shares: a light grid behind the data, muted ticks, and no top or right border.
    # grid_axis="y" draws only the horizontal grid lines (for bar charts)
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def qubit_axis(ax, qubits):
    # The x axis of a plot with one point or bar per Fez qubit: labelled "Fez qubit", with a tick every 10 qubits
    ax.set_xlabel("Fez qubit", color=MUTED)
    ax.set_xticks(range(0, max(qubits) + 1, 10))
    ax.set_xlim(min(qubits) - 1, max(qubits) + 1)


def label_above(ax, text, x, y, gap=3, fontsize=8):
    # Write text centred just above the point (x, y), gap points higher, e.g. a qubit's number over its bar
    ax.annotate(text, (x, y), xytext=(0, gap), textcoords="offset points", color=INK, fontsize=fontsize,
                ha="center", va="bottom")


def save_plot(fig, path, rect=None):
    # Fit everything inside the figure, then save it as a PNG at path, making its folder if needed.
    # rect keeps part of the figure free, e.g. (0, 0.03, 1, 1) leaves the bottom 3% for a footnote
    fig.tight_layout(rect=rect)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=DPI)
    print(f"Saved plot to {path}")


# ---- Printing ----

def print_table_header(header):
    # Print a table's header line with a rule of dashes the same length under it
    print(header)
    print("-" * len(header))


def print_wrapped(text, indent=""):
    # Print text wrapped into lines of at most 118 characters, for long lists. The first line starts with indent, and
    # the lines after it start 2 spaces further in than its text, so each wrapped item is easy to tell apart
    print(textwrap.fill(text, width=118, initial_indent=indent, subsequent_indent=" " * (len(indent) + 2)))


# ---- CSV and text files ----

def write_csv(path, header, rows):
    # Write a CSV file at path, making its folder if needed: the header, then one line per row
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Wrote {path}")


def read_csv(path):
    # The rows of a CSV file, each a dict keyed by the header, with every value as text
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_text(path, text):
    # Write text (e.g. a Markdown report or JSON) to a file at path, making its folder if needed
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    print(f"Wrote {path}")
