"""The three invariants that were documented as absent and are now built.

  A. Replay protection - a verification event is single-use and bound to one
     (request, destination, reference version).
  B. Reference-version lineage - a verification made against v1 is refused
     against v2, and a changed destination cannot inherit an old verification.
  C. Stale-reference escalation - CURRENT evaluates normally, STALE floors at
     REVIEW, MISSING holds a payment-destination change. None of them clears.

Every test here was sabotage-verified: each invariant has a single line in the
implementation that, if reverted, fails a named test in this file. The
sabotage notes are recorded next to the relevant test.
"""

from __future__ import annotations

import copy
import dataclasses
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.attestation import (  # noqa: E402
    ACCEPTED,
    DESTINATION_MISMATCH,
    NOT_REQUIRED,
    REFERENCE_VERSION_MISMATCH,
    REPLAY,
    REQUEST_MISMATCH,
    VENDOR_MISMATCH,
    AttestationStore,
    VerificationContext,
    VerificationEvent,
    destination_digest,
)
from threadgate.clock import fixed  # noqa: E402
from threadgate.compare import DESTINATION_FIELDS  # noqa: E402
from threadgate.extract import offline_extract  # noqa: E402
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.policy import decide  # noqa: E402
from threadgate.records import FIELD_PATHS, load_cases, load_vendors  # noqa: E402
from threadgate.reference import (  # noqa: E402
    DESTINATION_REFERENCE_FIELDS,
    reference_state,
    reference_version,
)
from threadgate.schema import Claim, FieldDiff  # noqa: E402
from threadgate.validate import ValidatedClaim, ValidationResult  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CASES: dict[str, dict] = {}
for _name in ("frozen_v1.json", "frozen_v2.json"):
    for _c in load_cases(ROOT / "data" / "cases" / _name):
        CASES[_c["id"]] = _c

NOW = "2026-10-06"   # inside the 90-day window for the records on file
LATER = "2027-01-01"  # well outside it


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def with_overrides(base, **overrides):
    """A copy of a vendor record with top-level keys replaced."""
    data = copy.deepcopy(base.data)
    data.update(overrides)
    out = dataclasses.replace(base, data=data)
    out.__post_init__()
    return out


def blank_destination(base):
    """A copy with no payment destination on file at all - the MISSING state."""
    data = copy.deepcopy(base.data)
    for field in DESTINATION_REFERENCE_FIELDS:
        path = FIELD_PATHS.get(field)
        if not path:
            continue
        node = data
        for key in path[:-1]:
            node = node.get(key)
            if not isinstance(node, dict):
                break
        else:
            if path[-1] in node:
                node[path[-1]] = None
    out = dataclasses.replace(base, data=data)
    out.__post_init__()
    return out


def vendor_copy(vendors, mut=None, vid="V-1001"):
    """Degrade one vendor. Used where the case under test is that vendor's."""
    v = dict(vendors)
    v[vid] = mut(vendors[vid]) if mut else vendors[vid]
    return v


def degrade_all(mut):
    """Degrade every vendor. The corpus spans V-1001 and V-1002."""
    return {vid: mut(v) for vid, v in VENDORS.items()}


def context_for(case, vendors=None, clock=NOW):
    """The VerificationContext the gate derives for a case. Code-derived only."""
    r = run_case(case, vendors or VENDORS, extractor_fn=offline_extract, clock=fixed(clock))
    return r, r.verification


def event_for(context, event_id="EV-1", **overrides):
    """An attestation minted against a context, with any binding overridable."""
    fields = dict(
        event_id=event_id,
        vendor_id=context.vendor_id,
        request_id=context.request_id,
        destination_digest=context.destination_digest,
        reference_version=context.reference_version,
    )
    fields.update(overrides)
    return VerificationEvent(**fields)


# ===========================================================================
# A. Replay protection
# ===========================================================================
def test_a_fresh_verification_event_is_accepted_once(case_by_id_all):
    """The happy path. Sabotage: make consume() always accept -> test 2 fails."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    out = store.consume(event_for(ctx), ctx, required=True)
    assert out.accepted and out.code == ACCEPTED
    assert store.used_event_ids() == {"EV-1"}


def test_the_same_event_cannot_be_used_twice(case_by_id_all):
    """The single-use property. Sabotage: drop the replay check -> this fails."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    event = event_for(ctx)
    assert store.consume(event, ctx, required=True).accepted
    second = store.consume(event, ctx, required=True)
    assert not second.accepted
    assert second.code == REPLAY
    assert "already been used" in second.message


