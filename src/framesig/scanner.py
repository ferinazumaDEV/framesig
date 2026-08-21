"""The scanner: decode a video, sample frames, score every signature.

This is the compute-heavy core. It walks the video once, sub-samples frames to
the configured rate, crops each signature's region and asks its detector for a
score. The resulting score timelines are what gets cached and later turned into
events.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import cv2

from . import cache as cache_mod
from .config import Config
from .errors import VideoError
from .events import Event, detect_events

ProgressFn = Callable[[int, int], None]


@dataclass
class ScanResult:
    """The scored timelines for one video under one config.

    Attributes:
        video: Path to the scanned video.
        meta: Decode metadata (native fps, dimensions, duration, sample step...).
        timestamps: The shared list of sample timestamps in seconds.
        scores: ``signature name -> list of scores`` aligned with ``timestamps``.
        from_cache: ``True`` if these scores were loaded from disk rather than
            recomputed.
    """

    video: str
    meta: dict[str, Any]
    timestamps: list[float]
    scores: dict[str, list[float]]
    from_cache: bool = False

    def to_payload(self) -> dict[str, Any]:
        """Serialise into the dict stored by :class:`~framesig.cache.ScoreCache`."""
        return {
            "video": self.video,
            "meta": self.meta,
            "timestamps": self.timestamps,
            "scores": self.scores,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ScanResult":
        return cls(
            video=payload["video"],
            meta=payload["meta"],
            timestamps=list(payload["timestamps"]),
            scores={k: list(v) for k, v in payload["scores"].items()},
            from_cache=True,
        )


def _iter_frames(cap: "cv2.VideoCapture", step: int) -> Iterator[tuple[int, Any]]:
    """Yield ``(frame_index, frame)`` for every ``step``-th decoded frame."""
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step == 0:
            yield index, frame
        index += 1


def _default_cache_dir(video: Path, config: Config, override: str | None) -> Path:
    if override is not None:
        return Path(override)
    if config.cache_dir is not None:
        return Path(config.cache_dir)
    return video.parent / ".framesig_cache"


def scan_video(
    video_path: str | Path,
    config: Config,
    *,
    use_cache: bool = True,
    cache_dir: str | None = None,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """Scan a video and return per-signature score timelines.

    Args:
        video_path: Path to the video file.
        config: A validated :class:`~framesig.config.Config`.
        use_cache: When ``True`` (default), reuse a matching cached result and
            write fresh results back to the cache.
        cache_dir: Override the cache directory. Falls back to
            ``config.cache_dir`` and then to ``<video>/../.framesig_cache``.
        progress: Optional callback ``(processed_samples, approx_total)`` invoked
            as scanning proceeds. ``approx_total`` may be ``0`` if the decoder
            cannot report a frame count.

    Returns:
        A :class:`ScanResult`.

    Raises:
        VideoError: If the file cannot be opened or has an unusable frame rate.
    """
    video = Path(video_path)
    if not video.exists():
        raise VideoError(f"video not found: {str(video)!r}")

    cache_directory = _default_cache_dir(video, config, cache_dir)
    key = cache_mod.cache_key(
        cache_mod.video_fingerprint(video), config.score_fingerprint()
    )
    store = cache_mod.ScoreCache(cache_directory)

    if use_cache:
        cached = store.load(key)
        if cached is not None:
            result = ScanResult.from_payload(cached)
            # Guard against a stale cache missing a newly added signature.
            if set(result.scores) == {s.name for s in config.signatures}:
                return result

    result = _scan_uncached(video, config, progress)
    if use_cache:
        store.store(key, result.to_payload())
    return result


def _scan_uncached(video: Path, config: Config, progress: ProgressFn | None) -> ScanResult:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise VideoError(f"could not open video: {str(video)!r}")

    try:
        native_fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(native_fps) or native_fps <= 0:
            raise VideoError(
                f"video reports an invalid frame rate ({native_fps}); "
                f"cannot map frames to timestamps"
            )
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        step = max(1, int(round(native_fps / config.sample_fps)))
        approx_total = frame_count // step if frame_count > 0 else 0

        for sig in config.signatures:
            sig.detector.reset()

        timestamps: list[float] = []
        scores: dict[str, list[float]] = {s.name: [] for s in config.signatures}

        processed = 0
        for index, frame in _iter_frames(cap, step):
            timestamps.append(index / native_fps)
            for sig in config.signatures:
                roi = sig.region.crop(frame)
                scores[sig.name].append(sig.detector.score(roi))
            processed += 1
            if progress is not None:
                progress(processed, approx_total)
    finally:
        cap.release()

    if not timestamps:
        raise VideoError(f"decoded zero frames from {str(video)!r}")

    duration = (timestamps[-1] + step / native_fps) if timestamps else 0.0
    meta = {
        "native_fps": native_fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "sample_fps": config.sample_fps,
        "step": step,
        "sample_period": step / native_fps,
        "samples": len(timestamps),
        "duration": duration,
    }
    return ScanResult(video=str(video), meta=meta, timestamps=timestamps, scores=scores)


def detect_all(config: Config, result: ScanResult) -> dict[str, list[Event]]:
    """Apply each signature's thresholds to its cached scores.

    This step is cheap, so it is kept separate from :func:`scan_video`: you can
    re-run it with edited thresholds against the same (cached) scores instantly.

    Returns:
        ``signature name -> list of events``, preserving config order.
    """
    out: dict[str, list[Event]] = {}
    for sig in config.signatures:
        out[sig.name] = detect_events(
            sig.name,
            result.timestamps,
            result.scores.get(sig.name, []),
            threshold=sig.threshold,
            min_duration=sig.min_duration,
            merge_gap=sig.merge_gap,
        )
    return out
