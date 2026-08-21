"""framesig — detect on-screen events in any video by pixel signature.

Define a region of interest plus a colour/brightness signature in YAML, and
framesig scans the video (sub-sampling frames, caching scores) to report the
timestamps where the event appears. It is game- and source-agnostic: it only
ever reasons about pixels, never about what produced them.

Typical use::

    from framesig import load_config, scan_video, detect_all

    config = load_config("signatures.yaml")
    result = scan_video("clip.mp4", config)
    events = detect_all(config, result)
    for name, evs in events.items():
        for e in evs:
            print(name, round(e.peak_t, 2))
"""

from __future__ import annotations

from .cache import ScoreCache
from .config import Config, Signature, load_config, parse_config
from .detectors import (
    Brightness,
    ChannelDominance,
    ColorFraction,
    Detector,
    SceneChange,
    available_detectors,
    build_detector,
)
from .errors import (
    ConfigError,
    DependencyError,
    FramesigError,
    VideoError,
)
from .events import Event, detect_events
from .regions import Region
from .scanner import ScanResult, detect_all, scan_video
from .videogen import GroundTruth, SampleVideo, generate_sample_video

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # config
    "Config",
    "Signature",
    "load_config",
    "parse_config",
    # regions & detectors
    "Region",
    "Detector",
    "Brightness",
    "ChannelDominance",
    "ColorFraction",
    "SceneChange",
    "available_detectors",
    "build_detector",
    # scanning & events
    "ScanResult",
    "scan_video",
    "detect_all",
    "Event",
    "detect_events",
    "ScoreCache",
    # sample generation
    "generate_sample_video",
    "SampleVideo",
    "GroundTruth",
    # errors
    "FramesigError",
    "ConfigError",
    "VideoError",
    "DependencyError",
]
