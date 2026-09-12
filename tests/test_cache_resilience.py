"""A bad cache must never break a scan, and two writers must not collide.

Audit findings F04 and F05.

F04: ``ScoreCache.load`` documented that a corrupt or unreadable file is a miss,
but caught only ``(OSError, json.JSONDecodeError)``. ``UnicodeDecodeError`` is a
``ValueError``, so a cache file holding arbitrary bytes raised straight out of
``load()`` and killed the scan the cache exists to speed up. Validation was also
thin enough that ``{"version": 2}`` counted as a hit, and the consumer then died
on a ``KeyError`` far from the real problem.

F05: every write of a key used the same temporary name, so two writers sharing a
cache directory raced: the first ``replace()`` moved the shared temporary away
and the second failed with ``FileNotFoundError`` on a file it had written.
"""

from __future__ import annotations

import json
import threading

import pytest

from framesig.cache import CACHE_VERSION, ScoreCache

GOOD = {
    "video": "sample.mp4",
    "meta": {"duration": 1.0},
    "timestamps": [0.0, 0.1],
    "scores": {"flash": [0.0, 1.0]},
}

CORRUPT = [
    pytest.param(b"\xff\xfe", id="not-utf8"),
    pytest.param(b"\x00\x01\x02\x03", id="binary-garbage"),
    pytest.param(b'{"version": 2, "scores"', id="truncated-json"),
    pytest.param(b"[1, 2, 3]", id="json-but-not-an-object"),
    pytest.param(b'{"version": 99, "video": "v", "meta": {}, "timestamps": [], "scores": {}}',
                 id="wrong-version"),
    pytest.param(b'{"version": 2}', id="no-payload-keys"),
    pytest.param(b'{"version": 2, "video": "v", "meta": {}, "timestamps": []}',
                 id="missing-scores"),
    pytest.param(b'{"version": 2, "video": "v", "meta": {}, "timestamps": [], "scores": []}',
                 id="scores-not-an-object"),
    pytest.param(b"", id="empty-file"),
]


@pytest.mark.parametrize("contents", CORRUPT)
def test_corrupt_cache_is_a_miss_not_an_exception(tmp_path, contents):
    (tmp_path / "scores_bad.json").write_bytes(contents)
    assert ScoreCache(tmp_path).load("bad") is None


def test_a_good_entry_still_loads(tmp_path):
    """The validation must not be so strict that nothing survives it."""
    cache = ScoreCache(tmp_path)
    cache.store("ok", GOOD)
    loaded = cache.load("ok")
    assert loaded is not None
    assert loaded["scores"] == GOOD["scores"]
    assert loaded["version"] == CACHE_VERSION


def test_missing_file_is_a_miss(tmp_path):
    assert ScoreCache(tmp_path).load("never-written") is None


def test_two_writers_on_one_key_do_not_collide(tmp_path):
    """F05: a barrier after the temporary write forces the interleaving."""
    cache = ScoreCache(tmp_path)
    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []

    original_replace = __import__("os").replace

    def slow_replace(src, dst):
        barrier.wait()          # both writers hold a temporary at this point
        return original_replace(src, dst)

    def writer(index):
        try:
            payload = {**GOOD, "scores": {"flash": [float(index)]}}
            cache.store("shared", payload)
        except BaseException as exc:      # noqa: BLE001 - the test is about what escapes
            errors.append(exc)

    import framesig.cache as cache_module
    monkeypatched = getattr(cache_module, "os")
    real = monkeypatched.replace
    monkeypatched.replace = slow_replace
    try:
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
    finally:
        monkeypatched.replace = real

    assert not errors, f"a writer raised: {errors!r}"

    # Whichever landed, the file must be complete and valid -- not half-written.
    written = json.loads((tmp_path / "scores_shared.json").read_text(encoding="utf-8"))
    assert written["version"] == CACHE_VERSION
    assert written["scores"]["flash"] in ([0.0], [1.0])
    assert cache.load("shared") is not None


def test_no_temporary_files_are_left_behind(tmp_path):
    cache = ScoreCache(tmp_path)
    for i in range(5):
        cache.store(f"key{i}", GOOD)
    assert list(tmp_path.glob("*.tmp")) == []
