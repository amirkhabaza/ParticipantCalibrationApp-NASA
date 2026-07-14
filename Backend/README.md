# Backend — Affine Gaze Calibration

Offline correction engine for Tobii gaze using Frontend ground-truth targets.

```bash
cd Backend
pip install -r requirements.txt
python calibration_engine.py
```

**Inputs:** `data/input/gazedata{N}.csv` + `../Frontend/calibration_output/calibration_targets{N}.csv`  
**Outputs:** `data/output/gazedata{N}_corrected.csv` + `drift_correction_summary.png`

See the [root README](../README.md) for the full pipeline. This guide covers backend logic, the summary figure, and CSV columns in detail.

---

## What problem does this solve?

The eye tracker reports gaze in **normalized coordinates** (`gaze2d_x`, `gaze2d_y` in 0–1). Those readings are often **offset / scaled / slightly skewed** relative to the real screen pixels where calibration targets appeared.

The backend:

1. Pairs each on-screen calibration target with the gaze samples collected while that target was bright
2. Fits a **2D affine transform** that maps observed gaze → true target pixels
3. Applies that transform to **every** gaze sample in the trial
4. Exports corrected CSVs and a validation plot

---

## Folder layout

| Path | Role |
|------|------|
| `data/input/gazedata{N}.csv` | Raw Tobii gaze for trial N |
| `../Frontend/calibration_output/calibration_targets{N}.csv` | Target positions + Unix timestamps from the frontend |
| `data/output/gazedata{N}_corrected.csv` | Full trial gaze + corrected pixels + kinematics |
| `data/output/drift_correction_summary.png` | Visual QA of the fit for all trials |

---

## Two clocks (why alignment exists)

| Source | Clock | Example columns |
|--------|-------|-----------------|
| Frontend targets | Unix epoch seconds | `Bright_Timestamp_Start`, `Dim_Timestamp_Start` |
| Gaze CSV | Session-relative Tobii time (starts near 0) | `timestamp` |

They are not the same clock. The backend estimates an **epoch offset**:

```text
Tobii_time ≈ Unix_time − epoch_offset
```

Implemented in `unix_to_tobii_time()` and searched by `optimize_session_alignment()`.

**Saccade trim:** after converting the bright window to Tobii time, the first `saccade_trim_s` seconds are dropped so the median gaze is taken after the eye has landed on the target (not during the jump).

---

## Pipeline overview (3 steps)

```text
┌─────────────────────────────────────────────────────────────┐
│ STEP 1 — Extract calibration points                         │
│  load gaze + targets → align clocks → one (obs, true)       │
│  point per bright target                                    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2 — Fit robust 2D affine                               │
│  observed pixels → true pixels; drop bad outliers           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3 — Apply globally + export + plot                     │
│  correct every gaze row → CSV; draw summary PNG             │
└─────────────────────────────────────────────────────────────┘
```

Entry point (`if __name__ == "__main__"`):

```text
run_step1() → run_step2() → run_step3()
```

---

## Step 1 — Build calibration points

### Inputs

**Gaze** (`gazedataN.csv`):

| Column | Meaning |
|--------|---------|
| `timestamp` | Tobii session time (s) |
| `gaze2d_x`, `gaze2d_y` | Normalized gaze (0–1) |
| `pupildiameter` | Pupil size (mm) |

**Targets** (`calibration_targetsN.csv`):

| Column | Meaning |
|--------|---------|
| `Target_ID` | 1–9 for the 9-point grid |
| `Target_X_Px`, `Target_Y_Px` | True on-screen position |
| `Screen_Width`, `Screen_Height` | Display size in pixels |
| `Bright_Timestamp_*` | When the target was bright (Unix) |
| `Dim_Timestamp_*` | Dim period (used as a time anchor) |

### Per-target extraction (`extract_calibration_point`)

For each target row:

