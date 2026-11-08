"""
session.py
----------
Manages single-session experiment state, precision timers, target sequencing,
audio triggering, participant name anonymization, and structured JSON recording.
"""

from datetime import datetime
import json
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from .config import (
        DEFAULT_RESULTS_DIR,
        MODE_SPECS,
        ExperimentConfig,
        generate_target_range,
        hash_participant_name,
        audio_correct_beep,
        audio_error_tone,
        audio_finish_chime,
    )
    from .layout import SpatialLayoutManager
except (ImportError, ValueError):
    from config import (
        DEFAULT_RESULTS_DIR,
        MODE_SPECS,
        ExperimentConfig,
        generate_target_range,
        hash_participant_name,
        audio_correct_beep,
        audio_error_tone,
        audio_finish_chime,
    )
    from layout import SpatialLayoutManager


class SpatialMemorySession:
    """Manages state, timers, latency measurements, and JSON recording for a single run."""

    def __init__(
        self,
        mode: Optional[int] = None,
        participant_id: Optional[str] = None,
        seed: Optional[int] = None,
        start_target: Optional[int] = None,
        end_target: Optional[int] = None,
        results_dir: Optional[Path] = None,
        raw_name: Optional[str] = None,
    ):
        active_mode = mode if mode is not None else ExperimentConfig.default_mode()
        self.mode = active_mode if active_mode in MODE_SPECS else 1
        self.mode_spec = MODE_SPECS[self.mode]

        # Anonymization / Participant identification
        if raw_name:
            self.participant_hash, self.anonymous_id = hash_participant_name(raw_name)
            self.participant_id = self.anonymous_id
        elif participant_id:
            self.participant_hash, self.anonymous_id = hash_participant_name(participant_id)
            self.participant_id = self.anonymous_id
        else:
            self.participant_hash, self.anonymous_id = hash_participant_name("participant")
            self.participant_id = self.anonymous_id

        self.seed = seed if seed is not None else random.randint(100000, 999999)
        self.rng = random.Random(self.seed)
        self.results_dir = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR

        # Configurable Target Range (reads .env defaults if not provided)
        if start_target is not None and end_target is not None:
            self.start_target = max(1, int(start_target))
            self.end_target = max(self.start_target + 1, int(end_target))
            self.target_count = self.end_target - self.start_target + 1
            self.target_list = [str(i) for i in range(self.start_target, self.end_target + 1)]
        else:
            s, e, cnt, t_list = generate_target_range()
            self.start_target = s
            self.end_target = e
            self.target_count = cnt
            self.target_list = t_list

        # Initial sprinkled layout
        self.layout = SpatialLayoutManager.generate_initial_layout(self.target_list, rng=self.rng)
        self.initial_layout = dict(self.layout)

        # Experiment progress
        self.current_target_index = self.start_target
        self.completed_count = 0
        self.completed = False
        self.started = False

        # Timers (high-precision perf_counter)
        self.start_perf_time: Optional[float] = None
        self.last_target_perf_time: Optional[float] = None

        # Data collection
        self.step_records: List[Dict[str, Any]] = []
        self.step_latencies_ms: List[float] = []
        self.current_step_errors = 0
        self.total_errors = 0
        self.start_iso_time: str = ""

    def start_test(self) -> None:
        """Starts timing the experiment."""
        self.started = True
        self.start_perf_time = time.perf_counter()
        self.last_target_perf_time = self.start_perf_time
        self.start_iso_time = datetime.now().isoformat()
        self.current_target_index = self.start_target
        self.completed_count = 0
        self.step_records.clear()
        self.step_latencies_ms.clear()
        self.current_step_errors = 0
        self.total_errors = 0
        self.completed = False

    def handle_click(self, clicked_target_str: Optional[str]) -> Tuple[bool, bool]:
        """
        Processes a click on the canvas.
        Returns:
            (is_correct: bool, is_finished: bool)
        """
        if not self.started or self.completed:
            return False, False

        expected_target_str = str(self.current_target_index)

        if clicked_target_str == expected_target_str:
            # CORRECT CLICK
            now = time.perf_counter()
            step_latency_ms = (now - self.last_target_perf_time) * 1000.0
            cumulative_ms = (now - self.start_perf_time) * 1000.0

            # Record step data
            self.step_latencies_ms.append(round(step_latency_ms, 2))
            self.step_records.append({
                "target": expected_target_str,
                "target_num": self.current_target_index,
                "step_index": self.completed_count + 1,
                "step_time_ms": round(step_latency_ms, 2),
                "cumulative_time_ms": round(cumulative_ms, 2),
                "errors_in_step": self.current_step_errors,
            })

            # Play audio confirmation (vital for unlit modes)
            audio_correct_beep()

            # Execute dynamic layout reshuffling according to mode rules
            if self.mode_spec["shuffle_mode"] == "remaining":
                completed_targets = self.target_list[:self.completed_count + 1]
                uncompleted_targets = self.target_list[self.completed_count + 1:]
                self.layout = SpatialLayoutManager.shuffle_uncompleted_targets(
                    self.layout, completed_targets, uncompleted_targets, rng=self.rng
                )
            elif self.mode_spec["shuffle_mode"] == "all":
                self.layout = SpatialLayoutManager.shuffle_all_targets(self.target_list, rng=self.rng)

            # Advance target
            self.completed_count += 1
            self.current_target_index += 1
            self.current_step_errors = 0
            self.last_target_perf_time = now

            if self.current_target_index > self.end_target:
                self.completed = True
                audio_finish_chime()
                return True, True

            return True, False
        else:
            self.current_step_errors += 1
            self.total_errors += 1
            audio_error_tone()
            return False, False

    def get_total_elapsed_ms(self) -> float:
        """Returns total elapsed time in ms."""
        if not self.started or self.start_perf_time is None:
            return 0.0
        if self.completed and self.last_target_perf_time is not None:
            return (self.last_target_perf_time - self.start_perf_time) * 1000.0
        return (time.perf_counter() - self.start_perf_time) * 1000.0

    def get_current_step_elapsed_ms(self) -> float:
        """Returns current step elapsed time in ms."""
        if not self.started or self.completed or self.last_target_perf_time is None:
            return 0.0
        return (time.perf_counter() - self.last_target_perf_time) * 1000.0

    def save_results_to_json(self, output_dir: Optional[str] = None) -> str:
        """Saves experimental metrics to a structured JSON file."""
        target_dir = Path(output_dir) if output_dir else self.results_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_anon_id = self.anonymous_id.lower().replace("-", "_")
        filename = f"tmta_mode{self.mode}_{self.mode_spec['key']}_{safe_anon_id}_T{self.start_target}-{self.end_target}_{timestamp_str}.json"
        full_filepath = target_dir / filename

        total_ms = self.get_total_elapsed_ms()
        mean_ms = float(sum(self.step_latencies_ms) / len(self.step_latencies_ms)) if self.step_latencies_ms else 0.0
        median_ms = float(sorted(self.step_latencies_ms)[len(self.step_latencies_ms) // 2]) if self.step_latencies_ms else 0.0

        payload = {
            "experiment": "TMT-A Spatial Memory & Visual Marking Decomposition",
            "task_type": "TMT-A",
            "mode": self.mode,
            "mode_key": self.mode_spec["key"],
            "mode_title": self.mode_spec["title"],
            "mode_hypothesis": self.mode_spec["hypothesis"],
            "visual_marking_active": self.mode_spec["visual_marking"],
            "layout_shuffle_mode": self.mode_spec["shuffle_mode"],
            "participant_id": self.anonymous_id,
            "anonymous_id": self.anonymous_id,
            "participant_hash": self.participant_hash,
            "seed": self.seed,
            "start_target": self.start_target,
            "end_target": self.end_target,
            "target_count": self.target_count,
            "targets": self.target_list,
            "timestamp": self.start_iso_time or datetime.now().isoformat(),
            "total_duration_ms": round(total_ms, 2),
            "mean_step_time_ms": round(mean_ms, 2),
            "median_step_time_ms": round(median_ms, 2),
            "min_step_time_ms": round(min(self.step_latencies_ms), 2) if self.step_latencies_ms else 0.0,
            "max_step_time_ms": round(max(self.step_latencies_ms), 2) if self.step_latencies_ms else 0.0,
            "total_errors": self.total_errors,
            "completed_targets_count": len(self.step_latencies_ms),
            "step_times_ms": self.step_latencies_ms,
            "steps": self.step_records,
            "initial_layout": self.initial_layout,
        }

        with open(full_filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return str(full_filepath)
