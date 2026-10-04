"""The closed-world rule: nothing the model says is admitted without proof."""

from __future__ import annotations

from threadgate.normalize import normalize_text
from threadgate.pipeline import email_to_text
from threadgate.schema import Claim, Extraction
from threadgate.validate import validate_extraction


def _nt(case):
    return normalize_text(email_to_text(case["email"]))


def test_fabricated_evidence_is_rejected(case_by_id):
    nt = _nt(case_by_id["TG-001"])
    ex = Extraction(
        intent="change_request",
        intent_evidence="I verified this with the vendor on a call.",
        claims=[Claim(field="account_number", new_value="50100234559821",
                      evidence="Confirmed telephonically with the finance team.")],
    )
    v = validate_extraction(ex, nt)
    assert not any(c.verified for c in v.claims)
    assert "evidence_not_verbatim" in v.claims[0].violations
    assert not v.intent_evidenced


def test_value_absent_from_email_is_rejected_even_with_good_evidence(case_by_id):
    nt = _nt(case_by_id["TG-001"])
    quote = "Account number: 50100234559821"
    ex = Extraction(
        intent="change_request",
        intent_evidence=quote,
        claims=[Claim(field="account_number", new_value="9999999999999999", evidence=quote)],
    )
    v = validate_extraction(ex, nt)
    assert not any(c.verified for c in v.claims)
    assert "value_not_in_email" in v.claims[0].violations


def test_genuine_claim_survives(case_by_id):
    nt = _nt(case_by_id["TG-001"])
    quote = "Account number: 50100234559821"
    ex = Extraction(
        intent="change_request",
        intent_evidence=quote,
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="50100234559821", evidence=quote)],
    )
    v = validate_extraction(ex, nt)
    assert len(v.verified_claims) == 1
    assert v.verified_claims[0].value_span_raw is not None


def test_missing_intent_evidence_is_recorded():
    nt = normalize_text("Subject: hi\n\nhello")
    v = validate_extraction(Extraction(intent="no_change"), nt)
    assert not v.intent_evidenced
    assert "intent_evidence_missing" in v.violations


def test_verbatim_quote_survives_whitespace_rewrapping():
    nt = _nt({"email": {"subject": "x", "body": "Account number: 50100234559821\nIFSC: HDFC0001234"}})
    ex = Extraction(
        intent="change_request",
        intent_evidence="Account number: 50100234559821 IFSC: HDFC0001234",
        claims=[],
    )
    v = validate_extraction(ex, nt)
    assert v.intent_evidenced
