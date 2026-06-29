# Participant Calibration App

PsychoPy app that runs a **9-point eye-tracker calibration** on the participant monitor. It shows fixation targets and logs **when** (VSYNC-aligned, Unix timestamps) and **where** each target appeared. Gaze is recorded separately by the eye tracker; this repo handles only the **stimulus + ground-truth log** side.

Built for NASA internship eye-tracking research.

---

## Quick start (for software engineers)

**Prerequisites:** Python **3.10**, a monitor with OpenGL (standard on Mac / Windows laptops).

```bash
git clone https://github.com/amirkhabaza/ParticipantCalibrationApp-FRONTEND-.git
cd ParticipantCalibrationApp-FRONTEND-/Frontend
chmod +x run.sh          # macOS / Linux, first time only
./run.sh                 # creates .venv, installs deps, runs calibration
```

Windows (PowerShell):

```powershell
cd Frontend
.\run.ps1
```

**Smoke test without a participant** (skips instructions and exit prompt):

```bash
./run.sh --auto
```

**Output:** `Frontend/output/calibration_targets_<UTC-timestamp>.csv` (one file per run; see [Output CSV](#output-csv))

---

## Table of contents

1. [What problem this solves](#what-problem-this-solves)
2. [Where it fits in the pipeline](#where-it-fits-in-the-pipeline)
3. [Repo layout](#repo-layout)
4. [Session flow](#session-flow)
5. [Output CSV](#output-csv)
6. [Configuration](#configuration)
7. [Manual setup](#manual-setup)
8. [Code map](#code-map)
9. [Troubleshooting](#troubleshooting)

---

## What problem this solves

Eye-tracker calibration needs two synchronized streams:

| Stream | Source  | What it contains |
|--------|---------|------------------|
| **Gaze**| Eye-tracker software | `(timestamp, gaze_x, gaze_y)` samples |
| **Ground truth** | **This app** | `(timestamp, target_x, target_y)` for each fixation point |

This app does **not** talk to the eye tracker. It fullscreen-opens on the stimulus monitor, presents nine known screen positions in shuffled order, and writes a CSV with VSYNC-aligned **Unix epoch** timestamps so downstream analysis can match gaze samples to each target window.

---

## Where it fits in the pipeline

```
┌─────────────────────┐     ┌──────────────────────────┐
│  Eye tracker        │     │  This app                │
│  (separate software)│     │  calibration_9point.py   │
│                     │     │                          │
│  Records gaze (x,y) │     │  Shows targets at known  │
│  with timestamps    │     │  (x,y) with VSYNC times  │
└─────────┬───────────┘     └────────────┬─────────────┘
          │                              │
          └──────────┬───────────────────┘
                     ▼
          ┌──────────────────────┐
          │  Analysis / backend  │
          │  Match gaze samples  │
          │  to target windows   │
          │  → calibration model │
          └──────────────────────┘
```

**Typical session:** start eye-tracker recording → run this app on the same monitor → stop recording → align the session’s `calibration_targets_*.csv` with gaze export by timestamp.

---

## Repo layout

```
ParticipantCalibrationApp-FRONTEND-/
├── Backend/                     ← Calibration model (separate workstream)
└── Frontend/
    ├── README.md                ← Start here
    ├── calibration_9point.py    ← Main application (~400 lines, single file)
    ├── requirements.txt         ← PsychoPy dependency
    ├── run.sh                   ← macOS/Linux: setup + run
    ├── run.ps1                  ← Windows: setup + run
    └── output/
        └── calibration_targets_<UTC-timestamp>.csv   ← Created after each run (gitignored)
```

| File | Purpose |
|------|---------|
| `calibration_9point.py` | Fullscreen stimulus, VSYNC timing, CSV export |
| `requirements.txt` | `psychopy>=2024.1.4,<2027.0.0` (Python 3.8–3.10) |
| `run.sh` / `run.ps1` | Create venv, install deps, run script |

Always run from `Frontend/` (or use the run scripts, which `cd` there for you).

---

## Session flow

```
[Instructions]  "Focus on each dot… Press SPACEBAR to begin"
       │ SPACEBAR
       ▼
[0.3 s blank]
       ▼
[Target 1 of 9]  center dot + crosshairs (optional shrinking ring) for 1.5 s
       ▼
[0.5 s blank]  →  repeat for all 9 targets
       ▼
[Calibration complete — press any key to exit]
```

| Key | Action |
|-----|--------|
| **SPACEBAR** | Start (instructions screen only) |
| **ESC** | Abort — completed targets are still saved |
| **Any key** | Exit after completion |

### 9-point grid

Targets sit on a 3×3 grid at **30%, 50%, 70%** of width and height (`EDGE_INSET_FRACTION = 0.30`). IDs are fixed by position (row-major, top-left = 1):

```
┌─────┬─────┬─────┐
│  1  │  2  │  3  │
├─────┼─────┼─────┤
│  4  │  5  │  6  │
├─────┼─────┼─────┤
│  7  │  8  │  9  │
└─────┴─────┴─────┘
```

**Presentation order** is shuffled each run by default (`RANDOM_SEED = None`). Set `RANDOM_SEED` to an integer (e.g. `42`) for a repeatable order. The CSV `Target_ID` is grid position, not show order.

### Stimulus

By default (`SHOW_CIRCLES = False`): **center dot + crosshairs** on a black background — no shrinking ring.

Optional bullseye mode (`SHOW_CIRCLES = True`) adds a shrinking ring around the dot.

```bash
python calibration_9point.py --no-circles   # force crosshairs + dot only (no ring)
```

---

## Output CSV

**Directory:** `Frontend/output/`

Each run writes a new file named with the **UTC session start time** (millisecond precision):

```
calibration_targets_<YYYY-MM-DD>T<HH-MM-SS>-<mmm>Z.csv
```

Example: `calibration_targets_2026-06-29T18-23-16-287Z.csv`

- Timestamp is captured when the session starts (before instructions).
- Colons are replaced with hyphens so the name is safe on all platforms.
- Aborted runs still save completed targets to the same file for that session.

| Column | Description |
|--------|-------------|
| `Timestamp_Start` | Unix seconds (VSYNC) when target first appeared |
| `Timestamp_End` | Unix seconds (VSYNC) when target was replaced by blank |
| `Target_ID` | Grid ID 1–9 |
| `Target_X_Px` | Horizontal pixel (top-left origin) |
| `Target_Y_Px` | Vertical pixel (top-left origin) |
| `Screen_Width` | Drawable width in pixels |
| `Screen_Height` | Drawable height in pixels |

Example:

```csv
Timestamp_Start,    Timestamp_End,      Target_ID,  Target_X_Px,  Target_Y_Px,  Screen_Width,     Screen_Height
1719154322.747760,  1719154323.756066,  4,          151,          491,          1512,             982
```

Use `Timestamp_Start` / `Timestamp_End` to select gaze samples during each target window.

### VSYNC timing

- `win.flip(waitBlanking=True)` blocks until vertical blank; PsychoPy returns a flip time.
- Flip times are converted to **Unix epoch seconds** via `time.time() - core.getTime()` at session start, so they can be compared directly to typical eye-tracker exports.
- This is **software VSYNC** from the graphics driver — accurate for research use, but not photodiode-grade.

---

## Configuration

Edit constants at the top of `calibration_9point.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `TARGET_DURATION_S` | `1.5` | Seconds each target is shown |
| `RANDOM_SEED` | `None` | Shuffle seed; `None` = new random order each run |
| `PRE_TARGET_BLANK_S` | `0.3` | Blank before first target |
| `INTER_TARGET_BLANK_S` | `0.5` | Blank between targets (time to locate next point) |
| `EDGE_INSET_FRACTION` | `0.30` | Grid inset from edges |
| `SCREEN_INDEX` | `0` | Default monitor index (0 = primary, 1 = secondary) |
| `SHOW_CIRCLES` | `False` | `True` = add shrinking ring around dot |
| `DOT_RADIUS_PX` | `15` | Center dot radius |
| `CROSSHAIR_ARM_PX` | `32` | Half-length of each crosshair arm |
| `CROSSHAIR_LINE_WIDTH_PX` | `3` | Crosshair stroke width (visibility on Retina) |
| `OUTPUT_BASENAME` | `calibration_targets` | Filename prefix before UTC timestamp |
| `TARGET_COLOR` / `BACKGROUND_COLOR` | `[1,1,1]` / `[0,0,0]` | White targets on black (`rgb` color space, −1…1) |

Filename format is built by `build_output_filename()` from `OUTPUT_BASENAME` plus UTC date-time to the millisecond.

### Monitor selection

Resolution order (first match wins):

1. CLI: `--screen 1` or `--screen=1`
2. Environment: `CALIBRATION_SCREEN` or `SCREEN`
3. Config: `SCREEN_INDEX`

```bash
./run.sh --screen 1
CALIBRATION_SCREEN=1 ./run.sh
```

### CLI flags

| Flag | Effect |
|------|--------|
| `--auto` | Skip instructions and exit prompt (testing / CI) |
| `--no-circles` | Dot + crosshairs only (no shrinking ring) |
| `--screen <index>` | Monitor to display on (e.g. `1` for secondary display) |

```bash
python calibration_9point.py --auto --no-circles --screen 1
```

---

## Manual setup

If you prefer not to use `run.sh` / `run.ps1`:

```bash
cd Frontend
python3.10 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python calibration_9point.py
```

### Mac without admin (no Homebrew)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.10
cd Frontend
uv venv --python 3.10 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python calibration_9point.py
```

### Platform notes

| Platform | Notes |
|----------|-------|
| **macOS** | Retina handled via `useRetina=True`; `resolve_window_size()` normalizes pixel coords |
| **Windows** | DPI awareness enabled for 125%/150% scaling (HP EliteBook tested) |
| **Both** | `screen=0` = primary monitor — use `--screen` for the eye-tracker display |

---

## Code map

Single-file design. Entry: `main()` → `run_calibration()`.

| Function | Role |
|----------|------|
| `enable_windows_dpi_awareness()` | Physical pixels on scaled Windows displays |
| `create_calibration_window()` | Fullscreen PsychoPy window on chosen monitor |
| `get_screen_index()` | Resolve monitor from CLI, env, or config |
| `resolve_window_size()` | Correct pixel dimensions (Retina / DPI) |
| `generate_grid_targets()` | 9 positions from screen size |
| `build_bullseye_stimuli()` | Dot, crosshairs, ring |
| `present_shrinking_bullseye()` | Show one target; return Unix VSYNC start/end |
| `unix_epoch_offset()` / `flip_to_unix_time()` | Map PsychoPy clock → Unix epoch |
| `build_output_filename()` | UTC timestamped CSV name for this session |
| `save_calibration_csv()` | Write `output/calibration_targets_<UTC-timestamp>.csv` |
| `wait_for_spacebar()` / `wait_blank_interval()` | Participant pacing + ESC abort |

**Data flow:**

```
resolve_window_size → generate_grid_targets → shuffle
    → for each target: present_shrinking_bullseye (flip loop)
    → append row → save_calibration_csv
```

---

## What this app does NOT do

- Read or control eye-tracker hardware
- Compute calibration mapping (backend / analysis)
- Upload data (local CSV only)
- Randomize target **positions** (only presentation order is shuffled)

## License / repo

[ParticipantCalibrationApp-FRONTEND-](https://github.com/amirkhabaza/ParticipantCalibrationApp-FRONTEND-) on GitHub.
