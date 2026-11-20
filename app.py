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
import uuid
import zipfile

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

try:
    from .config import (
        DEFAULT_RESULTS_DIR,
        ExperimentConfig,
        MODE_SPECS,
        generate_target_range,
        hash_ip_address,
        hash_participant_name,
    )
    from .layout import SpatialLayoutManager
except (ImportError, ValueError):
    from config import (
        DEFAULT_RESULTS_DIR,
        ExperimentConfig,
        MODE_SPECS,
        generate_target_range,
        hash_ip_address,
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


def get_client_ip() -> str:
    """
    Retrieves the client's IP address from request headers or socket address.
    Prioritizes Cloudflare (CF-Connecting-IP), reverse proxies (X-Forwarded-For, X-Real-IP),
    and falls back to remote_addr.
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or "127.0.0.1"


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
    Returns the active .env settings, experimental mode specifications,
    and client anonymous ID hashed from their IP address.
    """
    client_ip = get_client_ip()
    full_hash, anon_id = hash_ip_address(client_ip)
    cfg = ExperimentConfig.to_dict()
    return jsonify({
        "status": "success",
        "config": cfg,
        "modes": MODE_SPECS,
        "anonymous_id": anon_id,
        "anonymous_hash": full_hash,
    })


@app.route("/api/anonymous_id", methods=["GET"])
def api_anonymous_id():
    """Returns the current client's IP-derived anonymous identifier."""
    client_ip = get_client_ip()
    full_hash, anon_id = hash_ip_address(client_ip)
    return jsonify({
        "status": "success",
        "anonymous_id": anon_id,
        "anonymous_hash": full_hash,
    })


@app.route("/api/new_target_range", methods=["GET"])
def api_new_target_range():
    """
    Generates a new target range according to .env parameters.
    e.g., target_count=10, min=10, max=99 -> start randomly in [10, 90], end = start + 9.
    Query params can optionally override defaults: ?count=10&min=10&max=99
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


@app.route("/api/session/start", methods=["POST"])
def api_start_session():
    """
    Initializes a structured, zero-degrees-of-freedom experimental session.
    Generates a unique session_id, creates a session directory, and provides a
    pseudorandomized counterbalanced queue of 16 rounds (4 for each mode).
    """
    client_ip = get_client_ip()
    full_hash, anon_id = hash_ip_address(client_ip)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_anon_id = anon_id.lower().replace("-", "_")
    uid = uuid.uuid4().hex[:6]
    session_id = f"session_{safe_anon_id}_{timestamp_str}_{uid}"

    # Pseudorandomized queue: exactly 4 rounds for each mode (16 rounds total)
    queue = [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4]
    random.shuffle(queue)

    session_dir = DEFAULT_RESULTS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "session_id": session_id,
        "participant_id": anon_id,
        "participant_hash": full_hash,
        "created_at": datetime.now().isoformat(),
        "practice_sequence": [1, 2, 3, 4],
        "experiment_queue": queue,
        "completed_practice": [],
        "completed_rounds": [],
        "cancelled_rounds": [],
    }

    with open(session_dir / "session_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return jsonify({
        "status": "success",
        "session_id": session_id,
        "anonymous_id": anon_id,
        "practice_sequence": [1, 2, 3, 4],
        "experiment_queue": queue,
    })


@app.route("/api/submit", methods=["POST"])
def submit_results():
    """
    Receives experimental metrics from the browser, performs participant anonymization
    via salted SHA-256 hash of their IP address, strips all raw identity,
    computes performance statistics, and saves the structured JSON into the results/ folder.
    Supports session-specific tracking, practice rounds, and 16-round experiment queue.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "error", "message": "Invalid or missing JSON payload"}), 400

    # Cryptographically hash participant identity from IP address (GDPR / IRB privacy preservation)
    client_ip = payload.get("client_ip") or get_client_ip()
    full_hash, anon_id = hash_ip_address(client_ip)

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

    # Session & Protocol Tracking
    session_id = payload.get("session_id")
    is_practice = bool(payload.get("is_practice", False))
    trial_index = payload.get("trial_index")
    round_number = payload.get("round_number")

    safe_anon_id = anon_id.lower().replace("-", "_")
    range_str = f"T{start_target}-{end_target}" if start_target is not None else f"N{target_count}"

    target_dir = DEFAULT_RESULTS_DIR
    safe_session_id = None
    if session_id:
        safe_session_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(session_id))
        target_dir = DEFAULT_RESULTS_DIR / safe_session_id
        target_dir.mkdir(parents=True, exist_ok=True)

    if is_practice:
        t_idx = trial_index if trial_index is not None else mode
        filename = f"practice_trial{t_idx}_mode{mode}_{spec['key']}_{safe_anon_id}_{range_str}_{timestamp_str}.json"
    elif round_number is not None:
        filename = f"round_{int(round_number):02d}_mode{mode}_{spec['key']}_{safe_anon_id}_{range_str}_{timestamp_str}.json"
    else:
        filename = f"tmta_mode{mode}_{spec['key']}_{safe_anon_id}_{range_str}_{timestamp_str}.json"

    filepath = target_dir / filename

    # Build clean JSON dataset - STRICTLY NO RAW PERSONAL NAME OR RAW IP STORED
    record = {
        "experiment": "TMT-A Spatial Memory & Visual Marking Decomposition",
        "task_type": "TMT-A",
        "session_id": safe_session_id,
        "is_practice": is_practice,
        "trial_index": trial_index,
        "round_number": round_number,
        "mode": mode,
        "mode_key": spec["key"],
        "mode_title": spec["title"],
        "mode_hypothesis": spec["hypothesis"],
        "visual_marking_active": spec["visual_marking"],
        "layout_shuffle_mode": spec["shuffle_mode"],
        "participant_id": anon_id,
        "anonymous_id": anon_id,
        "participant_hash": full_hash,
        "ip_hash": full_hash,
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

    # Update session manifest if applicable
    if safe_session_id and (target_dir / "session_manifest.json").exists():
        try:
            with open(target_dir / "session_manifest.json", "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
            entry = {
                "filename": filename,
                "mode": mode,
                "is_practice": is_practice,
                "trial_index": trial_index,
                "round_number": round_number,
                "duration_ms": round(total_duration_ms, 2),
                "mean_step_time_ms": mean_ms,
                "errors": total_errors,
                "timestamp": iso_time,
            }
            if is_practice:
                manifest_data.setdefault("completed_practice", []).append(entry)
            else:
                manifest_data.setdefault("completed_rounds", []).append(entry)
            manifest_data["updated_at"] = datetime.now().isoformat()
            with open(target_dir / "session_manifest.json", "w", encoding="utf-8") as mf:
                json.dump(manifest_data, mf, indent=2)
        except Exception as e:
            print(f"Warning: Failed to update session_manifest.json: {e}")

    return jsonify({
        "status": "success",
        "message": "Experiment results successfully submitted and anonymized based on IP.",
        "anonymous_id": anon_id,
        "session_id": safe_session_id,
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


@app.route("/api/export_session_zip", methods=["GET"])
def export_session_zip():
    """
    Packages all results from a specific experimental session (all 16 rounds + practice)
    along with SESSION_SUMMARY.json and EXPERIMENT_REPORT.txt into a single clean ZIP archive
    ready for participant download and submission to the researcher.
    """
    session_id = request.args.get("session_id")
    client_ip = get_client_ip()
    full_hash, anon_id = hash_ip_address(client_ip)
    safe_anon_id = anon_id.lower().replace("-", "_")
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    files_to_zip = []
    session_dir = None
    if session_id:
        safe_session_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(session_id))
        session_dir = DEFAULT_RESULTS_DIR / safe_session_id
        if session_dir.exists() and session_dir.is_dir():
            files_to_zip = sorted(session_dir.rglob("*.json"))

    # Fallback search if no specific folder or empty
    if not files_to_zip and DEFAULT_RESULTS_DIR.exists():
        for f in DEFAULT_RESULTS_DIR.rglob("*.json"):
            if f.name == "session_manifest.json":
                continue
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    d = json.load(jf)
                if session_id and d.get("session_id") == session_id:
                    files_to_zip.append(f)
                elif not session_id and d.get("anonymous_id") == anon_id:
                    files_to_zip.append(f)
            except Exception:
                continue

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        rounds_by_mode = {1: [], 2: [], 3: [], 4: []}
        practice_by_mode = {1: [], 2: [], 3: [], 4: []}
        errors_by_mode = {1: 0, 2: 0, 3: 0, 4: 0}
        total_duration_ms = 0.0

        for f in files_to_zip:
            if f.name == "session_manifest.json":
                zf.write(f, arcname=f.name)
                continue
            arcname = f.name
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    d = json.load(jf)
                m = d.get("mode")
                if m in rounds_by_mode:
                    dur = float(d.get("total_duration_ms", 0.0))
                    total_duration_ms += dur
                    lat = d.get("mean_step_time_ms")
                    err = int(d.get("total_errors", 0))
                    errors_by_mode[m] += err
                    if d.get("is_practice"):
                        practice_by_mode[m].append(d)
                        arcname = f"practice/{f.name}"
                    else:
                        rounds_by_mode[m].append(d)
                        arcname = f"experiment/{f.name}"
            except Exception:
                pass
            zf.write(f, arcname=arcname)

        # Generate SESSION_SUMMARY.json
        summary_modes = {}
        report_lines = [
            "=" * 76,
            "  TMT-A SPATIAL MEMORY DECOMPOSITION EXPERIMENT - PROTOCOL REPORT",
            "=" * 76,
            f"Participant ID:       {anon_id}",
            f"Session ID:           {session_id or 'session_default'}",
            f"Export Timestamp:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Completed Runs: {sum(len(v) for v in rounds_by_mode.values())} / 16 experiment runs (+ {sum(len(v) for v in practice_by_mode.values())} practice)",
            f"Total Duration:       {round(total_duration_ms / 1000.0, 1)} seconds",
            "-" * 76,
            "EMPIRICAL PERFORMANCE BY COGNITIVE CONDITION (4 Rounds Each):",
            "-" * 76,
        ]

        for m in range(1, 5):
            spec = MODE_SPECS[m]
            rounds = rounds_by_mode[m]
            mean_lats = [r.get("mean_step_time_ms", 0.0) for r in rounds if r.get("mean_step_time_ms") is not None]
            avg_lat = round(sum(mean_lats) / len(mean_lats), 1) if mean_lats else 0.0
            total_err = errors_by_mode[m]

            # Linear regression of latencies across steps if available
            all_step_times = [r.get("step_times_ms", []) for r in rounds if r.get("step_times_ms")]
            slope = 0.0
            if all_step_times:
                min_steps = min(len(st) for st in all_step_times)
                if min_steps >= 2:
                    avg_per_step = [sum(st[i] for st in all_step_times) / len(all_step_times) for i in range(min_steps)]
                    steps = list(range(1, min_steps + 1))
                    n = len(steps)
                    sx = sum(steps)
                    sy = sum(avg_per_step)
                    sxx = sum(x * x for x in steps)
                    sxy = sum(x * y for x, y in zip(steps, avg_per_step))
                    denom = n * sxx - sx * sx
                    slope = round((n * sxy - sx * sy) / denom if denom != 0 else 0.0, 1)

            summary_modes[f"mode_{m}"] = {
                "mode": m,
                "title": spec["title"],
                "short_name": spec["short_name"],
                "completed_rounds": len(rounds),
                "required_rounds": 4,
                "mean_latency_ms": avg_lat,
                "slope_ms_per_target": slope,
                "total_errors": total_err,
            }

            slope_str = f"{slope:+.1f} ms/tgt" if slope != 0 else "  0.0 ms/tgt"
            report_lines.append(
                f"  Mode {m} ({spec['short_name']:<20}): {len(rounds)}/4 rounds | Mean Latency: {avg_lat:6.1f} ms | Slope: {slope_str:<12} | Errors: {total_err}"
            )

        report_lines.extend([
            "-" * 76,
            "COGNITIVE DECOMPOSITION ANALYSIS:",
            "  - Mode 1: Static + Lit (Spatial Memory + Bottom-Up Pop-Out active)",
            "  - Mode 2: Static + Unlit (Spatial Memory active without visual cues)",
            "  - Mode 3: Shuffled + Lit (Visual Marking distractor reduction without memory)",
            "  - Mode 4: Fully Shuffled + Unlit (Pure visual search baseline)",
            "-" * 76,
            "Verification Hash: " + full_hash,
            "=" * 76,
        ])

        summary_payload = {
            "experiment": "TMT-A Spatial Memory & Visual Marking Decomposition",
            "session_id": session_id or "session_unknown",
            "participant_id": anon_id,
            "ip_hash": full_hash,
            "export_time": datetime.now().isoformat(),
            "experiment_rounds_completed": sum(len(v) for v in rounds_by_mode.values()),
            "experiment_rounds_target": 16,
            "practice_rounds_completed": sum(len(v) for v in practice_by_mode.values()),
            "modes_summary": summary_modes,
        }

        zf.writestr("SESSION_SUMMARY.json", json.dumps(summary_payload, indent=2))
        zf.writestr("EXPERIMENT_REPORT.txt", "\n".join(report_lines))

    buffer.seek(0)
    zip_name = f"spatial_memory_test_{safe_anon_id}_{timestamp_str}.zip"
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
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
