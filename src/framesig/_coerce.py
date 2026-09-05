"""Shared coercions for turning parsed YAML scalars into typed values.

YAML hands us whatever the document contained, so ``threshold: high`` arrives as
a ``str`` and a bare ``gain:`` arrives as ``None``. Every conversion that can
fail on user input goes through this module, which reports the failure as a
:class:`~framesig.errors.ConfigError` — the contract stated in
:mod:`framesig.errors` and in :func:`framesig.config.parse_config`.

It lives in its own module so that both :mod:`framesig.config` and
:mod:`framesig.regions` can use it without an import cycle.
"""

from __future__ import annotations

from typing import Any

from .errors import ConfigError


def as_number(field: str, value: Any) -> float:
    """Coerce ``value`` to ``float``.

    Args:
        field: Human-readable name of the field, used in the error message.
        value: The raw value straight out of the YAML document.

    Raises:
        ConfigError: If ``float()`` rejects ``value``.
    """
    try:
        return float(value)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{field} must be a number, got {value!r}") from exc


def as_bool(field: str, value: Any) -> bool:
    """Return ``value`` if it is a real ``bool``.

    Deliberately strict: ``bool("false")`` is ``True``, so quietly coercing a
    quoted YAML string would invert the user's intent.

    Raises:
        ConfigError: If ``value`` is not a ``bool``.
    """
    if not isinstance(value, bool):
        raise ConfigError(f"{field} must be true or false, got {value!r}")
    return value
