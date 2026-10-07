"""Security invariants, stated as tests.

Each test here corresponds to a claim made in the README. If a claim cannot be
turned into a passing test, it does not go in the README.

All fourteen invariants are now enforced here or in
`test_verification_and_lineage.py`. Nothing in this file asserts that a
property is absent; the three that once were (replay protection, reference
version lineage, stale-reference escalation) are implemented and tested.
"""

from __future__ import annotations

import ast
from pathlib import Path

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


# policy for the gate, baseline for the rules-only comparison. Nothing else in
# src/threadgate may mint a decision.
ALLOWED_DECISION_MINTERS = {"policy.py", "baseline.py"}


def _decision_aliases(tree, path):
    """Local names that refer to the decision type in one module.

    Handles `from .policy import Decision`, `... import Decision as D`,
    `import threadgate.policy as pol` and `from threadgate import policy`
    followed by `policy.Decision(...)`. The previous version of this test grepped
    for the literal text `Decision(decision=` and so was blind to every aliased
    form and to any constructor split across lines. S4 below in the sabotage
    notes is the module-qualified form, which this resolver initially missed too.
    """
    names = {"Decision"}
    module_names = {"policy", "baseline"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "Decision":
                    names.add(alias.asname or alias.name)
                elif alias.name in module_names:
                    # `from threadgate import policy` / `from . import policy`
                    names.add((alias.asname or alias.name) + ".Decision")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] in module_names:
                    # `import threadgate.policy` / `import threadgate.policy as pol`
                    names.add((alias.asname or alias.name) + ".Decision")
    return names


def _mints_a_decision(tree, path):
    """True if this module constructs the decision type with a verdict."""
    names = _decision_aliases(tree, path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = ast.unparse(node.func)
        if called not in names:
            continue
        if any(kw.arg == "decision" for kw in node.keywords):
            return True
    return False


def test_only_policy_produces_a_decision():
    """The decision type is constructed in policy and baseline, and nowhere else.

    Rewritten from a `grep` subprocess for three reasons, all of which were
    demonstrated before this version replaced it:

    1. It could not run without GNU grep. On Windows the subprocess raises
       FileNotFoundError, so the whole suite errors out rather than failing.
    2. It passed while checking nothing. `cwd="."` plus empty stdout gave
       `set() <= {...}` -> True, so running pytest from any other directory
       produced a green test that had read no files at all.
    3. The text pattern `Decision(decision=` matched only `baseline.py`; the
       real call in `policy.py` is split across lines, and an aliased import
       evades the pattern's file-level scope too.

    The scan is now AST-based and asserts what it actually read, so an empty or
    misdirected scan is a failure rather than a pass.
    """
    import ast

    gate_dir = Path(__file__).resolve().parents[1] / "src" / "threadgate"
    sources = sorted(gate_dir.glob("*.py"))

    # Fail closed: an empty scan is not a clean scan.
    assert sources, f"no sources found under {gate_dir}"
    assert len(sources) >= 10, f"only {len(sources)} modules scanned under {gate_dir}"

    scanned = {p.name for p in sources}
    assert {"policy.py", "baseline.py"} <= scanned, (
        f"the two modules that may mint a decision are missing from the scan: "
        f"{sorted(scanned)}"
    )

    minters = set()
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _mints_a_decision(tree, path):
            minters.add(path.name)

    assert minters <= ALLOWED_DECISION_MINTERS, (
        f"a module outside {sorted(ALLOWED_DECISION_MINTERS)} constructs a "
        f"Decision: {sorted(minters)}"
    )
    # And the guard is not vacuous in the other direction: the scan must find
    # the two constructors that legitimately exist.
    assert minters == ALLOWED_DECISION_MINTERS, (
        f"expected a decision in {sorted(ALLOWED_DECISION_MINTERS)}, found "
        f"{sorted(minters)} - the detector has stopped detecting"
    )
