"""The policy engine: a monotone, deterministic decision rule.

The rule is deliberately one-directional. Triggers can only move a request
towards HOLD; none of them can move it towards CLEAR. The model's contribution
enters as *verified claims*, and a verified claim can add a HOLD trigger but can
never remove one. That is the whole security argument, and it is why the
compromised-model harness degrades to "hold everything" instead of "clear
everything".

Decision surface:

    HOLD    - cannot execute without out-of-band human verification
    REVIEW  - a change was identified and it matches the record on file;
              a human still attests before anything executes
    CLEAR   - no change was identified by this prototype; nothing to gate.
              This is not a statement that the email is safe or approved.
"""

from __future__ import annotations

from .invariants import (
    authentication_findings,
    change_act_detected,
    destination_floor,
    no_change_justified,
    out_of_band_destination,
    unverifiable_finding,
)

# What this gate is for. Anything not in DESTINATION_FIELDS is reported to the
# analyst but is not what the closed-world rule protects, and none of it feeds a
# numeric risk score.
DESTINATION_FIELDS = {"account_number", "iban", "swift", "ifsc", "beneficiary_name"}
INSTRUCTION_FIELDS = {"currency", "amount", "payment_terms"}
CONTACT_FIELDS = {"remittance_email", "contact_person", "contact_phone"}
from .normalize import NormalizedText
from .records import Vendor
from .schema import Decision, FieldDiff, Finding
from .tokens import Token
from .validate import ValidationResult


def _checklist(
    vendor: Vendor,
    diffs: list[FieldDiff],
    floor: list[Finding],
    unverifiable: bool,
    out_of_band: bool = False,
) -> list[str]:
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
    if out_of_band:
        items.append(
            "Do not open the attachment or image. Ask the vendor to read the destination "
            "out over the phone, or retrieve it from a channel you initiate."
        )
    if unverifiable:
        items.append("Ask for the new details through a channel you initiate.")
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
    ablation=None,
) -> Decision:
    """Apply the decision rule.

    `ablation` is evaluation-only. With `disable_destination_scan` the
    closed-world floor is skipped and the gate has to rely on the model's
    reading alone - which is the comparison the evaluation needs and the reason
    the floor exists.
    """
    findings: list[Finding] = list(authentication_findings(email or {}))

    if ablation is not None and ablation.disable_destination_scan:
        floor: list[Finding] = []
        findings.append(
            Finding(
                code="ABLATION_NO_DESTINATION_SCAN",
                severity="info",
                message="Ablation: the closed-world destination scan is disabled on this run.",
            )
        )
    else:
        floor = destination_floor(tokens, vendor)
    findings.extend(floor)

    # I4 - the destination is not in this message at all.
    out_of_band = out_of_band_destination(nt.text)
    findings.extend(out_of_band)

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
                    # Deliberately not severity="hold". This finding says the model's
                    # verdict was not accepted; whether that escalates is decided by
                    # I3 below. Marking it "hold" would assert a consequence it does
                    # not have when there is no change language and no unknown
                    # destination, and a finding that claims a hold that did not
                    # happen is worse than no finding at all.
                    code="I2B_NO_CHANGE_INTENT_NOT_JUSTIFIED",
                    severity="info",
                    message=(
                        "The model reports no change, but the sentence it quoted does not say "
                        "that. The verdict is not accepted and the request falls through to the "
                        "deterministic change-act check."
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

    if high or medium or floor or unverifiable or out_of_band:
        decision = "HOLD"
        if out_of_band:
            reasons.append("destination_out_of_band")
    elif low:
        decision = "REVIEW"
        reasons.append("verified_low_risk_change:" + ",".join(sorted({d.field for d in low})))
    else:
        decision = "CLEAR"
        reasons.append("no_change_evidenced" if no_change_accepted else "nothing_to_gate")

    return Decision(
        decision=decision,
        reasons=list(dict.fromkeys(reasons)),
        diffs=diffs,
        findings=findings,
        # Anything that is not CLEAR still needs a human to attest before the
        # change executes. Only HOLD additionally carries the out-of-band
        # callback checklist.
        attestation_required=(decision != "CLEAR"),
        checklist=_checklist(vendor, diffs, floor, unverifiable, bool(out_of_band))
        if decision == "HOLD"
        else [],
    )
