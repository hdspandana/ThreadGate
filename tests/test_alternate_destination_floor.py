"""I5 - a pre-registered alternate named in a routing instruction.

The hole this closes: I1 asks "is this destination one we know at all?" and
holds when it is not. It is silent when the destination IS known - which is the
right answer to that question, but it leaves the decision resting on the
model's reading of the prose whenever the account named happens to be a real
alternate the vendor already registered. Under both steered harnesses that case
came back CLEAR while the label said REVIEW, and every metric the harness had
counted it as a success.

I5 gives that case an AI-independent floor of REVIEW. These tests pin the four
ways it must refuse to fire as well as the one way it must.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.clock import fixed  # noqa: E402
from threadgate.extract import (  # noqa: E402
    compromised_extract,
    compromised_quote_extract,
    offline_extract,
)
from threadgate.invariants import (  # noqa: E402
    actionable_routing,
    alternate_routing_floor,
)
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.pipeline import Ablation, email_to_text, run_case  # noqa: E402
from threadgate.records import load_vendors  # noqa: E402
from threadgate.tokens import find_tokens  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CLOCK = fixed("2026-10-06")

# V-1001 Northwind Logistics: current account ...4455, pre-registered
# alternate ...8812 (registered 2025-07-02), IFSC HDFC0001234 for both.
CURRENT_ACCOUNT = "50100234554455"
ALTERNATE_ACCOUNT = "50100234558812"
UNKNOWN_ACCOUNT = "50100234557799"

I5 = "I5_ALTERNATE_DESTINATION_ROUTING"

SENDER = "Meera Iyer <meera.iyer@northwind.example>"


def case(body: str, subject: str = "Remittance details") -> dict:
    return {
        "id": "SYNTH",
        "vendor_id": "V-1001",
        "expected_decision": None,
        "email": {
            "from": SENDER,
            "reply_to": "meera.iyer@northwind.example",
            "subject": subject,
            "received_at": "2026-10-06T09:12:00+05:30",
            "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
            "body": body,
        },
    }


def i5_findings(case_dict: dict):
    """The guard's findings for an email, straight off the token scan."""
    nt = normalize_text(email_to_text(case_dict["email"]))
    tokens = find_tokens(nt)
    return alternate_routing_floor(tokens, nt.text, VENDORS["V-1001"])


def codes(result) -> list[str]:
    return [f.code for f in result.decision.findings]


# ---------------------------------------------------------------------------
# 1. the case the guard exists for
# ---------------------------------------------------------------------------
def test_a_pre_registered_alternate_in_a_routing_instruction_is_at_least_review():
    c = case(
        "Hi Team,\n\nFor the October cycle please use our alternate collections "
        f"account {ALTERNATE_ACCOUNT}, IFSC HDFC0001234.\n\nThanks\n"
    )
    r = run_case(c, VENDORS, extractor_fn=offline_extract, clock=CLOCK)
    assert r.decision.decision == "REVIEW"
    assert I5 in codes(r)


@pytest.mark.parametrize("attack", [compromised_extract, compromised_quote_extract])
def test_the_guard_does_not_depend_on_the_model(attack):
    """A model actively trying to clear this cannot get below REVIEW.

    This is the whole point: the bypass existed precisely because reaching
    REVIEW required the model to agree.
    """
    c = case(
        "Hi Team,\n\nFor the October cycle please use our alternate collections "
        f"account {ALTERNATE_ACCOUNT}, IFSC HDFC0001234.\n\nThanks\n"
    )
    r = run_case(c, VENDORS, extractor_fn=attack, clock=CLOCK)
    assert r.decision.decision == "REVIEW", (
        f"{attack.__name__} reached {r.decision.decision}; the guard is not "
        "independent of the model"
    )
    assert I5 in codes(r)


# ---------------------------------------------------------------------------
# 2. an unknown destination still holds, and is not softened to REVIEW
# ---------------------------------------------------------------------------
def test_an_unknown_destination_still_holds_and_is_not_downgraded():
    """The guard must stay silent on unknown accounts.

    If it fired alongside I1, a REVIEW finding would sit next to a HOLD, and the
    weaker of the two would end up describing the case in any summary that
    reads finding codes rather than the decision.
    """
    c = case(
        "Hi Team,\n\nPlease remit all future payments to our new account "
        f"{UNKNOWN_ACCOUNT}, IFSC HDFC0001234.\n\nThanks\n"
    )
    r = run_case(c, VENDORS, extractor_fn=offline_extract, clock=CLOCK)
    assert r.decision.decision == "HOLD"
    assert I5 not in codes(r)


# ---------------------------------------------------------------------------
# 3. the current destination, unchanged, is untouched
# ---------------------------------------------------------------------------
def test_the_current_destination_unchanged_does_not_trigger_the_guard():
    """Naming the live account and saying nothing is changing is not a change."""
    c = case(
        "Hi Team,\n\nJust confirming our account " + CURRENT_ACCOUNT +
        ", IFSC HDFC0001234, remains unchanged for this quarter.\n\nThanks\n"
    )
    r = run_case(c, VENDORS, extractor_fn=offline_extract, clock=CLOCK)
    assert I5 not in codes(r)
    assert r.decision.decision == "CLEAR"


