"""Tests for the pixel-signature detectors."""

from __future__ import annotations

import numpy as np
import pytest

from framesig.detectors import (
    Brightness,
    ChannelDominance,
    ColorFraction,
    SceneChange,
    available_detectors,
    build_detector,
)
from framesig.errors import ConfigError

from conftest import solid

RED = (0, 0, 255)  # BGR
BLUE = (255, 0, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def test_brightness_extremes():
    assert Brightness().score(solid(WHITE)) == pytest.approx(1.0, abs=1e-3)
    assert Brightness().score(solid(BLACK)) == pytest.approx(0.0, abs=1e-3)


def test_brightness_invert():
    assert Brightness(invert=True).score(solid(BLACK)) == pytest.approx(1.0, abs=1e-3)


def test_channel_dominance_red_fires_on_red_not_blue():
    det = ChannelDominance(channel="red", gain=1.0)
    assert det.score(solid(RED)) == pytest.approx(1.0, abs=1e-3)
    assert det.score(solid(BLUE)) == pytest.approx(0.0, abs=1e-3)
    # White has no channel dominance at all.
    assert det.score(solid(WHITE)) == pytest.approx(0.0, abs=1e-3)


def test_channel_dominance_gain_scales_partial_signal():
    # A region that is 20% red over black: mean red ~= 51 -> dominance ~= 0.2.
    img = solid(BLACK, size=10)
    img[:, :2] = RED  # 2 of 10 columns
    low = ChannelDominance(channel="red", gain=1.0).score(img)
    high = ChannelDominance(channel="red", gain=3.0).score(img)
    assert low == pytest.approx(0.2, abs=0.02)
    assert high == pytest.approx(min(1.0, 0.2 * 3), abs=0.02)


def test_channel_dominance_rejects_bad_params():
    with pytest.raises(ConfigError):
        ChannelDominance(channel="purple")
    with pytest.raises(ConfigError):
        ChannelDominance(channel="red", gain=0)


def test_color_fraction_counts_matching_pixels():
    det = ColorFraction(
        hsv_low=[0, 120, 70],
        hsv_high=[10, 255, 255],
        hsv_low2=[170, 120, 70],
        hsv_high2=[179, 255, 255],
    )
    assert det.score(solid(RED)) == pytest.approx(1.0, abs=1e-3)
    assert det.score(solid(BLUE)) == pytest.approx(0.0, abs=1e-3)
    half = solid(BLACK, size=10)
    half[:5, :] = RED
    assert det.score(half) == pytest.approx(0.5, abs=0.01)


def test_color_fraction_requires_paired_second_range():
    with pytest.raises(ConfigError):
        ColorFraction(hsv_low=[0, 0, 0], hsv_high=[10, 255, 255], hsv_low2=[170, 0, 0])


def test_scene_change_first_frame_is_zero_then_reacts():
    det = SceneChange()
    assert det.score(solid(BLACK)) == 0.0  # nothing to compare against yet
    assert det.score(solid(WHITE)) == pytest.approx(1.0, abs=1e-3)  # black -> white
    assert det.score(solid(WHITE)) == pytest.approx(0.0, abs=1e-3)  # no change


def test_scene_change_reset_forgets_previous():
    det = SceneChange()
    det.score(solid(WHITE))
    det.reset()
    assert det.score(solid(BLACK)) == 0.0


def test_registry_builds_all_detectors():
    assert set(available_detectors()) == {
        "brightness",
        "channel_dominance",
        "color_fraction",
        "scene_change",
    }
    det = build_detector("channel_dominance", {"channel": "green", "gain": 2.0})
    assert isinstance(det, ChannelDominance)
    assert det.channel == "green"


def test_registry_rejects_unknown_type():
    with pytest.raises(ConfigError):
        build_detector("telepathy", {})


def test_registry_reports_missing_required_param():
    with pytest.raises(ConfigError):
        build_detector("color_fraction", {})  # missing hsv_low/hsv_high


def test_registry_rejects_non_mapping_params():
    with pytest.raises(ConfigError, match="params must be a mapping"):
        build_detector("brightness", [1, 2])


def test_registry_reports_non_numeric_param():
    with pytest.raises(ConfigError, match="invalid params"):
        build_detector("channel_dominance", {"gain": "fast"})
    with pytest.raises(ConfigError, match="invalid params"):
        build_detector("channel_dominance", {"gain": None})


def test_brightness_factory_rejects_non_boolean_invert():
    """bool("false") is True, so a quoted YAML string must be rejected."""
    with pytest.raises(ConfigError, match="must be true or false"):
        build_detector("brightness", {"invert": "false"})


@pytest.mark.parametrize(
    "bounds",
    [
        {"hsv_low": [0, 0, 0], "hsv_high": [179, 255, 256]},  # V over 255
        {"hsv_low": [0, 0, 0], "hsv_high": [180, 255, 255]},  # H over 179
        {"hsv_low": [-1, 0, 0], "hsv_high": [179, 255, 255]},  # negative
    ],
)
def test_color_fraction_rejects_out_of_range_bounds(bounds):
    """Out-of-range bounds overflow on numpy 2.x and wrap on numpy 1.x."""
    with pytest.raises(ConfigError, match="out of range"):
        build_detector("color_fraction", bounds)


def test_color_fraction_rejects_non_integer_bounds():
    with pytest.raises(ConfigError, match="3 integers"):
        build_detector("color_fraction", {"hsv_low": [0, 0, "x"], "hsv_high": [10, 255, 255]})
    with pytest.raises(ConfigError, match="3 integers"):
        build_detector("color_fraction", {"hsv_low": 5, "hsv_high": [10, 255, 255]})
