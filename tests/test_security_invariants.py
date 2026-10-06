"""Security invariants, stated as tests.

Each test here corresponds to a claim made in the README. If a claim cannot be
turned into a passing test, it does not go in the README.

All fourteen invariants are now enforced here or in
`test_verification_and_lineage.py`. Nothing in this file asserts that a
property is absent; the three that once were (replay protection, reference
version lineage, stale-reference escalation) are implemented and tested.
"""

from __future__ import annotations

import pytest

from threadgate.extract import compromised_extract, compromised_quote_extract, offline_extract
from threadgate.pipeline import run_case
from threadgate.schema import Claim, Extraction
from threadgate.validate import validate_extraction

ROOT_CASES = "data/cases/frozen_v2.json"


# --- the model cannot express a verdict -----------------------------------

def test_the_model_output_schema_cannot_express_a_verdict():
    """The AI cannot directly set the final state, because it has nowhere to put it."""
    forbidden = {"decision", "verdict", "risk", "risk_score", "is_fraud", "fraud",
                 "safe", "action", "approve", "clear", "hold", "allow"}
    assert not (set(Extraction.model_fields) & forbidden), set(Extraction.model_fields)
    assert not (set(Claim.model_fields) & forbidden), set(Claim.model_fields)


# --- monotonicity ----------------------------------------------------------

@pytest.mark.parametrize("extractor", [offline_extract, compromised_extract, compromised_quote_extract])
def test_a_hold_trigger_can_never_produce_a_clear(case_by_id_all, vendors, extractor):
    """HOLD cannot become CLEAR in the same run: triggers only ever escalate."""
    for case in case_by_id_all.values():
        r = run_case(case, vendors, extractor_fn=extractor)
        holding = [f for f in r.decision.findings if f.severity == "hold"]
        if holding:
            assert r.decision.decision == "HOLD", (
                f"{case['id']} had hold findings {[f.code for f in holding]} "
                f"but decided {r.decision.decision}"
            )
        # The test name promises CLEAR specifically, so check CLEAR.
        if r.decision.decision == "CLEAR":
            assert not holding, f"{case['id']} cleared with hold findings present"


# --- masked / partial destinations ----------------------------------------

def _masked_claim_extractor(nt, vendor):
    """A model that reports the destination only as a masked last-four."""
    return Extraction(
        intent="change_request",
        intent_evidence="Our account is unchanged at ****4455.",
        summary="account given in masked form",
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="****4455",
                      evidence="Our account is unchanged at ****4455.", confidence=0.8)],
    )


def test_a_masked_destination_never_matches_the_reference(case_by_id_all, vendors):
    """A partial value is not a match. Last-four agreement proves nothing."""
    case = case_by_id_all["TG-011"]  # a confirmation request, no change expected
    body = case["email"]
    case = {**case, "email": {**body, "body": body["body"] + "\n\nOur account is unchanged at ****4455."}}
    r = run_case(case, vendors, extractor_fn=_masked_claim_extractor)
    assert r.validation.verified_claims, "the masked claim should be admissible for the test"
    account_diffs = [d for d in r.decision.diffs if d.field == "account_number"]
    assert account_diffs and all(d.changed for d in account_diffs)
    assert r.decision.decision == "HOLD"


def test_a_full_destination_that_matches_is_not_a_change(vendors):
    """The counterpart: the exact account on file is not reported as a change."""
    from threadgate.compare import diff_claims
    from threadgate.normalize import normalize_text

    vendor = vendors["V-1001"]
    nt = normalize_text("A/C 50100234554455\nIFSC HDFC0001234")
    ex = Extraction(
        intent="no_change",
        intent_evidence="A/C 50100234554455",
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="50100234554455", evidence="A/C 50100234554455")],
    )
    v = validate_extraction(ex, nt)
    diffs = diff_claims(v.claims, vendor)
    assert diffs and not any(d.changed for d in diffs)


# --- evidence --------------------------------------------------------------

def test_unsupported_destination_evidence_cannot_become_trusted(case_by_id_all, vendors):
    """A claim whose value is nowhere in the email never enters the pipeline."""
    case = case_by_id_all["TG-001"]
    from threadgate.normalize import normalize_text
    from threadgate.pipeline import email_to_text

    nt = normalize_text(email_to_text(case["email"]))
    ex = Extraction(
        intent="change_request",
        intent_evidence="Account number: 50100234559821",
        claims=[Claim(field="account_number", new_value="1111222233334444",
                      evidence="Account number: 50100234559821")],
    )
    v = validate_extraction(ex, nt)
    assert not v.verified_claims
    assert all("value_not_in_email" in c.violations for c in v.claims)


def test_a_forged_verbatim_quote_cannot_justify_no_change(case_by_id_all, vendors):
    """I2b. The quote must support the verdict, not merely exist in the email."""
    for cid in ("TG-001", "TG-015", "TG-020", "TG-034"):
        r = run_case(case_by_id_all[cid], vendors, extractor_fn=compromised_quote_extract)
        assert r.decision.decision == "HOLD", cid
        assert any(f.code == "I2B_NO_CHANGE_INTENT_NOT_JUSTIFIED" for f in r.decision.findings), cid


# --- what is and is not implemented ---------------------------------------

def test_the_three_formerly_absent_invariants_are_really_implemented():
    """Replay protection, reference version lineage, stale-reference escalation.

    These were once documented as not built. This test is the tripwire against
    ever regressing to that state: it checks the modules exist and actually
    expose the behaviour, so deleting a module or hollowing out a function
    fails here rather than only in the dedicated file.
    """
    from threadgate import attestation as att
    from threadgate import clock as clk
    from threadgate import reference as ref

    # replay protection: a store that accepts once and refuses the second time
    ctx = att.VerificationContext("V-1", "R-1", "d" * 64, "v1")
    event = att.VerificationEvent("EV-1", "V-1", "R-1", "d" * 64, "v1")
    store = att.AttestationStore()
    assert store.consume(event, ctx, required=True).accepted
    assert store.consume(event, ctx, required=True).code == att.REPLAY

    # reference version lineage: v1 against a v2 record is refused
    v2 = att.VerificationContext("V-1", "R-1", "d" * 64, "v2")
    fresh = att.AttestationStore()
    assert fresh.consume(event, v2, required=True).code == att.REFERENCE_VERSION_MISMATCH

    # stale-reference escalation: the three states exist and the clock drives them
    assert set(ref.ReferenceState.__args__) == {"CURRENT", "STALE", "MISSING"}
    vendor = _vendors()["V-1001"]
    assert ref.reference_state(vendor, clk.fixed("2026-10-06")) == "CURRENT"
    assert ref.reference_state(vendor, clk.fixed("2027-06-01")) == "STALE"


def _vendors():
    from pathlib import Path

    from threadgate.records import load_vendors

    return load_vendors(Path(__file__).resolve().parents[1]
                        / "data" / "records" / "vendor_master.json")


def test_only_policy_produces_a_decision():
    """The decision type is constructed in policy, and nowhere else in the gate."""
    import subprocess

    out = subprocess.run(
        ["grep", "-rn", "Decision(decision=", "src/threadgate", "--include=*.py"],
        capture_output=True, text=True, cwd=".",
    ).stdout
    files = {line.split(":")[0] for line in out.splitlines() if line.strip()}
    # policy for the gate, baseline for the rules-only comparison, eval for the
    # AI-only ablation row. Nothing else in src/ may mint a decision.
    assert files <= {
        "src/threadgate/policy.py",
        "src/threadgate/baseline.py",
    }, files
