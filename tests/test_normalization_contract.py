"""The normalisation contract.

Two claims are being pinned here.

The first is what normalisation does. It is an enumerated folding table, not
Unicode NFKC, and that is a deliberate choice rather than a shortcut: NFKC
rewrites variable-length substrings, which breaks the one-character-to-one-index
map that every span, highlight and evidence check in this pipeline rests on. So
the supported set is stated explicitly and each entry is tested.

The second is the one that matters for safety: an unsupported confusable must
not produce a false CLEAR. Normalisation decides how well the keyword rules and
the model read an email. It does NOT carry the security-critical check, because
the destination floor scans for any long digit run and Python's `\\d` matches
every Unicode decimal digit. An account number in Devanagari or mathematical
bold is still caught. That property is asserted end to end, because a future
change that made the floor depend on the folding table would quietly reintroduce
a homoglyph bypass.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.clock import fixed  # noqa: E402
from threadgate.extract import offline_extract  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.records import load_vendors  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CLOCK = fixed("2026-10-06")

# The attack account: a real-looking number that is not on file for V-1001.
ATTACK = "50100234559821"
DIGITS = [int(c) for c in ATTACK]


def fullwidth(n: str) -> str:
    return "".join(chr(0xFF10 + int(c)) for c in n)


def arabic(n: str) -> str:
    return "".join(chr(0x0660 + int(c)) for c in n)


def ext_arabic(n: str) -> str:
    return "".join(chr(0x06F0 + int(c)) for c in n)


def devanagari(n: str) -> str:
    return "".join(chr(0x0966 + int(c)) for c in n)


def math_bold(n: str) -> str:
    return "".join(chr(0x1D7CE + int(c)) for c in n)


# ---------------------------------------------------------------------------
# 1. the supported set
# ---------------------------------------------------------------------------
def test_fullwidth_digits_are_folded():
    nt = normalize_text(fullwidth(ATTACK))
    assert nt.text == ATTACK
    assert "digit_folded" in nt.normalizations_applied


def test_arabic_indic_digits_are_folded():
    assert normalize_text(arabic(ATTACK)).text == ATTACK


def test_extended_arabic_indic_digits_are_folded():
    assert normalize_text(ext_arabic(ATTACK)).text == ATTACK


@pytest.mark.parametrize(
    "invisible", ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"]
)
def test_invisible_characters_are_removed(invisible):
    """Zero-width joiners/spaces, BOM and soft hyphen.

    Soft hyphen is the interesting one: it is invisible at normal rendering and
    is the classic way to break a scanner while leaving the text readable.
    """
    nt = normalize_text(f"5010{invisible}0234")
    assert nt.text == "50100234"
    assert "invisible_removed" in nt.normalizations_applied


@pytest.mark.parametrize(
    "dash", ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015",
             "\u2212", "\u2043", "\uff0d", "\u02d7"]
)
def test_unusual_dashes_are_folded(dash):
    nt = normalize_text(f"5010{dash}0234")
    assert nt.text == "5010-0234"
    assert "dash_folded" in nt.normalizations_applied


@pytest.mark.parametrize(
    "space", ["\u00a0", "\u2007", "\u202f", "\u2009", "\u200a", "\u3000", "\t", "\r"]
)
def test_unusual_spaces_are_folded(space):
    assert normalize_text(f"5010{space}0234").text == "5010 0234"


@pytest.mark.parametrize(
    ("cyrillic", "latin"),
    [("А", "A"), ("Е", "E"), ("О", "O"), ("Р", "P"),
     ("С", "C"), ("Т", "T"), ("Х", "X"), ("а", "a"), ("е", "e"), ("о", "o")],
)
def test_cyrillic_lookalikes_are_folded(cyrillic, latin):
    """The table the module documents. It was defined but never applied."""
    nt = normalize_text(cyrillic)
    assert nt.text == latin
    assert "confusable_folded" in nt.normalizations_applied


def test_a_cyrillic_keyword_becomes_matchable():
    """The point of the fold: "Аccount" must reach the keyword rules."""
    assert normalize_text("Аccount number").text == "Account number"


# ---------------------------------------------------------------------------
# 2. what is explicitly NOT folded
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("fullwidth latin", "Ａccount"),
        ("devanagari digits", devanagari("5010")),
        ("mathematical bold digits", math_bold("5010")),
        ("greek omicron", "ο"),
        ("armenian", "օ"),
    ],
)
def test_confusables_outside_the_table_are_left_alone(name, text):
    """Folding these would mean guessing at scripts this system does not handle.

    A wrong guess corrupts a real string, which is worse than not folding.
    """
    nt = normalize_text(text)
    assert nt.text == text
    assert nt.normalizations_applied == []


def test_the_module_does_not_claim_nfkc():
    """NFKC would break the offset map. Assert it is not reached for."""
    assert "unicodedata" not in normalize_text.__globals__
    assert not hasattr(normalize_text, "__wrapped__")


def test_nfkc_would_change_lengths_and_therefore_break_offsets():
    """Documents why NFKC was rejected, with the actual counter-example."""
    ligature = "\ufb01"  # ﬁ
    assert len(unicodedata.normalize("NFKC", ligature)) == 2
    # The folding table leaves it at one character, so the index map holds.
    assert normalize_text(ligature).text == ligature


# ---------------------------------------------------------------------------
# 3. offsets survive every fold
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        fullwidth(ATTACK),
        arabic(ATTACK),
        ext_arabic(ATTACK),
        devanagari(ATTACK),
        math_bold(ATTACK),
        "5010\u200b0234\u00ad5598\u201121",
        "Аccount: 5010–0234‑5598—21",
    ],
)
def test_the_index_map_stays_aligned_with_the_normalised_text(raw):
    """One entry per output character, in range, monotonic.

    Every span in the pipeline - evidence, token, snippet - is computed against
    `nt.text` and mapped back through this list. If it drifts by one, findings
    highlight the wrong words, and a highlight that lies is worse than none.
    """
    nt = normalize_text(raw)
    assert len(nt.index_map) == len(nt.text)
    assert all(0 <= i < len(raw) for i in nt.index_map)
    assert nt.index_map == sorted(nt.index_map)
    # and round-trip through the public span API
    for i in range(len(nt.text)):
        s, e = nt.to_raw_span(i, i + 1)
        assert 0 <= s < e <= len(raw)


# ---------------------------------------------------------------------------
# 4. the safety property: no false CLEAR from an unsupported confusable
# ---------------------------------------------------------------------------
def _run_with(account_rendering: str, keyword: str = "Account number"):
    case = {
        "id": "SYNTH",
        "vendor_id": "V-1001",
        "expected_decision": None,
        "email": {
            "from": "Meera Iyer <meera.iyer@northwind.example>",
            "reply_to": "meera.iyer@northwind.example",
            "subject": "Updated bank account",
            "received_at": "2026-10-06T09:12:00+05:30",
            "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
            "body": (
                "Hi Team,\n\nPlease update the account used for our payments "
                f"with immediate effect.\n\n{keyword}: {account_rendering}\n"
                "IFSC: HDFC0001234\nBeneficiary: Northwind Logistics Pvt Ltd\n\n"
                "Thanks\n"
            ),
        },
    }
    return run_case(case, VENDORS, extractor_fn=offline_extract, clock=CLOCK)


OBFUSCATIONS = {
    "plain": ATTACK,
    "spaced": "5010 0234 5598 21",
    "hyphenated": "5010-0234-5598-21",
    "fullwidth": fullwidth(ATTACK),
    "arabic-indic": arabic(ATTACK),
    "ext-arabic-indic": ext_arabic(ATTACK),
    "zero-width": "5010\u200b0234\u200b5598\u200b21",
    "soft-hyphen": "5010\u00ad0234\u00ad5598\u00ad21",
    "unusual-dashes": "5010\u20110234\u20125598\u201321",
    "nbsp": "5010\u00a00234\u00a05598\u00a021",
    # deliberately unsupported: must still be caught
    "devanagari": devanagari(ATTACK),
    "math-bold": math_bold(ATTACK),
}


@pytest.mark.parametrize("name", list(OBFUSCATIONS))
def test_every_obfuscation_including_unsupported_ones_still_holds(name):
    """An obfuscated attack account must never come back CLEAR.

    The unsupported rows are the load-bearing ones. They pass only because the
    destination floor scans digit runs rather than depending on this table, so
    this test is what stops a future change from making the floor depend on
    normalisation and reopening a homoglyph bypass.
    """
    r = _run_with(OBFUSCATIONS[name])
    assert r.decision.decision != "CLEAR", (
        f"{name} obfuscation produced {r.decision.decision} "
        f"(reasons: {r.decision.reasons})"
    )


@pytest.mark.parametrize("name", list(OBFUSCATIONS))
def test_every_obfuscation_still_names_the_unknown_account(name):
    """Not merely non-CLEAR: the floor has to see the number itself."""
    r = _run_with(OBFUSCATIONS[name])
    assert "I1_UNKNOWN_ACCOUNT_TOKEN" in [f.code for f in r.decision.findings], name


def test_acyrillic_keyword_does_not_hide_the_account():
    """The keyword is homoglyphed; the floor must not care."""
    r = _run_with(ATTACK, keyword="Аccount number")
    assert r.decision.decision != "CLEAR"
    assert "I1_UNKNOWN_ACCOUNT_TOKEN" in [f.code for f in r.decision.findings]
