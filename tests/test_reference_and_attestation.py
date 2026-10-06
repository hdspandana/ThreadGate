"""Reference states, attestation, and the limits that are deliberately not built.

The gate is only as good as the record it checks against, so this module pins
down what happens when that record is incomplete, and what the system does and
does not promise about it.

Two properties are asserted as *absent* rather than present, because building
them would mean designing a reference-versioning and attestation-storage
subsystem, which is out of scope and is not claimed anywhere:

  * stale-reference detection (no reference version history exists)
  * replay protection (no attestation store exists)

`test_nothing_claims_the_absent_properties` fails if the code ever grows them
without the documentation being updated, which is the failure mode that would
actually be dangerous - a README promising a control the binary does not have.
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.compare import diff_claims  # noqa: E402
from threadgate.extract import offline_extract  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.pipeline import email_to_text, run_case  # noqa: E402
from threadgate.records import FIELD_PATHS, load_cases, load_vendors  # noqa: E402
from threadgate.schema import Claim, Extraction  # noqa: E402
from threadgate.validate import validate_extraction  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CASES: dict[str, dict] = {}
for _name in ("frozen_v1.json", "frozen_v2.json"):
    for _c in load_cases(ROOT / "data" / "cases" / _name):
        CASES[_c["id"]] = _c


def _nt(case):
    return normalize_text(email_to_text(case["email"]))


def _vendor_without(vendor, field_name: str):
    """A copy of the vendor record with one reference field blanked."""
    data = copy.deepcopy(vendor.data)
    path = FIELD_PATHS[field_name]
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = None
    out = dataclasses.replace(vendor, data=data)
    out.__post_init__()
    return out


# ---------------------------------------------------------------------------
# reference states
# ---------------------------------------------------------------------------
def test_current_reference_matches_the_record(vendors):
    v = vendors["V-1001"]
    assert v.current("account_number") == "50100234554455"
    assert v.account_status("50100234554455") == "current"
    assert v.is_known_account("50100234554455")


def test_missing_reference_is_none_not_a_guess(vendors):
    v = _vendor_without(vendors["V-1001"], "account_number")
    assert v.current("account_number") is None
    assert not v.is_known_account("50100234554455")


def test_a_missing_reference_escalates_instead_of_crashing(vendors):
    """Regression: account_floor used to slice current('account_number')[-4:],
    so a record with no account on file raised TypeError and took the whole
    pipeline down. Absent reference data must never crash the gate."""
    broken = dict(vendors)
    broken["V-1001"] = _vendor_without(vendors["V-1001"], "account_number")
    r = run_case(CASES["TG-001"], broken, extractor_fn=offline_extract)
    assert r.decision.decision == "HOLD"
    assert any(f.code == "I1_UNKNOWN_ACCOUNT_TOKEN" for f in r.decision.findings)


def test_a_missing_reference_only_ever_makes_the_gate_stricter(vendors):
    """Blanking the account on file must not release anything that was held."""
    broken = dict(vendors)
    broken["V-1001"] = _vendor_without(vendors["V-1001"], "account_number")
    released = []
    for cid, case in CASES.items():
        if case["expected_decision"] != "HOLD":
            continue
        r = run_case(case, broken, extractor_fn=offline_extract)
        if r.decision.decision != "HOLD":
            released.append(cid)
    assert released == [], released


def test_pre_registered_alternates_survive_a_blanked_current_account(vendors):
    """An allowlisted account is still known even with no current account."""
    v = _vendor_without(vendors["V-1001"], "account_number")
    assert v.is_known_account("50100234558812"), "alternate should stay on file"
    assert v.account_status("50100234558812", ).startswith("allowlisted:")


# ---------------------------------------------------------------------------
# the two properties that are deliberately absent
# ---------------------------------------------------------------------------
ABSENT = {
    "stale reference / version lineage": re.compile(
        r"\b(reference_version|reference_revision|stale_reference|version_lineage)\b", re.I),
    "replay protection": re.compile(
        r"\b(attestation_store|replay_protection|nonce|replay_token)\b", re.I),
}


def _source_text() -> str:
    out = []
    for path in (*(ROOT / "src").rglob("*.py"), *(ROOT / "eval").rglob("*.py")):
        out.append(path.read_text(encoding="utf-8"))
    return "\n".join(out)


@pytest.mark.parametrize("label", sorted(ABSENT))
def test_the_absent_properties_really_are_absent(label):
    """If either is ever implemented, this fails and the docs must be updated
    in the same change. Silently gaining the code without the claim - or
    vice versa - is the dangerous direction."""
    assert not ABSENT[label].search(_source_text()), (
        f"{label} appears in the source; either finish it and document it, or "
        f"remove it and update this test"
    )


def test_the_readme_states_what_is_not_built():
    """A reader who assumed replay protection or reference versioning existed
    would be misled about what this prototype guarantees. The README has to keep
    saying they are absent, in the same change that keeps them absent."""
    low = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    marker = next(
        (m for m in ("not built, and not claimed", "not built", "not implemented")
         if m in low),
        None,
    )
    assert marker, "README must keep an explicit list of what is not built"
    tail = low[low.index(marker): low.index(marker) + 1600]
    assert "replay" in tail, "replay protection must be listed as not built"
    assert "version" in tail, "reference version lineage must be listed as not built"


# ---------------------------------------------------------------------------
# attestation
# ---------------------------------------------------------------------------
def test_clear_is_the_only_decision_that_needs_no_human(vendors):
    """CLEAR means nothing was identified, so there is nothing to attest to.
    REVIEW and HOLD both still require a person before anything executes."""
    seen = set()
    for cid, case in CASES.items():
        r = run_case(case, vendors, extractor_fn=offline_extract)
        d = r.decision
        seen.add(d.decision)
        if d.decision == "CLEAR":
            assert not d.attestation_required, cid
        else:
            assert d.attestation_required, cid
    assert seen == {"CLEAR", "REVIEW", "HOLD"}, seen


def test_only_hold_carries_an_out_of_band_checklist(vendors):
    """Attestation is not the same as an out-of-band callback. REVIEW needs a
    sign-off; HOLD additionally needs someone to pick up the phone."""
    checklists = {}
    for cid, case in CASES.items():
        r = run_case(case, vendors, extractor_fn=offline_extract)
        checklists.setdefault(r.decision.decision, []).append(len(r.decision.checklist))
    assert max(checklists.get("CLEAR", [0])) == 0
    assert max(checklists.get("REVIEW", [0])) == 0
    assert min(checklists.get("HOLD", [1])) >= 1


# ---------------------------------------------------------------------------
# record selection and the comparator
# ---------------------------------------------------------------------------
def test_the_record_is_chosen_by_the_case_not_the_model(vendors):
    """A model asserting a different supplier must not change which record is
    compared against."""
    case = CASES["TG-001"]
    r = run_case(case, vendors, extractor_fn=offline_extract)
    assert r.vendor_id == case["vendor_id"]
    # and the summary the model returns cannot redirect it
    assert r.decision.decision == "HOLD"


def test_comparator_reports_a_real_change_and_a_pre_registered_one(vendors):
    v = vendors["V-1001"]
    nt = _nt(CASES["TG-001"])
    ex = Extraction(
        intent="change_request",
        intent_evidence="Account number: 50100234559821",
        claims=[Claim(field="account_number", new_value="50100234559821",
                      evidence="Account number: 50100234559821")],
    )
    diffs = diff_claims(validate_extraction(ex, nt).claims, v)
    assert diffs and diffs[0].changed and diffs[0].risk == "high"

    nt2 = _nt(CASES["TG-012"])
    ex2 = offline_extract(nt2, v)
    diffs2 = diff_claims(validate_extraction(ex2, nt2).claims, v)
    assert any(d.pre_registered for d in diffs2)


def test_an_absent_old_value_does_not_read_as_no_change(vendors):
    """If the record has nothing on file, a requested value is a change, not a
    match. Blank must never equal equal."""
    v = vendors["V-1001"]
    nt = _nt(CASES["TG-001"])
    ex = Extraction(
        intent="change_request",
        intent_evidence="Account number: 50100234559821",
        claims=[Claim(field="account_number", old_value=None,
                      new_value="50100234559821",
                      evidence="Account number: 50100234559821")],
    )
    diffs = diff_claims(validate_extraction(ex, nt).claims, v)
    assert diffs and diffs[0].changed


# ---------------------------------------------------------------------------
# quoted and forwarded content
# ---------------------------------------------------------------------------
QUOTED_MAIL = (
    "From: accounts@northwind.example\n"
    "Subject: Remittance update\n\n"
    "Hi,\n\nPlease note our new details:\n\n"
    "> -----Original message-----\n"
    "> From: Meera\n"
    "> A/C 50100234559821\n"
    "> IFSC HDFC0008890\n\n"
    "Thanks\n"
)


def test_destination_tokens_inside_quoted_text_are_still_scanned(vendors):
    """Forwarded and quoted blocks are part of the thread. An attacker who puts
    the new account behind a '>' must not slip past the floor."""
    from threadgate.invariants import destination_floor
    from threadgate.tokens import find_tokens

    nt = normalize_text(QUOTED_MAIL)
    floor = destination_floor(find_tokens(nt), vendors["V-1001"])
    codes = {f.code for f in floor}
    assert "I1_UNKNOWN_ACCOUNT_TOKEN" in codes
    assert "I1_UNKNOWN_DESTINATION_CODE" in codes
    assert all(f.independent_of_model for f in floor)
