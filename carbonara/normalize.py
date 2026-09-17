"""Deterministic normalization rules: dates, weights→grams, composition, references."""

from __future__ import annotations

import datetime
import re

from carbonara.references import material_vocab

__all__ = [
    "format_composition",
    "parse_composition",
    "parse_date",
    "parse_weight",
]

_WEIGHT = re.compile(r"([\d.]+)\s*(kg|g)", re.IGNORECASE)
_SHORTHAND = re.compile(r"(\d+)\s*/\s*(\d+)\s+([A-Za-z]{2,})\s*/\s*([A-Za-z]{2,})")
_PERCENT_PART = re.compile(r"(\d+)\s*%\s*(.+)")
_GRAMS_PER_KG = 1000


def parse_date(raw: str) -> datetime.date | None:
    """Parse an ISO date, or ``None`` for a blank or malformed value.

    >>> parse_date("2024-01-08")
    datetime.date(2024, 1, 8)
    >>> parse_date("2024-13-07") is None  # month 13
    True
    >>> parse_date("2024/02/31") is None  # slashes, invalid day
    True
    """
    try:
        return datetime.date.fromisoformat(raw.strip())
    except ValueError:
        return None


def parse_weight(raw: str) -> float | None:
    """Parse a weight to grams, or ``None`` if there is no number+unit to parse.

    The raw value and unit are preserved by the caller (the source row); this
    returns only the normalized grams.

    >>> parse_weight("200 g")
    200.0
    >>> parse_weight("0.49 kg")  # honest conversion of the given value
    490.0
    >>> parse_weight("0 g")
    0.0
    >>> parse_weight("") is None
    True
    """
    match = _WEIGHT.fullmatch(raw.strip())
    if match is None:
        return None
    value = float(match.group(1))
    return value * _GRAMS_PER_KG if match.group(2).lower() == "kg" else value


def _resolve_material(token: str) -> str:
    """Expand a shorthand code (``CO``) to its canonical material, else lowercase."""
    vocab = material_vocab()
    return vocab.code_to_canonical.get(token.upper(), token.strip().lower())


def parse_composition(raw: str) -> list[tuple[float, str]] | None:
    """Parse a composition to ordered ``(fraction, material)`` pairs, or ``None``.

    Handles the ``70/30 CO/PL`` shorthand and the ``80% cotton / 20% polyester``
    percent form; codes are expanded via the material vocabulary. The fractions
    are returned as given — checking that they sum to 1.0 is a validation step,
    not this parser's job.

    >>> parse_composition("70/30 CO/PL")
    [(0.7, 'cotton'), (0.3, 'polyester')]
    >>> parse_composition("100% cotton")
    [(1.0, 'cotton')]
    >>> parse_composition("80% cotton / 20% polyester")
    [(0.8, 'cotton'), (0.2, 'polyester')]
    """
    text = raw.strip()
    shorthand = _SHORTHAND.fullmatch(text)
    if shorthand is not None:
        p1, p2, c1, c2 = shorthand.groups()
        return [(int(p1) / 100, _resolve_material(c1)), (int(p2) / 100, _resolve_material(c2))]

    pairs: list[tuple[float, str]] = []
    for part in text.split("/"):
        match = _PERCENT_PART.fullmatch(part.strip())
        if match is None:
            return None
        pairs.append((int(match.group(1)) / 100, _resolve_material(match.group(2))))
    return pairs or None


def format_composition(pairs: list[tuple[float, str]]) -> str:
    """Render parsed pairs as the canonical composition string.

    >>> format_composition([(0.7, "cotton"), (0.3, "polyester")])
    '70% cotton / 30% polyester'
    """
    return " / ".join(f"{round(fraction * 100)}% {material}" for fraction, material in pairs)