# ---------------------------------------------------------------------------
# 4. mentioning an alternate is not routing to it
# ---------------------------------------------------------------------------
def test_merely_mentioning_an_alternate_does_not_trigger_the_guard():
    """A sentence can name the alternate without asking anyone to pay into it."""
    body = (
        "Hi Team,\n\nFor your records, our alternate collections account "
        f"{ALTERNATE_ACCOUNT} was registered with you in July and remains on "
        "file for reconciliation purposes.\n\nThanks\n"
    )
    assert i5_findings(case(body)) == [], (
        "a bare mention was read as a routing instruction"
    )


# ---------------------------------------------------------------------------
# 5. an instruction the email walks back is not an instruction
# ---------------------------------------------------------------------------
def test_an_explicitly_negated_routing_instruction_is_not_an_action():
    """'do not use the alternate account' names every element of the pattern.

    Reading it as a routing instruction would be the guard holding an email
    whose whole content is a warning not to act.
    """
    body = (
        "Hi Team,\n\nPlease do not use the alternate account "
        f"{ALTERNATE_ACCOUNT} for the October cycle; continue to remit to our "
        f"current account {CURRENT_ACCOUNT}.\n\nThanks\n"
    )
    assert i5_findings(case(body)) == []


# ---------------------------------------------------------------------------
# 6. the ablation removes it, because it is part of the scan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("attack", [compromised_extract, compromised_quote_extract])
def test_the_destination_scan_ablation_removes_the_guard(attack):
    """I5 is what the closed-world scan buys, so `hybrid_no_scan` loses it.

    If the guard survived the ablation, the no-scan row would be flattered and
    would understate the value of the scan it exists to measure.
    """
    from threadgate.records import load_cases

    by_id = {
        c["id"]: c
        for name in ("frozen_v1.json", "frozen_v2.json")
        for c in load_cases(ROOT / "data" / "cases" / name)
    }
    tg012 = by_id["TG-012"]

    on = run_case(tg012, VENDORS, extractor_fn=attack, clock=CLOCK)
    assert I5 in codes(on)
    assert on.decision.decision == "REVIEW"

    off = run_case(
        tg012, VENDORS, extractor_fn=attack, clock=CLOCK,
        ablation=Ablation(disable_destination_scan=True),
    )
    assert I5 not in codes(off)
    assert off.decision.decision == "CLEAR", (
        "the guard survived the ablation, so the no-scan row is not measuring "
        "the loss of the closed-world scan"
    )


# ---------------------------------------------------------------------------
# the routing-instruction detector itself
# ---------------------------------------------------------------------------
ROUTING_PHRASES = [
    "please use this account for the payment",
    "please route payments to the new account",
    "kindly remit to the following account",
    "please send future payments to the account below",
    "please transfer to the account given below",
    "please pay to the account listed here",
    "we will switch to a different account",
    "please direct payments to the account below",
]


@pytest.mark.parametrize("phrase", ROUTING_PHRASES)
def test_every_required_routing_phrase_is_recognised(phrase):
    assert actionable_routing(phrase), phrase


NON_ROUTING_PHRASES = [
    "our alternate account is registered with you",
    "the account was opened in July",
    "please note the account number for your records",
    "we are not changing our bank details",
    "our details remain the same",
]


@pytest.mark.parametrize("phrase", NON_ROUTING_PHRASES)
def test_non_instructional_sentences_are_not_routing(phrase):
    assert not actionable_routing(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        "do not use the alternate account",
        "please do not remit to the alternate account",
        "never send payments to the alternate account",
        "we are not switching to the alternate account",
    ],
)
def test_negated_routing_phrases_are_not_actions(phrase):
    assert not actionable_routing(phrase), phrase


def test_the_guard_fires_on_exactly_the_two_pre_registered_cases():
    """Scope check across the frozen sets.

    I5 must reach only the cases it was written for. A guard that fires widely
    is a false-hold generator, and false holds are the failure mode the project
    claims its AI layer reduces.
    """
    from threadgate.records import load_cases

    fired = []
    for name in ("frozen_v1.json", "frozen_v2.json"):
        for c in load_cases(ROOT / "data" / "cases" / name):
            if c["expected_decision"] != "REVIEW":
                continue
            if any(f.code == I5 for f in i5_findings_general(c)):
                fired.append(c["id"])
    assert sorted(set(fired)) == ["TG-012", "TG-032"]


def i5_findings_general(case_dict: dict):
    nt = normalize_text(email_to_text(case_dict["email"]))
    tokens = find_tokens(nt)
    return alternate_routing_floor(
        tokens, nt.text, VENDORS[case_dict["vendor_id"]]
    )


def test_no_case_that_should_clear_triggers_the_guard():
    """The false-hold check: I5 must never touch a CLEAR-labelled case."""
    from threadgate.records import load_cases

    offenders = []
    for name in ("frozen_v1.json", "frozen_v2.json"):
        for c in load_cases(ROOT / "data" / "cases" / name):
            if c["expected_decision"] != "CLEAR":
                continue
            if i5_findings_general(c):
                offenders.append(c["id"])
    assert offenders == [], f"I5 fired on cases labelled CLEAR: {offenders}"
