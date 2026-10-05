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
        default=None, description="Current value on file, if the email states or implies one."
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

DECISIONS = Literal["ALLOW", "HOLD", "NO_CHANGE"]


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
    attestation_required: bool = False
    checklist: list[str] = Field(default_factory=list)
    model_config = {"arbitrary_types_allowed": True}
