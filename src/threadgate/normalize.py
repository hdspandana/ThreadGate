"""Text normalisation with offset preservation.

Adversarial payment emails hide account numbers behind invisible characters,
non-ASCII separators and homoglyph digits. A regex run over the raw text sees
nothing. ThreadGate normalises first, but it keeps a character map back to the
raw text so every finding can still be highlighted in the original email.

Only the *display* is derived from the raw text; every comparison in the
pipeline runs on the normalised text the model also saw. That keeps the model,
the token finder and the validator looking at exactly the same string.

THE SUPPORTED SET

This is deliberate folding of an enumerated table, NOT Unicode NFKC. NFKC is
not an option here: it rewrites variable-length substrings (a ligature to two
letters, a compatibility character to a sequence), which would break the
one-character-to-one-index map that every span in this pipeline rests on. A
claim of "NFKC with correct offsets" would be a claim of NFKC plus a second,
separate offset bug.

What is folded, and only what is folded:

  1. Invisible characters, deleted: ZWSP ZWNJ ZWJ word-joiner BOM soft-hyphen
  2. Unusual dashes -> ASCII hyphen-minus
  3. Unusual spaces (NBSP, figure, thin, hair, ideographic, tabs, CR) -> space
  4. Homoglyph digits -> ASCII: fullwidth, Arabic-Indic, Extended Arabic-Indic
  5. Cyrillic letters that survive a side-by-side glance at a Latin one -> ASCII

Everything else passes through unchanged. Confusables outside table 5 are NOT
folded - Devanagari, Greek, Armenian, mathematical alphanumerics, fullwidth
Latin. Folding those would mean guessing at intent in scripts this system does
not handle, and a wrong guess corrupts a real string.

That is safe rather than merely tidy, because the security-critical check does
not depend on this table. The destination floor (I1) scans for ANY long digit
run and compares it against the record, so an account number written in
Devanagari or mathematical bold is still caught: Python's `\\d` matches every
Unicode decimal digit. Normalisation decides how well the KEYWORD rules and the
model read the email; the closed-world floor does not depend on it. See
tests/test_normalization_contract.py, which asserts exactly that - including
that an unsupported confusable does not produce a false CLEAR.
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

# Cyrillic characters that are visually identical to Latin ones, folded so that
# "Аccount" (Cyrillic А) does not slip past a keyword rule. Only look-alikes
# that survive a side-by-side glance are folded; this is not a general
# Unicode-confusable detector.
_CONFUSABLE = {
    "\u0410": "A", "\u0430": "a",  # А а
    "\u0412": "B", "\u0432": "b",  # В в (b is not a perfect match, kept for coverage)
    "\u0415": "E", "\u0435": "e",  # Е е
    "\u041a": "K", "\u043a": "k",  # К к
    "\u041c": "M", "\u043c": "m",  # М м
    "\u041d": "H", "\u043d": "h",  # Н н -> H
    "\u041e": "O", "\u043e": "o",  # О о
    "\u0420": "P", "\u0440": "p",  # Р р
    "\u0421": "C", "\u0441": "c",  # С с
    "\u0422": "T", "\u0442": "t",  # Т т
    "\u0423": "Y", "\u0443": "y",  # У у
    "\u0425": "X", "\u0445": "x",  # Х х
    "\u0456": "i", "\u0406": "I",  # і І
    "\u0455": "s", "\u0405": "S",  # ѕ Ѕ
    "\u04bb": "h",  # һ
    "\u0501": "d",  # ԁ
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
        if ch in _CONFUSABLE:
            out.append(_CONFUSABLE[ch])
            idx.append(i)
            applied.add("confusable_folded")
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
