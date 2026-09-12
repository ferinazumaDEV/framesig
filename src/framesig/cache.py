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
import os
import tempfile
from pathlib import Path
from typing import Any

CACHE_VERSION = 2

#: Keys :meth:`ScanResult.from_payload` reads. A file missing any of them is not
#: a usable cache entry, however well-formed its JSON is -- validating only the
#: version used to let ``{"version": 2}`` through as a hit, and the consumer
#: then died on a KeyError far from the actual problem.
_REQUIRED_KEYS = ("video", "meta", "timestamps", "scores")


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
        error, so a bad cache can never break a scan. "Corrupt" covers bytes
        that are not UTF-8, text that is not JSON, JSON that is not an object,
        the wrong cache version, and an object that does not carry what the
        consumer will ask for. Any of those means: recompute.
        """
        path = self._path_for(key)
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        # UnicodeDecodeError is a ValueError, not an OSError, so catching
        # (OSError, JSONDecodeError) missed it entirely: a cache file holding
        # arbitrary bytes -- a truncated write, a file from another tool, a disk
        # error -- raised out of load() and killed the scan it was meant to
        # protect. JSONDecodeError is itself a ValueError, so one clause covers
        # both without widening to bare Exception.
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return None
        if not all(key_name in payload for key_name in _REQUIRED_KEYS):
            return None
        if not isinstance(payload.get("scores"), dict):
            return None
        return payload

    def store(self, key: str, payload: dict[str, Any]) -> Path:
        """Write ``payload`` under ``key`` and return the file path.

        The write is atomic (temp file + replace) so a crash mid-write cannot
        leave a half-written cache behind, and each write uses a temporary of
        its own so two processes sharing a cache directory cannot collide.

        Concurrency beyond that is last-writer-wins. Two writers producing
        scores for the same key produce the same scores -- the key is a digest
        of the video and the score-relevant config -- so which one lands does
        not change the answer.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {**payload, "version": CACHE_VERSION}
        path = self._path_for(key)

        # A shared name like scores_<key>.json.tmp meant two writers used the
        # same temporary: the first replace() moved it away and the second
        # failed with FileNotFoundError on a path it had legitimately written.
        # mkstemp gives each writer its own, in the destination directory so
        # os.replace stays a rename within one filesystem, and therefore atomic.
        handle, tmp_name = tempfile.mkstemp(
            dir=self.directory, prefix=f"scores_{key}.", suffix=".json.tmp"
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return path
