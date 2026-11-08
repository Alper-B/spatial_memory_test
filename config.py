"""
config.py
---------
Configuration constants, environment variable loader (.env), mode specifications,
target range generator, and participant name hashing (anonymization) utilities.
"""

import hashlib
import os
from pathlib import Path
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    # Load .env from spatial_memory_test directory, fallback to root
    _env_local = Path(__file__).resolve().parent / ".env"
    _env_root = Path(__file__).resolve().parent.parent / ".env"
    if _env_local.exists():
        load_dotenv(dotenv_path=_env_local)
    elif _env_root.exists():
        load_dotenv(dotenv_path=_env_root)
    else:
        load_dotenv()
except ImportError:
    pass

# --- DIRECTORY CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR_NAME = os.getenv("RESULTS_DIR", "results")
if os.path.isabs(RESULTS_DIR_NAME):
    DEFAULT_RESULTS_DIR = Path(RESULTS_DIR_NAME)
else:
    DEFAULT_RESULTS_DIR = BASE_DIR / RESULTS_DIR_NAME

DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# --- WEBAPP & EXPERIMENT CONFIGURATION (.env) ---
class ExperimentConfig:
    """Provides strongly-typed access to .env parameters with sensible defaults."""

    @classmethod
    def server_host(cls) -> str:
        return os.getenv("SERVER_HOST", "0.0.0.0")

    @classmethod
    def server_port(cls) -> int:
        try:
            return int(os.getenv("PORT", os.getenv("SERVER_PORT", "5000")))
        except ValueError:
            return 5000

    @classmethod
    def debug(cls) -> bool:
        return os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    @classmethod
    def target_count(cls) -> int:
        try:
            return max(2, min(90, int(os.getenv("TARGET_COUNT", "6"))))
        except ValueError:
            return 6

    @classmethod
    def target_range_min(cls) -> int:
        try:
            return max(1, int(os.getenv("TARGET_RANGE_MIN", "10")))
        except ValueError:
            return 10

    @classmethod
    def target_range_max(cls) -> int:
        try:
            return max(cls.target_range_min() + 1, int(os.getenv("TARGET_RANGE_MAX", "99")))
        except ValueError:
            return 99

    @classmethod
    def randomize_range_each_run(cls) -> bool:
        return os.getenv("RANDOMIZE_RANGE_EACH_RUN", "True").lower() in ("true", "1", "yes")

    @classmethod
    def fixed_start_target(cls) -> int:
        try:
            return max(cls.target_range_min(), int(os.getenv("FIXED_START_TARGET", "21")))
        except ValueError:
            return 21

    @classmethod
    def default_mode(cls) -> int:
        try:
            m = int(os.getenv("DEFAULT_MODE", "1"))
            return m if m in (1, 2, 3, 4) else 1
        except ValueError:
            return 1

    @classmethod
    def allow_mode_selection(cls) -> bool:
        return os.getenv("ALLOW_MODE_SELECTION", "True").lower() in ("true", "1", "yes")

    @classmethod
    def hash_salt(cls) -> str:
        return os.getenv("HASH_SALT", "tmta_spatial_memory_salt_2026")

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Returns JSON-serializable dictionary of active settings for the frontend."""
        return {
            "server_host": cls.server_host(),
            "server_port": cls.server_port(),
            "target_count": cls.target_count(),
            "target_range_min": cls.target_range_min(),
            "target_range_max": cls.target_range_max(),
            "randomize_range_each_run": cls.randomize_range_each_run(),
            "fixed_start_target": cls.fixed_start_target(),
            "default_mode": cls.default_mode(),
            "allow_mode_selection": cls.allow_mode_selection(),
        }


def generate_target_range(
    count: Optional[int] = None,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
    randomize: Optional[bool] = None,
) -> Tuple[int, int, int, List[str]]:
    """
    Generates a target sequence based on .env rules.
    e.g. count=6, min=10, max=99 -> start randomly in [10, 94], end = start + 5.
    Returns:
        (start_target, end_target, count, target_list_as_strings)
    """
    cnt = count if count is not None else ExperimentConfig.target_count()
    low = min_val if min_val is not None else ExperimentConfig.target_range_min()
    high = max_val if max_val is not None else ExperimentConfig.target_range_max()
    is_rand = randomize if randomize is not None else ExperimentConfig.randomize_range_each_run()

    max_start = max(low, high - cnt + 1)

    if is_rand:
        start = random.randint(low, max_start)
    else:
        start = min(ExperimentConfig.fixed_start_target(), max_start)

    end = start + cnt - 1
    targets = [str(i) for i in range(start, end + 1)]
    return start, end, cnt, targets


def hash_participant_name(name: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Cryptographically hashes participant name with SHA-256 for GDPR/IRB compliance.
    Raw name is NEVER stored in the final JSON dataset.
    Returns:
        (full_sha256_hash, short_anonymous_id)
        e.g. ("bd63b068...", "Anon-BD63B068")
    """
    clean_name = (name or "anonymous").strip().lower()
    active_salt = salt if salt is not None else ExperimentConfig.hash_salt()
    salted_string = f"{clean_name}:{active_salt}".encode("utf-8")
    full_hash = hashlib.sha256(salted_string).hexdigest()
    anon_id = f"Anon-{full_hash[:8].upper()}"
    return full_hash, anon_id


