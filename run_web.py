"""
run_web.py (inside spatial_memory_test)
---------------------------------------
Launcher script when inside the spatial_memory_test folder.
Usage:
    python run_web.py
"""

import os
import sys
import threading
import time
import webbrowser

# Add current directory and parent directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in [current_dir, parent_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app import app
from config import ExperimentConfig


def open_browser(port: int):
    """Automatically launches default web browser to the experiment page."""
    time.sleep(0.8)
    url = f"http://localhost:{port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    host = ExperimentConfig.server_host()
    port = ExperimentConfig.server_port()
    debug = ExperimentConfig.debug()

    print("=" * 72)
    print("  TMT-A Spatial Memory & Visual Marking Experiment Webapp")
    print("=" * 72)
    print(f"  * Web Server URL:       http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"  * Local Network Access: Accessible from other PCs / tablets on your LAN")
    print(f"  * Target Count:         {ExperimentConfig.target_count()} targets")
    print(f"  * Target Range:         {ExperimentConfig.target_range_min()} to {ExperimentConfig.target_range_max()} (randomized: {ExperimentConfig.randomize_range_each_run()})")
    print(f"  * Anonymization:        SHA-256 with custom salt (Raw names never saved)")
    print(f"  * Stored Results:       spatial_memory_test/results/")
    print("=" * 72)
    print("  Starting server... Press Ctrl+C in terminal to stop.")
    print("=" * 72)

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()

