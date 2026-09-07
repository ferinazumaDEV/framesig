#!/usr/bin/env python3
"""Does the installed framesig actually work?

Run against a freshly installed wheel or sdist, never the repository.

Offline and without ffmpeg on purpose: scanning a clip needs a decoder and a
file, neither of which belongs in a release gate. What this checks is that the
package imports, that its detector registry is populated, and that a config
parses into real objects — the part that breaks when a build ships a truncated
package or a renamed module.
"""
from __future__ import annotations

import importlib.metadata
import sys

DISTRIBUTION = "framesig"


def main() -> int:
    import framesig
    from framesig import Brightness, Region, available_detectors, parse_config

    installed = importlib.metadata.version(DISTRIBUTION)
    if framesig.__version__ != installed:
        print(f"FAIL  __version__ is {framesig.__version__} but metadata says {installed}")
        return 1
    print(f"ok    {DISTRIBUTION} {installed}")

    missing = [n for n in framesig.__all__ if not hasattr(framesig, n)]
    if missing:
        print(f"FAIL  __all__ advertises names that do not exist: {missing}")
        return 1
    print(f"ok    all {len(framesig.__all__)} public names resolve")

    # The registry is what makes a config mean anything.
    detectors = available_detectors()
    for expected in ("brightness", "channel_dominance", "color_fraction", "scene_change"):
        if expected not in detectors:
            print(f"FAIL  detector {expected!r} missing from {detectors}")
            return 1
    print(f"ok    {len(detectors)} detectors registered: {', '.join(sorted(detectors))}")

    # A region is a fraction of the frame; the constructor is the contract.
    region = Region(name="hud", x=0.1, y=0.8, w=0.3, h=0.15)
    if region.name != "hud":
        print(f"FAIL  Region did not keep its name: {region}")
        return 1
    print("ok    Region accepts fractional coordinates")

    if Brightness(invert=True) is None:
        print("FAIL  Brightness could not be constructed")
        return 1
    print("ok    a detector constructs")

    # Config parsing is where a user's YAML becomes objects.
    # The shape a user's YAML actually has: named regions at the top level,
    # signatures referring to them by name. Mirrors examples/flash.yaml.
    config = parse_config({
        "sample_fps": 5,
        "regions": {"hud": {"x": 0.1, "y": 0.8, "w": 0.3, "h": 0.15}},
        "signatures": [{
            "name": "flash",
            "region": "hud",
            "detector": "brightness",
            "threshold": 0.6,
        }],
    })
    if not config.signatures or config.signatures[0].name != "flash":
        print(f"FAIL  parse_config did not build the signature: {config}")
        return 1
    print("ok    parse_config turns a mapping into a Config with its signatures")

    # The validator is a feature: unknown keys must be refused, not ignored.
    from framesig.errors import ConfigError
    try:
        parse_config({"video": "clip.mp4"})
    except ConfigError:
        print("ok    parse_config refuses unknown top-level keys")
    else:
        print("FAIL  parse_config accepted an unknown top-level key")
        return 1

    print("\nsmoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
