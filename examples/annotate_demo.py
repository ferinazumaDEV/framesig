"""Overlay framesig's regions and live detections onto a video.

A small, self-contained example of using the framesig API programmatically. It
scans a video, then re-reads it frame by frame and draws:

  * every region of interest as a labelled rectangle, and
  * a highlight + banner whenever a signature is firing at that instant.

The result is written as an ``.mp4`` (via OpenCV). This is what the project's
demo GIF is rendered from.

Usage:
    python examples/annotate_demo.py sample.mp4 -c examples/flash.yaml -o annotated.mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from framesig import detect_all, load_config, scan_video
from framesig.events import Event

# One BGR colour per signature (extend as needed).
PALETTE = [
    (90, 205, 120),   # green
    (235, 180, 90),   # blue
    (110, 110, 235),  # red
    (235, 120, 220),  # magenta
    (90, 215, 235),   # yellow
]


def active_events(events: list[Event], t: float) -> Event | None:
    """Return the event covering time ``t``, if any (spans are padded slightly)."""
    for e in events:
        if e.start - 0.05 <= t <= e.end + 0.05:
            return e
    return None


def annotate(video: str, config_path: str, out_path: str) -> Path:
    config = load_config(config_path)
    result = scan_video(video, config)
    events = detect_all(config, result)
    colors = {sig.name: PALETTE[i % len(PALETTE)] for i, sig in enumerate(config.signatures)}

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    font = cv2.FONT_HERSHEY_SIMPLEX
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps

        banner: list[tuple[str, tuple[int, int, int]]] = []
        for sig in config.signatures:
            color = colors[sig.name]
            x0, y0, x1, y1 = sig.region.resolve(w, h)
            hit = active_events(events[sig.name], t)
            thick = 3 if hit else 1
            cv2.rectangle(frame, (x0, y0), (x1, y1), color, thick)
            # Label along the bottom edge of the region, clear of the top banner.
            cv2.putText(frame, sig.name, (x0 + 4, y1 - 6), font, 0.42, color, 1, cv2.LINE_AA)
            if hit:
                banner.append((f"{sig.name}  {hit.peak_score:.2f}", color))

        # Top banner listing everything firing right now.
        cv2.putText(frame, f"framesig  t={t:4.1f}s", (10, h - 14), font, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
        bx = 10
        for text, color in banner:
            cv2.circle(frame, (bx + 6, 18), 6, color, -1)
            cv2.putText(frame, text, (bx + 18, 23), font, 0.5, color, 1, cv2.LINE_AA)
            bx += 20 + 10 * len(text)

        writer.write(frame)
        idx += 1

    cap.release()
    writer.release()
    return Path(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("-c", "--config", required=True)
    ap.add_argument("-o", "--output", default="annotated.mp4")
    args = ap.parse_args()
    path = annotate(args.video, args.config, args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
