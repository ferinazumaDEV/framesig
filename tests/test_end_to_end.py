"""End-to-end tests against a real, ffmpeg-generated video.

These render the synthetic HUD clip (via the ``sample_video`` fixture) and assert
that framesig recovers exactly the events baked into it, at the right times.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framesig.cli import DEMO_CONFIG
from framesig.config import load_config, parse_config
from framesig.scanner import detect_all, scan_video

EXAMPLE_CONFIG = Path(__file__).parents[1] / "examples" / "flash.yaml"
TOL = 0.2  # seconds


@pytest.fixture(scope="module")
def config():
    return load_config(EXAMPLE_CONFIG)


def test_example_config_matches_bundled_demo_config():
    """The shipped example YAML and the CLI's built-in demo config must agree."""
    assert load_config(EXAMPLE_CONFIG).score_fingerprint() == parse_config(
        DEMO_CONFIG
    ).score_fingerprint()


def test_event_counts_match_ground_truth(sample_video, config, tmp_path):
    result = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    events = detect_all(config, result)
    counts = {name: len(evs) for name, evs in events.items()}
    assert counts == sample_video.ground_truth.expected_counts()


def test_events_land_at_the_right_timestamps(sample_video, config, tmp_path):
    result = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    events = detect_all(config, result)

    for name, windows in sample_video.ground_truth.intervals.items():
        detected = sorted(e.peak_t for e in events[name])
        assert len(detected) == len(windows)
        for (start, end), peak in zip(windows, detected):
            assert start - TOL <= peak <= end + TOL, f"{name}: {peak} not in [{start},{end}]"


def test_scene_cut_detected_near_expected_time(sample_video, config, tmp_path):
    result = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    events = detect_all(config, result)["scene_cut"]
    assert len(events) == 1
    assert abs(events[0].peak_t - sample_video.ground_truth.cuts[0]) <= TOL


def test_death_and_flash_are_confident(sample_video, config, tmp_path):
    result = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    events = detect_all(config, result)
    assert all(e.peak_score > 0.9 for e in events["death_screen"])
    assert all(e.peak_score > 0.9 for e in events["kill_feed"])
    assert all(e.peak_score > 0.9 for e in events["white_flash"])


def test_second_scan_hits_cache(sample_video, config, tmp_path):
    first = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    assert first.from_cache is False
    second = scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    assert second.from_cache is True
    assert second.scores == first.scores


def test_no_cache_flag_forces_recompute(sample_video, config, tmp_path):
    scan_video(sample_video.path, config, cache_dir=str(tmp_path))
    again = scan_video(sample_video.path, config, cache_dir=str(tmp_path), use_cache=False)
    assert again.from_cache is False


def test_thresholds_are_reapplied_without_rescanning(sample_video, tmp_path):
    """Re-detecting with a stricter threshold uses the cached scores only."""
    cfg = load_config(EXAMPLE_CONFIG)  # own instance; safe to mutate
    result = scan_video(sample_video.path, cfg, cache_dir=str(tmp_path))
    assert result.from_cache is False
    # Raise every threshold above 1.0: nothing can fire, but no rescan happens.
    for sig in cfg.signatures:
        sig.threshold = 1.01
    reused = scan_video(sample_video.path, cfg, cache_dir=str(tmp_path))
    assert reused.from_cache is True
    events = detect_all(cfg, reused)
    assert sum(len(v) for v in events.values()) == 0
