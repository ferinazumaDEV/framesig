"""Turning score timelines into discrete events.

The scanner produces, for each signature, a score at every sampled timestamp.
This module thresholds that timeline, merges nearby hits, drops blips that are
too short, and reports one :class:`Event` per surviving run.

Detection is intentionally separated from scanning: because the (expensive)
scores are cached, you can re-run :func:`detect_events` with different
thresholds as many times as you like for free.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class Event:
    """A single detected occurrence of a signature.

    Attributes:
        signature: Name of the signature that fired.
        start: Timestamp (seconds) of the first sample in the run.
        end: Timestamp (seconds) of the last sample in the run.
        duration: ``end - start`` plus one sample period, so a single-sample
            spike still reports a non-zero duration.
        peak_t: Timestamp of the highest-scoring sample in the run.
        peak_score: The highest score in the run.
        mean_score: Mean score across the run's samples.
        samples: Number of sampled frames in the run.
    """

    signature: str
    start: float
    end: float
    duration: float
    peak_t: float
    peak_score: float
    mean_score: float
    samples: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict, with floats rounded for tidy output."""
        d = asdict(self)
        for key in ("start", "end", "duration", "peak_t", "peak_score", "mean_score"):
            d[key] = round(float(d[key]), 4)
        return d


def _sample_period(timestamps: Sequence[float]) -> float:
    """Estimate the spacing between samples (median of successive deltas)."""
    if len(timestamps) < 2:
        return 0.0
    deltas = sorted(timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1))
    return deltas[len(deltas) // 2]


def detect_events(
    signature: str,
    timestamps: Sequence[float],
    scores: Sequence[float],
    *,
    threshold: float,
    min_duration: float = 0.0,
    merge_gap: float = 0.0,
) -> list[Event]:
    """Detect events in a single signature's score timeline.

    Args:
        signature: Name attached to every returned event.
        timestamps: Sample timestamps in seconds, ascending.
        scores: Scores aligned with ``timestamps``.
        threshold: A sample is "active" when ``score >= threshold``.
        min_duration: Runs shorter than this (seconds) are discarded, filtering
            out single-frame noise.
        merge_gap: Active runs separated by a gap no larger than this (seconds)
            are merged into one event. Useful when an effect flickers.

    Returns:
        A list of :class:`Event`, ordered by start time.
    """
    if len(timestamps) != len(scores):
        raise ValueError("timestamps and scores must have equal length")
    if not timestamps:
        return []

    period = _sample_period(timestamps)

    # 1. Collect maximal runs of consecutive active samples as index ranges.
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, s in enumerate(scores):
        if s >= threshold:
            if start is None:
                start = i
        else:
            if start is not None:
                runs.append((start, i - 1))
                start = None
    if start is not None:
        runs.append((start, len(scores) - 1))

    if not runs:
        return []

    # 2. Merge runs whose time gap is within merge_gap.
    merged: list[tuple[int, int]] = [runs[0]]
    for a, b in runs[1:]:
        prev_a, prev_b = merged[-1]
        gap = timestamps[a] - timestamps[prev_b]
        if gap <= merge_gap:
            merged[-1] = (prev_a, b)
        else:
            merged.append((a, b))

    # 3. Build events, applying the minimum-duration filter.
    events: list[Event] = []
    for a, b in merged:
        start_t = float(timestamps[a])
        end_t = float(timestamps[b])
        duration = end_t - start_t + period
        if duration < min_duration:
            continue
        run_scores = scores[a : b + 1]
        peak_local = max(range(len(run_scores)), key=lambda k: run_scores[k])
        events.append(
            Event(
                signature=signature,
                start=start_t,
                end=end_t,
                duration=duration,
                peak_t=float(timestamps[a + peak_local]),
                peak_score=float(run_scores[peak_local]),
                mean_score=float(sum(run_scores) / len(run_scores)),
                samples=b - a + 1,
            )
        )
    return events
