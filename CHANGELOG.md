# Changelog

Notable changes, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A release pipeline.** A tag now builds in a clean job, refuses artefacts
  containing a virtualenv or repository metadata, installs the wheel and the
  sdist into separate empty environments and exercises each, attests build
  provenance, publishes, and then installs from PyPI to check that what the
  index serves is what was built. Nothing can be published from a working tree.
- `scripts/smoke.py` — what the release pipeline runs against the *installed*
  package. It deliberately needs neither ffmpeg nor a video: it checks that the
  version matches the installed metadata, that every name in `__all__`
  resolves, that all four detectors are registered, that a config parses into
  real objects, and that the validator still **refuses** an unknown top-level
  key. Scanning a clip needs a decoder and a file, neither of which belongs in
  a release gate.
- `SECURITY.md`, which says plainly where the risk actually is: framesig opens
  untrusted video through OpenCV and FFmpeg, and that is where memory-safety
  bugs live — not in a few hundred lines of Python doing arithmetic on arrays.
- CI across Python 3.9–3.13, **installing ffmpeg first and verifying it is on
  `PATH`**. Without it the end-to-end cases skip, and a green run would mean
  less than it appears to.
- This changelog.

### Changed

- `actions/checkout` and `actions/setup-python` on v7; no deprecated-runtime
  warnings.

## [0.1.0] — 2026-09-05

First tagged release and first publication to PyPI.

### Fixed

- Configuration validation: unknown keys are refused rather than ignored, so a
  typo in a signature name fails loudly instead of silently detecting nothing.
- Event duration for a single-sample event.
- README accuracy, and tests covering the public API surface.

