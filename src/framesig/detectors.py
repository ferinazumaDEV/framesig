"""Pixel-signature detectors.

A detector turns the pixels of a cropped region into a single score in
``[0, 1]``. Higher means "the event looks more present in this frame". Detectors
are deliberately dumb and stateless-per-frame (except :class:`SceneChange`,
which remembers the previous region); turning a stream of scores into discrete
events is the job of :mod:`framesig.events`.

Everything is game- and source-agnostic: a detector only ever sees a numpy BGR
crop, never any knowledge of what produced it.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import cv2
import numpy as np

from .errors import ConfigError

# BGR channel indices, matching OpenCV's default byte order.
_CHANNEL_INDEX = {"blue": 0, "green": 1, "red": 2}


class Detector:
    """Base class. Subclasses implement :meth:`score`.

    A detector instance is created once per signature and reused for every
    sampled frame, so it may cache small amounts of state between calls (see
    :class:`SceneChange`).
    """

    #: Registry key used in YAML ``detector:`` fields.
    type_name: str = "base"

    def score(self, roi: np.ndarray) -> float:
        """Return a score in ``[0, 1]`` for a single BGR region crop."""
        raise NotImplementedError

    def reset(self) -> None:
        """Forget any per-video state. Called once before each scan."""

    def fingerprint(self) -> dict[str, Any]:
        """Return the parameters that affect the score, for cache keying."""
        return {"type": self.type_name}

    @staticmethod
    def _clamp(value: float) -> float:
        return float(max(0.0, min(1.0, value)))


class Brightness(Detector):
    """Mean luminance of the region.

    Great for full-screen white flashes (explosions, flashbangs) with
    ``invert=False``, or for fades to black / death screens with ``invert=True``.
    """

    type_name = "brightness"

    def __init__(self, *, invert: bool = False) -> None:
        self.invert = bool(invert)

    def score(self, roi: np.ndarray) -> float:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        value = float(gray.mean()) / 255.0
        return self._clamp(1.0 - value if self.invert else value)

    def fingerprint(self) -> dict[str, Any]:
        return {"type": self.type_name, "invert": self.invert}


class ChannelDominance(Detector):
    """How strongly one BGR channel dominates the other two, region-averaged.

    This is the "relative red" signature: a red kill/death flash pushes the mean
    red far above mean green and blue, even under compression, without caring
    about absolute brightness. ``gain`` scales the raw dominance (in 0..255)
    into the ``[0, 1]`` score before clamping.
    """

    type_name = "channel_dominance"

    def __init__(self, *, channel: str = "red", gain: float = 1.0) -> None:
        if channel not in _CHANNEL_INDEX:
            raise ConfigError(
                f"channel_dominance: channel must be one of "
                f"{sorted(_CHANNEL_INDEX)}, got {channel!r}"
            )
        if gain <= 0:
            raise ConfigError("channel_dominance: gain must be positive")
        self.channel = channel
        self.gain = float(gain)

    def score(self, roi: np.ndarray) -> float:
        means = roi.reshape(-1, 3).mean(axis=0)  # [B, G, R]
        idx = _CHANNEL_INDEX[self.channel]
        others = float(max(means[i] for i in range(3) if i != idx))
        dominance = (float(means[idx]) - others) / 255.0
        return self._clamp(dominance * self.gain)

    def fingerprint(self) -> dict[str, Any]:
        return {"type": self.type_name, "channel": self.channel, "gain": self.gain}


class ColorFraction(Detector):
    """Fraction of region pixels that fall inside one or more HSV colour ranges.

    Ideal for a coloured HUD element that occupies a known band of the frame
    (a red kill-feed row, a blue objective banner). Because red wraps around the
    hue circle, you may pass a second range via ``hsv_low2`` / ``hsv_high2``.

    HSV bounds follow OpenCV's conventions: H in ``[0, 179]``, S and V in
    ``[0, 255]``.
    """

    type_name = "color_fraction"

    def __init__(
        self,
        *,
        hsv_low: list[int],
        hsv_high: list[int],
        hsv_low2: list[int] | None = None,
        hsv_high2: list[int] | None = None,
    ) -> None:
        self._ranges = [self._as_bound("hsv_low", hsv_low), self._as_bound("hsv_high", hsv_high)]
        self.ranges = [(self._ranges[0], self._ranges[1])]
        if (hsv_low2 is None) != (hsv_high2 is None):
            raise ConfigError(
                "color_fraction: hsv_low2 and hsv_high2 must be provided together"
            )
        if hsv_low2 is not None and hsv_high2 is not None:
            self.ranges.append(
                (self._as_bound("hsv_low2", hsv_low2), self._as_bound("hsv_high2", hsv_high2))
            )

    @staticmethod
    def _as_bound(field: str, value: list[int]) -> np.ndarray:
        if value is None or len(value) != 3:
            raise ConfigError(f"color_fraction: {field} must be a list of 3 integers [H, S, V]")
        return np.array([int(v) for v in value], dtype=np.uint8)

    def score(self, roi: np.ndarray) -> float:
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = None
        for low, high in self.ranges:
            part = cv2.inRange(hsv, low, high)
            mask = part if mask is None else cv2.bitwise_or(mask, part)
        assert mask is not None  # at least one range always exists
        return self._clamp(float(np.count_nonzero(mask)) / mask.size)

    def fingerprint(self) -> dict[str, Any]:
        return {
            "type": self.type_name,
            "ranges": [[low.tolist(), high.tolist()] for low, high in self.ranges],
        }


class SceneChange(Detector):
    """Mean absolute difference from the previously sampled region.

    Fires on hard cuts and big visual transitions. It is stateful: the first
    sampled frame of a scan always scores ``0`` because there is nothing to
    compare against yet.
    """

    type_name = "scene_change"

    def __init__(self) -> None:
        self._prev: np.ndarray | None = None

    def reset(self) -> None:
        self._prev = None

    def score(self, roi: np.ndarray) -> float:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if self._prev is None or self._prev.shape != gray.shape:
            self._prev = gray
            return 0.0
        diff = cv2.absdiff(gray, self._prev)
        self._prev = gray
        return self._clamp(float(diff.mean()) / 255.0)


# --- registry ---------------------------------------------------------------

_FACTORIES: dict[str, Callable[[Mapping[str, Any]], Detector]] = {
    Brightness.type_name: lambda p: Brightness(invert=bool(p.get("invert", False))),
    ChannelDominance.type_name: lambda p: ChannelDominance(
        channel=str(p.get("channel", "red")), gain=float(p.get("gain", 1.0))
    ),
    ColorFraction.type_name: lambda p: ColorFraction(
        hsv_low=p["hsv_low"],
        hsv_high=p["hsv_high"],
        hsv_low2=p.get("hsv_low2"),
        hsv_high2=p.get("hsv_high2"),
    ),
    SceneChange.type_name: lambda p: SceneChange(),
}


def available_detectors() -> list[str]:
    """Return the sorted list of detector type names known to framesig."""
    return sorted(_FACTORIES)


def build_detector(type_name: str, params: Mapping[str, Any] | None = None) -> Detector:
    """Instantiate a detector from its type name and a params mapping.

    Raises:
        ConfigError: If ``type_name`` is unknown or the params are invalid.
    """
    params = params or {}
    try:
        factory = _FACTORIES[type_name]
    except KeyError:
        raise ConfigError(
            f"unknown detector type {type_name!r}; "
            f"available: {available_detectors()}"
        ) from None
    try:
        return factory(params)
    except KeyError as exc:
        raise ConfigError(
            f"detector {type_name!r}: missing required param {exc.args[0]!r}"
        ) from exc
