"""The security properties, expressed as tests.

If any of these fail, the design claim is false and the project should not be
submitted as a fraud control.
"""

from __future__ import annotations

import pytest

from threadgate.baseline import rules_only, rules_only_normalized
from threadgate.extract import compromised_extract, compromised_quote_extract, offline_extract
from threadgate.pipeline import run_case

TOKEN_BEARING_HOLDS = ["TG-001", "TG-002", "TG-005", "TG-006", "TG-015", "TG-016", "TG-017", "TG-018", "TG-019"]
ALL_HOLDS = TOKEN_BEARING_HOLDS + ["TG-003", "TG-004", "TG-020"]


@pytest.mark.parametrize("cid", ALL_HOLDS)
@pytest.mark.parametrize("attack", [compromised_extract, compromised_quote_extract])
def test_a_steered_model_cannot_release_a_hold(case_by_id, vendors, cid, attack):
    """The core claim: safety does not depend on the model's honesty."""
    r = run_case(case_by_id[cid], vendors, extractor_fn=attack)
    assert r.decision.decision == "HOLD", f"{cid} released under {attack.__name__}"


@pytest.mark.parametrize("attack", [compromised_extract, compromised_quote_extract])
def test_steered_model_never_produces_a_review(case_by_id, vendors, attack):
    for cid in case_by_id:
        r = run_case(case_by_id[cid], vendors, extractor_fn=attack)
        assert r.decision.decision != "REVIEW"


def test_negation_cases_are_not_held_with_the_offline_double(case_by_id, vendors):
    for cid in ("TG-007", "TG-008", "TG-009", "TG-010", "TG-011"):
        r = run_case(case_by_id[cid], vendors, extractor_fn=offline_extract)
        assert r.decision.decision == "CLEAR", cid


def test_pre_registered_account_is_reviewed(case_by_id, vendors):
    r = run_case(case_by_id["TG-012"], vendors, extractor_fn=offline_extract)
    assert r.decision.decision == "REVIEW"
    assert any(d.pre_registered for d in r.decision.diffs)


def test_tokenless_request_is_held_as_unverifiable(case_by_id, vendors):
    r = run_case(case_by_id["TG-020"], vendors, extractor_fn=offline_extract)
    assert r.decision.decision == "HOLD"
    assert "unverifiable_no_values" in r.decision.reasons


def test_hold_produces_a_call_back_checklist(case_by_id, vendors):
    r = run_case(case_by_id["TG-001"], vendors, extractor_fn=offline_extract)
    assert r.decision.attestation_required
    assert any("number already on file" in c for c in r.decision.checklist)
    assert not any("50100234559821" in c for c in r.decision.checklist[:1])


def test_baseline_misses_obfuscation_on_raw_text(case_by_id, vendors):
    for cid in ("TG-016", "TG-017"):
        case = case_by_id[cid]
        assert rules_only(case, vendors[case["vendor_id"]]).decision != "HOLD"
        assert rules_only_normalized(case, vendors[case["vendor_id"]]).decision == "HOLD"


def test_baseline_false_holds_on_negation(case_by_id, vendors):
    """Why the baseline comparison is worth running: it cannot read 'not'."""
    false_holds = 0
    for cid in ("TG-007", "TG-008", "TG-009", "TG-010", "TG-011"):
        case = case_by_id[cid]
        if rules_only(case, vendors[case["vendor_id"]]).decision == "HOLD":
            false_holds += 1
    assert false_holds == 5


def test_offline_double_matches_the_frozen_labels(case_by_id, vendors):
    """Regression guard. The offline extractor is a test double, not the result."""
    wrong = [
        c["id"]
        for c in case_by_id.values()
        if run_case(c, vendors, extractor_fn=offline_extract).decision.decision != c["expected_decision"]
    ]
    assert wrong == []
