"""
9-point eye-tracker calibration prototype (PsychoPy).

Output: output/calibratio_targets.csv
"""

from __future__ import annotations

import csv
import random 
import sys
import time
from pathlib import Path
from turtle import position

from psychopy import core, event, visual 

# Project root is one level up from calibration/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configuration 

TARGET_DURATION_S = 1.0
RANDOM_SEED = 42
PRE_TARGET_BLANK_S = 0.3
INTER_TARGET_BLANK_S = 0.3
EDGE_INSET_FRACTION = 0.10

DOT_RADIUS_PX = 4
CROSSHAIR_ARM_PX = 24
CROSSHAIR_LINE_WIDTH_PX = 1
RING_START_RADIUS_PX = 48
RING_END_RADIUS_PX = DOT_RADIUS_PX + 2
RING_LINE_WIDTH_PX = 2

TARGET_COLOR = [1, 1, 1]
BACKGROUND_COLOR = [0, 0, 0]

INSTRUCTIONS_TEXT = (
    "Please focus your gaze precisely on the center of each dotas it appears.\n\n"
    "Press the SPACEBAR to begin."
)

OUTPUT_FILENAME = "calibration_targets.csv"
CSV_HEADERS = [
    "Timestamp_Start",
    "Timestamp_End",
    "Target_ID",
    "Target_X_Px",
    "Target_Y_Px",
    "Screen_Width",
    "Screen_Height",

]

def generate_grid_targets(screen_width: int, screen_height: int) -> list[dict]:
    """Build a 3×3 grid; Target_ID 1–9 in row-major order (top-left → bottom-right)."""
    inset = EDGE_INSET_FRACTION
    fractions = [inset, 0.5, 1.0 - inset]

    targets: list[dict] = []
    target_id = 1
    for y_frac in fractions:
        for x_frac in fractions:
            x_px = int(round(x_frac * screen_width))
            y_px = int(round(y_frac * screen_height))
            pos_x = x_px - (screen_width / 2.0)
            pos_y = (screen_height / 2.0) - y_px
            targets.append(
                {
                    "Target_ID": target_id,
                    "Target_X_Px": x_px,
                    "Target_Y_Px": y_px,
                    "pos": (pos_x, pos_y),
                }
            )
            target_id += 1

    return targets

 def build_bullseye_stimuli(win: visual.Window) -> dict:
    dot = visual.Circle(
        win,   
        radius=DOT_RADIUS_PX,
        pos=(0, 0),
        fillColor=TARGET_COLOR,
        lineColor=TARGET_COLOR,
        unit="pix",
    )
    cross_h = visual.Line(
        win,
        start=(-CROSSHAIR_ARM_PX, 0),
        end=(CROSSHAIR_ARM_PX, 0),
        pos=(0, 0),
        lineColor=TARGET_COLOR,
        lineWidth=CROSSHAIR_LINE_WIDTH_PX,
        unit="pix",
    )
    cross_v = visual.Line(
        win,
        start=(0, -CROSSHAIR_ARM_PX),
        end=(0, CROSSHAIR_ARM_PX),
        pos=(0, 0),
        lineColor=TARGET_COLOR,
        lineWidth=CROSSHAIR_LINE_WIDTH_PX,
        unit="pix",
    )
    ring = visual.Circle(
        win,
        radius=RING_START_RADIUS_PX,
        pos=(0, 0),
        fillColor=None,
        lineColor=TARGET_COLOR,
        lineWidth=RING_LINE_WIDTH_PX,
        unit="pix",
    )
    return {"dot": dot, "cross_h": cross_h, "cross_v": cross_v, "ring": ring}

def set_bullseye_position(stimuli: dict, pos: tuple[float, float]) -> None:
    for stim in stimuli.values():
        stim.pos = position 

def draw_bullseye(stimuli: dict, progress_text: visual.TextStim | None = None) -> None:
    stimuli["dot"].draw()
    stimuli["cross_h"].draw()
    stimuli["cross_v"].draw()
    stimuli["dot"].draw()
   if progress_text is not None:
        progress_text.draw()

def wait_for_spacebar(win: visual.Window, message: str) -> None:
    text_stim = visual.TextStim(
    win, 
    text=message, 
    color=TARGET_COLOR
    height=28,
    wrapWidth=win.size[0] * 0.75,
    units="pix",
    )
    event.clearEvents()
    while True:
        if "escape" in event.getKeys():
            raise KeyboardInterrupt("Calibration aborted by user (ESC).")     
        texrt_stim.draw()
        win.flip()
        if event.getKeys(keyList=["space"]):
            event.clearEvents(eventType="keyboard")
            break

def resolve_window_size(win: visual.Window) -> tuple[int, int]:
  """
  Drawable Pixel dimesions for units='pix.
  On macOS Retina, win.size is 2x the coordinate space used for drawing.
  """
  win.flip()
  fb_w, fb_h = float(win.size[0]), float(win.size[1])
  try:
      logical_w = float(win.winHandle.screen.width)
      logical_h = float(win.winHandle.screen.height)
  except Exception:
      return int(round(fb_w)), int(round(fb_h))
  
  if sys.platform == "darwin" and win.useRetina:
      if abs(fb_w - logical_w * 2) < 2 and abs(fb_h - logical_h * 2) < 2:
          return int(round(logical_w)), int(round(logical_h))
      
    return int(round(fb_w)), int(round(fb_h))