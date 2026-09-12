# Changelog

Notable changes, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **A corrupt cache file no longer breaks a scan.** `ScoreCache.load` documented
  that an unreadable file is a miss, but caught only `(OSError,
  json.JSONDecodeError)`. `UnicodeDecodeError` is a `ValueError`, so a cache
  file holding arbitrary bytes — a truncated write, a file from another tool, a
  disk error — raised straight out of `load()` and killed the scan the cache
  exists to speed up. One `except ValueError` now covers both, without widening
  to a bare `except Exception` that would hide real bugs.

- **A well-formed but useless cache entry is now a miss too.** Validation
  checked only that the payload was a dict with the right version, so
  `{"version": 2}` counted as a hit and the consumer died on a `KeyError` far
  from the actual problem. The keys `ScanResult.from_payload` reads are checked
  before the entry is handed back.

- **Two writers sharing a cache directory no longer collide.** Every write of a
  key used the same temporary name, so the first `replace()` moved the shared
  temporary away and the second failed with `FileNotFoundError` on a file it had
  legitimately written. Each write now gets its own temporary from `mkstemp`, in
  the destination directory so the replace stays a rename within one filesystem
  and therefore atomic. Concurrency beyond that is last-writer-wins, and now
  documented as such — two writers for the same key produce the same scores,
  because the key is a digest of the video and the score-relevant config.

Reported in the external audit of the `2026.09.0` ecosystem snapshot as F04 and
F05.

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

