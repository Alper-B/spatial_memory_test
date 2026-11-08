# TMT-A Spatial Memory & Visual Marking Decomposition Suite

A psychophysics testing and analysis environment designed to dissociate **Bottom-Up Visual Marking** (distractor pop-out & inhibition of return) from **Top-Down Spatial Working Memory** (layout familiarity) in Trail Making Test Part A (TMT-A).

Includes both a **Web Application** (accessible on desktop, tablet, and mobile browsers over LAN) and a **Desktop Tkinter Suite**, with centralized configuration via `.env`, cryptographic participant anonymization (salted SHA-256), and multi-condition analytics.

---

## 4 Experimental Conditions

| Mode | Visual Marking (Completed Lit) | Layout Dynamics | Cognitive Mechanism Isolated | Expected Latency Curve ($\Delta t_k$ over target $k$) |
|---|---|---|---|---|
| **Mode 1: Normal Static & Lit** | **YES** (Lit green + connecting trail) | **Static** (positions fixed) | **Both Active:** Spatial Memory + Bottom-Up Pop-Out | **Steep non-linear decrease** (e.g. $-x \cdot \log x$ or power-law decay) because the active distractor pool shrinks and previous glances inform future targets. |
| **Mode 2: Static & Unlit** | **NO** (All targets look identical: white) | **Static** (positions fixed) | **Spatial Memory Only** (No bottom-up pop-out) | **Moderate decrease:** Layout familiarity speeds up search, but completed targets remain visual distractors. Subtle audio beep confirms each correct click. |
| **Mode 3: Shuffled Remaining & Lit** | **YES** (Completed targets stay & lit up) | **Dynamic Reshuffle:** Uncompleted targets move every click | **Bottom-Up Only** (No future target memory) | **Linear decrease:** Target pool decreases steadily, but spatial memory for future targets is destroyed because they move on every step. |
| **Mode 4: Fully Shuffled & Unlit** | **NO** (All targets look identical: white) | **Dynamic Reshuffle:** All targets move every click | **Control / Baseline** (Neither active) | **Flat horizontal baseline:** Every target requires an exhaustive random visual search across identical white circles. Subtle audio beep confirms each correct click. |

---

## Web Application (`run_web.py` & `spatial_memory_test/app.py`)

Anyone can perform the experiment in their browser and submit structured results.

### Features
- **Zero Installation for Participants:** Accessible via standard web browsers at `http://localhost:5000` (or `http://<ip>:5000` over WiFi/LAN).
- **Sub-Millisecond Timing:** Uses `window.performance.now()` client-side, eliminating network lag for inter-target click latencies ($\Delta t_k$).
- **Native Web Audio API:** 1150 Hz confirmation beep for correct clicks, 380 Hz error blip, and completion fanfare.
- **Dynamic Floor Sprinkling:** Targets are scattered randomly without proximity bias and repositioned dynamically in Modes 3 & 4.
- **Participant Anonymization:** Participant names are cryptographically hashed on the server with salted SHA-256 (`Anon-XXXXXXXX`). Raw personal names are **never stored** on disk.
- **Results Modal & Inline Latency Curve:** Displays instant feedback, step breakdown, and fitted trendline slope after completion.
- **Analytics Dashboard (`/analytics`):** Real-time comparative latency chart across all 4 modes, trendlines ($ms/target$), and submission history.

### Quick Launch
```bash
# Launch the web application (starts Flask server and opens default browser)
python run_web.py

# Or launch directly from spatial_memory_test
python spatial_memory_test/app.py
```

---

## Configuration (`.env`)

All settings can be adjusted in `spatial_memory_test/.env`:

```ini
# Networking
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
DEBUG=False

# Target Sequence & Range
TARGET_COUNT=6
TARGET_RANGE_MIN=10
TARGET_RANGE_MAX=99
RANDOMIZE_RANGE_EACH_RUN=true
FIXED_START_TARGET=21

# Default Mode & UI
DEFAULT_MODE=1
ALLOW_MODE_SELECTION=true

# Storage & Privacy
RESULTS_DIR=results
HASH_SALT=tmta_spatial_memory_salt_2026
```

- When `TARGET_COUNT=6` and `RANDOMIZE_RANGE_EACH_RUN=true`, each run chooses a random starting point in `[10, 94]`, yielding sequences like `21..26`, `54..59`, or `81..86`.
- The participant's name is hashed with `SHA-256(name.lower() + ":" + HASH_SALT)` to create an anonymous ID (e.g., `Anon-BD63B068`).

---

## Package Structure

```
spatial_memory_test/
├── .env                         # Active configuration parameters
├── .env.example                 # Example environment template
├── app.py                       # Flask web application & REST API endpoints
├── config.py                    # Environment loader, mode specs, anonymization utilities
├── layout.py                    # SpatialLayoutManager: floor sprinkling & dynamic reshuffling
├── session.py                   # SpatialMemorySession: desktop engine & JSON serializer
├── plotter.py                   # Matplotlib comparative plotting with trendlines
├── gui.py                       # Desktop Tkinter GUI with dynamic range & audio feedback
├── tmta_spatial_memory_test.py  # Standalone desktop CLI / executable script
├── static/
│   ├── css/style.css            # Dark scientific UI theme
│   └── js/
│       ├── audio.js             # Web Audio API tone generator (1150Hz beep, fanfare)
│       ├── layout.js            # Client-side sprinkling & reshuffling algorithm
│       └── app.js               # Experiment loop, high-precision timing, AJAX submit
├── templates/
│   ├── index.html               # Main interactive web experiment interface
│   └── analytics.html           # Multi-condition analytics & submissions dashboard
└── results/                     # Anonymized JSON results files (legacy/ and legacy2/)
```

---

## Desktop Application

If you prefer running the native desktop Tkinter interface:

```bash
# Run desktop GUI
python spatial_memory_test/tmta_spatial_memory_test.py

# Custom target range
python spatial_memory_test/tmta_spatial_memory_test.py --start 26 --end 68

# View multi-condition comparison plot
python spatial_memory_test/tmta_spatial_memory_test.py --plot
```
