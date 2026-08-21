"""Tests for turning score timelines into events."""

from __future__ import annotations

import pytest

from framesig.events import detect_events


def _grid(n: int, dt: float = 0.1) -> list[float]:
    return [round(i * dt, 6) for i in range(n)]


def test_single_run_becomes_one_event():
    ts = _grid(10)
    scores = [0, 0, 0.9, 0.95, 0.8, 0, 0, 0, 0, 0]
    events = detect_events("s", ts, scores, threshold=0.5)
    assert len(events) == 1
    e = events[0]
    assert e.start == pytest.approx(0.2)
    assert e.end == pytest.approx(0.4)
    assert e.peak_score == pytest.approx(0.95)
    assert e.peak_t == pytest.approx(0.3)
    assert e.samples == 3


def test_two_runs_stay_separate_without_merge():
    ts = _grid(12)
    scores = [0, 0.9, 0, 0, 0, 0.9, 0.9, 0, 0, 0, 0, 0]
    events = detect_events("s", ts, scores, threshold=0.5)
    assert len(events) == 2


def test_merge_gap_bridges_close_runs():
    ts = _grid(12)
    # Active at t=0.1 and again at t=0.3..0.4: the two nearest active samples
    # are 0.2 s apart (one inactive sample sits between them).
    scores = [0, 0.9, 0, 0.9, 0.9, 0, 0, 0, 0, 0, 0, 0]
    merged = detect_events("s", ts, scores, threshold=0.5, merge_gap=0.25)
    assert len(merged) == 1
    kept = detect_events("s", ts, scores, threshold=0.5, merge_gap=0.15)
    assert len(kept) == 2


def test_min_duration_filters_blips():
    ts = _grid(10)
    scores = [0, 0, 0.9, 0, 0, 0, 0, 0, 0, 0]  # single-sample spike
    # sample period is 0.1, so a lone spike lasts ~0.1 s.
    assert detect_events("s", ts, scores, threshold=0.5, min_duration=0.05)
    assert not detect_events("s", ts, scores, threshold=0.5, min_duration=0.2)


def test_threshold_is_inclusive():
    ts = _grid(4)
    scores = [0.0, 0.5, 0.5, 0.0]
    assert len(detect_events("s", ts, scores, threshold=0.5)) == 1
    assert len(detect_events("s", ts, scores, threshold=0.51)) == 0


def test_event_at_timeline_end_is_closed():
    ts = _grid(5)
    scores = [0, 0, 0, 0.9, 0.9]
    events = detect_events("s", ts, scores, threshold=0.5)
    assert len(events) == 1
    assert events[0].end == pytest.approx(0.4)


def test_empty_and_mismatched_inputs():
    assert detect_events("s", [], [], threshold=0.5) == []
    with pytest.raises(ValueError):
        detect_events("s", [0.0, 0.1], [0.5], threshold=0.5)


def test_mean_score_reported():
    ts = _grid(5)
    scores = [0, 0.6, 0.8, 1.0, 0]
    e = detect_events("s", ts, scores, threshold=0.5)[0]
    assert e.mean_score == pytest.approx((0.6 + 0.8 + 1.0) / 3)


def test_to_dict_is_json_friendly():
    ts = _grid(4)
    e = detect_events("kill", ts, [0, 0.9, 0.9, 0], threshold=0.5)[0]
    d = e.to_dict()
    assert d["signature"] == "kill"
    assert isinstance(d["peak_score"], float)
    assert set(d) == {
        "signature", "start", "end", "duration",
        "peak_t", "peak_score", "mean_score", "samples",
    }
