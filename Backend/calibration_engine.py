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

# Add optional learning extras: Pre-window velocity/amplitude and per-sample
# output columns once the core calibration pipeline already works.
def compute_window_velocity_y(window_df: pd.DataFrame, screen_height: int) -> float:
    """Median absolute vertical gaze velocity (px/s) during a calibration window."""
    if len(window_df) < 2:
        return 0.0
    t = window_df["timestamp"].to_numpy()
    y_px = window_df["gaze2d_y"].to_numpy() * screen_height
    dt = np.diff(t)
    dt = np.where(dt <= 0, np.nan, dt)
    velocity_y = np.abs(np.diff(y_px) / dt)
    return float(np.nanmedian(velocity_y))

def compute_window_amplitude_x(window_df: pd.DataFrame, screen_width: int) -> float:
    """Peak-to-peak horizontal gaze displacement (px) during a calibration window."""
    x_px = window_df["gaze2d_x"].to_numpy() * screen_width
    return float(np.max(x_px) - np.min(x_px))

def add_kinematics_columns(
    gaze_df: pd.DataFrame,
    screen_width: int,
    screen_height: int,
    *,
    use_corrected: bool = False,
) -> pd.DataFrame:
    """
    Add per-sample Velocity_Y (px/s) and Amplitude_X (px) columns.

    Velocity_Y: |dY/dt| from corrected gaze Y when available.
    Amplitude_X: rolling ~0.5 s peak-to-peak of gaze X (fixation stability).
    """
    df = gaze_df.sort_values("timestamp").copy()
    if use_corrected and "Corrected_Gaze_X" in df.columns:
        x = df["Corrected_Gaze_X"].to_numpy()
        y = df["Corrected_Gaze_Y"].to_numpy()
    else:
        x, y = gaze2d_to_pixels(
            df["gaze2d_x"].to_numpy(), df["gaze2d_y"].to_numpy(), screen_width, screen_height
        )

    dt = df["timestamp"].diff().to_numpy()
    dy = np.diff(y, prepend=y[0])
    velocity_y = np.zeros(len(df))
    valid = dt > 0
    velocity_y[valid] = np.abs(dy[valid] / dt[valid])
    if len(df) > 1:
        velocity_y[0] = velocity_y[1]

    # ~0.5 s rolling window at ~50 Hz ≈ 25 samples
    roll = max(3, int(round(0.5 / np.median(dt[dt > 0]))))
    x_series = pd.Series(x)
    amplitude_x = (
        x_series.rolling(roll, center=True, min_periods=1).max()
        - x_series.rolling(roll, center=True, min_periods=1).min()
    ).to_numpy()

    df["Velocity_Y"] = velocity_y
    df["Amplitude_X"] = amplitude_x
    return df


def extract_calibration_point(
    gaze_df: pd.DataFrame,
    target_row: pd.Series,
    epoch_offset: float,
    screen_width: int,
    screen_height: int,
    saccade_trim_s: float = SACCADE_TRIM_S,
) -> dict | None:
    """Extract one calibration pair; return None if window is empty."""
    window_start = (
        unix_to_tobii_time(target_row["Bright_Timestamp_Start"], epoch_offset)
        + saccade_trim_s
    )
    window_end = unix_to_tobii_time(target_row["Bright_Timestamp_End"], epoch_offset)

    if window_end <= window_start:
        return None

    try:
        window_df = slice_calibration_window(
            gaze_df,
            bright_start_unix=target_row["Bright_Timestamp_Start"],
            bright_end_unix=target_row["Bright_Timestamp_End"],
            epoch_offset=epoch_offset,
            saccade_trim_s=saccade_trim_s,
        )
    except ValueError:
        return None

    obs_gaze2d_x, obs_gaze2d_y = compute_observed_median(window_df)
    obs_x, obs_y = gaze2d_to_pixels(
        obs_gaze2d_x, obs_gaze2d_y, screen_width, screen_height
    )
    true_x = float(target_row["Target_X_Px"])
    true_y = float(target_row["Target_Y_Px"])
    std_x = float(window_df["gaze2d_x"].std())
    std_y = float(window_df["gaze2d_y"].std())
    n_samples = len(window_df)
    error_before_px = float(np.hypot(true_x - obs_x, true_y - obs_y))
    velocity_y = compute_window_velocity_y(window_df, screen_height)
    amplitude_x = compute_window_amplitude_x(window_df, screen_width)

    flags: list[str] = []
    if n_samples < MIN_GAZE_SAMPLES:
        flags.append("low_n")
    if std_x > MAX_GAZE_STD or std_y > MAX_GAZE_STD:
        flags.append("unstable")

    return {
        "target_id": int(target_row["Target_ID"]),
        "true_x_px": true_x,
        "true_y_px": true_y,
        "obs_gaze2d_x": obs_gaze2d_x,
        "obs_gaze2d_y": obs_gaze2d_y,
        "obs_x_px": float(obs_x),
        "obs_y_px": float(obs_y),
        "error_before_px": error_before_px,
        "std_gaze2d_x": std_x,
        "std_gaze2d_y": std_y,
        "velocity_y": velocity_y,
        "amplitude_x": amplitude_x,
        "n_gaze_samples": n_samples,
        "window_start_tobii": window_start,
        "window_end_tobii": window_end,
        "quality_flags": flags,
    }


