"""The policy engine: a monotone, deterministic decision rule.

The rule is deliberately one-directional. Triggers can only move a request
towards HOLD; none of them can move it towards ALLOW. The model's contribution
enters as *verified claims*, and a verified claim can add a HOLD trigger but can
never remove one. That is the whole security argument, and it is why the
compromised-model harness degrades to "hold everything" instead of "allow
everything".

Decision surface:

    HOLD       - cannot execute without out-of-band human verification
    ALLOW      - verified as pre-registered or low risk, safe to execute
    NO_CHANGE  - the email asks for nothing; there is nothing to gate
"""

from __future__ import annotations

from .invariants import (
    account_floor,
    authentication_findings,
    change_act_detected,
    no_change_justified,
    unverifiable_finding,
)
from .normalize import NormalizedText
from .records import Vendor
from .schema import Decision, FieldDiff, Finding
from .tokens import Token
from .validate import ValidationResult


def _checklist(vendor: Vendor, diffs: list[FieldDiff], floor: list[Finding], unverifiable: bool) -> list[str]:
    items: list[str] = []
    phone = vendor.current("contact_phone")
    items.append(
        f"Call {vendor.display_name} on the number already on file"
        + (f" ({phone})" if phone else "")
        + ". Do not call any number in this email."
    )
    for f in floor:
        items.append("Read the account number back digit by digit and confirm who it belongs to.")
    for d in diffs:
        if not d.changed:
            continue
        if d.field == "account_number":
            items.append(
                f"Confirm in writing that {d.new_value} belongs to {vendor.current('beneficiary_name')}."
            )
        elif d.field == "beneficiary_name":
            items.append("Obtain the merger or name-change document before renaming the beneficiary.")
        elif d.field == "ifsc":
            items.append("Confirm the branch move with the bank's published IFSC list.")
        elif d.field == "currency" or d.field == "amount":
            items.append("Re-issue the invoice from the vendor's billing system, not from this email.")
        elif d.field == "remittance_email":
            items.append("Verify the new advice mailbox through the vendor's primary contact.")
    if unverifiable:
        items.append("Ask for the new details through a channel you initiate; do not open the attachment.")
    items.append("Two-person approval before the record is updated, and re-confirm on the next payment run.")
    return list(dict.fromkeys(items))


def decide(
    vendor: Vendor,
    intent: str,
    validation: ValidationResult,
    diffs: list[FieldDiff],
    tokens: list[Token],
    nt: NormalizedText,
    email: dict | None = None,
) -> Decision:
    findings: list[Finding] = list(authentication_findings(email or {}))

    floor = account_floor(tokens, vendor)
    findings.extend(floor)

    changed = [d for d in diffs if d.changed]
    high = [d for d in changed if d.risk == "high"]
    medium = [d for d in changed if d.risk == "medium"]
    low = [d for d in changed if d.risk == "low"]

    reasons: list[str] = []

    if high:
        findings.append(
            Finding(
                code="P_HIGH_RISK_FIELD_CHANGE",
                severity="hold",
                message="High-risk field(s) differ from the record: "
                + ", ".join(f"{d.field} ({d.note or 'changed'})" for d in high),
            )
        )
        reasons.append("high_risk_field_change:" + ",".join(sorted({d.field for d in high})))

    if medium:
        findings.append(
            Finding(
                code="P_MEDIUM_RISK_FIELD_CHANGE",
                severity="hold",
                message="Medium-risk field(s) differ from the record: "
                + ", ".join(f"{d.field} ({d.note or 'changed'})" for d in medium),
            )
        )
        reasons.append("medium_risk_field_change:" + ",".join(sorted({d.field for d in medium})))

    ceiling = vendor.typical_max_amount()
    over_ceiling = [
        d for d in diffs if d.amount_value is not None and ceiling and d.amount_value > ceiling
    ]
    if over_ceiling:
        findings.append(
            Finding(
                code="P_AMOUNT_ABOVE_CEILING",
                severity="hold",
                message="Value above this vendor's typical ceiling ("
                + f"{ceiling:,.0f}): "
                + ", ".join(f"{d.amount_value:,.0f}" for d in over_ceiling),
            )
        )
        reasons.append("amount_above_typical_ceiling")

    if floor:
        reasons.append("unknown_account_token")

    # --- what counts as an accepted "nothing to do"? ----------------------
    # I2: the intent must be quoted. I2b: for a no_change verdict the quote has
    # to actually say nothing is changing. See invariants.no_change_justified.
    quote = ""
    if validation.intent_evidenced and validation.intent_span_norm:
        quote = nt.text[validation.intent_span_norm[0]: validation.intent_span_norm[1]]
    if intent == "confirmation_request":
        no_change_accepted = validation.intent_evidenced
    elif intent == "no_change":
        no_change_accepted = validation.intent_evidenced and no_change_justified(quote)
        if validation.intent_evidenced and not no_change_justified(quote):
            findings.append(
                Finding(
                    code="I2B_NO_CHANGE_NOT_JUSTIFIED",
                    severity="hold",
                    message=(
                        "The model reports no change, but the sentence it quoted does not say "
                        "that. The verdict and its justification disagree, so the verdict is "
                        "not accepted."
                    ),
                    snippet=quote[:200],
                    span_norm=validation.intent_span_norm,
                )
            )
    else:
        no_change_accepted = False

    unverifiable = False
    if not no_change_accepted and not validation.verified_claims:
        # Nothing survived validation, and the model is not credibly saying
        # "nothing to do". Either it admits it cannot read the values, or it
        # claims a change it could not point at, or deterministic change
        # language is present with no values behind it. Any of those is a hold.
        if intent in ("unverifiable", "change_request") or change_act_detected(nt.text):
            unverifiable = True
            findings.append(
                unverifiable_finding(
                    "The email talks about a payment change but no value in it could be "
                    "verified against the record."
                )
            )
            reasons.append("unverifiable_no_values")

    for f in floor:
        reasons.append("I1_UNKNOWN_ACCOUNT_TOKEN")

    if high or medium or floor or unverifiable or over_ceiling:
        decision = "HOLD"
    elif low:
        decision = "ALLOW"
        reasons.append("verified_low_risk_change:" + ",".join(sorted({d.field for d in low})))
    else:
        decision = "NO_CHANGE"
        reasons.append("no_change_evidenced" if no_change_accepted else "nothing_to_gate")

    return Decision(
        decision=decision,
        reasons=list(dict.fromkeys(reasons)),
        diffs=diffs,
        findings=findings,
        attestation_required=(decision == "HOLD"),
        checklist=_checklist(vendor, diffs, floor, unverifiable) if decision == "HOLD" else [],
    )
