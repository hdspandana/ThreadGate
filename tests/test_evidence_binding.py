"""The quote is the warrant for the value.

A claim says "the email asks to change field F to value V, and here is the
sentence that says so". If V is not in that sentence, the sentence does not
warrant the claim - however confident the model is and however many times V
happens to appear elsewhere in the same message.

That is not a hypothetical. Payment mail routinely carries several numbers: an
account being closed, an account being opened, an invoice total, a reference
from an earlier thread. Before this fix the validator searched the whole email
before it looked at the quote, so a claim quoting the sentence about the new
account while carrying the number of the old one validated cleanly, and the
analyst was shown a highlighted quote that said the opposite of the value
attached to it.

Reading an email is the model's job. Deciding whether the model's quote
supports the model's own value is not, and it is the part that has to be code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.schema import Claim, Extraction  # noqa: E402
from threadgate.validate import validate_extraction  # noqa: E402

# One email, two accounts, two sentences. Every number below is "in the email",
# so a validator that searches the email rather than the quote passes them all.
EMAIL = (
    "Hi Team,\n\n"
    "Our old account 50100234551111 is being closed at the end of the month.\n"
    "Please remit all future payments to our new account 50100234552222, "
    "IFSC HDFC0001234.\n"
    "The outstanding invoice total is 50100234553333.\n\n"
    "Thanks\n"
)

OLD_ACCOUNT = "50100234551111"
NEW_ACCOUNT = "50100234552222"
INVOICE_TOTAL = "50100234553333"

SENTENCE_ABOUT_THE_NEW_ACCOUNT = (
    "Please remit all future payments to our new account 50100234552222, "
    "IFSC HDFC0001234."
)
SENTENCE_ABOUT_THE_OLD_ACCOUNT = (
    "Our old account 50100234551111 is being closed at the end of the month."
)


def validate(new_value: str | None, evidence: str, field: str = "account_number"):
    ex = Extraction(
        intent="change_request",
        intent_evidence=SENTENCE_ABOUT_THE_NEW_ACCOUNT,
        summary="s",
        claims=[
            Claim(
                field=field,
                new_value=new_value,
                evidence=evidence,
                confidence=0.9,
            )
        ],
    )
    return validate_extraction(ex, normalize_text(EMAIL))


# ---------------------------------------------------------------------------
# the property
# ---------------------------------------------------------------------------
def test_a_value_inside_its_own_evidence_is_admissible():
    r = validate(NEW_ACCOUNT, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert len(r.verified_claims) == 1
    assert r.violations == [] or "value_not_in_email" not in r.violations


def test_a_value_elsewhere_in_the_email_is_not_admissible():
    """The bug. Both numbers are in the email; only one is in the quote."""
    r = validate(OLD_ACCOUNT, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert r.verified_claims == [], (
        "a value that is not in the quoted sentence was admitted because it "
        "appears elsewhere in the email"
    )


def test_a_value_quoted_from_the_wrong_sentence_is_not_admissible():
    """The two-account case that motivated the fix.

    The claim is "the new account is 1111", the quote is the sentence about
    2222, and 1111 is in the email. Before the fix this validated, and the
    analyst would have been shown a highlighted sentence saying the new account
    is 2222 next to a value of 1111.
    """
    r = validate(OLD_ACCOUNT, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert r.verified_claims == []
    assert r.dropped_claims == 1


def test_no_number_from_the_email_is_admissible_under_an_unrelated_quote():
    """A quote about something else is not a warrant for any value."""
    for candidate in (OLD_ACCOUNT, NEW_ACCOUNT, INVOICE_TOTAL):
        r = validate(candidate, "The outstanding invoice total is.")
        assert r.verified_claims == [], candidate


def test_the_value_span_lies_inside_the_evidence_span():
    """Where the UI highlights the value, it must be within the quote."""
    r = validate(NEW_ACCOUNT, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    claim = r.verified_claims[0]
    assert claim.evidence_span_norm is not None
    assert claim.value_span_norm is not None
    v0, v1 = claim.value_span_norm
    e0, e1 = claim.evidence_span_norm
    assert e0 <= v0 and v1 <= e1, (
        f"value span {(v0, v1)} is outside evidence span {(e0, e1)}"
    )


# ---------------------------------------------------------------------------
# what must keep working
# ---------------------------------------------------------------------------
def test_a_deletion_claim_with_no_new_value_is_still_admissible():
    """The no-new-value case has to survive: there is no value to bind."""
    r = validate(None, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert len(r.verified_claims) == 1
    assert r.verified_claims[0].value_span_norm is None


def test_an_empty_new_value_is_treated_as_no_value():
    r = validate("", SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert len(r.verified_claims) == 1


def test_a_value_nowhere_in_the_email_at_all_is_rejected():
    r = validate("99999999999999", SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert r.verified_claims == []


def test_separator_differences_inside_the_quote_still_match():
    """The model may re-emit a value with different spacing than the quote.

    Binding the value to the quote must not degenerate into a byte comparison;
    the containment test is separator-insensitive, only the *location* is now
    constrained.
    """
    r = validate("5010 0234 5522 22", SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    assert len(r.verified_claims) == 1, (
        "a spaced-out rendering of a value that IS in the quote was rejected"
    )


def test_a_non_verbatim_evidence_quote_is_still_rejected():
    r = validate(NEW_ACCOUNT, "This sentence is not in the email at all.")
    assert r.verified_claims == []


def test_a_claim_with_a_value_but_no_evidence_is_not_admissible():
    r = validate(NEW_ACCOUNT, "")
    assert r.verified_claims == []


# ---------------------------------------------------------------------------
# end-to-end: the misquote cannot buy a decision
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "quoted_value", [OLD_ACCOUNT, NEW_ACCOUNT, INVOICE_TOTAL]
)
def test_a_misquoted_value_never_produces_a_diff(quoted_value):
    """A dropped claim must not reach the comparator.

    If it did, the value would be compared against the record and could produce
    a real diff - a decision resting on a quote that does not contain the value
    it is supposed to support.
    """
    from threadgate.compare import diff_claims
    from threadgate.records import load_vendors

    vendors = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
    r = validate(quoted_value, SENTENCE_ABOUT_THE_NEW_ACCOUNT)
    diffs = diff_claims(r.verified_claims, vendors["V-1001"])
    if quoted_value == NEW_ACCOUNT:
        assert diffs, "the correctly-quoted value should produce a diff"
    else:
        assert [d for d in diffs if d.field == "account_number"] == []
