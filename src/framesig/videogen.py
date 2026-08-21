"""Generate a self-contained synthetic test clip with ffmpeg.

The clip is a fake game HUD painted with solid colour boxes at *known*
timestamps, so tests (and the README demo) have deterministic ground truth to
check the detector against — no external video, model or network required.

Layout (640x360, 15 s, 30 fps, dark-blue base):

  * a red flash across the top HUD area       -> ``death_screen`` (channel_dominance)
  * a red bar in the lower kill-feed band      -> ``kill_feed``     (color_fraction)
  * a white flash on a central screen panel    -> ``white_flash``   (brightness)
  * a hard cut to teal across the whole frame  -> ``scene_cut``     (scene_change)

The four effects occupy disjoint parts of the frame, so each detector sees only
its own event and the ground truth stays clean.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import DependencyError

WIDTH = 640
HEIGHT = 360
FPS = 30
DURATION = 15.0
BASE_COLOR = "0x101828"  # dark blue


@dataclass(frozen=True)
class GroundTruth:
    """The events baked into the synthetic clip, per signature.

    ``intervals`` maps a signature name to the ``(start, end)`` windows during
    which its effect is on screen. ``cuts`` lists the timestamps of hard scene
    cuts (single-frame events).
    """

    intervals: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    cuts: list[float] = field(default_factory=list)

    def expected_counts(self) -> dict[str, int]:
        """Number of distinct events expected for each signature."""
        counts = {name: len(windows) for name, windows in self.intervals.items()}
        counts["scene_cut"] = len(self.cuts)
        return counts


@dataclass(frozen=True)
class SampleVideo:
    """Result of :func:`generate_sample_video`."""

    path: Path
    width: int
    height: int
    fps: int
    duration: float
    ground_truth: GroundTruth


# Ground-truth timings, shared by the ffmpeg filter builder and the tests.
_DEATH = [(2.0, 2.4), (7.5, 7.9)]
_FEED = [(4.0, 4.3), (4.8, 5.0), (9.4, 9.8)]
_WHITE = [(11.0, 11.3)]
_CUT_T = 13.0


def ground_truth() -> GroundTruth:
    """Return the ground-truth events for the synthetic clip."""
    return GroundTruth(
        intervals={
            "death_screen": list(_DEATH),
            "kill_feed": list(_FEED),
            "white_flash": list(_WHITE),
        },
        cuts=[_CUT_T],
    )


def _enable(windows: list[tuple[float, float]]) -> str:
    # between(t,a,b) is inclusive; summing non-overlapping windows acts as OR.
    return "+".join(f"between(t,{a},{b})" for a, b in windows)


def _filtergraph() -> str:
    # Disjoint boxes; single-quoted enable values keep their commas literal.
    death = (
        f"drawbox=x=0:y=0:w={WIDTH}:h={int(HEIGHT * 0.55)}:color=red:t=fill:"
        f"enable='{_enable(_DEATH)}'"
    )
    feed = (
        f"drawbox=x={int(WIDTH * 0.08)}:y={int(HEIGHT * 0.74)}:"
        f"w={int(WIDTH * 0.84)}:h={int(HEIGHT * 0.18)}:color=red:t=fill:"
        f"enable='{_enable(_FEED)}'"
    )
    white = (
        f"drawbox=x={int(WIDTH * 0.30)}:y={int(HEIGHT * 0.58)}:"
        f"w={int(WIDTH * 0.40)}:h={int(HEIGHT * 0.12)}:color=white:t=fill:"
        f"enable='{_enable(_WHITE)}'"
    )
    cut = (
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=0x18A060:t=fill:"
        f"enable='gte(t,{_CUT_T})'"
    )
    return ",".join([death, feed, white, cut])


def generate_sample_video(
    out_path: str | Path, *, ffmpeg: str = "ffmpeg", overwrite: bool = True
) -> SampleVideo:
    """Render the synthetic HUD clip to ``out_path`` using ffmpeg.

    Args:
        out_path: Destination ``.mp4`` file.
        ffmpeg: Name or path of the ffmpeg binary.
        overwrite: Overwrite an existing file (passes ``-y``).

    Returns:
        A :class:`SampleVideo` describing the file and its ground truth.

    Raises:
        DependencyError: If the ffmpeg binary is not on ``PATH`` or ffmpeg fails.
    """
    binary = shutil.which(ffmpeg)
    if binary is None:
        raise DependencyError(
            f"ffmpeg binary {ffmpeg!r} not found on PATH; install ffmpeg to "
            f"generate the sample clip"
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        binary,
        "-y" if overwrite else "-n",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={BASE_COLOR}:s={WIDTH}x{HEIGHT}:r={FPS}:d={DURATION}",
        "-vf",
        _filtergraph(),
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise DependencyError(
            f"ffmpeg failed to render the sample clip (exit {proc.returncode}):\n"
            f"{proc.stderr.strip()}"
        )

    return SampleVideo(
        path=out,
        width=WIDTH,
        height=HEIGHT,
        fps=FPS,
        duration=DURATION,
        ground_truth=ground_truth(),
    )
