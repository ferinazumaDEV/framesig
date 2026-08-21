"""Regions of interest (ROIs).

A :class:`Region` describes a rectangular slice of the frame. Bounds may be
given either as fractions of the frame size (the default, resolution
independent) or as absolute pixels. The scanner resolves each region to an
integer pixel box once per video and then crops every sampled frame with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .errors import ConfigError

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1) in pixels


@dataclass(frozen=True)
class Region:
    """A rectangular region of interest.

    Attributes:
        name: Identifier used by signatures to reference this region.
        x: Left edge.
        y: Top edge.
        w: Width.
        h: Height.
        unit: ``"fraction"`` (default) interprets the bounds as fractions of the
            frame size, so the same region works at any resolution.
            ``"pixels"`` interprets them as absolute integers.
    """

    name: str
    x: float
    y: float
    w: float
    h: float
    unit: str = "fraction"

    def __post_init__(self) -> None:
        if self.unit not in ("fraction", "pixels"):
            raise ConfigError(
                f"region {self.name!r}: unit must be 'fraction' or 'pixels', "
                f"got {self.unit!r}"
            )
        if self.w <= 0 or self.h <= 0:
            raise ConfigError(f"region {self.name!r}: width and height must be positive")
        if self.unit == "fraction":
            if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
                raise ConfigError(
                    f"region {self.name!r}: fractional x/y must be within [0, 1]"
                )
            if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
                raise ConfigError(
                    f"region {self.name!r}: fractional box extends past the frame edge"
                )

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, Any]) -> "Region":
        """Build a region from a parsed YAML mapping."""
        allowed = {"x", "y", "w", "h", "unit"}
        unknown = set(data) - allowed
        if unknown:
            raise ConfigError(
                f"region {name!r}: unknown keys {sorted(unknown)}; "
                f"allowed keys are {sorted(allowed)}"
            )
        try:
            return cls(
                name=name,
                x=float(data["x"]),
                y=float(data["y"]),
                w=float(data["w"]),
                h=float(data["h"]),
                unit=str(data.get("unit", "fraction")),
            )
        except KeyError as exc:
            raise ConfigError(
                f"region {name!r}: missing required key {exc.args[0]!r}"
            ) from exc

    def resolve(self, frame_w: int, frame_h: int) -> Box:
        """Return the integer pixel box ``(x0, y0, x1, y1)`` for a given frame size.

        The box is always at least one pixel wide and tall, and is clamped to
        the frame bounds so cropping can never raise.
        """
        if self.unit == "fraction":
            x0 = int(round(self.x * frame_w))
            y0 = int(round(self.y * frame_h))
            x1 = int(round((self.x + self.w) * frame_w))
            y1 = int(round((self.y + self.h) * frame_h))
        else:
            x0, y0 = int(round(self.x)), int(round(self.y))
            x1, y1 = int(round(self.x + self.w)), int(round(self.y + self.h))

        x0 = max(0, min(x0, frame_w - 1))
        y0 = max(0, min(y0, frame_h - 1))
        x1 = max(x0 + 1, min(x1, frame_w))
        y1 = max(y0 + 1, min(y1, frame_h))
        return x0, y0, x1, y1

    def crop(self, frame: np.ndarray) -> np.ndarray:
        """Crop ``frame`` (an ``H x W x 3`` BGR array) to this region."""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = self.resolve(w, h)
        return frame[y0:y1, x0:x1]

    def fingerprint(self) -> dict[str, Any]:
        """Return the score-relevant fields for cache keying."""
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "unit": self.unit}
