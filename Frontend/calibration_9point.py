"""
9-point eye-tracker calibration prototype (PsychoPy).
"""

from __future__ import annotations

import csv
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from psychopy import core, event, visual


# All paths relative to this script's directory (Frontend/)
FRONTEND_DIR = Path(__file__).resolve().parent


def enable_windows_dpi_awareness() -> None:
    """Use physical pixels on scaled Windows displays (e.g. HP EliteBook at 125%)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # 2 = PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Configuration

BRIGHT_DURATION_S = 2.0  # seconds the bright target stays on after confirmation
AUTO_DIM_WAIT_S = 0.3    # --auto mode: dim phase before auto-confirming each target
RANDOM_SEED = None
PRE_TARGET_BLANK_S = 0.3
INTER_TARGET_BLANK_S = 0.5  # blank between targets — time to find the next one
EDGE_INSET_FRACTION = 0.30
SHOW_CIRCLES = False  # False = no shrinking ring; center dot + crosshairs always shown
SCREEN_INDEX = 0      # default screen index (0 = primary, 1 = secondary, etc.)

DOT_RADIUS_PX = 15
CROSSHAIR_ARM_PX = 32
CROSSHAIR_LINE_WIDTH_PX = 3  # thicker lines improve visibility on Retina/high-DPI
RING_START_RADIUS_PX = 48
RING_END_RADIUS_PX = DOT_RADIUS_PX + 2
RING_LINE_WIDTH_PX = 2

TARGET_COLOR = [1, 1, 1]         # bright white (PsychoPy rgb: -1..1)
DIM_COLOR = [0.25, 0.25, 0.25]   # dim grey — visible but clearly not recording yet
BACKGROUND_COLOR = [-1, -1, -1]  # black — [-1,-1,-1] in rgb is mid-grey
TARGET_CONFIRM_KEY = "space"
JOYSTICK_INDEX = 0           # default joystick device index
JOYSTICK_CONFIRM_BUTTON = 0  # button index for click (0 = typical trigger)

TEXT_HEIGHT_PX = 28
TEXT_WRAP_FRACTION = 0.75
PROMPT_COLOR = [0.7, 0.7, 0.7]


def build_confirm_prompt(use_joystick: bool) -> str:
    if use_joystick:
        return "Press the joystick button or SPACEBAR"
    return "Press SPACEBAR"


def build_instructions_text(use_joystick: bool) -> str:
    confirm = build_confirm_prompt(use_joystick)
    return (
        "Eye-tracker calibration\n\n"
        "1. A dim dot will appear.\n"
        "2. Look at the center of the dot.\n"
        f"3. {confirm} when you are ready.\n"
        "4. The dot will turn bright for 2 seconds. Keep looking at it.\n\n"
        f"{confirm} to begin."
    )


def build_dim_prompt_text(use_joystick: bool) -> str:
    return f"Look at the dot, then {build_confirm_prompt(use_joystick).lower()}"

OUTPUT_BASENAME = "calibration_targets"
CSV_HEADERS = [
    "Dim_Timestamp_Start",
    "Dim_Timestamp_End",
    "Bright_Timestamp_Start",
    "Bright_Timestamp_End",
    "Target_ID",
    "Target_X_Px",
    "Target_Y_Px",
    "Screen_Width",
    "Screen_Height",
]


def build_output_filename() -> str:
    """UTC date-time to the millisecond, filesystem-safe (e.g. ..._2026-06-29T14-30-45-123Z.csv)."""
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    ms = now.microsecond // 1000
    return f"{OUTPUT_BASENAME}_{stamp}-{ms:03d}Z.csv"


def generate_grid_targets(screen_width: int, screen_height: int) -> list[dict]:
    """Build a 3×3 grid with equal pixel spacing on both axes (Target_ID 1–9, row-major)."""
    inset = EDGE_INSET_FRACTION
    center_x = screen_width / 2.0
    center_y = screen_height / 2.0

    # Spacing between adjacent dots, derived from vertical edge inset (EDGE_INSET_FRACTION).
    step = center_y - (inset * screen_height)
    step = min(step, center_x, screen_width - center_x)

    x_px_values = [
        int(round(center_x - step)),
        int(round(center_x)),
        int(round(center_x + step)),
    ]
    y_px_values = [
        int(round(center_y - step)),
        int(round(center_y)),
        int(round(center_y + step)),
    ]

    targets: list[dict] = []
    target_id = 1
    for y_px in y_px_values:
        for x_px in x_px_values:
            pos_x = x_px - center_x
            pos_y = center_y - y_px
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
        units="pix",
    )
    cross_h = visual.Line(
        win,
        start=(-CROSSHAIR_ARM_PX, 0),
        end=(CROSSHAIR_ARM_PX, 0),
        pos=(0, 0),
        lineColor=TARGET_COLOR,
        lineWidth=CROSSHAIR_LINE_WIDTH_PX,
        units="pix",
    )
    cross_v = visual.Line(
        win,
        start=(0, -CROSSHAIR_ARM_PX),
        end=(0, CROSSHAIR_ARM_PX),
        pos=(0, 0),
        lineColor=TARGET_COLOR,
        lineWidth=CROSSHAIR_LINE_WIDTH_PX,
        units="pix",
    )
    ring = visual.Circle(
        win,
        radius=RING_START_RADIUS_PX,
        pos=(0, 0),
        fillColor=None,
        lineColor=TARGET_COLOR,
        lineWidth=RING_LINE_WIDTH_PX,
        units="pix",
    )
    return {"dot": dot, "cross_h": cross_h, "cross_v": cross_v, "ring": ring}


def set_bullseye_position(stimuli: dict, position: tuple[float, float]) -> None:
    for stim in stimuli.values():
        stim.pos = position


def set_bullseye_color(stimuli: dict, color: list[float]) -> None:
    stimuli["dot"].setFillColor(color, colorSpace="rgb")
    stimuli["dot"].setLineColor(color, colorSpace="rgb")
    stimuli["cross_h"].setLineColor(color, colorSpace="rgb")
    stimuli["cross_v"].setLineColor(color, colorSpace="rgb")
    stimuli["ring"].setLineColor(color, colorSpace="rgb")


def circles_enabled() -> bool:
    if "--no-circles" in sys.argv:
        return False
    return SHOW_CIRCLES


def unix_epoch_offset() -> float:
    """Map PsychoPy monotonic flip times to Unix epoch seconds."""
    return time.time() - core.getTime()


def flip_to_unix_time(flip_time: float, epoch_offset: float) -> float:
    return epoch_offset + flip_time


def make_screen_text(
    win: visual.Window,
    text: str,
    screen_width: int,
    *,
    color: list[float] | None = None,
    pos: tuple[float, float] = (0, 0),
) -> visual.TextStim:
    return visual.TextStim(
        win,
        text=text,
        color=color if color is not None else TARGET_COLOR,
        height=TEXT_HEIGHT_PX,
        wrapWidth=screen_width * TEXT_WRAP_FRACTION,
        units="pix",
        pos=pos,
        alignText="center",
        anchorHoriz="center",
        anchorVert="center",
    )


def poll_keys(*allowed: str) -> list[str]:
    """Return pressed keys once per frame (PsychoPy clears the queue on each call)."""
    if allowed:
        return event.getKeys(keyList=list(allowed))
    return event.getKeys()


def abort_if_escape(keys: list[str]) -> None:
    if "escape" in keys:
        raise KeyboardInterrupt("Calibration aborted by user (ESC).")


def confirm_key_pressed(keys: list[str]) -> bool:
    return TARGET_CONFIRM_KEY in keys


class ConfirmDevice:
    """Participant confirm input: joystick button (default) or keyboard fallback."""

    def __init__(
        self,
        *,
        use_joystick: bool,
        joystick=None,
        button_id: int = JOYSTICK_CONFIRM_BUTTON,
    ) -> None:
        self.use_joystick = use_joystick
        self.joystick = joystick
        self.button_id = button_id
        self._button_was_down = False

    @property
    def label(self) -> str:
        if self.use_joystick:
            return f"joystick button {self.button_id} or SPACEBAR"
        return "SPACEBAR"

    def sync_button_state(self) -> None:
        """Track current button state so a held click does not re-trigger."""
        if self.use_joystick and self.joystick is not None:
            self._button_was_down = bool(self.joystick.getButton(self.button_id))
        else:
            self._button_was_down = False

    def reset(self) -> None:
        event.clearEvents(eventType="keyboard")
        self.sync_button_state()

    def poll(self) -> tuple[list[str], bool]:
        """Poll ESC and confirm input once per frame."""
        keys = poll_keys("escape", TARGET_CONFIRM_KEY)
        keyboard_confirmed = confirm_key_pressed(keys)

        if self.use_joystick and self.joystick is not None:
            pressed = bool(self.joystick.getButton(self.button_id))
            joystick_confirmed = pressed and not self._button_was_down
            self._button_was_down = pressed
            return keys, joystick_confirmed or keyboard_confirmed

        return keys, keyboard_confirmed


def draw_bullseye(
    stimuli: dict,
    progress_text: visual.TextStim | None = None,
    *,
    show_circles: bool = True,
) -> None:
    if show_circles:
        stimuli["ring"].draw()
    stimuli["cross_h"].draw()
    stimuli["cross_v"].draw()
    stimuli["dot"].draw()
    if progress_text is not None:
        progress_text.draw()


def wait_for_confirm(
    win: visual.Window,
    message: str,
    screen_width: int,
    confirm_device: ConfirmDevice,
) -> None:
    text_stim = make_screen_text(win, message, screen_width)
    confirm_device.reset()
    while True:
        text_stim.draw()
        win.flip()
        keys, confirmed = confirm_device.poll()
        abort_if_escape(keys)
        if confirmed:
            confirm_device.reset()
            break


def get_screen_index() -> int:
    """Resolve the screen index from CLI arguments, environment variables, or config."""
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--screen="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == "--screen" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
    env_val = os.environ.get("CALIBRATION_SCREEN") or os.environ.get("SCREEN")
    if env_val is not None:
        try:
            return int(env_val)
        except ValueError:
            pass
    return SCREEN_INDEX


def parse_int_cli(flag: str, default: int) -> int:
    """Parse ``--flag N`` or ``--flag=N`` from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg.startswith(f"{flag}="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == flag and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
    return default


def use_keyboard_input() -> bool:
    return "--keyboard" in sys.argv


def get_joystick_index() -> int:
    env_val = os.environ.get("CALIBRATION_JOYSTICK") or os.environ.get("JOYSTICK_INDEX")
    if env_val is not None:
        try:
            return int(env_val)
        except ValueError:
            pass
    return parse_int_cli("--joystick", parse_int_cli("--joystick-index", JOYSTICK_INDEX))


def get_joystick_button() -> int:
    env_val = os.environ.get("CALIBRATION_JOYSTICK_BUTTON") or os.environ.get("JOYSTICK_BUTTON")
    if env_val is not None:
        try:
            return int(env_val)
        except ValueError:
            pass
    return parse_int_cli("--joystick-button", JOYSTICK_CONFIRM_BUTTON)


def create_confirm_device() -> ConfirmDevice:
    if use_keyboard_input():
        print("Confirm input: SPACEBAR (--keyboard)")
        return ConfirmDevice(use_joystick=False)

    from psychopy.hardware import joystick

    num_joysticks = joystick.getNumJoysticks()
    if num_joysticks == 0:
        print("No joystick connected. Using SPACEBAR for confirm.")
        return ConfirmDevice(use_joystick=False)

    index = get_joystick_index()
    button_id = get_joystick_button()
    if index < 0 or index >= num_joysticks:
        print(
            f"Warning: joystick index {index} is not available "
            f"({num_joysticks} device(s) connected). Falling back to SPACEBAR."
        )
        return ConfirmDevice(use_joystick=False)

    try:
        joy = joystick.Joystick(index)
        name = getattr(joy, "name", None) or f"joystick {index}"
        num_buttons = joy.getNumButtons()
        if button_id < 0 or button_id >= num_buttons:
            raise ValueError(
                f"Button {button_id} out of range; joystick has {num_buttons} button(s) (0–{num_buttons - 1})"
            )
        print(
            f"Confirm input: {name}, button {button_id} "
            f"({num_buttons} button(s) total); SPACEBAR accepted as secondary"
        )
        return ConfirmDevice(use_joystick=True, joystick=joy, button_id=button_id)
    except Exception as exc:
        print(f"Warning: could not open joystick {index} ({exc}). Falling back to SPACEBAR.")
        return ConfirmDevice(use_joystick=False)


def create_calibration_window() -> visual.Window:
    """Open a fullscreen window with platform-appropriate display settings."""
    screen_idx = get_screen_index()
    print(f"Opening window on screen {screen_idx}")
    return visual.Window(
        fullscr=True,
        units="pix",
        useRetina=sys.platform == "darwin",
        color=BACKGROUND_COLOR,
        colorSpace="rgb",
        allowGUI=False,
        screen=screen_idx,
    )


def resolve_window_size(win: visual.Window) -> tuple[int, int]:
    """
    Drawable pixel dimensions for units='pix'.

    macOS Retina: win.size can be 2× the logical coordinate space.
    Windows/Linux: win.size matches the drawable pixel coordinate space.
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


def wait_blank_interval(win: visual.Window, duration_s: float) -> None:
    if duration_s <= 0:
        return
    clock = core.Clock()
    while clock.getTime() < duration_s:
        win.flip()
        keys = poll_keys("escape")
        abort_if_escape(keys)


def wait_for_target_confirm(
    win: visual.Window,
    stimuli: dict,
    target: dict,
    progress_text: visual.TextStim | None,
    *,
    show_circles: bool = True,
    auto_confirm_after_s: float | None = None,
    dim_prompt_text: visual.TextStim | None = None,
    epoch_offset: float,
    confirm_device: ConfirmDevice,
) -> tuple[float, float]:
    """Show a dim target until confirm; return vsync times for the dim phase."""
    set_bullseye_position(stimuli, target["pos"])
    set_bullseye_color(stimuli, DIM_COLOR)
    if show_circles:
        stimuli["ring"].radius = RING_START_RADIUS_PX

    confirm_device.reset()
    clock = core.Clock()
    dim_start: float | None = None
    dim_end: float | None = None
    while True:
        draw_bullseye(stimuli, progress_text, show_circles=show_circles)
        if dim_prompt_text is not None:
            dim_prompt_text.draw()
        flip_time = win.flip()
        if flip_time is None:
            flip_time = core.getTime()
        flip_unix = flip_to_unix_time(flip_time, epoch_offset)
        if dim_start is None:
            dim_start = flip_unix
        dim_end = flip_unix
        keys, confirmed = confirm_device.poll()
        abort_if_escape(keys)
        if auto_confirm_after_s is not None and clock.getTime() >= auto_confirm_after_s:
            break
        if confirmed:
            confirm_device.reset()
            break

    if dim_start is None or dim_end is None:
        raise RuntimeError("Dim target was not displayed (no vsync flip recorded).")

    return dim_start, dim_end


def present_shrinking_bullseye(
    win: visual.Window,
    stimuli: dict,
    target: dict,
    progress_text: visual.TextStim | None,
    duration_s: float = BRIGHT_DURATION_S,
    *,
    show_circles: bool = True,
    epoch_offset: float,
    auto_confirm_after_s: float | None = None,
    dim_prompt_text: visual.TextStim | None = None,
    confirm_device: ConfirmDevice,
) -> tuple[float, float, float, float]:
    dim_start, dim_end = wait_for_target_confirm(
        win,
        stimuli,
        target,
        progress_text,
        show_circles=show_circles,
        auto_confirm_after_s=auto_confirm_after_s,
        dim_prompt_text=dim_prompt_text,
        epoch_offset=epoch_offset,
        confirm_device=confirm_device,
    )

    ring = stimuli["ring"]
    set_bullseye_color(stimuli, TARGET_COLOR)
    if show_circles:
        ring.radius = RING_START_RADIUS_PX

    clock = core.Clock()
    bright_start: float | None = None
    bright_end: float | None = None

    while clock.getTime() < duration_s:
        if show_circles:
            progress = min(clock.getTime() / duration_s, 1.0)
            ring.radius = RING_START_RADIUS_PX + (
                RING_END_RADIUS_PX - RING_START_RADIUS_PX
            ) * progress
        draw_bullseye(stimuli, progress_text, show_circles=show_circles)
        flip_time = win.flip()
        if flip_time is None:
            flip_time = core.getTime()
        flip_unix = flip_to_unix_time(flip_time, epoch_offset)
        if bright_start is None:
            bright_start = flip_unix
        bright_end = flip_unix
        keys = poll_keys("escape")
        abort_if_escape(keys)

    if bright_start is None or bright_end is None:
        raise RuntimeError("Bright target was not displayed (no vsync flip recorded).")

    return dim_start, dim_end, bright_start, bright_end


def save_calibration_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def run_calibration() -> Path:
    output_path = FRONTEND_DIR / "calibration_output" / build_output_filename()

    enable_windows_dpi_awareness()
    print(f"Platform: {sys.platform}")
    print(f"Output file: {output_path}")

    win = create_calibration_window()

    rows: list[dict] = []

    try:
        screen_width, screen_height = resolve_window_size(win)
        fb_w, fb_h = int(round(win.size[0])), int(round(win.size[1]))
        print(
            f"Calibration display size: {screen_width} x {screen_height} px "
            f"(framebuffer {fb_w} x {fb_h}, retina={sys.platform == 'darwin'})"
        )

        bullseye = build_bullseye_stimuli(win)
        confirm_device = create_confirm_device()

        auto_mode = "--auto" in sys.argv
        show_circles = circles_enabled()
        auto_confirm_after_s = AUTO_DIM_WAIT_S if auto_mode else None
        dim_prompt_text = None
        if not auto_mode:
            dim_prompt_text = make_screen_text(
                win,
                build_dim_prompt_text(confirm_device.use_joystick),
                screen_width,
                color=PROMPT_COLOR,
                pos=(0, -(screen_height / 2.0) + 56),
            )
        print(f"Show circles: {show_circles}")
        print(
            f"Gated targets: dim until "
            f"{'auto-confirm' if auto_mode else confirm_device.label}, "
            f"then bright for {BRIGHT_DURATION_S}s"
        )
        if auto_mode:
            print("Auto mode: skipping instructions and exit prompt.")
            event.clearEvents(eventType="keyboard")
        else:
            wait_for_confirm(
                win,
                build_instructions_text(confirm_device.use_joystick),
                screen_width,
                confirm_device,
            )

        targets = generate_grid_targets(screen_width, screen_height)
        if len(targets) != 9:
            raise RuntimeError(f"Expected 9 calibration targets, got {len(targets)}")

        presentation_order = targets.copy()
        if RANDOM_SEED is not None:
            random.seed(RANDOM_SEED)
        random.shuffle(presentation_order)
        print("Presentation order (Target_ID):", [t["Target_ID"] for t in presentation_order])

        wait_blank_interval(win, PRE_TARGET_BLANK_S)

        epoch_offset = unix_epoch_offset()
        print("Timestamps: vsync flip times converted to Unix epoch seconds")

        total_targets = len(presentation_order)
        for index, target in enumerate(presentation_order):
            dim_start, dim_end, bright_start, bright_end = present_shrinking_bullseye(
                win,
                bullseye,
                target,
                None,
                show_circles=show_circles,
                epoch_offset=epoch_offset,
                auto_confirm_after_s=auto_confirm_after_s,
                dim_prompt_text=dim_prompt_text,
                confirm_device=confirm_device,
            )

            rows.append(
                {
                    "Dim_Timestamp_Start": f"{dim_start:.6f}",
                    "Dim_Timestamp_End": f"{dim_end:.6f}",
                    "Bright_Timestamp_Start": f"{bright_start:.6f}",
                    "Bright_Timestamp_End": f"{bright_end:.6f}",
                    "Target_ID": target["Target_ID"],
                    "Target_X_Px": target["Target_X_Px"],
                    "Target_Y_Px": target["Target_Y_Px"],
                    "Screen_Width": screen_width,
                    "Screen_Height": screen_height,
                }
            )
            print(
                f"Logged target {index + 1}/{total_targets} "
                f"(ID={target['Target_ID']}, x={target['Target_X_Px']}, y={target['Target_Y_Px']}, "
                f"dim {dim_start:.6f}–{dim_end:.6f}, "
                f"bright {bright_start:.6f}–{bright_end:.6f})"
            )

            if index < total_targets - 1:
                wait_blank_interval(win, INTER_TARGET_BLANK_S)

        done_text = make_screen_text(
            win,
            "Calibration complete.\n\nPress any key to exit.",
            screen_width,
        )
        event.clearEvents(eventType="keyboard")
        done_text.draw()
        win.flip()
        if not auto_mode:
            event.waitKeys()

    finally:
        if rows:
            save_calibration_csv(rows, output_path)
            print(f"Saved {len(rows)} calibration target(s) to {output_path}")
        win.close()
        core.quit()

    return output_path


def main() -> int:
    try:
        output_path = run_calibration()
        print(f"Calibration finished. Data saved to: {output_path}")
        return 0
    except KeyboardInterrupt:
        print("\nCalibration aborted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nCalibration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
