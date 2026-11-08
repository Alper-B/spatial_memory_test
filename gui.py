"""
gui.py
------
Tkinter graphical user interface for TMT-A Spatial Memory Experiments.
Provides dynamic target range configuration, responsive node scaling,
interactive touch/click tracking, live HUD metrics, and embedded analytics plots.
"""

import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple

import numpy as np

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from .config import DEFAULT_RESULTS_DIR, MODE_SPECS
    from .plotter import generate_multi_condition_comparison
    from .session import SpatialMemorySession
except (ImportError, ValueError):
    from config import DEFAULT_RESULTS_DIR, MODE_SPECS
    from plotter import generate_multi_condition_comparison
    from session import SpatialMemorySession


class TMTASpatialMemoryApp:
    """Primary GUI application for running TMT-A spatial memory decomposition experiments with custom target ranges."""

    def __init__(
        self,
        root: tk.Tk,
        initial_mode: int = 1,
        participant_id: str = "participant",
        start_target: int = 1,
        end_target: int = 25,
        results_dir: Optional[Path] = None,
    ):
        self.root = root
        self.root.title("TMT-A Spatial Memory & Visual Marking Decomposition Suite")
        self.root.configure(bg="#121214")
        self.results_dir = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR

        self.current_mode = initial_mode
        self.participant_id_var = tk.StringVar(value=participant_id)
        self.start_target_var = tk.StringVar(value=str(start_target))
        self.end_target_var = tk.StringVar(value=str(end_target))
        self.range_count_lbl_var = tk.StringVar(value=f"({end_target - start_target + 1} Targets)")

        self.session = SpatialMemorySession(
            mode=self.current_mode,
            participant_id=participant_id,
            start_target=start_target,
            end_target=end_target,
            results_dir=self.results_dir,
        )

        # Canvas sizing & adaptive node radius
        screen_h = self.root.winfo_screenheight()
        self.canvas_size = max(420, min(int(screen_h * 0.70), 700))
        self._recompute_geometry()

        # UI State variables
        self.hud_target_var = tk.StringVar(value=f"Next Target: {self.session.start_target}")
        self.hud_step_time_var = tk.StringVar(value="Step Time: 0.0s")
        self.hud_total_time_var = tk.StringVar(value="Total Time: 0.0s")
        self.hud_errors_var = tk.StringVar(value="Errors: 0")

        self._build_ui()
        self._select_mode(initial_mode, trigger_new_layout=False)
        self._redraw_canvas()

        # Stopwatch tick loop (updates HUD during test)
        self._tick_stopwatch()

    def _recompute_geometry(self) -> None:
        """Dynamically scales node circle radius and typography based on target count and number of digits."""
        N = self.session.target_count
        self.node_radius = max(11, min(int(self.canvas_size * 0.028), int(self.canvas_size * (0.138 / math.sqrt(N)))))

        max_digits = max(len(str(self.session.start_target)), len(str(self.session.end_target)))
        font_ratio = 0.72 if max_digits <= 2 else (0.58 if max_digits == 3 else 0.46)
        self.node_font_size = max(7, int(self.node_radius * font_ratio))

    def _build_ui(self) -> None:
        # 1. TOP HEADER FRAME
        header_frame = tk.Frame(self.root, bg="#18181b", padx=14, pady=10)
        header_frame.pack(fill=tk.X)

        # Row 1: Participant, Target Range (Start/End), Action Buttons
        row_top = tk.Frame(header_frame, bg="#18181b")
        row_top.pack(fill=tk.X, pady=(0, 8))

        tk.Label(row_top, text="Participant:", font=("Segoe UI", 9, "bold"), bg="#18181b", fg="#e4e4e7").pack(side=tk.LEFT)
        pid_entry = ttk.Entry(row_top, textvariable=self.participant_id_var, width=11)
        pid_entry.pack(side=tk.LEFT, padx=(4, 15))

        # Configurable Target Range Controls
        tk.Label(row_top, text="Start Target:", font=("Segoe UI", 9, "bold"), bg="#18181b", fg="#38bdf8").pack(side=tk.LEFT)
        self.start_entry = ttk.Entry(row_top, textvariable=self.start_target_var, width=5)
        self.start_entry.pack(side=tk.LEFT, padx=(4, 8))
        self.start_entry.bind("<KeyRelease>", self._on_range_entry_changed)
        self.start_entry.bind("<Return>", lambda e: self._apply_new_target_range())

        tk.Label(row_top, text="End Target:", font=("Segoe UI", 9, "bold"), bg="#18181b", fg="#38bdf8").pack(side=tk.LEFT)
        self.end_entry = ttk.Entry(row_top, textvariable=self.end_target_var, width=5)
        self.end_entry.pack(side=tk.LEFT, padx=(4, 6))
        self.end_entry.bind("<KeyRelease>", self._on_range_entry_changed)
        self.end_entry.bind("<Return>", lambda e: self._apply_new_target_range())

        self.range_count_lbl = tk.Label(row_top, textvariable=self.range_count_lbl_var, font=("Segoe UI", 9, "bold"), bg="#18181b", fg="#a1a1aa")
        self.range_count_lbl.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(row_top, text="Apply Range", command=self._apply_new_target_range).pack(side=tk.LEFT, padx=(0, 15))

        self.start_btn = tk.Button(
            row_top,
            text="▶ START TEST",
            font=("Segoe UI", 10, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            padx=14,
            pady=3,
            relief=tk.FLAT,
            command=self._start_experiment,
        )
        self.start_btn.pack(side=tk.LEFT, padx=6)

        self.reset_btn = tk.Button(
            row_top,
            text="🎲 New Seed / Reset",
            font=("Segoe UI", 9),
            bg="#27272a",
            fg="#d4d4d8",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            padx=10,
            pady=3,
            relief=tk.FLAT,
            command=self._reset_board,
        )
        self.reset_btn.pack(side=tk.LEFT, padx=6)

        self.plot_btn = tk.Button(
            row_top,
            text="📊 View Comparison Curves",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            padx=12,
            pady=3,
            relief=tk.FLAT,
            command=self._open_comparison_window,
        )
        self.plot_btn.pack(side=tk.RIGHT, padx=6)

        # 2. MODE SELECTION TABS
        row_modes = tk.Frame(header_frame, bg="#18181b")
        row_modes.pack(fill=tk.X, pady=(2, 6))

        tk.Label(row_modes, text="Experiment Mode:", font=("Segoe UI", 9, "bold"), bg="#18181b", fg="#a1a1aa").pack(side=tk.LEFT, padx=(0, 8))

        self.mode_buttons = {}
        for m in [1, 2, 3, 4]:
            spec = MODE_SPECS[m]
            btn = tk.Button(
                row_modes,
                text=f"Mode {m}: {spec['short_name']}",
                font=("Segoe UI", 9),
                bg="#27272a",
                fg="#a1a1aa",
                activebackground="#3f3f46",
                activeforeground="#ffffff",
                padx=8,
                pady=3,
                relief=tk.FLAT,
                command=lambda mode_id=m: self._select_mode(mode_id),
            )
            btn.pack(side=tk.LEFT, padx=4)
            self.mode_buttons[m] = btn

        # 3. STATUS & HYPOTHESIS BANNER
        self.banner_frame = tk.Frame(self.root, bg="#1e293b", padx=14, pady=6)
        self.banner_frame.pack(fill=tk.X, padx=14, pady=(6, 4))

        self.banner_title_lbl = tk.Label(self.banner_frame, text="", font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#38bdf8")
        self.banner_title_lbl.pack(anchor="w")

        self.banner_desc_lbl = tk.Label(self.banner_frame, text="", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1")
        self.banner_desc_lbl.pack(anchor="w")

        # 4. HUD METRICS STRIP
        hud_frame = tk.Frame(self.root, bg="#09090b", padx=16, pady=6)
        hud_frame.pack(fill=tk.X, padx=14, pady=(2, 6))

        self.hud_target_lbl = tk.Label(hud_frame, textvariable=self.hud_target_var, font=("Segoe UI", 12, "bold"), bg="#09090b", fg="#4ade80")
        self.hud_target_lbl.pack(side=tk.LEFT, padx=(0, 25))

        self.hud_step_lbl = tk.Label(hud_frame, textvariable=self.hud_step_time_var, font=("Consolas", 11, "bold"), bg="#09090b", fg="#38bdf8")
        self.hud_step_lbl.pack(side=tk.LEFT, padx=15)

        self.hud_total_lbl = tk.Label(hud_frame, textvariable=self.hud_total_time_var, font=("Consolas", 11), bg="#09090b", fg="#e4e4e7")
        self.hud_total_lbl.pack(side=tk.LEFT, padx=15)

        self.hud_err_lbl = tk.Label(hud_frame, textvariable=self.hud_errors_var, font=("Segoe UI", 10), bg="#09090b", fg="#f87171")
        self.hud_err_lbl.pack(side=tk.RIGHT, padx=10)

        # 5. MAIN INTERACTIVE EXPERIMENT CANVAS
        canvas_container = tk.Frame(self.root, bg="#121214")
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 10))

        self.canvas = tk.Canvas(
            canvas_container,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="#f8fafc",
            highlightthickness=2,
            highlightbackground="#334155",
        )
        self.canvas.pack(pady=4)

        # Bind mouse click event
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    def _on_range_entry_changed(self, event=None) -> None:
        """Live feedback when typing into Start or End target boxes."""
        try:
            s = int(self.start_target_var.get())
            e = int(self.end_target_var.get())
            if e >= s:
                count = e - s + 1
                self.range_count_lbl_var.set(f"({count} Targets)")
                self.range_count_lbl.config(fg="#4ade80")
            else:
                self.range_count_lbl_var.set("(End must be >= Start)")
                self.range_count_lbl.config(fg="#f87171")
        except ValueError:
            self.range_count_lbl_var.set("(Enter valid integers)")
            self.range_count_lbl.config(fg="#f87171")

    def _apply_new_target_range(self) -> None:
        """Applies custom start and end targets, and reinitializes board layout."""
        try:
            s = int(self.start_target_var.get())
            e = int(self.end_target_var.get())
            if s < 1 or e <= s:
                messagebox.showwarning("Invalid Range", "Start target must be >= 1, and End target must be greater than Start target.")
                return
            if (e - s + 1) > 90:
                messagebox.showwarning("Range Too Large", "Maximum recommended target count is 90 for clean canvas legibility.")
                return
        except ValueError:
            messagebox.showerror("Error", "Please enter valid integers for Start and End targets.")
            return

        self.session = SpatialMemorySession(
            mode=self.current_mode,
            participant_id=self.participant_id_var.get(),
            start_target=s,
            end_target=e,
            results_dir=self.results_dir,
        )
        self._recompute_geometry()
        self._select_mode(self.current_mode, trigger_new_layout=False)

    def _select_mode(self, mode_id: int, trigger_new_layout: bool = True) -> None:
        """Switches active experimental mode and updates UI styling and hypothesis descriptions."""
        self.current_mode = mode_id
        spec = MODE_SPECS[mode_id]

        # Update button highlights
        for m, btn in self.mode_buttons.items():
            if m == mode_id:
                btn.config(bg=spec["badge_color"], fg="#ffffff", font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 9))

        # Update description banner
        self.banner_title_lbl.config(text=f"🔬 {spec['title']}")
        self.banner_desc_lbl.config(text=f"Rule: {spec['description']}\nHypothesis: {spec['hypothesis']}")

        try:
            s = int(self.start_target_var.get())
            e = int(self.end_target_var.get())
        except ValueError:
            s, e = 1, 25

        seed = None if trigger_new_layout else self.session.seed
        self.session = SpatialMemorySession(
            mode=mode_id,
            participant_id=self.participant_id_var.get(),
            seed=seed,
            start_target=s,
            end_target=e,
            results_dir=self.results_dir,
        )
        self._recompute_geometry()

        self.start_btn.config(text="▶ START TEST", bg="#16a34a", state=tk.NORMAL)
        self.hud_target_var.set(f"Next Target: {self.session.start_target} (Click START to Begin)")
        self.hud_step_time_var.set("Step Time: 0.0s")
        self.hud_total_time_var.set("Total Time: 0.0s")
        self.hud_errors_var.set("Errors: 0")

        self._redraw_canvas()

    def _start_experiment(self) -> None:
        """Starts timing and activates the experiment."""
        self._apply_new_target_range()
        self.session.participant_id = self.participant_id_var.get()
        self.session.start_test()
        self.start_btn.config(text="⏸ Test Running...", bg="#475569", state=tk.DISABLED)
        self.hud_target_var.set(f"Target: '{self.session.start_target}' (1/{self.session.target_count})")
        self.hud_errors_var.set("Errors: 0")
        self._redraw_canvas()

    def _reset_board(self) -> None:
        """Generates a fresh randomized seed and resets current mode."""
        self._apply_new_target_range()
        self._select_mode(self.current_mode, trigger_new_layout=True)

    def _get_canvas_pos(self, pct_x: float, pct_y: float) -> Tuple[int, int]:
        """Converts percentage coordinates [6.0, 94.0] to canvas pixel coordinates."""
        padding = self.canvas_size * 0.06
        active_area = self.canvas_size - (padding * 2.0)
        cx = int((pct_x / 100.0) * active_area + padding)
        cy = int((pct_y / 100.0) * active_area + padding)
        return cx, cy

    def _find_target_at_pos(self, px: int, py: int) -> Optional[str]:
        """Detects whether a mouse click landed on any target circle."""
        tolerance_r = self.node_radius * 1.25
        for target_str, (pct_x, pct_y) in self.session.layout.items():
            cx, cy = self._get_canvas_pos(pct_x, pct_y)
            if math.hypot(px - cx, py - cy) <= tolerance_r:
                return target_str
        return None

    def _on_canvas_click(self, event) -> None:
        """Event handler for canvas clicks."""
        if not self.session.started or self.session.completed:
            return

        hit_target = self._find_target_at_pos(event.x, event.y)
        is_correct, is_finished = self.session.handle_click(hit_target)

        # Brief visual click ring on canvas
        self._draw_click_ripple(event.x, event.y, is_correct)

        if is_correct:
            if is_finished:
                self._handle_experiment_finished()
            else:
                progress_step = self.session.completed_count + 1
                self.hud_target_var.set(f"Target: '{self.session.current_target_index}' ({progress_step}/{self.session.target_count})")
        else:
            self.hud_errors_var.set(f"Errors: {self.session.total_errors}")

        self._redraw_canvas()

    def _draw_click_ripple(self, x: int, y: int, is_correct: bool) -> None:
        """Draws a quick expanding ripple circle at the click location."""
        color = "#22c55e" if is_correct else "#ef4444"
        r = self.node_radius
        ripple_id = self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=color, width=2)
        self.root.after(120, lambda: self.canvas.delete(ripple_id))

    def _redraw_canvas(self) -> None:
        """Draws the board state strictly honoring active experimental mode rules and custom target range."""
        self.canvas.delete("all")
        w = self.canvas_size
        self.canvas.create_rectangle(0, 0, w, w, fill="#f8fafc", outline="#cbd5e1")

        mode_spec = self.session.mode_spec
        visual_marking = mode_spec["visual_marking"]
        completed_count = self.session.completed_count
        r = self.node_radius

        # 1. DRAW CONNECTING TRAIL (Only in Mode 1 and Mode 3 where visual marking is active)
        if visual_marking and completed_count >= 1:
            trail_color = "#38bdf8" if self.current_mode == 1 else "#818cf8"
            completed_targets = self.session.target_list[:completed_count]
            for i in range(len(completed_targets) - 1):
                k1, k2 = completed_targets[i], completed_targets[i + 1]
                if k1 in self.session.layout and k2 in self.session.layout:
                    p1 = self.session.layout[k1]
                    p2 = self.session.layout[k2]
                    x1, y1 = self._get_canvas_pos(p1[0], p1[1])
                    x2, y2 = self._get_canvas_pos(p2[0], p2[1])
                    self.canvas.create_line(x1, y1, x2, y2, fill=trail_color, width=2.5)

        # 2. DRAW TARGET CIRCLES
        completed_set = set(self.session.target_list[:completed_count])

        for key in self.session.target_list:
            if key not in self.session.layout:
                continue
            pct_x, pct_y = self.session.layout[key]
            cx, cy = self._get_canvas_pos(pct_x, pct_y)

            is_completed = (key in completed_set)

            if visual_marking:
                # Mode 1 & Mode 3: Visual marking enabled
                if is_completed:
                    fill_col = "#86efac"
                    outline_col = "#16a34a"
                    text_col = "#14532d"
                    border_w = 2
                else:
                    fill_col = "#ffffff"
                    outline_col = "#475569"
                    text_col = "#0f172a"
                    border_w = 1.5
            else:
                # Mode 2 & Mode 4: Visual marking DISABLED
                fill_col = "#ffffff"
                outline_col = "#475569"
                text_col = "#0f172a"
                border_w = 1.5

            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=fill_col, outline=outline_col, width=border_w
            )
            self.canvas.create_text(
                cx, cy, text=key,
                fill=text_col, font=("Segoe UI", self.node_font_size, "bold")
            )

        # 3. WATERMARK / OVERLAY ON CANVAS (With prominent First Target callout)
        self.canvas.create_rectangle(10, 10, 160, 50, fill="#0f172a", outline="#38bdf8", width=1.5)
        self.canvas.create_text(85, 21, text="FIRST TARGET", font=("Segoe UI", 8, "bold"), fill="#94a3b8")
        self.canvas.create_text(85, 37, text=f"{self.session.start_target}  (Goal: {self.session.start_target}..{self.session.end_target})", font=("Segoe UI", 10, "bold"), fill="#38bdf8")

        self.canvas.create_text(
            172, 18, anchor="nw",
            text=f"Condition: {mode_spec['title']} | Range: {self.session.start_target}..{self.session.end_target} ({self.session.target_count} targets) | Seed: {self.session.seed}",
            font=("Segoe UI", 9, "bold"), fill="#64748b"
        )

        if not self.session.started:
            self.canvas.create_rectangle(w * 0.12, w * 0.42, w * 0.88, w * 0.58, fill="#ffffff", outline="#3b82f6", width=2)
            self.canvas.create_text(
                w / 2, w / 2,
                text=f"Click 'START TEST' to Begin\nConnect targets {self.session.start_target} -> {self.session.start_target + 1} -> ... -> {self.session.end_target}",
                font=("Segoe UI", 12, "bold"), fill="#1e293b", justify=tk.CENTER
            )
        elif self.session.completed:
            self.canvas.create_rectangle(w * 0.12, w * 0.42, w * 0.88, w * 0.58, fill="#dcfce7", outline="#16a34a", width=2)
            self.canvas.create_text(
                w / 2, w / 2,
                text=f"✓ TEST COMPLETE!\nTargets {self.session.start_target}..{self.session.end_target} ({self.session.target_count})\nTotal Time: {self.session.get_total_elapsed_ms()/1000.0:.2f}s  |  Errors: {self.session.total_errors}",
                font=("Segoe UI", 12, "bold"), fill="#15803d", justify=tk.CENTER
            )

    def _tick_stopwatch(self) -> None:
        """Timer callback updating the live stopwatch HUD."""
        if self.session.started and not self.session.completed:
            step_ms = self.session.get_current_step_elapsed_ms()
            tot_ms = self.session.get_total_elapsed_ms()
            self.hud_step_time_var.set(f"Step Time: {step_ms/1000.0:.1f}s")
            self.hud_total_time_var.set(f"Total Time: {tot_ms/1000.0:.1f}s")

        self.root.after(50, self._tick_stopwatch)

    def _handle_experiment_finished(self) -> None:
        """Called when final target is reached: saves JSON and opens result dialog."""
        saved_file = self.session.save_results_to_json()
        self.start_btn.config(text="✓ COMPLETED", bg="#16a34a", state=tk.NORMAL)
        self.hud_target_var.set(f"Complete! ({self.session.target_count}/{self.session.target_count})")

        self.root.after(300, lambda: self._show_run_results_window(saved_file))

    def _show_run_results_window(self, json_path: str) -> None:
        """Displays completion metrics and the individual run's target latency graph."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load result JSON: {e}")
            return

        win = tk.Toplevel(self.root)
        start_t = data.get("start_target", 1)
        end_t = data.get("end_target", 25)
        count_t = data.get("target_count", 25)

        win.title(f"Test Results — {data['mode_title']} (Targets {start_t}..{end_t})")
        win.geometry("860x670")
        win.configure(bg="#18181b")

        # Top stats header
        header = tk.Frame(win, bg="#27272a", padx=16, pady=12)
        header.pack(fill=tk.X, padx=12, pady=10)

        tk.Label(header, text=f"Results: {data['mode_title']}", font=("Segoe UI", 13, "bold"), bg="#27272a", fg="#4ade80").pack(anchor="w")
        tk.Label(
            header,
            text=f"Participant: {data['participant_id']}  |  Targets: {start_t} to {end_t} ({count_t} targets)  |  Seed: {data['seed']}",
            font=("Segoe UI", 9),
            bg="#27272a",
            fg="#cbd5e1",
        ).pack(anchor="w")

        stats_row = tk.Frame(header, bg="#27272a")
        stats_row.pack(fill=tk.X, pady=(8, 0))

        tot_s = data["total_duration_ms"] / 1000.0
        mean_ms = data["mean_step_time_ms"]
        errs = data["total_errors"]

        tk.Label(stats_row, text=f"Total Time: {tot_s:.2f}s", font=("Segoe UI", 11, "bold"), bg="#27272a", fg="#38bdf8").pack(side=tk.LEFT, padx=(0, 25))
        tk.Label(stats_row, text=f"Mean Latency / Target: {mean_ms:.1f} ms", font=("Segoe UI", 11, "bold"), bg="#27272a", fg="#a78bfa").pack(side=tk.LEFT, padx=15)
        tk.Label(stats_row, text=f"Errors: {errs}", font=("Segoe UI", 11, "bold"), bg="#27272a", fg="#f87171").pack(side=tk.LEFT, padx=15)

        tk.Label(header, text=f"Saved JSON: {Path(json_path).resolve()}", font=("Consolas", 8), bg="#27272a", fg="#94a3b8").pack(anchor="w", pady=(6, 0))

        # Matplotlib Graph of Target Latency Curve
        if MATPLOTLIB_AVAILABLE:
            fig = Figure(figsize=(7.8, 4.3), dpi=100)
            ax = fig.add_subplot(111)

            latencies = data.get("step_times_ms", [])
            steps = list(range(1, len(latencies) + 1))
            target_labels = [str(start_t + i) for i in range(len(latencies))]

            ax.plot(steps, latencies, color="#2563eb", marker="o", linewidth=2.0, markersize=5, label="Measured Search Latency Δt")

            # Linear trendline
            if len(latencies) >= 2:
                p = np.polyfit(steps, latencies, 1)
                trend = [p[0] * x + p[1] for x in steps]
                ax.plot(steps, trend, color="#dc2626", linestyle="--", linewidth=1.8, label=f"Trendline (slope: {p[0]:+.1f} ms/target)")

            ax.set_title(f"Target Latency Curve (Targets {start_t} to {end_t})", fontsize=11, fontweight="bold")
            ax.set_xlabel(f"Target Sequence ({start_t} -> {end_t})", fontsize=9, fontweight="bold")
            ax.set_ylabel("Time to Find Target Δt (ms)", fontsize=9, fontweight="bold")

            tick_step = max(1, len(steps) // 15)
            ax.set_xticks(steps[::tick_step])
            ax.set_xticklabels(target_labels[::tick_step])

            ax.grid(True, linestyle=":", alpha=0.6)
            ax.legend(loc="upper right", fontsize=9)
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        btn_row = tk.Frame(win, bg="#18181b", pady=6)
        btn_row.pack(fill=tk.X, padx=12)
        ttk.Button(btn_row, text="📊 Open All-Modes Comparison", command=self._open_comparison_window).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side=tk.RIGHT, padx=6)

    def _open_comparison_window(self) -> None:
        """Opens a dedicated window plotting historical comparison curves for all 4 modes."""
        fig = generate_multi_condition_comparison(self.results_dir)
        if fig is None:
            messagebox.showinfo("Plotting Unavailable", "Matplotlib is not installed or no results available.")
            return

        win = tk.Toplevel(self.root)
        win.title("TMT-A Spatial Memory Decomposition — Multi-Mode Comparison")
        win.geometry("1020x680")
        win.configure(bg="#18181b")

        header = tk.Frame(win, bg="#27272a", padx=16, pady=10)
        header.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(header, text="Dissociating Bottom-Up Visual Marking vs. Spatial Working Memory", font=("Segoe UI", 12, "bold"), bg="#27272a", fg="#38bdf8").pack(anchor="w")
        tk.Label(header, text="Comparing Target Latency Profiles & Trendlines across Experimental Conditions.", font=("Segoe UI", 9), bg="#27272a", fg="#cbd5e1").pack(anchor="w")

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)
