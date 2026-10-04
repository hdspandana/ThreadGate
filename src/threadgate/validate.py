"""The evidence validator - the closed-world rule.

Everything the model says must be traceable to characters that are actually in
the email. Concretely, for an output to survive validation:

  1. Every `evidence` string must be found verbatim in the email text the model
     was given (whitespace-tolerant, offsets preserved).
  2. Every `new_value` must be findable in the email, or inside its own
     evidence string. A value the model produced from memory or inference is
     dropped.
  3. If the model states an `old_value` for a field we hold on file and it does
     not match the record, the claim is kept but flagged - the model may be
     reading a different record, and that is worth showing the analyst.

Anything that fails is dropped, not repaired. The validator never guesses what
the model "meant". This is the component that makes the system more than a
wrapper: the model's output is a *hypothesis* about the email, and this module
decides how much of that hypothesis is admissible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import NormalizedText, find_span
from .schema import Claim, Extraction

NUMERIC_FIELDS = {"account_number", "amount", "contact_phone"}
CODE_FIELDS = {"ifsc", "iban", "swift"}


@dataclass
class ValidatedClaim:
    claim: Claim
    verified: bool
    value_span_norm: tuple[int, int] | None = None
    evidence_span_norm: tuple[int, int] | None = None
    value_span_raw: tuple[int, int] | None = None
    evidence_span_raw: tuple[int, int] | None = None
    violations: list[str] = field(default_factory=list)

    @property
    def field(self) -> str:
        return self.claim.field


@dataclass
class ValidationResult:
    intent: str
    intent_evidenced: bool
    intent_span_norm: tuple[int, int] | None = None
    intent_span_raw: tuple[int, int] | None = None
    claims: list[ValidatedClaim] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    dropped_claims: int = 0

    @property
    def verified_claims(self) -> list[ValidatedClaim]:
        return [c for c in self.claims if c.verified]


def _value_candidates(value: str) -> list[str]:
    out = []
    v = (value or "").strip()
    if not v:
        return out
    out.append(v)
    collapsed = re.sub(r"\s+", " ", v)
    if collapsed != v:
        out.append(collapsed)
    digits = re.sub(r"[\s.\-]", "", v)
    if len(digits) >= 8:
        out.append(digits)
    return out


def _locate_value(nt: NormalizedText, value: str, evidence_span: tuple[int, int] | None):
    """Find a value in the email, or inside the claim's own evidence."""
    for cand in _value_candidates(value):
        span = find_span(nt.text, cand)
        if span:
            return span
    if evidence_span:
        ev = nt.text[evidence_span[0]: evidence_span[1]]
        for cand in _value_candidates(value):
            if re.sub(r"\s+", " ", cand).lower() in re.sub(r"\s+", " ", ev).lower():
                return evidence_span
    return None


def validate_extraction(ex: Extraction, nt: NormalizedText) -> ValidationResult:
    result = ValidationResult(intent=ex.intent, intent_evidenced=False)
    text_len = len(nt.text)

    # --- intent evidence -------------------------------------------------
    if ex.intent_evidence:
        span = find_span(nt.text, ex.intent_evidence)
        if span:
            result.intent_evidenced = True
            result.intent_span_norm = span
            result.intent_span_raw = nt.to_raw_span(*span)
        else:
            result.violations.append("intent_evidence_not_verbatim")
    else:
        result.violations.append("intent_evidence_missing")

    # --- claims ----------------------------------------------------------
    for claim in ex.claims:
        vc = ValidatedClaim(claim=claim, verified=False)

        ev_span = None
        if claim.evidence:
            ev_span = find_span(nt.text, claim.evidence)
            if ev_span:
                vc.evidence_span_norm = ev_span
                vc.evidence_span_raw = nt.to_raw_span(*ev_span)
            else:
                vc.violations.append("evidence_not_verbatim")

        if claim.new_value:
            v_span = _locate_value(nt, claim.new_value, ev_span)
            if v_span:
                vc.value_span_norm = v_span
                vc.value_span_raw = nt.to_raw_span(*v_span)
            else:
                vc.violations.append("value_not_in_email")

        # A claim is admissible when it has a verbatim quote AND either a
        # locatable new value or no new value at all (e.g. a deletion claim).
        admissible = bool(ev_span) and (
            vc.value_span_norm is not None or not claim.new_value
        )
        vc.verified = admissible
        result.claims.append(vc)

    result.dropped_claims = sum(1 for c in result.claims if not c.verified)

    # Safety net: offsets must be inside the text.
    for c in result.claims:
        for sp in (c.evidence_span_norm, c.value_span_norm):
            if sp and (sp[0] < 0 or sp[1] > text_len):
                c.verified = False
                c.violations.append("span_out_of_range")
    return result


def check_old_values(claims: list[ValidatedClaim], record_values: dict[str, str | None]) -> list[str]:
    """Flag claims whose stated old value disagrees with the record."""
    notes: list[str] = []
    for c in claims:
        if not c.verified or not c.claim.old_value:
            continue
        current = record_values.get(c.claim.field)
        if current is None:
            continue
        norm = lambda s: re.sub(r"[^0-9a-z]", "", str(s).lower())  # noqa: E731
        if norm(c.claim.old_value) != norm(current):
            notes.append(
                f"model_old_value_mismatch:{c.claim.field}="
                f"{c.claim.old_value[:24]!r}"
            )
    return notes
