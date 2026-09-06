# Security policy

## Supported versions

Only the latest release is supported. Fixes land on `main`; there are no backport branches.

| Version | Supported |
| --- | --- |
| 0.1.x | yes |
| older | no |

## Reporting a problem

Please report privately first.

1. Preferred: GitHub's private vulnerability reporting on this repository — **Security → Report a
   vulnerability** ([direct link](https://github.com/ferinazumaDEV/framesig/security/advisories/new)).
2. If that form is not available to you,
   [open an issue](https://github.com/ferinazumaDEV/framesig/issues) saying only that you have a
   security report and how to reach you. **Do not attach a malicious sample or paste exploit details
   into a public issue** — a private channel will be arranged from there.

Expect a first reply within a week. Small project, spare time; no formal SLA and no bug bounty.

Useful to include: the framesig, Python, OpenCV and ffmpeg versions, a minimal config, and what an
attacker gains.

## The real attack surface is the decoder, not framesig

framesig's job is to open a video file and look at its pixels. It does that through
**OpenCV (`cv2.VideoCapture`)**, which decodes through FFmpeg. Those decoders parse untrusted,
attacker-controlled binary data in C and C++, and that is where memory-safety bugs live — not in a
few hundred lines of Python doing arithmetic on numpy arrays.

So, if you scan video you did not produce:

- **Keep `opencv-python-headless` and your system ffmpeg current.** A framesig release cannot fix a
  decoder CVE; only updating the decoder can.
- **Treat it as processing hostile input.** Run it as an unprivileged user, in a container or VM, with
  no access to anything you would mind losing. This is the same advice that applies to any tool that
  hands a file to a media decoder.
- A crash or hang on a malformed file is most likely a decoder bug. Report it here anyway — knowing
  which files break it is useful — but the fix will usually live upstream.

## What framesig does with your files and your machine

- **It reads the video you point it at, and nothing else.** No directory is scanned, no other file is
  opened.
- **It writes only where you ask it to**: the `--output` events JSON, the `--chart` PNG, the demo's
  `--out-dir`, and the cache directory if you enable one. Cache entries are plain JSON named `scores_<digest>.json`; they hold
  scores and timings, never frame content. Nothing is encrypted, and the directory keeps whatever
  permissions your umask gives it.
- **Configs are parsed with `yaml.safe_load`.** A config file cannot construct Python objects or
  execute code, however it is crafted.
- **ffmpeg is never run through a shell.** It is only used to render the synthetic demo clip: the
  binary is resolved with `shutil.which`, and the command is passed as an argument list, so a path
  containing spaces, quotes or `;` is an argument and never a command.

## Network and telemetry

**framesig makes no network connections whatsoever.** It does not check for updates, report usage, or
fetch anything. It works fully offline, and the only thing it ever touches is the files you name.

## Out of scope

Reports that a caller can hurt themselves — writing the cache into a world-readable directory, or
deliberately feeding the tool a file crafted to crash the decoder on a machine that matters — are
documentation issues rather than vulnerabilities. Still welcome as issues.
