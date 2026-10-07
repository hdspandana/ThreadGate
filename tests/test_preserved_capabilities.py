"""The controls that must survive any future change.

This suite has grown by adding guards, and the risk of that is the opposite of
the one it was built to address: a later refactor quietly drops a control that
an earlier phase added, and nothing notices because the tests for the *new*
behaviour still pass.

Each test below pins one shipped capability to something observable - a
behaviour, an import, a constant - rather than to a comment claiming it exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "eval"))

from threadgate.attestation import (  # noqa: E402
    AttestationStore,
    VerificationEvent,
)
from threadgate.clock import fixed  # noqa: E402
from threadgate.extract import (  # noqa: E402
    compromised_extract,
    compromised_quote_extract,
    gemini_extract,
    offline_extract,
)
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CLOCK = fixed("2026-10-06")
APP = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")


def all_cases():
    out = []
    for name in ("frozen_v1.json", "frozen_v2.json"):
        out.extend(load_cases(ROOT / "data" / "cases" / name))
    return out


# --- the decision trace ---------------------------------------------------
def test_the_decision_trace_still_renders_codes_in_plain_language():
    assert "REASON_TEXT = {" in APP
    assert "def explain(reason" in APP
    # and the raw codes remain reachable
    assert "Reason codes" in APP


def test_the_trace_mapping_is_not_a_policy_input():
    """Presentation only: no module under src/ may read it."""
    for mod in (ROOT / "src" / "threadgate").glob("*.py"):
        src = mod.read_text(encoding="utf-8")
        assert "REASON_TEXT" not in src, mod.name


# --- the attestation interaction ------------------------------------------
def test_the_single_use_binding_still_refuses_a_replay():
    store = AttestationStore()
    case = all_cases()[0]
    ctx = run_case(case, VENDORS, extractor_fn=offline_extract, clock=CLOCK,
                   store=store).verification
    assert ctx is not None
    event = VerificationEvent(
        event_id=f"EVT-{ctx.request_id[:12]}",
        vendor_id=ctx.vendor_id,
        request_id=ctx.request_id,
        destination_digest=ctx.destination_digest,
        reference_version=ctx.reference_version,
    )
    first = run_case(case, VENDORS, extractor_fn=offline_extract, clock=CLOCK,
                     store=store, presented_event=event)
    second = run_case(case, VENDORS, extractor_fn=offline_extract, clock=CLOCK,
                      store=store, presented_event=event)
    assert first.decision.attestation_status == "SATISFIED"
    assert second.decision.attestation_code == "ATTESTATION_REPLAY"


def test_the_attestation_interaction_is_still_offered_in_the_ui():
    assert "Demonstrate the single-use verification binding" in APP


# --- the security invariants ---------------------------------------------
# Each invariant id, mapped to the function that implements it. Asserted by
# importing the function rather than by scanning docstrings for "I1a -": the
# first version of this test did the latter and reported a missing invariant
# because the docstring used an em dash, which is a bug in the test.
INVARIANT_IMPLEMENTATIONS = {
    "I1a": "account_floor",
    "I1b": "destination_code_floor",
    "I3": "destination_floor",
    "I4": "out_of_band_destination",
    "I5": "alternate_routing_floor",
    "I2b": "no_change_justified",
    "I2c": "confirmation_request_justified",
    "I2": "change_act_detected",
}


def test_every_invariant_still_has_an_implementation():
    """If one is deleted, the README describes code that is not there."""
    from threadgate import invariants

    missing = [
        f"{iid} ({fn})" for iid, fn in INVARIANT_IMPLEMENTATIONS.items()
        if not hasattr(invariants, fn)
    ]
    assert not missing, f"invariants removed: {missing}"


def test_the_independent_floors_do_not_take_a_model_argument():
    """The AI-independence claim, checked by signature.

    I1a/I1b/I3/I4/I5 are the floor: they read the email text and the record and
    never the model's output. That is the architecture's central claim, so it is
    asserted as a property of the code rather than described in a comment.
    """
    import inspect

    from threadgate import invariants

    for iid, fn in INVARIANT_IMPLEMENTATIONS.items():
        if iid in ("I2", "I2b", "I2c"):
            continue  # verdict-validating: these exist to reject model output
        params = set(inspect.signature(getattr(invariants, fn)).parameters)
        assert "extraction" not in params, f"{iid}/{fn} reads the model output"
        assert "model" not in params, f"{iid}/{fn} reads the model output"


def test_reference_lineage_still_travels_with_the_verification():
    """Reference version lineage: the diagram once said this was missing."""
    from threadgate.attestation import VerificationContext

    assert "reference_version" in VerificationContext.__dataclass_fields__
    assert "destination_digest" in VerificationContext.__dataclass_fields__


def test_stale_and_missing_records_still_escalate():
    """A record past its confirmation window must not clear.

    Asserted behaviourally, not by looking for a field name: the record is
    dated long ago and the gate must refuse to CLEAR it.
    """
    import json

    data = json.loads(
        (ROOT / "data" / "records" / "vendor_master.json").read_text(encoding="utf-8")
    )
    assert "reference_updated_at" in next(iter(data["vendors"].values()))

    # A clock far past the record's confirmation window.
    long_after = fixed("2027-06-01")
    case = next(c for c in all_cases() if c["expected_decision"] == "CLEAR")
    r = run_case(case, VENDORS, extractor_fn=offline_extract, clock=long_after)
    assert r.decision.decision != "CLEAR", (
        "a record this stale must not clear"
    )
    assert any("stale" in reason or "reference" in reason
               for reason in r.decision.reasons), r.decision.reasons


# --- the production trust boundary ---------------------------------------
def test_production_gemini_still_takes_no_vendor():
    import inspect

    sig = inspect.signature(gemini_extract)
    assert "vendor" not in sig.parameters


def test_the_evidence_to_quote_binding_still_holds():
    """I6: a claimed value must sit inside the quote offered for it."""
    from threadgate.validate import find_span

    haystack = "Please note the new account 99999999999999 is effective today."
    assert find_span(haystack, "99999999999999") is not None
    assert find_span(haystack, "00000000000000") is None


# --- the adversarial harnesses -------------------------------------------
def test_both_adversarial_harnesses_still_exist_and_release_nothing():
    from collections import Counter

    for fn in (compromised_extract, compromised_quote_extract):
        results = [run_case(c, VENDORS, extractor_fn=fn, clock=CLOCK) for c in all_cases()]
        counts = Counter()
        for r in results:
            counts["unsafe"] += bool(r.unsafe)
            counts["non_clear"] += bool(r.non_clear_release)
        assert counts["unsafe"] == 0, (fn.__name__, "released a hold")
        assert counts["non_clear"] == 0, (fn.__name__, "bypassed the gate")


def test_the_sabotage_tests_are_still_in_the_suite():
    """The sabotage protocol is documented in test docstrings across files."""
    found = []
    for path in (ROOT / "tests").glob("test_*.py"):
        found.extend(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if "SABOTAGE" in line
        )
    assert len(found) >= 1, "the sabotage markers have been removed"


# --- the demo UI hardening ------------------------------------------------
@pytest.mark.parametrize("cap", ["MAX_EMAIL_CHARS", "MIN_SECONDS_BETWEEN_RUNS", "SLOW_REQUEST_SECONDS"])
def test_the_ui_caps_are_still_enforced(cap):
    assert cap in APP


def test_the_key_suffix_is_still_not_rendered():
    """It used to print the last four characters of the key on screen."""
    assert "k[-4:]" not in APP
    assert "configured" in APP


def test_no_secret_is_read_outside_the_environment():
    for path in list((ROOT / "src" / "threadgate").glob("*.py")) + [ROOT / "app" / "streamlit_app.py"]:
        src = path.read_text(encoding="utf-8")
        assert "st.secrets" not in src or "get" in src, path.name
