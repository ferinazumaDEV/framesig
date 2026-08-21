"""Render a score-timeline chart, using only OpenCV (no plotting dependency).

Given a :class:`~framesig.scanner.ScanResult` and the detected events, this draws
one stacked lane per signature: the score curve, its threshold line, and shaded
bands where events fired. It is handy for tuning thresholds by eye and for the
project's README image.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .config import Config
from .events import Event
from .scanner import ScanResult

# Colours are BGR (OpenCV order).
_BG = (24, 20, 16)
_PANEL = (34, 30, 26)
_GRID = (60, 54, 48)
_TEXT = (210, 210, 210)
_MUTED = (140, 140, 140)
_CURVE = (235, 180, 90)
_THRESH = (110, 110, 235)
_EVENT = (90, 205, 120)


def render_timeline(
    config: Config,
    result: ScanResult,
    events: dict[str, list[Event]],
    out_path: str | Path,
    *,
    width: int = 1040,
    lane_height: int = 118,
) -> Path:
    """Render the score timelines to a PNG and return its path."""
    signatures = config.signatures
    pad_l, pad_r, pad_t, pad_b = 150, 24, 54, 40
    plot_w = width - pad_l - pad_r
    height = pad_t + pad_b + lane_height * len(signatures)

    img = np.full((height, width, 3), _BG, dtype=np.uint8)
    duration = max(result.meta.get("duration", 0.0), 1e-6)
    ts = result.timestamps

    def x_of(t: float) -> int:
        return int(pad_l + (t / duration) * plot_w)

    _text(img, "framesig  score timelines", (pad_l, 34), 0.72, _TEXT, 2)

    for lane, sig in enumerate(signatures):
        top = pad_t + lane * lane_height
        bottom = top + lane_height - 26
        cv2.rectangle(img, (pad_l, top), (pad_l + plot_w, bottom), _PANEL, -1)

        # Horizontal grid at score 0, 0.5, 1.0.
        for frac in (0.0, 0.5, 1.0):
            y = int(bottom - frac * (bottom - top))
            cv2.line(img, (pad_l, y), (pad_l + plot_w, y), _GRID, 1)

        # Shade detected event spans.
        for ev in events.get(sig.name, []):
            x0, x1 = x_of(ev.start), max(x_of(ev.end), x_of(ev.start) + 2)
            overlay = img.copy()
            cv2.rectangle(overlay, (x0, top), (x1, bottom), _EVENT, -1)
            cv2.addWeighted(overlay, 0.22, img, 0.78, 0, img)
            cv2.line(img, (x_of(ev.peak_t), top), (x_of(ev.peak_t), bottom), _EVENT, 1)

        # Threshold line.
        yt = int(bottom - sig.threshold * (bottom - top))
        for xd in range(pad_l, pad_l + plot_w, 10):
            cv2.line(img, (xd, yt), (xd + 5, yt), _THRESH, 1)

        # Score curve.
        scores = result.scores.get(sig.name, [])
        pts = [
            (x_of(t), int(bottom - min(max(s, 0.0), 1.0) * (bottom - top)))
            for t, s in zip(ts, scores)
        ]
        if len(pts) >= 2:
            cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, _CURVE, 2, cv2.LINE_AA)

        n = len(events.get(sig.name, []))
        _text(img, sig.name, (16, top + 26), 0.56, _TEXT, 1)
        _text(img, f"{sig.detector.type_name}", (16, top + 48), 0.44, _MUTED, 1)
        _text(img, f"thr {sig.threshold:g}", (16, top + 68), 0.44, _THRESH, 1)
        _text(img, f"{n} event{'s' if n != 1 else ''}", (16, top + 88), 0.44, _EVENT, 1)

    # Time axis ticks.
    axis_y = height - pad_b + 16
    for k in range(0, int(duration) + 1, 2):
        x = x_of(k)
        cv2.line(img, (x, pad_t - 6), (x, height - pad_b), _GRID, 1)
        _text(img, f"{k}s", (x - 8, axis_y), 0.42, _MUTED, 1)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), img):
        raise OSError(f"failed to write chart image to {str(out)!r}")
    return out


def _text(img: np.ndarray, s: str, org: tuple[int, int], scale: float, color, thick: int) -> None:
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
