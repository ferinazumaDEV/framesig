"""Tests for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

from framesig.cli import main

from conftest import requires_ffmpeg

EXAMPLE_CONFIG = Path(__file__).parents[1] / "examples" / "flash.yaml"


def test_detectors_command_lists_all(capsys):
    assert main(["detectors"]) == 0
    out = capsys.readouterr().out.split()
    assert set(out) == {"brightness", "channel_dominance", "color_fraction", "scene_change"}


def test_scan_writes_events_json(sample_video, tmp_path, capsys):
    out = tmp_path / "events.json"
    code = main(
        [
            "scan",
            str(sample_video.path),
            "-c",
            str(EXAMPLE_CONFIG),
            "-o",
            str(out),
            "--no-cache",
            "-q",
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    counts = {k: len(v) for k, v in data["events"].items()}
    assert counts == sample_video.ground_truth.expected_counts()


def test_scan_can_render_chart(sample_video, tmp_path):
    chart = tmp_path / "timeline.png"
    code = main(
        [
            "scan",
            str(sample_video.path),
            "-c",
            str(EXAMPLE_CONFIG),
            "-o",
            str(tmp_path / "e.json"),
            "--chart",
            str(chart),
            "-q",
        ]
    )
    assert code == 0
    assert chart.exists() and chart.stat().st_size > 0


def test_missing_config_returns_error_code(sample_video, capsys):
    code = main(["scan", str(sample_video.path), "-c", "does-not-exist.yaml", "-q"])
    assert code == 2
    assert "error" in capsys.readouterr().err.lower()


@requires_ffmpeg
def test_gen_sample_writes_video(tmp_path):
    out = tmp_path / "clip.mp4"
    assert main(["gen-sample", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0


def test_bad_sample_fps_flag_is_an_error(sample_video, capsys):
    """--sample-fps bypasses parse_config, so the flag needs its own guard."""
    for value in ("0", "-5"):
        code = main(
            [
                "scan",
                str(sample_video.path),
                "-c",
                str(EXAMPLE_CONFIG),
                "--sample-fps",
                value,
                "--no-cache",
                "-q",
            ]
        )
        assert code == 2
        assert "--sample-fps must be positive" in capsys.readouterr().err


@requires_ffmpeg
def test_demo_writes_all_three_outputs(tmp_path):
    """The README Quickstart's headline command."""
    out_dir = tmp_path / "demo"
    assert main(["demo", "--out-dir", str(out_dir)]) == 0
    for name in ("sample.mp4", "events.json", "timeline.png"):
        produced = out_dir / name
        assert produced.exists() and produced.stat().st_size > 0, name


def test_sample_fps_flag_overrides_the_config(sample_video, tmp_path):
    out = tmp_path / "events.json"
    code = main(
        [
            "scan",
            str(sample_video.path),
            "-c",
            str(EXAMPLE_CONFIG),
            "-o",
            str(out),
            "--sample-fps",
            "5",
            "--no-cache",
            "-q",
        ]
    )
    assert code == 0
    meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
    assert meta["sample_fps"] == 5.0
    assert meta["step"] == 6  # 30 fps native / 5 fps requested


@requires_ffmpeg
def test_gen_sample_print_truth_emits_the_ground_truth(tmp_path, capsys):
    assert main(["gen-sample", str(tmp_path / "clip.mp4"), "--print-truth"]) == 0
    truth = json.loads(capsys.readouterr().out)
    assert set(truth) == {"intervals", "cuts"}
    assert set(truth["intervals"]) == {"death_screen", "kill_feed", "white_flash"}


def test_scan_of_a_missing_video_is_an_error(tmp_path, capsys):
    code = main(["scan", str(tmp_path / "nope.mp4"), "-c", str(EXAMPLE_CONFIG), "-q"])
    assert code == 2
    assert "video not found" in capsys.readouterr().err
