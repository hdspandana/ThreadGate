"""Scope discipline.

These tests exist to stop the project drifting into being a generic risk
scorer. A risk score can be argued with, tuned until it stops firing, and
eventually waved through. A destination check cannot.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from threadgate.compare import diff_claims
from threadgate.extract import compromised_extract, compromised_quote_extract, offline_extract
from threadgate.invariants import out_of_band_destination
from threadgate.normalize import normalize_text
from threadgate.pipeline import email_to_text, run_case
from threadgate.records import load_cases
from threadgate.schema import Claim, Extraction
from threadgate.validate import validate_extraction

ROOT = Path(__file__).resolve().parents[1]
V2 = load_cases(ROOT / "data" / "cases" / "frozen_v2.json")
CATEGORIES = json.loads((ROOT / "data" / "cases" / "categories.json").read_text(encoding="utf-8"))


def _amount_only_extractor(nt, vendor):
    """A model that reports nothing but an invoice amount.

    The quote has to be verbatim or the closed-world rule drops it - which is
    the validator working, not a loophole being tested.
    """
    sentence_match = re.search(r"[^\n]*INR\s?[\d,]+\.\d{2}[^\n]*", nt.text)
    sentence = sentence_match.group(0).strip() if sentence_match else ""
    value_match = re.search(r"[\d,]+\.\d{2}", sentence) if sentence else None
    return Extraction(
        intent="change_request",
        intent_evidence=sentence,
        summary="an invoice amount was reported",
        claims=[Claim(field="amount", new_value=value_match.group(0) if value_match else "0",
                      evidence=sentence, confidence=0.9)],
    )


def test_an_amount_alone_never_produces_a_hold(case_by_id_all, vendors):
    """No amount, however large, is a payment-destination change.

    A payment reminder quoting a value is not a request to change anything, and
    a large value is not a risk signal this gate is allowed to act on.
    """
    case = case_by_id_all["TG-028"]  # an overdue-invoice chaser, expects CLEAR
    r = run_case(case, vendors, extractor_fn=_amount_only_extractor)
    assert r.validation.verified_claims, "the amount claim should be admissible here"
    assert r.decision.decision == "CLEAR", r.decision.reasons
    assert not any("amount" in reason for reason in r.decision.reasons)


def test_amount_diff_is_never_marked_as_changed(case_by_id_all, vendors):
    vendor = vendors["V-1001"]
    nt = normalize_text(email_to_text(case_by_id_all["TG-028"]["email"]))
    ex = Extraction(
        intent="change_request",
        intent_evidence="Invoice INV-4471 for INR 320,000.00 is now 12 days overdue.",
        claims=[Claim(field="amount", new_value="320,000.00",
                      evidence="Invoice INV-4471 for INR 320,000.00 is now 12 days overdue.")],
    )
    v = validate_extraction(ex, nt)
    diffs = diff_claims(v.claims, vendor)
    assert diffs and all(not d.changed for d in diffs)
    assert all(d.field != "amount" or "not a payment-destination field" in d.note for d in diffs)


def test_no_risk_scoring_survives_in_the_record(vendors):
    """The vendor record carries no numeric risk thresholds."""
    raw = (ROOT / "data" / "records" / "vendor_master.json").read_text(encoding="utf-8")
    assert "typical_max" not in raw
    for v in vendors.values():
        assert not hasattr(v, "typical_max_amount")


def test_destination_code_floor_does_not_ask_the_model(case_by_id_all, vendors):
    """An IFSC belonging to neither the record nor an alternate is a hold."""
    r = run_case(case_by_id_all["TG-027"], vendors, extractor_fn=compromised_quote_extract)
    assert r.decision.decision == "HOLD"
    assert any(f.code == "I1_UNKNOWN_DESTINATION_CODE" for f in r.decision.findings)
    assert all(f.independent_of_model for f in r.decision.findings if f.code.startswith("I1"))


def test_known_branch_code_does_not_break_a_pre_registered_review(case_by_id_all, vendors):
    """The floor must not eat the legitimate REVIEW path."""
    r = run_case(case_by_id_all["TG-012"], vendors, extractor_fn=offline_extract)
    assert r.decision.decision == "REVIEW"
    assert not any(f.code.startswith("I1") for f in r.decision.findings)


@pytest.mark.parametrize("cid", ["TG-020", "TG-034"])
@pytest.mark.parametrize("attack", [offline_extract, compromised_extract, compromised_quote_extract])
def test_a_destination_we_cannot_read_is_never_cleared(case_by_id_all, vendors, cid, attack):
    """No OCR, no attachment parsing. If the value is outside the text, hold it."""
    r = run_case(case_by_id_all[cid], vendors, extractor_fn=attack)
    assert r.decision.decision == "HOLD"
    assert any(f.code == "I4_DESTINATION_OUT_OF_BAND" for f in r.decision.findings)
    assert any("attachment" in c.lower() or "channel you initiate" in c.lower()
               for c in r.decision.checklist)


def test_out_of_band_never_fires_on_a_case_that_should_clear(vendors):
    """A false out-of-band hold would be a false hold on legitimate mail."""
    offenders = []
    for case in V2:
        if case["expected_decision"] == "HOLD":
            continue
        nt = normalize_text(email_to_text(case["email"]))
        if out_of_band_destination(nt.text):
            offenders.append(case["id"])
    assert offenders == []


def test_no_unsafe_outcomes_anywhere(vendors):
    """Item 4: safety is never traded for accuracy. All three sets, both harnesses."""
    from threadgate.pipeline import PipelineResult

    for name in ("frozen_v1.json", "frozen_v2.json"):
        cases = load_cases(ROOT / "data" / "cases" / name)
        for attack in (compromised_extract, compromised_quote_extract):
            for case in cases:
                r: PipelineResult = run_case(case, vendors, extractor_fn=attack)
                assert not r.unsafe, f"{name} {case['id']} released a hold under {attack.__name__}"
                assert r.decision.decision != "REVIEW"


def test_every_case_has_a_category():
    assignments = CATEGORIES["assignments"]
    missing = sorted(c["id"] for c in V2 if c["id"] not in assignments)
    assert not missing, missing
    unknown = {v for v in assignments.values() if v not in CATEGORIES["categories"]}
    assert not unknown, unknown


def test_gemini_is_skipped_not_silently_degraded():
    """With no key the live systems must be reported as skipped, never as a result.

    Behavioural rather than textual: the harness is actually invoked and the
    output checked, so a refactor that quietly starts reporting a fail-closed
    row as if it were a model result will fail this.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    proc = subprocess.run(
        [sys.executable, "eval/run_eval.py", "--sets", "v1",
         "--systems", "gemini", "ai_only", "hybrid_no_scan", "hybrid_no_validation",
         "--out", tempfile.mkdtemp()],
        cwd=ROOT, capture_output=True, text=True, env=env, timeout=180,
    )
    out = proc.stdout + proc.stderr
    assert "SKIPPED" in out, out[-800:]
    for name in ("gemini", "ai_only", "hybrid_no_scan", "hybrid_no_validation"):
        assert name in out.split("SKIPPED:")[1].split("\n")[0], out[-800:]
    # and no row was produced for any of them
    for line in out.splitlines():
        if line.startswith(("gemini", "ai_only", "hybrid_")):
            raise AssertionError(f"a model row was reported without a key: {line}")


def test_require_gemini_fails_closed_without_a_key():
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    proc = subprocess.run(
        [sys.executable, "eval/run_eval.py", "--sets", "v1", "--require-gemini",
         "--out", tempfile.mkdtemp()],
        cwd=ROOT, capture_output=True, text=True, env=env, timeout=180,
    )
    assert proc.returncode == 2, proc.stdout[-600:]
