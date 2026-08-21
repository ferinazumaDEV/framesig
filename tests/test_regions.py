"""Tests for region resolution, cropping and validation."""

from __future__ import annotations

import numpy as np
import pytest

from framesig.errors import ConfigError
from framesig.regions import Region


def test_fraction_resolves_to_pixels():
    r = Region("r", x=0.5, y=0.5, w=0.5, h=0.5)
    assert r.resolve(200, 100) == (100, 50, 200, 100)


def test_pixel_unit_is_literal():
    r = Region("r", x=10, y=20, w=30, h=40, unit="pixels")
    assert r.resolve(640, 480) == (10, 20, 40, 60)


def test_resolve_clamps_to_frame_and_stays_non_empty():
    r = Region("r", x=90, y=90, w=100, h=100, unit="pixels")
    x0, y0, x1, y1 = r.resolve(100, 100)
    assert 0 <= x0 < x1 <= 100
    assert 0 <= y0 < y1 <= 100


def test_crop_returns_expected_shape():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[50:100, 100:200] = (0, 0, 255)
    r = Region("r", x=0.5, y=0.5, w=0.5, h=0.5)
    crop = r.crop(frame)
    assert crop.shape == (50, 100, 3)
    assert (crop == (0, 0, 255)).all()


def test_from_mapping_roundtrip():
    r = Region.from_mapping("hud", {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4})
    assert (r.x, r.y, r.w, r.h, r.unit) == (0.1, 0.2, 0.3, 0.4, "fraction")


@pytest.mark.parametrize(
    "box",
    [
        {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.5},  # zero width
        {"x": 0.6, "y": 0.0, "w": 0.6, "h": 0.5},  # extends past edge
        {"x": -0.1, "y": 0.0, "w": 0.5, "h": 0.5},  # negative origin
    ],
)
def test_invalid_fraction_boxes_raise(box):
    with pytest.raises(ConfigError):
        Region.from_mapping("bad", box)


def test_unknown_unit_raises():
    with pytest.raises(ConfigError):
        Region("r", x=0, y=0, w=1, h=1, unit="furlongs")


def test_unknown_key_raises():
    with pytest.raises(ConfigError):
        Region.from_mapping("r", {"x": 0, "y": 0, "w": 1, "h": 1, "colour": "red"})
