"""Tests for the on-disk score cache."""

from __future__ import annotations

from framesig.cache import CACHE_VERSION, ScoreCache, cache_key, video_fingerprint


def _payload():
    return {"video": "x.mp4", "meta": {}, "timestamps": [0.0, 0.1], "scores": {"s": [0.1, 0.9]}}


def test_store_and_load_roundtrip(tmp_path):
    cache = ScoreCache(tmp_path)
    key = "abc123"
    cache.store(key, _payload())
    loaded = cache.load(key)
    assert loaded is not None
    assert loaded["scores"]["s"] == [0.1, 0.9]
    assert loaded["version"] == CACHE_VERSION


def test_missing_key_is_none(tmp_path):
    assert ScoreCache(tmp_path).load("nope") is None


def test_corrupt_cache_is_a_miss_not_an_error(tmp_path):
    cache = ScoreCache(tmp_path)
    cache.directory.mkdir(parents=True, exist_ok=True)
    (tmp_path / "scores_broken.json").write_text("{ this is not json", encoding="utf-8")
    assert cache.load("broken") is None


def test_version_mismatch_is_a_miss(tmp_path):
    cache = ScoreCache(tmp_path)
    path = cache.store("k", _payload())
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(f'"version": {CACHE_VERSION}', '"version": 0'), encoding="utf-8")
    assert cache.load("k") is None


def test_cache_key_is_stable_and_sensitive():
    vfp = {"path": "/v.mp4", "size": 10, "mtime_ns": 1}
    cfp_a = {"sample_fps": 5, "signatures": {"s": {"detector": {"type": "brightness"}}}}
    cfp_b = {"sample_fps": 5, "signatures": {"s": {"detector": {"type": "scene_change"}}}}
    assert cache_key(vfp, cfp_a) == cache_key(vfp, cfp_a)  # stable
    assert cache_key(vfp, cfp_a) != cache_key(vfp, cfp_b)  # config-sensitive
    assert cache_key(vfp, cfp_a) != cache_key({**vfp, "size": 11}, cfp_a)  # video-sensitive


def test_video_fingerprint_fields(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"0123456789")
    fp = video_fingerprint(f)
    assert fp["size"] == 10
    assert fp["path"].endswith("clip.mp4")
    assert "mtime_ns" in fp