def build_calibration_points(
    gaze_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    epoch_offset: float,
    saccade_trim_s: float,
) -> list[dict]:
    screen_width = int(targets_df.iloc[0]["Screen_Width"])
    screen_height = int(targets_df.iloc[0]["Screen_Height"])
    points: list[dict] = []
    for _, target_row in targets_df.iterrows():
        point = extract_calibration_point(
            gaze_df, target_row, epoch_offset, screen_width, screen_height, saccade_trim_s
        )
        if point is not None:
            points.append(point)
    return points

# Once point extraction works, search offset/trim combinations and keep the one that minimizes pre-fit error across calibration targets. 
def mean_pre_fit_error(points: list[dict]) -> float:
    if not points:
        return float("inf")
    return float(np.mean([p["error_before_px"] for p in points]))

def optimize_session_alignment(
    gaze_df: pd.DataFrame,
    targets_df: pd.DataFrame,
) -> tuple[float, float, str, float]:

  """
    Grid-search epoch offset (relative to dim_min) and saccade trim.

    Returns (epoch_offset, saccade_trim_s, strategy_label, mean_pre_fit_error_px).
    """
    base_offset = estimate_epoch_offset_dim_min(gaze_df, targets_df)
    best_offset = base_offset
    best_trim = SACCADE_TRIM_S
    best_err = float("inf")
    best_label = "dim_min"

    candidates: list[tuple[float, float, str]] = []
    for delta in np.arange(
        OFFSET_SEARCH_MIN_S, OFFSET_SEARCH_MAX_S + 1e-9, OFFSET_SEARCH_STEP_S
    ):
        for trim in TRIM_CANDIDATES:
            label = f"grid_d{delta:+.2f}_t{trim:.1f}"
            candidates.append((base_offset + float(delta), float(trim), label))

    # Named strategies as grid starting points / fallbacks
    candidates.extend([
        (base_offset, 0.2, "dim_min"),
        (estimate_epoch_offset_bright_first(gaze_df, targets_df), 0.2, "bright_first"),
        (base_offset - 5.0, 0.2, "dim_min_minus_5s"),
    ])

    for offset, trim, label in candidates:
        points = build_calibration_points(gaze_df, targets_df, offset, trim)
        if len(points) < MIN_AFFINE_POINTS:
            continue
        err = mean_pre_fit_error(points)
        if err < best_err:
            best_err = err
            best_offset = offset
            best_trim = trim
            best_label = label

    return best_offset, best_trim, best_label, best_err