def test_the_same_event_cannot_be_used_against_another_request(case_by_id_all):
    """Sabotage: drop the request_id comparison -> this fails."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    stolen = event_for(ctx, request_id="TG-999")
    out = store.consume(stolen, ctx, required=True)
    assert not out.accepted and out.code == REQUEST_MISMATCH


def test_the_same_event_cannot_be_used_against_another_vendor(case_by_id_all):
    """Sabotage: drop the vendor_id comparison -> this fails."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    out = store.consume(event_for(ctx, vendor_id="V-1002"), ctx, required=True)
    assert not out.accepted and out.code == VENDOR_MISMATCH


def test_the_same_event_cannot_be_used_against_another_destination(case_by_id_all):
    """Two destinations that differ, one request id - isolates the digest binding.

    TG-028 carries no verified destination change, so the digest falls back to
    the record's own destination. Changing the record therefore changes the
    digest while the request id stays put.

    Sabotage: make destination_digest() return a constant -> this fails.
    """
    case = CASES["TG-028"]
    _, ctx_v1 = context_for(case, vendor_copy(VENDORS))
    moved = vendor_copy(VENDORS, lambda b: with_overrides(
        b, reference_version="v1",
        **{"bank": {**b.data["bank"], "account_number": "50100234550001"}}))
    _, ctx_moved = context_for(case, moved)

    assert ctx_v1.request_id == ctx_moved.request_id, "same request, so only the destination differs"
    assert ctx_v1.destination_digest != ctx_moved.destination_digest
    assert ctx_v1.reference_version == ctx_moved.reference_version

    store = AttestationStore()
    out = store.consume(event_for(ctx_v1), ctx_moved, required=True)
    assert not out.accepted and out.code == DESTINATION_MISMATCH


