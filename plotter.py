"""
plotter.py
----------
Matplotlib comparative visualization for TMT-A Spatial Memory Experiments.
Scans experimental logs, calculates condition-level mean latencies, fits trendlines,
and renders publication-quality comparison charts.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from .config import DEFAULT_RESULTS_DIR, MODE_SPECS
except (ImportError, ValueError):
    from config import DEFAULT_RESULTS_DIR, MODE_SPECS


def generate_multi_condition_comparison(results_dir: Optional[Path] = None) -> Optional[Figure]:
    """
    Scans results_dir recursively, groups records by Mode (1, 2, 3, 4), computes the mean latency
    across step progress (1..N), and produces a comparative Matplotlib Figure
    with both empirical curves and fitted linear trend lines showing the rates of change across all conditions.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None

    path = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    if not path.exists():
        return None

    mode_data: Dict[int, List[List[float]]] = {1: [], 2: [], 3: [], 4: []}

    # Recursive scan to find runs in root, legacy, legacy2, etc.
    for json_file in path.rglob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            mode = data.get("mode")
            latencies = data.get("step_times_ms", [])
            if mode in mode_data and len(latencies) >= 2:
                mode_data[mode].append(latencies)
        except Exception:
            continue

    fig = Figure(figsize=(10.0, 6.0), dpi=100)
    ax = fig.add_subplot(111)

    colors = {1: "#16a34a", 2: "#d97706", 3: "#2563eb", 4: "#dc2626"}
    markers = {1: "o", 2: "s", 3: "^", 4: "D"}
    has_any_data = False
    slopes_summary = []

    for m in range(1, 5):
        runs = mode_data[m]
        spec = MODE_SPECS[m]
        if runs:
            has_any_data = True
            # Find min length among runs in this mode for fair mean aggregation
            min_len = min(len(r) for r in runs)
            truncated_runs = [r[:min_len] for r in runs]
            arr = [sum(col) / len(col) for col in zip(*truncated_runs)]
            steps = list(range(1, min_len + 1))

            # 1. Plot empirical mean curve
            ax.plot(
                steps,
                arr,
                label=f"{spec['short_name']} (N={len(runs)}, Len={min_len})",
                color=colors[m],
                marker=markers[m],
                linewidth=2.0,
                markersize=5.0,
                alpha=0.9,
            )

            # 2. Fit and plot trend line (dashed line with matching color)
            p = np.polyfit(steps, arr, 1)
            slope = p[0]
            trend_vals = [slope * x + p[1] for x in steps]
            ax.plot(
                steps,
                trend_vals,
                color=colors[m],
                linestyle="--",
                linewidth=2.0,
                alpha=0.8,
                label=f"  -- Mode {m} Trend: {slope:+.1f} ms/target",
            )
            slopes_summary.append((m, spec["short_name"], slope))

    if not has_any_data:
        # Show theoretical reference curves + theoretical trendlines if no experimental data recorded yet
        ax.set_title("Theoretical Predictions & Trendlines across 4 Spatial Memory Modes", fontsize=12, fontweight="bold", pad=12)
        steps = list(range(1, 26))
        # Theoretical curves:
        t1 = [1650 * math.exp(-0.065 * i) + 400 for i in steps]
        t2 = [1600 * math.exp(-0.028 * i) + 550 for i in steps]
        t3 = [1550 - (42 * i) for i in steps]
        t4 = [1350 for _ in steps]

        curves = {1: t1, 2: t2, 3: t3, 4: t4}
        for m in range(1, 5):
            arr = curves[m]
            ax.plot(steps, arr, label=f"Mode {m}: {MODE_SPECS[m]['short_name']}", color=colors[m], linewidth=2.0, alpha=0.85)
            p = np.polyfit(steps, arr, 1)
            slope = p[0]
            trend_vals = [slope * x + p[1] for x in steps]
            ax.plot(
                steps,
                trend_vals,
                color=colors[m],
                linestyle="--",
                linewidth=1.8,
                alpha=0.75,
                label=f"  -- Trend: {slope:+.1f} ms/target",
            )
            slopes_summary.append((m, MODE_SPECS[m]["short_name"], slope))

        ax.text(
            12.5,
            1850,
            "Showing Theoretical Hypotheses (No empirical runs found in folder yet)",
            ha="center",
            color="#64748b",
            fontstyle="italic",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f1f5f9", edgecolor="#cbd5e1", alpha=0.9),
        )
    else:
        ax.set_title("Empirical Target Latency & Fitted Trendlines across TMT-A Spatial Memory Modes", fontsize=12, fontweight="bold", pad=12)

    # Summary box in corner showing comparative slopes
    if slopes_summary:
        summary_lines = ["Trendline Slopes (Rate of Latency Change):"]
        for m, _, slope in slopes_summary:
            summary_lines.append(f"  Mode {m}: {slope:+.1f} ms/target")
        ax.text(
            0.02,
            0.05,
            "\n".join(summary_lines),
            transform=ax.transAxes,
            fontsize=8.5,
            verticalalignment="bottom",
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8fafc", edgecolor="#94a3b8", alpha=0.92),
        )

    ax.set_xlabel("Step Progress in Sequence (1 -> N)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Search Latency per Target Δt (ms)", fontsize=10, fontweight="bold")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", frameon=True, facecolor="#ffffff", framealpha=0.95, fontsize=8.5)
    fig.tight_layout()

    return fig
