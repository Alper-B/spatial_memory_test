"""
app.py
------
Flask Web Application for TMT-A Spatial Memory Decomposition Experiment.
Allows any user to perform the experiment across all 4 modes in a web browser,
with real-time performance timing, Web Audio feedback, .env configuration,
and anonymized result storage (SHA-256 salted hash).
"""

from datetime import datetime
import io
import json
import math
import os
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

try:
    from .config import (
        DEFAULT_RESULTS_DIR,
        ExperimentConfig,
        MODE_SPECS,
        generate_target_range,
        hash_participant_name,
    )
    from .layout import SpatialLayoutManager
except (ImportError, ValueError):
    from config import (
        DEFAULT_RESULTS_DIR,
        ExperimentConfig,
        MODE_SPECS,
        generate_target_range,
        hash_participant_name,
    )
    from layout import SpatialLayoutManager

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)


@app.route("/")
def index():
    """Renders the main interactive TMT-A experiment web interface."""
    return render_template("index.html")


@app.route("/analytics")
def analytics():
    """Renders the multi-condition analytics & submissions dashboard."""
    return render_template("analytics.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    """
    Returns the active .env settings and experimental mode specifications
    to the frontend.
    """
    cfg = ExperimentConfig.to_dict()
    return jsonify({
        "status": "success",
        "config": cfg,
        "modes": MODE_SPECS,
    })


@app.route("/api/new_target_range", methods=["GET"])
def api_new_target_range():
    """
    Generates a new target range according to .env parameters.
    e.g., target_count=6, min=10, max=99 -> start randomly in [10, 94], end = start + 5.
    Query params can optionally override defaults: ?count=6&min=10&max=99
    """
    count = request.args.get("count", type=int)
    min_val = request.args.get("min", type=int)
    max_val = request.args.get("max", type=int)
    randomize = request.args.get("randomize", type=lambda v: v.lower() in ("true", "1", "yes"))

    start, end, cnt, targets = generate_target_range(
        count=count,
        min_val=min_val,
        max_val=max_val,
        randomize=randomize,
    )

    return jsonify({
        "status": "success",
        "start_target": start,
        "end_target": end,
        "target_count": cnt,
        "targets": targets,
    })


@app.route("/api/generate_layout", methods=["POST"])
def api_generate_layout():
    """
    Generates sprinkled floor layout coordinates for a given list of targets.
    Coordinates are in percentage [0, 100].
    """
    data = request.get_json(silent=True) or {}
    targets = data.get("targets", [])
    if not targets:
        s, e, cnt, targets = generate_target_range()

    seed = data.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()
    layout = SpatialLayoutManager.generate_initial_layout(targets, rng=rng)

    return jsonify({
        "status": "success",
        "targets": targets,
        "layout": layout,
    })


@app.route("/api/submit", methods=["POST"])
def submit_results():
    """
    Receives experimental metrics from the browser, performs participant anonymization
    via salted SHA-256, strips all raw personal identity, computes performance statistics,
    and saves the structured JSON into the results/ folder.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "error", "message": "Invalid or missing JSON payload"}), 400

    raw_name = str(payload.get("name", "")).strip()
    if not raw_name:
        raw_name = "anonymous"

    # Cryptographically hash participant identity (GDPR / IRB privacy preservation)
    full_hash, anon_id = hash_participant_name(raw_name)

    mode = int(payload.get("mode", 1))
    if mode not in MODE_SPECS:
        mode = 1
    spec = MODE_SPECS[mode]

    step_times = [float(t) for t in payload.get("step_times_ms", [])]
    steps = payload.get("steps", [])
    total_duration_ms = float(payload.get("total_duration_ms", sum(step_times) if step_times else 0.0))
    total_errors = int(payload.get("total_errors", 0))

    start_target = payload.get("start_target")
    end_target = payload.get("end_target")
    target_count = payload.get("target_count", len(step_times))
    targets = payload.get("targets", [])

    if not targets and steps:
        targets = [str(s.get("target")) for s in steps]

    if start_target is None and targets:
        try:
            start_target = int(targets[0])
            end_target = int(targets[-1])
        except ValueError:
            start_target = 1
            end_target = len(targets)

    # Compute statistical descriptors
    mean_ms = round(float(sum(step_times) / len(step_times)), 2) if step_times else 0.0
    sorted_times = sorted(step_times)
    median_ms = round(float(sorted_times[len(sorted_times) // 2]), 2) if sorted_times else 0.0
    min_ms = round(float(min(step_times)), 2) if step_times else 0.0
    max_ms = round(float(max(step_times)), 2) if step_times else 0.0

    timestamp_dt = datetime.now()
    timestamp_str = timestamp_dt.strftime("%Y%m%d_%H%M%S")
    iso_time = payload.get("start_iso_time") or timestamp_dt.isoformat()

    # Format output filename
    safe_anon_id = anon_id.lower().replace("-", "_")
    range_str = f"T{start_target}-{end_target}" if start_target is not None else f"N{target_count}"
    filename = f"tmta_mode{mode}_{spec['key']}_{safe_anon_id}_{range_str}_{timestamp_str}.json"
    filepath = DEFAULT_RESULTS_DIR / filename

    # Build clean JSON dataset - STRICTLY NO RAW NAME STORED
    record = {
        "experiment": "TMT-A Spatial Memory & Visual Marking Decomposition",
        "task_type": "TMT-A",
        "mode": mode,
        "mode_key": spec["key"],
        "mode_title": spec["title"],
        "mode_hypothesis": spec["hypothesis"],
        "visual_marking_active": spec["visual_marking"],
        "layout_shuffle_mode": spec["shuffle_mode"],
        "participant_id": anon_id,
        "anonymous_id": anon_id,
        "participant_hash": full_hash,
        "seed": payload.get("seed"),
        "start_target": start_target,
        "end_target": end_target,
        "target_count": target_count,
        "targets": targets,
        "timestamp": iso_time,
        "total_duration_ms": round(total_duration_ms, 2),
        "mean_step_time_ms": mean_ms,
        "median_step_time_ms": median_ms,
        "min_step_time_ms": min_ms,
        "max_step_time_ms": max_ms,
        "total_errors": total_errors,
        "completed_targets_count": len(step_times),
        "step_times_ms": step_times,
        "steps": steps,
        "initial_layout": payload.get("initial_layout", {}),
        "canvas_size": payload.get("canvas_size", {}),
        "user_agent": request.headers.get("User-Agent", "WebBrowser"),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return jsonify({
        "status": "success",
        "message": "Experiment results successfully submitted and anonymized.",
        "anonymous_id": anon_id,
        "filename": filename,
        "summary": {
            "mode": mode,
            "mode_name": spec["short_name"],
            "targets": f"{start_target} -> {end_target} ({target_count} targets)",
            "total_duration_ms": round(total_duration_ms, 2),
            "mean_step_time_ms": mean_ms,
            "total_errors": total_errors,
            "steps_count": len(step_times),
        },
    })


@app.route("/api/comparison", methods=["GET"])
def api_comparison():
    """
    Aggregates all stored experimental sessions across Mode 1, Mode 2, Mode 3, and Mode 4.
    Computes empirical average latencies per step and linear regression slopes
    for live browser visualization.
    """
    mode_data: Dict[int, List[List[float]]] = {1: [], 2: [], 3: [], 4: []}
    submissions_count = 0

    if DEFAULT_RESULTS_DIR.exists():
        for json_file in DEFAULT_RESULTS_DIR.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                m = data.get("mode")
                latencies = data.get("step_times_ms", [])
                if m in mode_data and len(latencies) >= 2:
                    mode_data[m].append(latencies)
                    submissions_count += 1
            except Exception:
                continue

    result_modes = {}
    for m in range(1, 5):
        runs = mode_data[m]
        spec = MODE_SPECS[m]
        if runs:
            min_len = min(len(r) for r in runs)
            truncated = [r[:min_len] for r in runs]
            mean_latencies = [round(sum(col) / len(col), 2) for col in zip(*truncated)]
            steps = list(range(1, min_len + 1))

            # Linear regression: slope and intercept
            n = len(steps)
            if n >= 2:
                sx = sum(steps)
                sy = sum(mean_latencies)
                sxx = sum(x * x for x in steps)
                sxy = sum(x * y for x, y in zip(steps, mean_latencies))
                denom = (n * sxx - sx * sx)
                slope = (n * sxy - sx * sy) / denom if denom != 0 else 0.0
                intercept = (sy - slope * sx) / n
            else:
                slope = 0.0
                intercept = mean_latencies[0] if mean_latencies else 0.0

            trend_line = [round(slope * x + intercept, 2) for x in steps]

            result_modes[m] = {
                "has_data": True,
                "mode_key": spec["key"],
                "short_name": spec["short_name"],
                "title": spec["title"],
                "hypothesis": spec["hypothesis"],
                "color": spec["badge_color"],
                "runs_count": len(runs),
                "steps": steps,
                "mean_latencies": mean_latencies,
                "slope": round(slope, 2),
                "intercept": round(intercept, 2),
                "trend_line": trend_line,
            }
        else:
            # Theoretical fallback curve for visualization
            steps = list(range(1, 7))
            if m == 1:
                curve = [round(1500 * math.exp(-0.15 * i) + 500, 2) for i in steps]
            elif m == 2:
                curve = [round(1450 * math.exp(-0.06 * i) + 650, 2) for i in steps]
            elif m == 3:
                curve = [round(1400 - (75 * i), 2) for i in steps]
            else:
                curve = [1150.0 for _ in steps]

            n = len(steps)
            sx = sum(steps)
            sy = sum(curve)
            sxx = sum(x * x for x in steps)
            sxy = sum(x * y for x, y in zip(steps, curve))
            slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
            intercept = (sy - slope * sx) / n

            result_modes[m] = {
                "has_data": False,
                "mode_key": spec["key"],
                "short_name": spec["short_name"],
                "title": spec["title"],
                "hypothesis": spec["hypothesis"],
                "color": spec["badge_color"],
                "runs_count": 0,
                "steps": steps,
                "mean_latencies": curve,
                "slope": round(slope, 2),
                "intercept": round(intercept, 2),
                "trend_line": [round(slope * x + intercept, 2) for x in steps],
                "note": "Theoretical projection (no runs recorded yet)",
            }

    return jsonify({
        "status": "success",
        "total_submissions_analyzed": submissions_count,
        "modes": result_modes,
    })


@app.route("/api/submissions", methods=["GET"])
def api_submissions():
    """
    Returns a list of all recorded submissions with anonymous IDs and summary metrics.
    """
    items = []
    if DEFAULT_RESULTS_DIR.exists():
        for f in sorted(DEFAULT_RESULTS_DIR.rglob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    d = json.load(jf)
                items.append({
                    "filename": f.name,
                    "mode": d.get("mode"),
                    "mode_key": d.get("mode_key"),
                    "anonymous_id": d.get("anonymous_id") or d.get("participant_id"),
                    "timestamp": d.get("timestamp"),
                    "targets": f"{d.get('start_target', '?')} -> {d.get('end_target', '?')} ({d.get('target_count', len(d.get('step_times_ms', [])))} targets)",
                    "total_duration_ms": d.get("total_duration_ms"),
                    "mean_step_time_ms": d.get("mean_step_time_ms"),
                    "total_errors": d.get("total_errors", 0),
                })
            except Exception:
                continue

    return jsonify({
        "status": "success",
        "count": len(items),
        "submissions": items[:100],  # Return up to 100 recent entries
    })


@app.route("/api/export_zip", methods=["GET"])
def export_zip():
    """Packages all submitted JSON experimental results into a downloadable zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if DEFAULT_RESULTS_DIR.exists():
            for f in sorted(DEFAULT_RESULTS_DIR.rglob("*.json")):
                rel_path = f.relative_to(DEFAULT_RESULTS_DIR)
                zf.write(f, arcname=str(rel_path))
    buffer.seek(0)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"tmta_spatial_memory_results_{timestamp_str}.zip",
    )


def main():
    """Runs the Flask application."""
    host = ExperimentConfig.server_host()
    port = ExperimentConfig.server_port()
    debug = ExperimentConfig.debug()
    print("=" * 70)
    print("  TMT-A Spatial Memory Decomposition Web Application")
    print(f"  Listening on: http://localhost:{port} (or http://{host}:{port})")
    print(f"  Target Count: {ExperimentConfig.target_count()} | Range: {ExperimentConfig.target_range_min()}-{ExperimentConfig.target_range_max()}")
    print("=" * 70)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
