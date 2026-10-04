"""Text normalisation with offset preservation.

Adversarial payment emails hide account numbers behind invisible characters,
non-ASCII separators and homoglyph digits. A regex run over the raw text sees
nothing. ThreadGate normalises first, but it keeps a character map back to the
raw text so every finding can still be highlighted in the original email.

Only the *display* is derived from the raw text; every comparison in the
pipeline runs on the normalised text the model also saw. That keeps the model,
the token finder and the validator looking at exactly the same string.
"""

from __future__ import annotations

from dataclasses import dataclass

# Characters deleted outright: zero-width joiners/spaces, BOM, soft hyphen.
_DELETE = {
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM / zero width no-break space
    "\u00ad",  # soft hyphen
}

# Characters folded to an ASCII hyphen-minus.
_DASH = {
    "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015",
    "\u2212", "\u2043", "\uff0d", "\u02d7",
}

# Characters folded to a plain space.
_SPACE = {
    "\u00a0", "\u2007", "\u202f", "\u2009", "\u200a", "\u3000",
    "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005", "\u2006",
    "\t", "\r",
}

# Homoglyph digits folded to ASCII.
_DIGIT_FOLD = {}
for _i in range(10):
    _DIGIT_FOLD[chr(0xFF10 + _i)] = str(_i)  # fullwidth
    _DIGIT_FOLD[chr(0x0660 + _i)] = str(_i)  # arabic-indic
    _DIGIT_FOLD[chr(0x06F0 + _i)] = str(_i)  # extended arabic-indic


@dataclass
class NormalizedText:
    """Normalised text plus the map back to raw offsets."""

    raw: str
    text: str
    index_map: list[int]  # index_map[i] = index in `raw` of text[i]
    normalizations_applied: list[str]

    def to_raw_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a half-open span in normalised coords to a raw span."""
        if not self.index_map or start == end:
            return (0, 0)
        start = max(0, min(start, len(self.index_map) - 1))
        end = max(start + 1, min(end, len(self.index_map)))
        return (self.index_map[start], self.index_map[end - 1] + 1)


def normalize_text(raw: str) -> NormalizedText:
    out: list[str] = []
    idx: list[int] = []
    applied: set[str] = set()

    for i, ch in enumerate(raw):
        if ch in _DELETE:
            applied.add("invisible_removed")
            continue
        if ch in _DASH:
            out.append("-")
            idx.append(i)
            applied.add("dash_folded")
            continue
        if ch in _SPACE:
            out.append(" ")
            idx.append(i)
            applied.add("space_folded")
            continue
        if ch in _DIGIT_FOLD:
            out.append(_DIGIT_FOLD[ch])
            idx.append(i)
            applied.add("digit_folded")
            continue
        out.append(ch)
        idx.append(i)

    return NormalizedText(
        raw=raw,
        text="".join(out),
        index_map=idx,
        normalizations_applied=sorted(applied),
    )


def _collapse(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to one space, keeping an offset map."""
    out: list[str] = []
    offs: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            out.append(" ")
            offs.append(i)
            prev_ws = True
        else:
            out.append(ch)
            offs.append(i)
            prev_ws = False
    return "".join(out), offs


def find_span(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate `needle` in `haystack`, tolerating whitespace differences.

    Returns a half-open span in `haystack` coordinates, or None. Exact match is
    tried first so that ordinary quotes keep exact offsets; the whitespace-loose
    path exists because the model re-emits quotes across line breaks.
    """
    if not needle:
        return None
    i = haystack.find(needle)
    if i >= 0:
        return (i, i + len(needle))

    ch, coffs = _collapse(haystack)
    cn, _ = _collapse(needle)
    if not cn:
        return None
    j = ch.find(cn)
    if j < 0:
        return None
    start = coffs[j]
    end = coffs[min(j + len(cn) - 1, len(coffs) - 1)] + 1
    return (start, end)