1. Convert bright start/end Unix → Tobii time using `epoch_offset`
2. Slice gaze in that window (after saccade trim)
3. Take **median** `gaze2d_x/y` in the window
4. Convert to pixels: `x_px = gaze2d_x * Screen_Width` (same for Y)
5. Compare to true `(Target_X_Px, Target_Y_Px)` → `error_before_px`
6. Also store kinematics for the plot: `velocity_y`, `amplitude_x`
7. Quality flags: `low_n` (too few samples), `unstable` (high std)

### Auto-alignment (`optimize_session_alignment`)

Grid-searches:

- Offset deltas around the `dim_min` anchor (`OFFSET_SEARCH_*`)
- Trim candidates `(0.1, 0.2, 0.3)` s

Picks the combination that **minimizes mean pre-fit error** across targets.  
Labels like `grid_d-10.00_t0.3` mean: offset = dim_min − 10 s, trim = 0.3 s.

---

## Step 2 — Affine fit (the math you explain)

### What is a 2D affine?

Maps observed pixel `(x, y)` to corrected `(x', y')`:

```text
[x']   [a  b  tx] [x]
[y'] = [c  d  ty] [y]
[1 ]   [0  0   1] [1]
```

This covers translation, scale, rotation, and shear — enough for typical tracker drift on a flat screen.

`fit_affine_2d()` solves this with least squares (`numpy.linalg.lstsq`) separately for X and Y.

### Robust / iterative fit (`fit_affine_iterative`)

1. Fit on all points
2. If any point still has post-fit error > `MAX_AFTER_ERROR_PX` (75 px), drop the worst and refit
3. **Protect** points that were already accurate before the fit (`PROTECT_BEFORE_PX`) unless after-error is clearly bad
4. Stop when remaining points are good enough, or too few points left (`MIN_AFFINE_POINTS = 3`)

Excluded points still get corrected for the plot, but they did **not** influence the matrix.

### Metrics printed / shown

| Metric | Meaning |
|--------|---------|
| MSE before / after | Mean squared pixel error (all targets) |
| MSE after (fit set) | Same, only points used in the fit |
| Mean error before → after | Average Euclidean error on the fit set |
| Condition # | Design-matrix condition number (lower is more numerically stable) |

---

## Step 3 — Global correction + CSV + PNG

### Corrected CSV (`gazedataN_corrected.csv`)

Every original gaze row is kept, then new columns are added:

| Column | Meaning |
|--------|---------|
| `timestamp` | Same Tobii time as input |
| `gaze2d_x`, `gaze2d_y` | Original normalized gaze (unchanged) |
| `pupildiameter` | Original pupil size |
| **`Corrected_Gaze_X`** | Affined gaze X in **screen pixels** |
| **`Corrected_Gaze_Y`** | Affined gaze Y in **screen pixels** |
| `Velocity_Y` | Per-sample \|dY/dt\| (px/s) from corrected Y |
| `Amplitude_X` | Short-window peak-to-peak X (px) — fixation stability proxy |

**How correction is applied** (`apply_global_correction`):

1. Convert every sample’s `gaze2d_*` → raw pixels using screen size  
2. Multiply by the trial’s affine matrix  
3. Write `Corrected_Gaze_X/Y`  
4. Add kinematics columns  

**How to talk about it:**  
“The corrected CSV is the full continuous gaze stream in screen coordinates after removing systematic tracker offset/scale, ready for downstream analysis. Raw `gaze2d_*` is preserved for audit.”

---

## How to explain the PNG (`drift_correction_summary.png`)

Layout: **3 rows × N trials (columns)**. Title: *2D Affine Calibration (auto-aligned + robust fit)*.

### Top row — Spatial map (screen coordinates)

| Symbol | Meaning |
|--------|---------|
| Green ★ | True calibration target location |
| Red ● | Original observed median gaze (used in fit) |
| Blue ○ | Same point after affine correction |
| Orange / cyan | Excluded from fit (outlier), shown for honesty |
| Gray dotted line | Error **before** (obs → true) |
| Blue dashed line | Error **after** (corrected → true) |

