"""The evidence validator - the closed-world rule.

Everything the model says must be traceable to characters that are actually in
the email. Concretely, for an output to survive validation:

  1. Every `evidence` string must be found verbatim in the email text the model
     was given (whitespace-tolerant, offsets preserved).
  2. Every `new_value` must occur inside its own evidence span - the quote the
     model offered has to actually contain the value it is offered for. A value
     the model produced from memory, inferred, or lifted from a different part
     of the email is dropped.
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
    """Find a value INSIDE the claim's own evidence span.

    The quote is the warrant for the value, so the value has to be in it. The
    previous version searched the whole email first and only fell back to the
    evidence, which broke the binding: a claim could quote one sentence and
    carry a value that appears somewhere else in the message entirely.

    That matters because an email routinely contains several payment numbers.
    "Our old account 1111 is closing" and "our new account is 2222" are two
    sentences about two numbers, and a claim that new_value is 1111 while
    quoting the sentence about 2222 is not a claim the quote supports - but it
    validated, because 1111 was in the email. The analyst reading the
    highlighted evidence would have been shown a quote that says the opposite
    of the value attached to it.

    The value is now located only within the span the model quoted. If it is not
    there, the claim is inadmissible and is dropped rather than repaired.
    """
    if evidence_span is None:
        return None
    s0, s1 = evidence_span
    ev = nt.text[s0:s1]
    for cand in _value_candidates(value):
        span = find_span(ev, cand)
        if span:
            return (s0 + span[0], s0 + span[1])
    # Separator-insensitive fallback. The model may report a value with
    # different spacing or punctuation than the quote uses - "5010 0234 559 821"
    # against "50100234559821". Precise offsets are lost here and the evidence
    # span is returned instead; the property being enforced is containment, and
    # the evidence span is still the correct thing to highlight.
    ev_key = re.sub(r"[^0-9a-z]", "", ev.lower())
    for cand in _value_candidates(value):
        key = re.sub(r"[^0-9a-z]", "", cand.lower())
        if key and key in ev_key:
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