def process_trial(trial_id: int) -> dict:
    gaze_df, targets_df = load_trial_data(trial_id)
    if targets_df.empty or len(targets_df) < MIN_AFFINE_POINTS:
        raise ValueError(f"Trial {trial_id}: need at least {MIN_AFFINE_POINTS} target rows.")

    epoch_offset, saccade_trim_s, align_strategy, align_mean_err = optimize_session_alignment(
        gaze_df, targets_df
    )
    screen_width = int(targets_df.iloc[0]["Screen_Width"])
    screen_height = int(targets_df.iloc[0]["Screen_Height"])
    calibration_points = build_calibration_points(
        gaze_df, targets_df, epoch_offset, saccade_trim_s
    )
    if len(calibration_points) < MIN_AFFINE_POINTS:
        raise ValueError(f"Trial {trial_id}: insufficient valid calibration windows.")

    obs_xy = np.array([[p["obs_x_px"], p["obs_y_px"]] for p in calibration_points])
    true_xy = np.array([[p["true_x_px"], p["true_y_px"]] for p in calibration_points])

    return {
        "trial": trial_id,
        "screen_width": screen_width,
        "screen_height": screen_height,
        "epoch_offset": epoch_offset,
        "saccade_trim_s": saccade_trim_s,
        "align_strategy": align_strategy,
        "align_mean_error_px": align_mean_err,
        "n_calibration_points": len(calibration_points),
        "calibration_points": calibration_points,
        "obs_xy": obs_xy,
        "true_xy": true_xy,
    }

    # Start with the simplest observed→true affine transform before adding any outlier handling. This is the core milestone.

def fit_affine_2d(obs_xy: np.ndarray, true_xy: np.ndarray) -> np.ndarray:
    if len(obs_xy) < MIN_AFFINE_POINTS:
        raise ValueError(f"Need at least {MIN_AFFINE_POINTS} point pairs.")
    n = len(obs_xy)
    design = np.column_stack([obs_xy[:, 0], obs_xy[:, 1], np.ones(n)])
    params_x, _, _, _ = np.linalg.lstsq(design, true_xy[:, 0], rcond=None)
    params_y, _, _, _ = np.linalg.lstsq(design, true_xy[:, 1], rcond=None)
    return np.array([
        [params_x[0], params_x[1], params_x[2]],
        [params_y[0], params_y[1], params_y[2]],
        [0.0, 0.0, 1.0],
    ])