# --- EXPERIMENTAL MODE SPECIFICATIONS ---
MODE_SPECS = {
    1: {
        "title": "Mode 1: Normal Static & Lit",
        "short_name": "Normal (Static + Lit)",
        "key": "static_lit",
        "visual_marking": True,
        "shuffle_mode": "none",
        "hypothesis": "Both spatial memory and bottom-up distractor reduction active (-x*log(x) / steep decrease)",
        "description": "Completed targets light up green with connecting trail. Layout is static throughout the test.",
        "badge_color": "#16a34a",
        "badge_bg": "#dcfce7",
    },
    2: {
        "title": "Mode 2: Static & Unlit (Spatial Memory Only)",
        "short_name": "Memory Only (Static + Unlit)",
        "key": "static_unlit",
        "visual_marking": False,
        "shuffle_mode": "none",
        "hypothesis": "Spatial memory active without bottom-up pop-out (moderate decrease in latency due to layout familiarity)",
        "description": "Completed targets look IDENTICAL to uncompleted targets (all white). Layout is static. Subtle beep on correct click.",
        "badge_color": "#d97706",
        "badge_bg": "#fef3c7",
    },
    3: {
        "title": "Mode 3: Shuffled Remaining & Lit (Bottom-Up Only)",
        "short_name": "Bottom-Up Only (Shuffled Remaining + Lit)",
        "key": "shuffled_lit",
        "visual_marking": True,
        "shuffle_mode": "remaining",
        "hypothesis": "Bottom-up distractor reduction active, spatial memory disabled (approximately linear latency decrease)",
        "description": "Completed targets stay in place and light up. Uncompleted targets RESHUFFLE after every correct click.",
        "badge_color": "#2563eb",
        "badge_bg": "#dbeafe",
    },
    4: {
        "title": "Mode 4: Fully Shuffled & Unlit (Control / Baseline)",
        "short_name": "Control (Fully Shuffled + Unlit)",
        "key": "fully_shuffled_unlit",
        "visual_marking": False,
        "shuffle_mode": "all",
        "hypothesis": "Neither spatial memory nor bottom-up attention helps (constant latency / flat horizontal line)",
        "description": "ALL targets RESHUFFLE after every correct click, and NONE light up. Subtle beep on correct click.",
        "badge_color": "#dc2626",
        "badge_bg": "#fee2e2",
    },
}


# --- AUDIO FEEDBACK ENGINE (Desktop Tkinter Fallback) ---
def play_sound_tone(frequency: int, duration_ms: int) -> None:
    """Plays an audio tone in a background thread to prevent UI freezing."""
    def _worker():
        try:
            import winsound
            winsound.Beep(frequency, duration_ms)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def audio_correct_beep() -> None:
    """Crisp confirmation beep for correct target selection (vital for unlit modes)."""
    play_sound_tone(1150, 70)


def audio_error_tone() -> None:
    """Subtle low-frequency blip for incorrect clicks."""
    play_sound_tone(380, 85)


def audio_finish_chime() -> None:
    """Completion fanfare on reaching final target."""
    def _fanfare():
        try:
            import winsound
            for f in [660, 880, 1175, 1568]:
                winsound.Beep(f, 65)
                time.sleep(0.02)
        except Exception:
            pass

    threading.Thread(target=_fanfare, daemon=True).start()
