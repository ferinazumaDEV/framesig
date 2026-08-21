"""On-disk caching of per-frame scores.

Scanning a video is the expensive part; thresholding the resulting scores is
practically free. framesig therefore caches the raw score timelines keyed by

  * a fingerprint of the *video* (path, size, mtime), and
  * a fingerprint of the *score-relevant* config (sampling rate, regions, and
    detector parameters — but **not** thresholds, ``min_duration`` or
    ``merge_gap``).

That split is the whole point: tweak a threshold, re-run, and framesig reuses
the cached scores for an instant answer. Change a detector's parameters and the
fingerprint changes, so a stale cache is transparently ignored.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CACHE_VERSION = 2


def video_fingerprint(path: str | Path) -> dict[str, Any]:
    """Cheap identity for a video file: absolute path, byte size and mtime."""
    p = Path(path)
    stat = p.stat()
    return {"path": str(p.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def cache_key(video_fp: dict[str, Any], config_fp: dict[str, Any]) -> str:
    """Combine video and config fingerprints into a stable filename stem."""
    return _digest({"video": video_fp, "config": config_fp, "v": CACHE_VERSION})


class ScoreCache:
    """A tiny JSON-backed cache of score timelines.

    Args:
        directory: Where cache files live. Created on first write.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def _path_for(self, key: str) -> Path:
        return self.directory / f"scores_{key}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        """Return the cached payload for ``key``, or ``None`` on a miss.

        A corrupt or unreadable cache file is treated as a miss rather than an
        error, so a bad cache can never break a scan.
        """
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return None
        return payload

    def store(self, key: str, payload: dict[str, Any]) -> Path:
        """Write ``payload`` under ``key`` and return the file path.

        The write is atomic (temp file + replace) so a crash mid-write cannot
        leave a half-written cache behind.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {**payload, "version": CACHE_VERSION}
        path = self._path_for(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
        return path
