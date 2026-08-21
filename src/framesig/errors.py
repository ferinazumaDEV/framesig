"""Exception hierarchy for framesig.

Every error raised by the library inherits from :class:`FramesigError`, so
callers can catch the whole family with a single ``except`` while still being
able to distinguish the interesting cases.
"""

from __future__ import annotations


class FramesigError(Exception):
    """Base class for every error raised by framesig."""


class ConfigError(FramesigError):
    """Raised when a configuration file is malformed or inconsistent.

    For example: an unknown detector type, a signature that references a region
    that was never declared, or a region whose fractional bounds fall outside
    the ``[0, 1]`` range.
    """


class VideoError(FramesigError):
    """Raised when a video file cannot be opened or decoded."""


class DependencyError(FramesigError):
    """Raised when an external dependency (e.g. the ``ffmpeg`` binary) is missing."""
