"""Tests for the scanner's error paths and its progress callback."""

from __future__ import annotations

import pytest

from framesig.config import parse_config
from framesig.errors import VideoError
from framesig.scanner import scan_video

CONFIG = parse_config(
    {
        "sample_fps": 5,
        "regions": {"full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
        "signatures": [{"name": "flash", "region": "full", "detector": "brightness"}],
    }
)


def test_missing_video_raises_video_error(tmp_path):
    with pytest.raises(VideoError, match="video not found"):
        scan_video(tmp_path / "missing.mp4", CONFIG, cache_dir=str(tmp_path))


def test_undecodable_file_raises_video_error(tmp_path):
    """A file that exists but is not a video must not escape as an OpenCV error."""
    fake = tmp_path / "x.mp4"
    fake.write_text("this is not a video", encoding="utf-8")
    with pytest.raises(VideoError, match="could not open"):
        scan_video(fake, CONFIG, cache_dir=str(tmp_path))


def test_progress_callback_reports_every_sample(sample_video, tmp_path):
    seen: list[tuple[int, int]] = []
    result = scan_video(
        sample_video.path,
        CONFIG,
        cache_dir=str(tmp_path),
        use_cache=False,
        progress=lambda done, total: seen.append((done, total)),
    )
    assert len(seen) == result.meta["samples"]
    # The callback counts up from 1, and the last count is the sample total.
    assert [done for done, _ in seen] == list(range(1, result.meta["samples"] + 1))
    assert seen[-1][1] == result.meta["frame_count"] // result.meta["step"]
