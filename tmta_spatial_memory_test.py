"""
tmta_spatial_memory_test.py
---------------------------
Main entry point for the TMT-A Spatial Memory & Visual Marking Decomposition Suite.

Features:
- Configurable Target Ranges: Start and End targets can be set freely (e.g. 1..25, 26..68, 50..100).
- Fully Random 'Sprinkled Floor' Layout: Targets are scattered uniformly across the canvas with zero sequential proximity bias.
- 4 Experimental Modes:
    1. Mode 1: Normal Static & Lit (Memory + Bottom-Up Pop-Out)
    2. Mode 2: Static & Unlit (Spatial Memory Only, Audio Confirmation Beep)
    3. Mode 3: Dynamic Shuffled Remaining & Lit (Bottom-Up Only)
    4. Mode 4: Fully Shuffled & Unlit (Control / Baseline, Audio Confirmation Beep)
- High-precision inter-target search latency tracking (delta_t_k in ms) saved to JSON in results/.
- Built-in Matplotlib visualization with fitted linear trend lines and multi-mode comparison overlays.

Usage:
    python tmta_spatial_memory_test.py                          # Default 1..25
    python tmta_spatial_memory_test.py --start 26 --end 68      # Custom target range (26 to 68)
    python tmta_spatial_memory_test.py --mode 2 --start 26 --end 68
    python tmta_spatial_memory_test.py --plot                   # Multi-mode historical comparison plot
"""

import argparse
from pathlib import Path
import sys
import tkinter as tk

# Ensure current folder is on sys.path for direct script execution
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .gui import TMTASpatialMemoryApp
    from .plotter import generate_multi_condition_comparison
    from .config import DEFAULT_RESULTS_DIR
except ImportError:
    from gui import TMTASpatialMemoryApp
    from plotter import generate_multi_condition_comparison
    from config import DEFAULT_RESULTS_DIR

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def main() -> None:
    parser = argparse.ArgumentParser(description="TMT-A Spatial Memory & Visual Marking Decomposition Suite")
    parser.add_argument(
        "--mode",
        type=int,
        default=1,
        choices=[1, 2, 3, 4],
        help="Experimental Mode (1: Static+Lit, 2: Static+Unlit, 3: Shuffled+Lit, 4: Fully Shuffled+Unlit)",
    )
    parser.add_argument("--start", type=int, default=1, help="Starting target number (default: 1)")
    parser.add_argument("--end", type=int, default=25, help="Ending target number (default: 25)")
    parser.add_argument("--participant", type=str, default="participant", help="Participant ID")
    parser.add_argument("--plot", action="store_true", help="Launch the multi-mode historical comparison plot directly")
    parser.add_argument(
        "--results-dir",
        type=str,
        default=str(DEFAULT_RESULTS_DIR),
        help="Custom directory path for saving/reading JSON results",
    )
    args = parser.parse_args()

    results_path = Path(args.results_dir)

    if args.plot:
        # Plot-only direct launch
        root = tk.Tk()
        root.title("TMT-A Spatial Memory Decomposition — Historical Comparison")
        fig = generate_multi_condition_comparison(results_path)
        if fig and MATPLOTLIB_AVAILABLE:
            canvas = FigureCanvasTkAgg(fig, master=root)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            root.mainloop()
        else:
            print("Error: Could not generate comparison plot. Ensure matplotlib is installed.")
        return

    root = tk.Tk()
    app = TMTASpatialMemoryApp(
        root=root,
        initial_mode=args.mode,
        participant_id=args.participant,
        start_target=args.start,
        end_target=args.end,
        results_dir=results_path,
    )
    root.mainloop()


if __name__ == "__main__":
    main()

