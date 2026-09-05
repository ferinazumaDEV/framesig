"""Declarative configuration.

A framesig run is described entirely by a small YAML document: how densely to
sample the video, which regions of interest exist, and which signatures to
evaluate over them. This module parses that document into validated dataclasses.

Example:
    sample_fps: 10
    regions:
      hud_top:   {x: 0.0, y: 0.0,  w: 1.0,  h: 0.55}
      kill_feed: {x: 0.08, y: 0.74, w: 0.84, h: 0.18}
    signatures:
      - name: death_screen
        region: hud_top
        detector: channel_dominance
        params: {channel: red, gain: 2.0}
        threshold: 0.30
        min_duration: 0.1
        merge_gap: 0.25
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from ._coerce import as_number
from .detectors import Detector, build_detector
from .errors import ConfigError
from .regions import Region

_ALLOWED_TOP_KEYS = {"sample_fps", "regions", "signatures", "cache_dir"}

_ALLOWED_SIGNATURE_KEYS = {
    "name",
    "region",
    "detector",
    "params",
    "threshold",
    "min_duration",
    "merge_gap",
}


@dataclass
class Signature:
    """One thing to look for: a detector applied to a region, plus event rules.

    Attributes:
        name: Unique identifier, used in output and cache keys.
        region: The :class:`~framesig.regions.Region` to crop before scoring.
        detector: The instantiated :class:`~framesig.detectors.Detector`.
        threshold: Minimum score for a sample to count as active.
        min_duration: Discard events shorter than this many seconds.
        merge_gap: Merge active runs separated by at most this many seconds.
    """

    name: str
    region: Region
    detector: Detector
    threshold: float = 0.5
    min_duration: float = 0.0
    merge_gap: float = 0.0

    def score_fingerprint(self) -> dict[str, Any]:
        """Fields that change the *scores* (not the thresholds)."""
        return {"region": self.region.fingerprint(), "detector": self.detector.fingerprint()}


@dataclass
class Config:
    """A fully validated framesig configuration.

    Attributes:
        sample_fps: Target sampling rate in frames per second. The scanner
            processes roughly this many frames per second of video, regardless
            of the source frame rate.
        regions: Declared regions, keyed by name.
        signatures: The signatures to evaluate.
        cache_dir: Optional directory for the score cache. ``None`` defers to
            the scanner's default (a ``.framesig_cache`` folder next to the video).
    """

    sample_fps: float = 5.0
    regions: dict[str, Region] = field(default_factory=dict)
    signatures: list[Signature] = field(default_factory=list)
    cache_dir: str | None = None

    def score_fingerprint(self) -> dict[str, Any]:
        """The score-relevant projection of the config, for cache keying."""
        return {
            "sample_fps": self.sample_fps,
            "signatures": {s.name: s.score_fingerprint() for s in self.signatures},
        }


def _parse_signature(raw: Mapping[str, Any], regions: Mapping[str, Region]) -> Signature:
    if not isinstance(raw, Mapping):
        raise ConfigError(f"each signature must be a mapping, got {type(raw).__name__}")
    unknown = set(raw) - _ALLOWED_SIGNATURE_KEYS
    if unknown:
        raise ConfigError(
            f"signature has unknown keys {sorted(unknown)}; "
            f"allowed: {sorted(_ALLOWED_SIGNATURE_KEYS)}"
        )
    try:
        name = str(raw["name"])
        region_name = str(raw["region"])
        detector_type = str(raw["detector"])
    except KeyError as exc:
        raise ConfigError(f"signature missing required key {exc.args[0]!r}") from exc

    if region_name not in regions:
        raise ConfigError(
            f"signature {name!r} references unknown region {region_name!r}; "
            f"declared regions: {sorted(regions)}"
        )

    params = raw.get("params") or {}
    if not isinstance(params, Mapping):
        raise ConfigError(
            f"signature {name!r}: 'params' must be a mapping, "
            f"got {type(params).__name__}"
        )

    detector = build_detector(detector_type, params)
    return Signature(
        name=name,
        region=regions[region_name],
        detector=detector,
        threshold=as_number(f"signature {name!r}: threshold", raw.get("threshold", 0.5)),
        min_duration=as_number(
            f"signature {name!r}: min_duration", raw.get("min_duration", 0.0)
        ),
        merge_gap=as_number(f"signature {name!r}: merge_gap", raw.get("merge_gap", 0.0)),
    )


def parse_config(data: Mapping[str, Any]) -> Config:
    """Build a :class:`Config` from an already-parsed mapping.

    Raises:
        ConfigError: On any structural or semantic problem.
    """
    if not isinstance(data, Mapping):
        raise ConfigError("top-level config must be a mapping")

    unknown = set(data) - _ALLOWED_TOP_KEYS
    if unknown:
        raise ConfigError(
            f"unknown top-level keys {sorted(unknown)}; "
            f"allowed: {sorted(_ALLOWED_TOP_KEYS)}"
        )

    sample_fps = as_number("sample_fps", data.get("sample_fps", 5.0))
    if sample_fps <= 0:
        raise ConfigError("sample_fps must be positive")

    raw_regions = data.get("regions") or {}
    if not isinstance(raw_regions, Mapping):
        raise ConfigError("'regions' must be a mapping of name -> box")
    regions = {name: Region.from_mapping(name, box) for name, box in raw_regions.items()}

    raw_signatures = data.get("signatures") or []
    if not isinstance(raw_signatures, list):
        raise ConfigError("'signatures' must be a list")
    signatures = [_parse_signature(s, regions) for s in raw_signatures]

    if not signatures:
        raise ConfigError("config declares no signatures; nothing to detect")

    names = [s.name for s in signatures]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ConfigError(f"duplicate signature names: {sorted(dupes)}")

    cache_dir = data.get("cache_dir")
    return Config(
        sample_fps=sample_fps,
        regions=regions,
        signatures=signatures,
        cache_dir=str(cache_dir) if cache_dir is not None else None,
    )


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config from disk."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {str(path)!r}: {exc}") from exc
    if data is None:
        raise ConfigError(f"config {str(path)!r} is empty")
    return parse_config(data)
