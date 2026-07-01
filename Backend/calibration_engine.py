"""
Backend calibration engine — Step 1: load and synchronize ground-truth targets
with observed Tobii gaze samples.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Trim initial saccadic latency after the bright target appears (seconds).
SACCADIC_LATENCY_OFFSET_S = 0.200

GROUND_TRUTH_COLUMNS = (
    "Bright_Timestamp_Start",
    "Bright_Timestamp_End",
    "Target_ID",
    "Target_X_Px",
    "Target_Y_Px",
)
GAZE_COLUMNS = ("Timestamp", "Gaze_X", "Gaze_Y")


def load_ground_truth(csv_path: str | Path) -> pd.DataFrame:
    """Load the calibration_targets CSV produced by the frontend app."""
    df = pd.read_csv(csv_path)
    missing = [col for col in GROUND_TRUTH_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Ground-truth CSV is missing required columns: {missing}")
    return df


def load_observed_gaze(csv_path: str | Path) -> pd.DataFrame:
    """
    Load the continuous Tobii gaze stream.

    Coordinates use a top-left origin [0, 0]; the Y-axis is not inverted.
    """
    df = pd.read_csv(csv_path)
    missing = [col for col in GAZE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Gaze CSV is missing required columns: {missing}")
    return df.sort_values("Timestamp").reset_index(drop=True)


def synchronize_calibration_pairs(
    ground_truth: pd.DataFrame,
    gaze: pd.DataFrame,
    latency_offset_s: float = SACCADIC_LATENCY_OFFSET_S,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Pair each ground-truth target with the median observed gaze in its bright window.

    Returns
    -------
    true_targets : ndarray, shape (N, 2)
        [Target_X_Px, Target_Y_Px] for each target (CSV row order).
    observed_gaze : ndarray, shape (N, 2)
        [median Gaze_X, median Gaze_Y] for the matching gaze window.
    """
    true_targets: list[list[float]] = []
    observed_gaze: list[list[float]] = []

    for _, target in ground_truth.iterrows():
        window_start = target["Bright_Timestamp_Start"] + latency_offset_s
        window_end = target["Bright_Timestamp_End"]

        in_window = (gaze["Timestamp"] >= window_start) & (
            gaze["Timestamp"] <= window_end
        )
        window_samples = gaze.loc[in_window, ["Gaze_X", "Gaze_Y"]].dropna()

        if window_samples.empty:
            raise ValueError(
                f"No valid gaze samples for Target_ID={target['Target_ID']} "
                f"in window [{window_start:.6f}, {window_end:.6f}] s."
            )

        true_targets.append(
            [float(target["Target_X_Px"]), float(target["Target_Y_Px"])]
        )
        observed_gaze.append(
            [
                float(window_samples["Gaze_X"].median()),
                float(window_samples["Gaze_Y"].median()),
            ]
        )

    return np.asarray(true_targets, dtype=float), np.asarray(observed_gaze, dtype=float)


def run_step1(
    ground_truth_path: str | Path,
    gaze_path: str | Path,
    latency_offset_s: float = SACCADIC_LATENCY_OFFSET_S,
) -> tuple[np.ndarray, np.ndarray]:
    """Load both CSVs and return paired true-target / observed-gaze arrays."""
    ground_truth = load_ground_truth(ground_truth_path)
    gaze = load_observed_gaze(gaze_path)
    return synchronize_calibration_pairs(
        ground_truth, gaze, latency_offset_s=latency_offset_s
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 1: synchronize ground-truth targets with Tobii gaze."
    )
    parser.add_argument(
        "ground_truth_csv",
        type=Path,
        help="Path to calibration_targets.csv",
    )
    parser.add_argument(
        "gaze_csv",
        type=Path,
        help="Path to tobii_rawtopleftcorner.csv",
    )
    parser.add_argument(
        "--latency-offset",
        type=float,
        default=SACCADIC_LATENCY_OFFSET_S,
        help="Seconds added to Bright_Timestamp_Start before slicing gaze.",
    )
    args = parser.parse_args()

    true_pts, observed_pts = run_step1(
        args.ground_truth_csv,
        args.gaze_csv,
        latency_offset_s=args.latency_offset,
    )

    print(f"Paired {len(true_pts)} targets.\n")
    print("True targets (px):")
    print(true_pts)
    print("\nObserved gaze medians:")
    print(observed_pts)
