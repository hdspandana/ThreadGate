"""Data contracts.

`Extraction` is the ONLY thing the model is allowed to produce. Note what is
not in it: there is no `risk` field, no `verdict` field, no `is_fraud` field.
The model interprets; it never decides. Every claim carries an `evidence`
string that must be copied verbatim from the email.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

INTENTS = Literal["change_request", "no_change", "confirmation_request", "unverifiable"]

CHANGE_FIELDS = Literal[
    "account_number",
    "ifsc",
    "iban",
    "swift",
    "beneficiary_name",
    "bank_name",
    "branch",
    "currency",
    "amount",
    "payment_terms",
    "remittance_email",
    "contact_person",
    "contact_phone",
    "other",
]


class Claim(BaseModel):
    field: CHANGE_FIELDS
    old_value: str | None = Field(
        default=None,
        description="A previous or current value that the EMAIL explicitly states. It is "
        "NOT the value on file: the model is not shown the record and must never "
        "guess it. Leave null unless the email itself states the value.",
    )
    new_value: str | None = Field(default=None, description="Requested new value, verbatim from the email.")
    evidence: str = Field(default="", description="Verbatim quote from the email supporting this claim.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Extraction(BaseModel):
    intent: INTENTS
    intent_evidence: str = Field(
        default="",
        description="Verbatim quote from the email that justifies the intent. Required; an "
        "unquoted intent is treated as unverified by the validator.",
    )
    summary: str = Field(default="", description="One sentence, neutral description of what the email asks for.")
    claims: list[Claim] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Pipeline types (produced by code, never by the model)
# --------------------------------------------------------------------------

# The final decision vocabulary. Three states, and the escalation ladder is
# CLEAR < REVIEW < HOLD: triggers may only move a request towards HOLD.
#
# CLEAR  means "no change was identified by this prototype". It is NOT a
#        statement that the email is safe, approved, or fraud-free. Nothing in
#        the codebase may render it as one.
# REVIEW means a change was identified and it matches the record on file. It
#        still requires a human to attest before anything executes.
# HOLD   means the change cannot be executed without out-of-band human
#        verification.
#
# `no_change` remains in INTENTS above, but that is model-facing: it describes
# what the *email* asks for, not what the gate decides.
DECISIONS = Literal["CLEAR", "REVIEW", "HOLD"]


class FieldDiff(BaseModel):
    field: str
    old_value: str | None
    new_value: str | None
    changed: bool
    risk: Literal["high", "medium", "low", "unknown"]
    pre_registered: bool = False
    note: str = ""


class Finding(BaseModel):
    code: str
    severity: Literal["block", "hold", "info"]
    message: str
    snippet: str = ""
    span_norm: tuple[int, int] | None = None
    independent_of_model: bool = False


class Decision(BaseModel):
    decision: DECISIONS
    reasons: list[str] = Field(default_factory=list)
    diffs: list[FieldDiff] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    # True whenever the decision is not CLEAR. It describes the *requirement*,
    # not whether it has been met - a satisfied attestation does not set this to
    # False, because the requirement still exists and rule 19 pins it to
    # `decision != "CLEAR"`. `attestation_status` carries the state.
    attestation_required: bool = False
    checklist: list[str] = Field(default_factory=list)
    # Which version of the record this decision was made against, and whether
    # that record was current. Both are security inputs, not annotations: an
    # attestation made against another version is refused.
    reference_version: str = "unversioned"
    reference_state: str = "CURRENT"
    # NOT_REQUIRED | PENDING | SATISFIED | REJECTED
    attestation_status: str = "NOT_REQUIRED"
    attestation_code: str = ""
    model_config = {"arbitrary_types_allowed": True}
