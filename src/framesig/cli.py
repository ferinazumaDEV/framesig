"""Command-line interface for framesig.

Subcommands:
  * ``scan``       — scan a video against a YAML config and emit JSON events.
  * ``gen-sample`` — render the self-contained synthetic test clip.
  * ``demo``       — generate the clip, scan it, and write events + a chart.
  * ``detectors``  — list the available detector types.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import Config, load_config, parse_config
from .detectors import available_detectors
from .errors import ConfigError, FramesigError
from .events import Event
from .scanner import ScanResult, detect_all, scan_video
from .videogen import generate_sample_video

# Canonical demo config, mirrored by examples/flash.yaml. Matches the ground
# truth baked into framesig.videogen.
DEMO_CONFIG: dict[str, Any] = {
    "sample_fps": 10,
    "regions": {
        "hud_top": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.55},
        "kill_feed": {"x": 0.08, "y": 0.74, "w": 0.84, "h": 0.18},
        "screen_mid": {"x": 0.30, "y": 0.58, "w": 0.40, "h": 0.12},
        "corner": {"x": 0.82, "y": 0.94, "w": 0.18, "h": 0.06},
    },
    "signatures": [
        {
            "name": "death_screen",
            "region": "hud_top",
            "detector": "channel_dominance",
            "params": {"channel": "red", "gain": 2.0},
            "threshold": 0.30,
            "min_duration": 0.15,
            "merge_gap": 0.25,
        },
        {
            "name": "kill_feed",
            "region": "kill_feed",
            "detector": "color_fraction",
            "params": {
                "hsv_low": [0, 120, 70],
                "hsv_high": [10, 255, 255],
                "hsv_low2": [170, 120, 70],
                "hsv_high2": [179, 255, 255],
            },
            "threshold": 0.20,
            "min_duration": 0.10,
            "merge_gap": 0.20,
        },
        {
            "name": "white_flash",
            "region": "screen_mid",
            "detector": "brightness",
            "threshold": 0.75,
            "min_duration": 0.10,
        },
        {
            "name": "scene_cut",
            "region": "corner",
            "detector": "scene_change",
            "threshold": 0.15,
            "min_duration": 0.0,
        },
    ],
}


def _events_payload(events: dict[str, list[Event]]) -> dict[str, list[dict[str, Any]]]:
    return {name: [e.to_dict() for e in evs] for name, evs in events.items()}


def _print_summary(result: ScanResult, events: dict[str, list[Event]], stream) -> None:
    meta = result.meta
    src = "cache" if result.from_cache else "scan"
    total = sum(len(v) for v in events.values())
    print(
        f"{Path(result.video).name}  "
        f"{meta.get('width')}x{meta.get('height')}  "
        f"{meta.get('duration', 0):.1f}s  "
        f"{meta.get('samples')} samples @ {meta.get('sample_fps')} fps  ({src})",
        file=stream,
    )
    print(f"{total} event(s) across {len(events)} signature(s)", file=stream)
    for name, evs in events.items():
        print(f"  {name}: {len(evs)}", file=stream)
        for e in evs:
            print(
                f"    [{e.start:6.2f}s -> {e.end:6.2f}s]  "
                f"peak {e.peak_score:.2f} @ {e.peak_t:6.2f}s  "
                f"({e.samples} samples)",
                file=stream,
            )


def _write_json(obj: dict[str, Any], out: str | None) -> None:
    text = json.dumps(obj, indent=2)
    if out is None or out == "-":
        print(text)
    else:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)


def _run_scan(config: Config, video: str, *, use_cache: bool) -> tuple[ScanResult, dict[str, list[Event]]]:
    result = scan_video(video, config, use_cache=use_cache)
    events = detect_all(config, result)
    return result, events


def cmd_scan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.sample_fps is not None:
        # Mutating the dataclass skips parse_config's validation, so repeat it
        # here: the flag must obey the same rule as the YAML key.
        if args.sample_fps <= 0:
            raise ConfigError("--sample-fps must be positive")
        config.sample_fps = float(args.sample_fps)
    result, events = _run_scan(config, args.video, use_cache=not args.no_cache)

    if not args.quiet:
        _print_summary(result, events, sys.stderr)
    payload = {
        "video": result.video,
        "meta": result.meta,
        "from_cache": result.from_cache,
        "events": _events_payload(events),
    }
    _write_json(payload, args.output)

    if args.chart:
        from .viz import render_timeline

        path = render_timeline(config, result, events, args.chart)
        print(f"wrote chart {path}", file=sys.stderr)
    return 0


def cmd_gen_sample(args: argparse.Namespace) -> int:
    sample = generate_sample_video(args.output)
    print(f"wrote {sample.path}  ({sample.width}x{sample.height}, {sample.duration:g}s)", file=sys.stderr)
    if args.print_truth:
        _write_json(
            {
                "intervals": {k: v for k, v in sample.ground_truth.intervals.items()},
                "cuts": sample.ground_truth.cuts,
            },
            "-",
        )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "sample.mp4"

    print("[1/3] rendering synthetic clip with ffmpeg...", file=sys.stderr)
    generate_sample_video(video_path)

    print("[2/3] scanning for pixel signatures...", file=sys.stderr)
    config = parse_config(DEMO_CONFIG)
    result, events = _run_scan(config, str(video_path), use_cache=not args.no_cache)
    _print_summary(result, events, sys.stderr)

    events_path = out_dir / "events.json"
    _write_json(
        {"video": result.video, "meta": result.meta, "events": _events_payload(events)},
        str(events_path),
    )

    print("[3/3] rendering score-timeline chart...", file=sys.stderr)
    from .viz import render_timeline

    chart_path = render_timeline(config, result, events, out_dir / "timeline.png")
    print(f"done. outputs in {out_dir}/", file=sys.stderr)
    print(f"  {video_path.name}, {events_path.name}, {chart_path.name}", file=sys.stderr)
    return 0


def cmd_detectors(_args: argparse.Namespace) -> int:
    for name in available_detectors():
        print(name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="framesig",
        description="Detect on-screen events in a video by pixel signature.",
    )
    parser.add_argument("--version", action="version", version=f"framesig {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="scan a video against a YAML config")
    p_scan.add_argument("video", help="path to the video file")
    p_scan.add_argument("-c", "--config", required=True, help="YAML config path")
    p_scan.add_argument("-o", "--output", help="write events JSON here ('-' for stdout)")
    p_scan.add_argument("--sample-fps", type=float, help="override the sampling rate")
    p_scan.add_argument("--no-cache", action="store_true", help="ignore and skip the score cache")
    p_scan.add_argument("--chart", help="also render a score-timeline PNG here")
    p_scan.add_argument("-q", "--quiet", action="store_true", help="suppress the text summary")
    p_scan.set_defaults(func=cmd_scan)

    p_gen = sub.add_parser("gen-sample", help="render the synthetic test clip")
    p_gen.add_argument("output", help="destination .mp4 path")
    p_gen.add_argument("--print-truth", action="store_true", help="print the ground-truth events")
    p_gen.set_defaults(func=cmd_gen_sample)

    p_demo = sub.add_parser("demo", help="generate a clip, scan it, and chart the result")
    p_demo.add_argument("--out-dir", default="framesig_demo", help="output directory")
    p_demo.add_argument("--no-cache", action="store_true", help="skip the score cache")
    p_demo.set_defaults(func=cmd_demo)

    p_det = sub.add_parser("detectors", help="list available detector types")
    p_det.set_defaults(func=cmd_detectors)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FramesigError as exc:
        print(f"framesig: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
