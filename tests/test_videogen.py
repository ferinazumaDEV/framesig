"""Tests for the synthetic-clip generator."""

from __future__ import annotations

import pytest

from framesig.errors import DependencyError
from framesig.videogen import generate_sample_video, ground_truth


def test_missing_ffmpeg_raises_dependency_error(tmp_path):
    """The one documented reason framesig needs an external binary."""
    with pytest.raises(DependencyError, match="not found on PATH"):
        generate_sample_video(tmp_path / "a.mp4", ffmpeg="definitely-not-a-binary")


def test_ground_truth_counts_match_the_painted_windows():
    truth = ground_truth()
    counts = truth.expected_counts()
    assert counts == {
        "death_screen": len(truth.intervals["death_screen"]),
        "kill_feed": len(truth.intervals["kill_feed"]),
        "white_flash": len(truth.intervals["white_flash"]),
        "scene_cut": len(truth.cuts),
    }
