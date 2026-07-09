from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
GAZE_DIR = BACKEND_DIR / "data" / "input"
OUTPUT_DIR = BACKEND_DIR / "data" / "output"
TARGETS_DIR = BACKEND_DIR.parent / "Frontend" / "calibration output"

NUM_TRIALS = 3
MIN_AFFINE_POINTS = 3
PREFERRED_FIT_POINTS = 6
MIN_GAZE_SAMPLES = 50
MAX_GAZE_STD = 0.05

#Grid search: shift epoch offset relative to dim_min anchor (seconds)
OFFSET_SEARCH_MIN_S = -10.0
OFFSET_SEARCH_MAX_S = 2.0
OFFSET_SEARCH_STEP_S = 0.25
TRIM_CANDIDATES = (0.1, 0.2, 0.3)

MAX_AFTER_ERROR_PX = 75.0
PROTECT_BEFORE_PX = 100.0
PROTECT_MAX_AFTER_PX = 150.0
SACCADE_TRIM_S = 0.2

# Implement paths/constants, file loading, and a minimal runnable entrypoint. 

def load_trial_data(trial_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    gaze_path = GAZE_DIR / f"gazedata{trial_id}.csv"
    targets_path = TARGETS_DIR / f"calibration_targets{trial_id}.csv"
    return pd.read_csv(gaze_path), pd.read_csv(targets_path)

# Implement the clock bridge between Unix epoch timestamps from the frontend and session-relative Tobii timestamps from the gaze CSV.

def estimate_epoch_offset_dim_min(gaze_df: pd.DataFrame, targets_df: pd.DataFrame) -> float:
    """Anchor: earliest dim onset ↔ earliest gaze sample."""
    return targets_df["Dim_Timestamp_Start"].min() - gaze_df["timestamp"].min()


def estimate_epoch_offset_bright_first(gaze_df: pd.DataFrame, targets_df: pd.DataFrame) -> float:
    """Anchor: first bright start ↔ earliest gaze sample."""
    return targets_df["Bright_Timestamp_Start"].iloc[0] - gaze_df["timestamp"].min()


def unix_to_tobii_time(unix_ts: float, epoch_offset: float) -> float:
    return unix_ts - epoch_offset


def estimate_epoch_offset(gaze_df: pd.DataFrame, targets_df: pd.DataFrame) -> float:
    """Backward-compatible alias; prefer optimize_session_alignment."""
    return estimate_epoch_offset_dim_min(gaze_df, targets_df)

# Implement window extraction, median ovserved gaze, normalized->pixel
# conversion, and building one calibration point per target.

def slice_calibration_window(
    gaze_df: pd.DataFrame,
    bright_start_unix: float,
    bright_end_unix: float,
    epoch_offset: float,
    saccade_trim_s: float = SACCADE_TRIM_S,
) -> pd.DataFrame:
    window_start = unix_to_tobii_time(bright_start_unix, epoch_offset) + saccade_trim_s
    window_end = unix_to_tobii_time(bright_end_unix, epoch_offset)
    mask = (gaze_df["timestamp"] >= window_start) & (gaze_df["timestamp"] <= window_end)
    return gaze_df.loc[mask].copy()

def compute_observed_median(window_df: pd.DataFrame) -> tuple[float, float]:
    return (
        float(np.median(window_df["gaze2d_x"].to_numpy())),
        float(np.median(window_df["gaze2d_y"].to_numpy())),
    )


def gaze2d_to_pixels(
    gaze2d_x: float | np.ndarray,
    gaze2d_y: float | np.ndarray,
    screen_width: int,
    screen_height: int,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    return gaze2d_x * screen_width, gaze2d_y * screen_height


