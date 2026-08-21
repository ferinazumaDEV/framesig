"""Tests for YAML config parsing and validation."""

from __future__ import annotations

import textwrap

import pytest

from framesig.config import load_config, parse_config
from framesig.detectors import ChannelDominance
from framesig.errors import ConfigError

VALID = {
    "sample_fps": 8,
    "regions": {"full": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
    "signatures": [
        {
            "name": "flash",
            "region": "full",
            "detector": "channel_dominance",
            "params": {"channel": "red", "gain": 2.0},
            "threshold": 0.4,
            "min_duration": 0.2,
            "merge_gap": 0.3,
        }
    ],
}


def test_parse_valid_config():
    cfg = parse_config(VALID)
    assert cfg.sample_fps == 8
    assert "full" in cfg.regions
    (sig,) = cfg.signatures
    assert sig.name == "flash"
    assert isinstance(sig.detector, ChannelDominance)
    assert sig.threshold == 0.4
    assert sig.min_duration == 0.2


def test_load_config_from_disk(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text(
        textwrap.dedent(
            """
            sample_fps: 5
            regions:
              band: {x: 0.1, y: 0.8, w: 0.8, h: 0.15}
            signatures:
              - name: subs
                region: band
                detector: brightness
                threshold: 0.6
            """
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.signatures[0].name == "subs"
    assert cfg.regions["band"].y == 0.8


def test_unknown_region_reference_raises():
    bad = {**VALID, "signatures": [{**VALID["signatures"][0], "region": "ghost"}]}
    with pytest.raises(ConfigError, match="unknown region"):
        parse_config(bad)


def test_unknown_detector_raises():
    bad = {**VALID, "signatures": [{**VALID["signatures"][0], "detector": "vibes"}]}
    with pytest.raises(ConfigError, match="unknown detector"):
        parse_config(bad)


def test_duplicate_signature_names_raise():
    sig = VALID["signatures"][0]
    bad = {**VALID, "signatures": [sig, sig]}
    with pytest.raises(ConfigError, match="duplicate signature names"):
        parse_config(bad)


def test_no_signatures_raises():
    with pytest.raises(ConfigError, match="no signatures"):
        parse_config({"regions": VALID["regions"], "signatures": []})


def test_bad_sample_fps_raises():
    with pytest.raises(ConfigError, match="sample_fps"):
        parse_config({**VALID, "sample_fps": 0})


def test_score_fingerprint_ignores_thresholds():
    """Changing a threshold must NOT change the score fingerprint (cache key)."""
    a = parse_config(VALID)
    tweaked = {**VALID, "signatures": [{**VALID["signatures"][0], "threshold": 0.9}]}
    b = parse_config(tweaked)
    assert a.score_fingerprint() == b.score_fingerprint()


def test_score_fingerprint_tracks_detector_params():
    a = parse_config(VALID)
    tweaked = {
        **VALID,
        "signatures": [
            {**VALID["signatures"][0], "params": {"channel": "red", "gain": 5.0}}
        ],
    }
    b = parse_config(tweaked)
    assert a.score_fingerprint() != b.score_fingerprint()


def test_empty_yaml_raises(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load_config(path)