Y-axis is inverted (`ylim` top→bottom) to match screen coordinates (origin top-left).

**Subtitle** example: `Trial 1 — 8 fit / 1 excl | grid_d-10.00_t0.3 | trim 0.3s`

- 8 points built the matrix; 1 was excluded  
- Alignment strategy + saccade trim used  

**Text box:** `MSE fit` and `Mean err: before→after` — the headline accuracy claim.

**What “good” looks like:** blue rings sit near green stars; red dots are systematically off (drift), not randomly scattered.

### Middle row — Kinematics during the bright window

| Series | Axis | Meaning |
|--------|------|---------|
| Purple ○ Vel Y | Left | Median \|vertical velocity\| in the bright window (px/s) |
| Teal □ Amp X | Right | Peak-to-peak horizontal travel in the window (px) |

High velocity or amplitude can flag unstable fixations (`unstable` quality flag). Hollow markers on excluded points highlight kinematics for outliers.

### Bottom row — Per-target error bars

- Salmon = error before correction (px)  
- Steel blue = error after correction (px)  
- X-axis = target IDs (order = processing order, not 1…9 sorted)

**What “good” looks like:** blue bars much shorter than salmon for almost every target. A remaining tall blue bar on an excluded target is expected (that point was not trusted for the fit).

---

## End-to-end story (elevator pitch)

1. **Frontend** shows 9 targets and logs when each was bright (Unix time) and where it was (pixels).  
2. **Tobii** logs continuous gaze with its own session clock.  
3. **Backend** finds the best clock offset + trim so bright windows line up with real fixations.  
4. For each target it takes median gaze → observed pixel, pairs with true pixel.  
5. It fits a robust affine map observed→true, dropping targets that disagree with the global transform.  
6. That map is applied to **all** gaze samples → corrected CSV.  
7. The PNG proves the map works: corrected points hug true targets and per-target error drops (~200 px → ~30 px in the current runs).

---

## Key functions cheat sheet

| Function | Job |
|----------|-----|
| `load_trial_data` | Read gaze + targets CSVs |
| `estimate_epoch_offset_*` / `unix_to_tobii_time` | Clock bridge |
| `slice_calibration_window` | Gaze samples in one bright window |
| `extract_calibration_point` / `build_calibration_points` | One calibration pair per target |
| `optimize_session_alignment` | Best offset + trim |
| `fit_affine_2d` | Least-squares affine |
| `fit_affine_iterative` | Affine + outlier rejection |
| `apply_global_correction` | Correct full gaze stream |
| `export_corrected_gaze` | Write `gazedataN_corrected.csv` |
| `plot_affine_calibration_summary` | Write `drift_correction_summary.png` |
| `run_step1` / `run_step2` / `run_step3` | Orchestrate the three stages |

---

## Important constants (tuning knobs)

| Constant | Typical role |
|----------|--------------|
| `NUM_TRIALS` | How many trials to process (3) |
| `MIN_AFFINE_POINTS` | Minimum points to fit (3) |
| `OFFSET_SEARCH_*` / `TRIM_CANDIDATES` | Alignment search space |
| `SACCADE_TRIM_S` | Default post-saccade trim |
| `MAX_AFTER_ERROR_PX` | Drop points worse than this after fit |
| `PROTECT_BEFORE_PX` / `PROTECT_MAX_AFTER_PX` | Don’t casually drop already-good points |
| `MIN_GAZE_SAMPLES` / `MAX_GAZE_STD` | Quality flags on windows |

---

## Quick talking points for demos

- **PNG:** “Top: did correction land on true targets? Middle: was the eye stable (amplitude/velocity)? Bottom: by how many pixels did error drop?”  
- **CSV:** “Same timeline as raw gaze, plus screen-pixel corrected X/Y you can use for analysis.”  
- **Logic:** “Align clocks → median per target → affine map → apply to whole trial.”
