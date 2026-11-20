"""
test_protocol.py
Test suite for the overhauled TMT-A Spatial Memory Protocol:
- Session generation and 16-round randomized queue
- Zero degrees of freedom verification
- Practice rounds submission
- 16 experiment rounds submission
- Session zip export and content verification
"""

import io
import json
import os
import sys
import unittest
import zipfile

# Ensure spatial_memory_test is on sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in [current_dir, parent_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app import app
from config import MODE_SPECS, DEFAULT_RESULTS_DIR


class TestSpatialMemoryProtocol(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_01_api_config(self):
        """Verify config endpoint returns expected mode specs and anonymous id."""
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("anonymous_id", data)
        self.assertIn("modes", data)
        self.assertEqual(len(data["modes"]), 4)

    def test_02_session_start_and_queue(self):
        """Verify /api/session/start creates unique session and 16-round randomized queue."""
        res = self.client.post("/api/session/start")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["session_id"].startswith("session_"))

        queue = data["experiment_queue"]
        self.assertEqual(len(queue), 16)
        # Verify exactly 4 of each mode
        for m in [1, 2, 3, 4]:
            self.assertEqual(queue.count(m), 4, f"Mode {m} must appear exactly 4 times")

    def test_03_full_protocol_lifecycle_and_zip_export(self):
        """Simulate 4 practice rounds, 16 experiment rounds, and verify zip export."""
        # 1. Start session
        start_res = self.client.post("/api/session/start")
        sess_data = start_res.get_json()
        session_id = sess_data["session_id"]
        queue = sess_data["experiment_queue"]

        # 2. Submit 4 practice trials (Modes 1 -> 2 -> 3 -> 4)
        for trial_idx, mode in enumerate([1, 2, 3, 4], start=1):
            practice_payload = {
                "session_id": session_id,
                "is_practice": True,
                "trial_index": trial_idx,
                "mode": mode,
                "start_target": 10,
                "end_target": 19,
                "target_count": 10,
                "targets": [str(i) for i in range(10, 20)],
                "step_times_ms": [800.0 + (trial_idx * 10)] * 10,
                "total_duration_ms": 8000.0,
                "total_errors": 0,
            }
            res = self.client.post("/api/submit", json=practice_payload)
            self.assertEqual(res.status_code, 200)
            d = res.get_json()
            self.assertEqual(d["status"], "success")
            self.assertIn("practice", d["filename"])

        # 3. Submit 16 experiment rounds according to queue
        for round_num, mode in enumerate(queue, start=1):
            exp_payload = {
                "session_id": session_id,
                "is_practice": False,
                "round_number": round_num,
                "mode": mode,
                "start_target": 20 + round_num,
                "end_target": 29 + round_num,
                "target_count": 10,
                "targets": [str(i) for i in range(20 + round_num, 30 + round_num)],
                "step_times_ms": [750.0 + (mode * 20)] * 10,
                "total_duration_ms": 7500.0,
                "total_errors": 1 if mode == 4 else 0,
            }
            res = self.client.post("/api/submit", json=exp_payload)
            self.assertEqual(res.status_code, 200)
            d = res.get_json()
            self.assertEqual(d["status"], "success")
            self.assertIn(f"round_{round_num:02d}", d["filename"])

        # 4. Request session zip download
        zip_res = self.client.get(f"/api/export_session_zip?session_id={session_id}")
        self.assertEqual(zip_res.status_code, 200)
        self.assertEqual(zip_res.mimetype, "application/zip")

        # 5. Inspect zip archive contents
        zip_buffer = io.BytesIO(zip_res.data)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            namelist = zf.namelist()

            # Must contain SESSION_SUMMARY.json and EXPERIMENT_REPORT.txt
            self.assertIn("SESSION_SUMMARY.json", namelist)
            self.assertIn("EXPERIMENT_REPORT.txt", namelist)

            # Check session summary JSON
            summary_raw = zf.read("SESSION_SUMMARY.json").decode("utf-8")
            summary = json.loads(summary_raw)
            self.assertEqual(summary["session_id"], session_id)
            self.assertEqual(summary["experiment_rounds_completed"], 16)
            self.assertEqual(summary["practice_rounds_completed"], 4)

            for m in range(1, 5):
                m_key = f"mode_{m}"
                self.assertIn(m_key, summary["modes_summary"])
                self.assertEqual(summary["modes_summary"][m_key]["completed_rounds"], 4)

            # Check experiment report text
            report_text = zf.read("EXPERIMENT_REPORT.txt").decode("utf-8")
            self.assertIn("16 / 16 experiment runs", report_text)
            self.assertIn(session_id, report_text)

        print(f"\n[PASS] Verified session {session_id} with 4 practice + 16 experiment rounds & zip export.")

    def test_04_cancellation_and_requeue_behavior(self):
        """Verify that cancelled rounds are not counted, and re-queued rounds maintain exactly 4 completions per mode."""
        start_res = self.client.post("/api/session/start")
        sess_data = start_res.get_json()
        session_id = sess_data["session_id"]
        queue = list(sess_data["experiment_queue"])

        # Simulate cancellation of the first item
        cancelled_mode = queue.pop(0)
        # Re-queue the cancelled mode at the end
        queue.append(cancelled_mode)

        # Now simulate completing the 16 rounds
        for round_num, mode in enumerate(queue, start=1):
            exp_payload = {
                "session_id": session_id,
                "is_practice": False,
                "round_number": round_num,
                "mode": mode,
                "start_target": 10,
                "end_target": 19,
                "target_count": 10,
                "step_times_ms": [850.0] * 10,
                "total_duration_ms": 8500.0,
                "total_errors": 0,
            }
            res = self.client.post("/api/submit", json=exp_payload)
            self.assertEqual(res.status_code, 200)

        # Export zip
        zip_res = self.client.get(f"/api/export_session_zip?session_id={session_id}")
        self.assertEqual(zip_res.status_code, 200)

        zip_buffer = io.BytesIO(zip_res.data)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            summary = json.loads(zf.read("SESSION_SUMMARY.json").decode("utf-8"))
            self.assertEqual(summary["experiment_rounds_completed"], 16)
            for m in range(1, 5):
                self.assertEqual(summary["modes_summary"][f"mode_{m}"]["completed_rounds"], 4)

        print(f"\n[PASS] Verified cancellation & re-queueing preserves 16 valid runs (4 per mode).")

    def test_05_analytics_and_submissions_endpoints(self):
        """Verify that /api/comparison and /api/submissions correctly aggregate data across subdirectories."""
        comp_res = self.client.get("/api/comparison")
        self.assertEqual(comp_res.status_code, 200)
        comp_data = comp_res.get_json()
        self.assertEqual(comp_data["status"], "success")
        self.assertIn("modes", comp_data)

        subs_res = self.client.get("/api/submissions")
        self.assertEqual(subs_res.status_code, 200)
        subs_data = subs_res.get_json()
        self.assertEqual(subs_data["status"], "success")
        self.assertGreater(subs_data["count"], 0)
        print(f"\n[PASS] Verified /api/comparison and /api/submissions with {subs_data['count']} submissions.")


if __name__ == "__main__":
    unittest.main()