def apply_affine_to_points(xy: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.hstack([xy, np.ones((len(xy), 1))]).T
    return (matrix @ homogeneous)[:2].T

def compute_mse_points(true_xy: np.ndarray, pred_xy: np.ndarray) -> float:
    errors = true_xy - pred_xy
    return float(np.mean(np.sum(errors**2, axis=1)))

def is_translation_only(matrix: np.ndarray, tol: float = 1e-6) -> bool:
    return (
        abs(matrix[0, 0] - 1.0) < tol
        and abs(matrix[1, 1] - 1.0) < tol
        and abs(matrix[0, 1]) < tol
        and abs(matrix[1, 0]) < tol
    )

def format_affine_matrix(matrix: np.ndarray) -> str:
    rows = [
        f"[{matrix[0, 0]:8.4f}  {matrix[0, 1]:8.4f}  {matrix[0, 2]:8.2f}]",
        f"[{matrix[1, 0]:8.4f}  {matrix[1, 1]:8.4f}  {matrix[1, 2]:8.2f}]",
        f"[{matrix[2, 0]:8.4f}  {matrix[2, 1]:8.4f}  {matrix[2, 2]:8.4f}]",
    ]
    return "\n".join(f"    {row}" for row in rows)

def design_matrix_condition_number(obs_xy: np.ndarray) -> float:
    """Condition number of the affine design matrix (lower is better)."""
    n = len(obs_xy)
    design = np.column_stack([obs_xy[:, 0], obs_xy[:, 1], np.ones(n)])
    return float(np.linalg.cond(design))

# After the basic affine fit works, make it practical by excluding calibration points that do not agree with the global transform.
def fit_affine_iterative(
    obs_xy: np.ndarray,
    true_xy: np.ndarray,
    calibration_points: list[dict],
    *,
    max_after_error_px: float = MAX_AFTER_ERROR_PX,
    protect_before_px: float = PROTECT_BEFORE_PX,
    protect_max_after_px: float = PROTECT_MAX_AFTER_PX,
) -> tuple[np.ndarray, list[int], list[int], list[str]]:
    """
    Fit affine on all points, then iteratively drop worst post-fit outliers.

    Points with before-error < protect_before_px are kept unless their
    after-error exceeds protect_max_after_px.
    """
    n = len(obs_xy)
    fit_indices = list(range(n))
    exclusion_log: list[str] = ["start: all points in fit set"]

    while len(fit_indices) >= MIN_AFFINE_POINTS:
        obs_fit = obs_xy[fit_indices]
        matrix = fit_affine_2d(obs_fit, true_xy[fit_indices])
        pred_all = apply_affine_to_points(obs_xy, matrix)
        errors = np.sqrt(np.sum((true_xy - pred_all) ** 2, axis=1))

        if all(errors[i] <= max_after_error_px for i in fit_indices):
            break

        # Worst point among current fit set
        worst_i = max(fit_indices, key=lambda i: errors[i])
        worst_err = errors[worst_i]
        worst_before = calibration_points[worst_i]["error_before_px"]
        worst_id = calibration_points[worst_i]["target_id"]

        if worst_err <= max_after_error_px:
            break

        # Protect low-before points unless after-error is clearly bad
        if worst_before < protect_before_px and worst_err < protect_max_after_px:
            exclusion_log.append(
                f"protected ID {worst_id} (before={worst_before:.0f}px, "
                f"after={worst_err:.0f}px)"
            )
            break

        if len(fit_indices) <= MIN_AFFINE_POINTS:
            break

        fit_indices.remove(worst_i)
        exclusion_log.append(
            f"dropped ID {worst_id} (before={worst_before:.0f}px, "
            f"after={worst_err:.0f}px)"
        )

    excluded_indices = [i for i in range(n) if i not in fit_indices]
    final_matrix = fit_affine_2d(obs_xy[fit_indices], true_xy[fit_indices])
    return final_matrix, fit_indices, excluded_indices, exclusion_log


def apply_step2(trial_result: dict) -> dict:
    obs_xy = trial_result["obs_xy"]
    true_xy = trial_result["true_xy"]
    points = trial_result["calibration_points"]

    affine_matrix, fit_indices, excluded_indices, exclusion_log = fit_affine_iterative(
        obs_xy, true_xy, points
    )

    final_fit_mask = np.zeros(len(obs_xy), dtype=bool)
    final_fit_mask[fit_indices] = True

    corrected_xy = apply_affine_to_points(obs_xy, affine_matrix)
    per_point_error = np.sqrt(np.sum((true_xy - corrected_xy) ** 2, axis=1))

    mse_before = compute_mse_points(true_xy, obs_xy)
    mse_after_all = compute_mse_points(true_xy, corrected_xy)
    mse_after_fit = compute_mse_points(true_xy[final_fit_mask], corrected_xy[final_fit_mask])
    mean_err_before_fit = float(np.mean([points[i]["error_before_px"] for i in fit_indices]))
    mean_err_after_fit = float(np.mean(per_point_error[final_fit_mask]))
    worst_fit_idx = max(fit_indices, key=lambda i: per_point_error[i])
    worst_after = float(per_point_error[worst_fit_idx])
    worst_target_id = points[worst_fit_idx]["target_id"]
    cond_num = design_matrix_condition_number(obs_xy[fit_indices])

    exclusion_reasons: dict[int, str] = {}
    for i in excluded_indices:
        p = points[i]
        exclusion_reasons[p["target_id"]] = (
            f"post-fit outlier (before={p['error_before_px']:.0f}px, "
            f"after={per_point_error[i]:.0f}px)"
        )

    corrected_points = []
    for i, (point, corr) in enumerate(zip(points, corrected_xy)):
        corrected_points.append({
            **point,
            "corrected_x_px": float(corr[0]),
            "corrected_y_px": float(corr[1]),
            "error_after_px": float(per_point_error[i]),
            "used_for_fit": i in fit_indices,
            "exclusion_reason": exclusion_reasons.get(point["target_id"], ""),
        })

    return {
        **trial_result,
        "affine_matrix": affine_matrix,
        "corrected_xy": corrected_xy,
        "corrected_points": corrected_points,
        "fit_indices": fit_indices,
        "excluded_indices": excluded_indices,
        "exclusion_log": exclusion_log,
        "exclusion_reasons": exclusion_reasons,
        "fit_method": f"iterative post-fit ({len(fit_indices)} points)",
        "design_condition_number": cond_num,
        "mse_before": mse_before,
        "mse_after": mse_after_all,
        "mse_after_fit_set": mse_after_fit,
        "mean_error_before_fit_set": mean_err_before_fit,
        "mean_error_after_fit_set": mean_err_after_fit,
        "worst_target_id": worst_target_id,
        "worst_after_px": worst_after,
        "is_translation_only": is_translation_only(affine_matrix),
    }
