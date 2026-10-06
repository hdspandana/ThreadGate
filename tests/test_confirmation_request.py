"""I2c - a "they only want us to confirm" verdict has to be justified too.

`confirmation_request` was the one intent that skipped the justification check
entirely: any verbatim quote was accepted as evidence that there was nothing to
gate. That made it the cheapest route past the gate, because a steered model did
not need to find a sentence claiming nothing was changing - it only needed any
sentence it could label as a request for confirmation, and the sentence asking
for the change was sitting right there in the email.

Pointing it at that sentence returned CLEAR, with the reason recorded as
`no_change_evidenced`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.clock import fixed  # noqa: E402
from threadgate.extract import offline_extract  # noqa: E402
from threadgate.invariants import confirmation_request_justified  # noqa: E402
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402
from threadgate.schema import Extraction  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CLOCK = fixed("2026-10-06")


def case_by_id() -> dict:
    out = {}
    for name in ("frozen_v1.json", "frozen_v2.json"):
        for c in load_cases(ROOT / "data" / "cases" / name):
            out[c["id"]] = c
    return out


# ---------------------------------------------------------------------------
# the predicate
# ---------------------------------------------------------------------------
CONFIRMATIONS = [
    "Can you confirm you have our correct bank details on file?",
    "Please confirm the account number you hold for us.",
    "Could you verify the IFSC on your records?",
    "Please check whether the beneficiary name you have matches ours.",
    "Let us know if anything needs correcting.",
    "As per your records, is this right?",
]


@pytest.mark.parametrize("quote", CONFIRMATIONS)
def test_a_genuine_confirmation_request_is_accepted(quote):
    assert confirmation_request_justified(quote), quote


NOT_CONFIRMATIONS = [
    "please update the beneficiary name on our record to Northwind Logistics Ltd",
    "Please remit all future payments to our new account 50100234552222.",
    "Our bank details have changed with immediate effect.",
    "",
    "Following the finance system migration we completed last week.",
]


@pytest.mark.parametrize("quote", NOT_CONFIRMATIONS)
def test_a_quote_that_does_not_ask_for_confirmation_is_rejected(quote):
    assert not confirmation_request_justified(quote), quote


@pytest.mark.parametrize(
    "quote",
    [
        "Please confirm you will update our beneficiary name to Northwind Logistics Ltd.",
        "Can you confirm and change the account on file to 50100234552222?",
    ],
)
def test_a_quote_that_confirms_and_changes_in_one_breath_is_rejected(quote):
    """The confirmation framing does not make the change go away."""
    assert not confirmation_request_justified(quote), quote


def test_the_word_correct_alone_is_not_read_as_a_change_directive():
    """TG-011 turns on this.

    "Our correct bank details" uses `correct` as an adjective. Treating it as a
    request to correct something would reject the one genuine confirmation case
    in the frozen set.
    """
    assert confirmation_request_justified(
        "Can you confirm you have our correct bank details on file?"
    )


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------
BODY = (
    "Hi Priya,\n\n"
    "Following the finance migration, please update the beneficiary name on our "
    "record to Northwind Logistics Ltd with immediate effect.\n\n"
    "Thanks\nMeera\n"
)
CHANGE_SENTENCE = (
    "please update the beneficiary name on our record to Northwind Logistics "
    "Ltd with immediate effect."
)


def _case() -> dict:
    return {
        "id": "SYNTH-CONFIRM",
        "vendor_id": "V-1001",
        "expected_decision": None,
        "email": {
            "from": "Meera Iyer <meera.iyer@northwind.example>",
            "reply_to": "meera.iyer@northwind.example",
            "subject": "Remittance",
            "received_at": "2026-10-06T09:12:00+05:30",
            "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
            "body": BODY,
        },
    }


def _steered(nt, vendor) -> Extraction:
    """A model that labels the change sentence as a request for confirmation."""
    return Extraction(
        intent="confirmation_request",
        intent_evidence=CHANGE_SENTENCE,
        summary="The vendor is asking us to confirm their details.",
        claims=[],
    )


def test_a_steered_model_cannot_clear_a_change_by_calling_it_a_confirmation():
    """The exploit.

    No destination token appears anywhere in this email, so I1 and I5 are both
    silent. The only thing standing between it and a CLEAR was whether the
    `confirmation_request` verdict had to be justified. It did not.
    """
    r = run_case(_case(), VENDORS, extractor_fn=_steered, clock=CLOCK)
    assert r.decision.decision != "CLEAR", (
        "a steered model labelled the change sentence a confirmation request and "
        f"cleared it (reasons: {r.decision.reasons})"
    )
    assert r.decision.decision == "HOLD"
    assert "I2C_CONFIRMATION_REQUEST_NOT_JUSTIFIED" in [
        f.code for f in r.decision.findings
    ]


def test_the_genuine_confirmation_case_still_clears():
    """Tightening this must not cost TG-011, which is exactly this shape."""
    by_id = case_by_id()
    r = run_case(by_id["TG-011"], VENDORS, extractor_fn=offline_extract, clock=CLOCK)
    assert r.decision.decision == "CLEAR", r.decision.reasons


def test_no_frozen_case_regresses():
    """The change touches every `confirmation_request` verdict in the corpus."""
    by_id = case_by_id()
    offenders = []
    for cid, c in by_id.items():
        r = run_case(c, VENDORS, extractor_fn=offline_extract, clock=CLOCK)
        if r.decision.decision != c["expected_decision"]:
            offenders.append((cid, c["expected_decision"], r.decision.decision))
    assert offenders == [], offenders