def test_a_rejected_attempt_still_burns_the_event(case_by_id_all):
    """A failed presentation must not leave the event usable for a second try."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    first = store.consume(event_for(ctx, request_id="TG-999"), ctx, required=True)
    assert first.code == REQUEST_MISMATCH
    # The correct binding, presented afterwards with the same event id.
    second = store.consume(event_for(ctx), ctx, required=True)
    assert not second.accepted, "an event burned by a failed attempt must stay burned"
    assert second.code == REPLAY


def test_a_verification_is_not_required_when_there_is_nothing_to_verify(case_by_id_all):
    """CLEAR means nothing was identified, so there is nothing to attest to."""
    case = CASES["TG-028"]
    _, ctx = context_for(case)
    store = AttestationStore()
    out = store.consume(event_for(ctx), ctx, required=False)
    assert not out.accepted and out.code == NOT_REQUIRED
    assert not out.consumed, "a not-required presentation must not burn the event"
    assert store.used_event_ids() == frozenset()


def test_a_replayed_attestation_is_rejected_end_to_end_without_moving_the_decision():
    """Through run_case: the second presentation of one event is a replay.

    The decision must be identical before and after. A rejected attestation
    cannot release a hold, and it also cannot be used to argue the gate
    stricter than the evidence supports.
    """
    case = CASES["TG-001"]
    store = AttestationStore()
    probe = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW))
    assert probe.decision.attestation_required
    event = event_for(probe.verification, event_id="EV-1")

    first = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW),
                     store=store, presented_event=event)
    assert first.decision.attestation_status == "SATISFIED"

    replayed = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW),
                        store=store, presented_event=event)
    assert replayed.decision.attestation_code == REPLAY
    assert replayed.decision.attestation_status == "REJECTED"
    assert replayed.decision.decision == probe.decision.decision, (
        "a replayed attestation must not move the decision in either direction")
    assert replayed.decision.attestation_required is True
    assert any(f.code == REPLAY for f in replayed.decision.findings)


def test_a_correctly_bound_attestation_is_satisfied_end_to_end():
    """The positive end-to-end path: mint against the context, present once."""
    case = CASES["TG-001"]
    store = AttestationStore()
    probe = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW))
    event = event_for(probe.verification, event_id="EV-7", attested_by="ops@example")

    satisfied = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW),
                         store=store, presented_event=event)
    assert satisfied.decision.attestation_status == "SATISFIED"
    assert satisfied.decision.attestation_code == ACCEPTED
    assert satisfied.decision.decision == probe.decision.decision
    # the requirement does not disappear because it was met
    assert satisfied.decision.attestation_required is True


def test_the_store_survives_a_round_trip():
    """`dump` / `restore` exist so a deployment can persist consumed events."""
    _, ctx = context_for(CASES["TG-001"])
    store = AttestationStore()
    store.consume(event_for(ctx, event_id="EV-1"), ctx, required=True)
    restored = AttestationStore.restore(store.dump())
    out = restored.consume(event_for(ctx, event_id="EV-1"), ctx, required=True)
    assert out.code == REPLAY, "a restored store must still know what was used"


# ===========================================================================
# B. Reference-version lineage
# ===========================================================================
def test_an_attestation_matches_its_own_reference_version(case_by_id_all):
    """v1 attestation against the v1 record: valid. The baseline for the rest."""
    case = CASES["TG-028"]
    _, ctx = context_for(case)
    assert ctx.reference_version == "v1"
    store = AttestationStore()
    assert store.consume(event_for(ctx), ctx, required=False).code == NOT_REQUIRED
    # and against a decision that does require one
    _, ctx_hold = context_for(CASES["TG-001"])
    assert ctx_hold.reference_version == "v1"
    assert store.consume(event_for(ctx_hold, event_id="EV-2"), ctx_hold, required=True).accepted


def test_a_v1_attestation_is_refused_against_a_v2_record(case_by_id_all):
    """The lineage rule. Sabotage: drop the reference_version check -> this fails.

    Same request, same destination, record moved on: the old verification no
    longer describes the record and must not be inherited.
    """
    case = CASES["TG-028"]
    _, ctx_v1 = context_for(case, vendor_copy(VENDORS))
    v2 = vendor_copy(VENDORS, lambda b: with_overrides(b, reference_version="v2"))
    _, ctx_v2 = context_for(case, v2)

    assert ctx_v1.request_id == ctx_v2.request_id
    assert ctx_v1.destination_digest == ctx_v2.destination_digest, (
        "only the version may differ here, so the version is what is being tested")
    assert ctx_v1.reference_version == "v1" and ctx_v2.reference_version == "v2"

    store = AttestationStore()
    out = store.consume(event_for(ctx_v1), ctx_v2, required=True)
    assert not out.accepted and out.code == REFERENCE_VERSION_MISMATCH


def test_a_changed_destination_cannot_inherit_the_previous_verification():
    """The digest binding, isolated from the version binding."""
    vendor = VENDORS["V-1001"]
    d_a = destination_digest(
        [FieldDiff(field="account_number", old_value=None, new_value="50100234558812",
                   changed=True, risk="high")], vendor)
    d_b = destination_digest(
        [FieldDiff(field="account_number", old_value=None, new_value="50100234559999",
                   changed=True, risk="high")], vendor)
    assert d_a != d_b, "different destinations must not share a digest"

    ctx_a = VerificationContext("V-1001", "TG-001", d_a, "v1")
    ctx_b = VerificationContext("V-1001", "TG-001", d_b, "v1")
    store = AttestationStore()
    event = event_for(ctx_a, event_id="EV-3")
    assert store.consume(event, ctx_a, required=True).accepted
    # the destination moved; the old verification does not cover the new one
    fresh = AttestationStore()
    assert fresh.consume(event_for(ctx_a, event_id="EV-4"), ctx_b,
                         required=True).code == DESTINATION_MISMATCH


def test_the_digest_ignores_the_model_and_follows_the_record():
    """Two runs that describe the same destination must share a digest."""
    vendor = VENDORS["V-1001"]
    d1 = destination_digest(
        [FieldDiff(field="account_number", old_value="50100234554455",
                   new_value="5010 0234 5588 12", changed=True, risk="low")], vendor)
    d2 = destination_digest(
        [FieldDiff(field="account_number", old_value="50100234554455",
                   new_value="50100234558812", changed=True, risk="low")], vendor)
    assert d1 == d2, "presentation-only differences must not change the binding"


def test_a_new_verification_must_be_tied_to_the_new_version(case_by_id_all):
    """After the record moves, only an attestation minted against v2 is accepted."""
    case = CASES["TG-028"]
    v2 = vendor_copy(VENDORS, lambda b: with_overrides(b, reference_version="v2"))
    _, ctx_v2 = context_for(case, v2)

    store = AttestationStore()
    stale_event = event_for(ctx_v2, event_id="EV-5", reference_version="v1")
    assert store.consume(stale_event, ctx_v2, required=True).code == REFERENCE_VERSION_MISMATCH

    fresh_event = event_for(ctx_v2, event_id="EV-6", reference_version="v2")
    assert store.consume(fresh_event, ctx_v2, required=True).code == ACCEPTED


def test_the_version_comes_from_the_record_not_the_model():
    """Which version is in force is decided by the record, never by the request."""
    assert reference_version(VENDORS["V-1001"]) == "v1"
    assert reference_version(with_overrides(VENDORS["V-1001"], reference_version="v9")) == "v9"
    unversioned = with_overrides(VENDORS["V-1001"], reference_version=None)
    assert reference_version(unversioned) == "unversioned"


# ===========================================================================
# C. Stale-reference escalation
# ===========================================================================
def test_a_current_reference_evaluates_normally(case_by_id_all):
    """CURRENT must not change any outcome. This is the no-regression check."""
    case = CASES["TG-028"]  # clears under the offline double
    r = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW))
    assert r.decision.reference_state == "CURRENT"
    assert r.decision.decision == "CLEAR"
    assert r.decision.reasons == ["nothing_to_gate"]


def test_the_clock_decides_whether_a_record_is_stale():
    """The same record is CURRENT on one date and STALE on another.

    The record on file was last confirmed 2026-09-15, and the window is 90
    days, so day 90 is still inside it and day 91 is the first stale day.
    """
    v = VENDORS["V-1001"]
    assert reference_state(v, fixed("2026-10-06")) == "CURRENT"   # day 21
    assert reference_state(v, fixed("2026-12-13")) == "CURRENT"   # day 89
    assert reference_state(v, fixed("2026-12-14")) == "CURRENT"   # day 90, boundary
    assert reference_state(v, fixed("2026-12-15")) == "STALE"     # day 91
    assert reference_state(v, fixed(LATER)) == "STALE"


def test_a_stale_reference_never_clears(case_by_id_all):
    """STALE floors at REVIEW. Sabotage: drop the STALE branch -> this fails."""
    case = CASES["TG-028"]
    stale = vendor_copy(VENDORS, lambda b: with_overrides(b, reference_updated_at="2025-01-01"))
    assert reference_state(stale["V-1001"], fixed(NOW)) == "STALE"

    r = run_case(case, stale, extractor_fn=offline_extract, clock=fixed(NOW))
    assert r.decision.reference_state == "STALE"
    assert r.decision.decision == "REVIEW", r.decision.reasons
    assert "reference_stale_record" in r.decision.reasons
    assert any(f.code == "R_STALE_REFERENCE" for f in r.decision.findings)


def test_a_record_with_no_confirmation_date_is_stale_not_current():
    """An absent date is not proof of recency. Absent means stale."""
    v = with_overrides(VENDORS["V-1001"], reference_updated_at=None)
    assert reference_state(v, fixed(NOW)) == "STALE"
    v_bad = with_overrides(VENDORS["V-1001"], reference_updated_at="not-a-date")
    assert reference_state(v_bad, fixed(NOW)) == "STALE"


def test_a_missing_reference_is_reported_as_missing():
    """No payment destination on file at all."""
    v = blank_destination(VENDORS["V-1001"])
    assert reference_state(v, fixed(NOW)) == "MISSING"
    assert not any((v.current(f) or "").strip() for f in DESTINATION_REFERENCE_FIELDS)


def test_a_missing_reference_holds_a_payment_destination_change():
    """MISSING + destination change -> HOLD. Isolated at the policy boundary.

    Sabotage: change `forces_hold` to False -> this fails.
    """
    from threadgate.policy import DESTINATION_FIELDS as POLICY_DESTINATION_FIELDS

    assert POLICY_DESTINATION_FIELDS is DESTINATION_FIELDS, "policy must use the shared set"

    nt = normalize_text("Account number: 50100234558812")
    validation = ValidationResult(intent="change_request", intent_evidenced=True)
    # The policy reads `verified_claims`, not the diff list, to decide whether
    # anything was verifiable at all - so the claim has to be there too.
    validation.claims.append(
        ValidatedClaim(claim=Claim(field="account_number", new_value="50100234558812",
                                   evidence="Account number: 50100234558812"),
                       verified=True))
    changed = [FieldDiff(field="account_number", old_value=None,
                         new_value="50100234558812", changed=True, risk="low",
                         pre_registered=True, note="matches record")]

    current = decide(VENDORS["V-1001"], "change_request", validation, changed, [],
                     nt, {}, clock=fixed(NOW))
    assert current.decision == "REVIEW", "a pre-registered change is a review, not a hold"

    missing = decide(blank_destination(VENDORS["V-1001"]), "change_request", validation,
                     changed, [], nt, {}, clock=fixed(NOW))
    assert missing.reference_state == "MISSING"
    assert missing.decision == "HOLD", missing.reasons
    assert "reference_missing_destination_change" in missing.reasons
    assert any(f.code == "R_MISSING_REFERENCE" and f.severity == "hold"
               for f in missing.findings)


def test_a_missing_reference_with_no_destination_change_floors_at_review():
    """MISSING without a destination change must still never clear."""
    nt = normalize_text("Please confirm the invoice schedule for next quarter.")
    validation = ValidationResult(intent="no_change", intent_evidenced=True)
    validation.intent_span_norm = (0, min(len(nt.text), 40))

    missing = decide(blank_destination(VENDORS["V-1001"]), "no_change", validation,
                     [], [], nt, {}, clock=fixed(NOW))
    assert missing.decision == "REVIEW", missing.reasons
    assert "reference_missing_record" in missing.reasons


@pytest.mark.parametrize("label,mut", [
    ("stale", lambda b: with_overrides(b, reference_updated_at="2025-01-01")),
    ("missing", blank_destination),
])
def test_no_case_ever_clears_on_a_degraded_reference(label, mut):
    """The whole corpus: a stale or missing reference never yields CLEAR."""
    degraded = degrade_all(mut)
    assert reference_state(degraded["V-1001"], fixed(NOW)) != "CURRENT"
    assert reference_state(degraded["V-1002"], fixed(NOW)) != "CURRENT"
    cleared = []
    for cid, case in CASES.items():
        r = run_case(case, degraded, extractor_fn=offline_extract, clock=fixed(NOW))
        if r.decision.decision == "CLEAR":
            cleared.append(cid)
        assert r.decision.reference_state != "CURRENT", cid
    assert cleared == [], f"{label} reference cleared {cleared}"


@pytest.mark.parametrize("label,mut", [
    ("stale", lambda b: with_overrides(b, reference_updated_at="2025-01-01")),
    ("missing", blank_destination),
])
def test_a_degraded_reference_only_ever_makes_the_gate_stricter(label, mut):
    """Degrading the record must never release anything the good record held."""
    degraded = degrade_all(mut)
    released = []
    for cid, case in CASES.items():
        good = run_case(case, VENDORS, extractor_fn=offline_extract, clock=fixed(NOW))
        bad = run_case(case, degraded, extractor_fn=offline_extract, clock=fixed(NOW))
        order = {"CLEAR": 0, "REVIEW": 1, "HOLD": 2}
        if order[bad.decision.decision] < order[good.decision.decision]:
            released.append((cid, good.decision.decision, bad.decision.decision))
    assert released == [], released


def test_the_degraded_reference_states_are_reported_to_the_analyst():
    """A decision carries the version and state it was made against."""
    r = run_case(CASES["TG-001"], VENDORS, extractor_fn=offline_extract, clock=fixed(NOW))
    assert r.decision.reference_version == "v1"
    assert r.decision.reference_state == "CURRENT"
    stale = vendor_copy(VENDORS, lambda b: with_overrides(b, reference_updated_at="2025-01-01"))
    r2 = run_case(CASES["TG-001"], stale, extractor_fn=offline_extract, clock=fixed(NOW))
    assert r2.decision.reference_version == "v1"
    assert r2.decision.reference_state == "STALE"
