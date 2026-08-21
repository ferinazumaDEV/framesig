"""Shared fixtures and helpers for the framesig test suite."""

from __future__ import annotations

import shutil

import numpy as np
import pytest

from framesig.videogen import SampleVideo, generate_sample_video

HAS_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg binary not on PATH")


def solid(color_bgr: tuple[int, int, int], size: int = 24) -> np.ndarray:
    """Return a ``size x size`` BGR image filled with a single colour."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:, :] = color_bgr
    return img


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> SampleVideo:
    """Render the synthetic HUD clip once for the whole test session."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg binary not on PATH")
    out = tmp_path_factory.mktemp("framesig") / "sample.mp4"
    return generate_sample_video(out)
