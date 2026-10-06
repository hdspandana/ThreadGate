"""Model failure modes must stay conservative.

The gate is allowed to be wrong in exactly one direction. Every way an AI call
can fail - no key, timeout, malformed output, an intent the schema does not
allow, evidence that is not in the email, or a model that is simply lying -
must land on HOLD. Not one of them may produce CLEAR, and not one may crash.

These tests drive the real `gemini_extract` code path with a fake client, so
they exercise the production parsing, retry and validation logic rather than a
stand-in. `google-genai` is a declared dependency and is imported for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT / "src")
import sys  # noqa: E402

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from threadgate import extract as extract_mod  # noqa: E402
from threadgate.extract import ExtractorError, gemini_extract  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.pipeline import email_to_text, run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CASES = {
    c["id"]: c for c in load_cases(ROOT / "data" / "cases" / "frozen_v1.json")
}

# The environment variable under test. This is a throwaway string used only
# inside these tests; it is never a real credential and is never written to disk.
_KEY_ENV = "GEMINI_API_KEY"
_FAKE_KEY = "test-key-not-real"

VALID_EVIDENCE = "Account number: 50100234559821"


def _nt(case):
    return normalize_text(email_to_text(case["email"]))


def _valid_payload() -> str:
    return json.dumps(
        {
            "intent": "change_request",
            "intent_evidence": VALID_EVIDENCE,
            "summary": "The vendor asks for the payment account to be updated.",
            "claims": [
                {
                    "field": "account_number",
                    "old_value": "50100234554455",
                    "new_value": "50100234559821",
                    "evidence": VALID_EVIDENCE,
                    "confidence": 0.9,
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# fake client
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, text=None, parsed=None):
        self.text = text
        self.parsed = parsed


class _Models:
    def __init__(self, respond):
        self._respond = respond
        self.calls = 0

    def generate_content(self, model=None, contents=None, config=None):
        self.calls += 1
        return self._respond()


class _FakeClient:
    def __init__(self, respond, api_key=None, **_):
        self.models = _Models(respond)


@pytest.fixture
def gemini(monkeypatch):
    """Install a fake Gemini client and a key, and record retry sleeps.

    Returns a function used to set the responder for the next test.
    """
    monkeypatch.setenv(_KEY_ENV, _FAKE_KEY)
    sleeps: list[float] = []
    monkeypatch.setattr(extract_mod.time, "sleep", lambda s: sleeps.append(s))

    box: dict = {}

    def factory(api_key=None, **kwargs):
        assert api_key, "the key must be handed to the client"
        return _FakeClient(box["respond"], api_key=api_key)

    import google.genai as genai  # noqa: PLC0415 - only needed with the fake

    monkeypatch.setattr(genai, "Client", factory)

    def set_responder(fn):
        box["respond"] = fn
        return sleeps

    return set_responder


# ---------------------------------------------------------------------------
# 1. key absent
# ---------------------------------------------------------------------------
def test_no_key_raises_rather_than_returning_a_fake_result(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ExtractorError, match="not set"):
        gemini_extract(_nt(CASES["TG-001"]))


def test_no_key_means_the_pipeline_holds_and_never_clears(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = run_case(CASES["TG-001"], VENDORS, extractor_mode="gemini")
    assert r.decision.decision == "HOLD"
    assert "extractor_failed_fail_closed" in r.decision.reasons
    assert not r.unsafe


# ---------------------------------------------------------------------------
# 2. key present - the happy path still works
# ---------------------------------------------------------------------------
def test_key_present_parses_a_valid_response(gemini):
    gemini(lambda: _Resp(text=_valid_payload()))
    ex = gemini_extract(_nt(CASES["TG-001"]))
    assert ex.intent == "change_request"
    assert ex.claims and ex.claims[0].new_value.endswith("9821")


def test_fenced_json_is_unwrapped(gemini):
    gemini(lambda: _Resp(text="```json\n" + _valid_payload() + "\n```"))
    ex = gemini_extract(_nt(CASES["TG-001"]))
    assert ex.intent == "change_request"


def test_sdk_parsed_object_is_accepted(gemini):
    gemini(lambda: _Resp(parsed=json.loads(_valid_payload())))
    ex = gemini_extract(_nt(CASES["TG-001"]))
    assert ex.intent == "change_request"


# ---------------------------------------------------------------------------
# 3-7. every failure mode
# ---------------------------------------------------------------------------
FAILURES = {
    "timeout": lambda: (_ for _ in ()).throw(TimeoutError("read timeout")),
    "api_error": lambda: (_ for _ in ()).throw(RuntimeError("503 unavailable")),
    "not_json": lambda: _Resp(text="I'm sorry, I can't help with that."),
    "truncated_json": lambda: _Resp(text='{"intent": "change_request", "claims": ['),
    "invalid_intent": lambda: _Resp(
        text=json.dumps({"intent": "banana", "intent_evidence": VALID_EVIDENCE})
    ),
    "empty_response": lambda: _Resp(text=""),
}


@pytest.mark.parametrize("mode", sorted(FAILURES))
def test_a_failing_model_call_raises_extractor_error(gemini, mode):
    sleeps = gemini(FAILURES[mode])
    with pytest.raises(ExtractorError):
        gemini_extract(_nt(CASES["TG-001"]))
    # it retried rather than giving up on the first hiccup
    assert len(sleeps) == 3, sleeps


@pytest.mark.parametrize("mode", sorted(FAILURES))
@pytest.mark.parametrize("cid", ["TG-001", "TG-007", "TG-012"])
def test_a_failing_model_never_clears(gemini, mode, cid):
    gemini(FAILURES[mode])
    r = run_case(CASES[cid], VENDORS, extractor_mode="gemini")
    assert r.decision.decision == "HOLD", f"{mode}/{cid} decided {r.decision.decision}"
    assert "extractor_failed_fail_closed" in r.decision.reasons
    assert r.decision.attestation_required
    assert not r.unsafe


# --- failure modes that do NOT raise, but must still not clear -------------
def test_incomplete_evidence_never_clears(gemini):
    """A no_change verdict with no quote behind it. I2 must catch it."""
    gemini(lambda: _Resp(text=json.dumps(
        {"intent": "no_change", "intent_evidence": "", "summary": "nothing to do", "claims": []}
    )))
    r = run_case(CASES["TG-001"], VENDORS, extractor_mode="gemini")
    assert r.decision.decision == "HOLD"
    assert not r.unsafe


def test_claims_the_email_does_not_support_are_dropped_not_trusted(gemini):
    gemini(lambda: _Resp(text=json.dumps(
        {
            "intent": "no_change",
            "intent_evidence": "Everything else stays exactly the same.",
            "summary": "informational",
            "claims": [
                {
                    "field": "account_number",
                    "new_value": "1111222233334444",
                    "evidence": "Account number: 1111222233334444",
                    "confidence": 0.99,
                }
            ],
        }
    )))
    r = run_case(CASES["TG-001"], VENDORS, extractor_mode="gemini")
    # the account floor still sees 9821 regardless of what the model invented
    assert r.decision.decision == "HOLD"
    assert not r.unsafe


def test_a_forged_quote_for_a_real_change_still_holds(gemini):
    """The compromised_quote harness, arriving through the real model path."""
    gemini(lambda: _Resp(text=json.dumps(
        {
            "intent": "no_change",
            "intent_evidence": "Everything else stays exactly the same.",
            "summary": "no change",
            "claims": [],
        }
    )))
    r = run_case(CASES["TG-001"], VENDORS, extractor_mode="gemini")
    assert r.decision.decision == "HOLD"
    assert any(f.independent_of_model for f in r.decision.findings)


def test_adversarial_output_cannot_turn_a_hold_into_a_clear(gemini):
    """Sweep: for every case, a model that says no_change must never clear a
    case whose label is HOLD."""
    gemini(lambda: _Resp(text=json.dumps(
        {
            "intent": "no_change",
            "intent_evidence": "Everything else stays exactly the same.",
            "summary": "no change",
            "claims": [],
        }
    )))
    for cid, case in CASES.items():
        r = run_case(case, VENDORS, extractor_mode="gemini")
        if case["expected_decision"] == "HOLD":
            assert r.decision.decision == "HOLD", cid
        assert not r.unsafe


def test_the_model_cannot_select_a_different_vendor_record(gemini):
    """The record is chosen by the case, never by what the model claims."""
    gemini(lambda: _Resp(text=json.dumps(
        {
            "intent": "no_change",
            "intent_evidence": "Everything else stays exactly the same.",
            "summary": "this is actually a different supplier entirely",
            "claims": [],
        }
    )))
    case = CASES["TG-001"]
    r = run_case(case, VENDORS, extractor_mode="gemini")
    assert r.vendor_id == case["vendor_id"]
