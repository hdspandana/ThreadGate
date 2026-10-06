"""Orchestration: one email in, one Decision out.

    normalise -> tokenise (code) -> extract (model) -> validate (code)
              -> compare (code) -> invariants (code) -> policy (code)

The model is one box in the middle. Everything before it prepares untrusted
text; everything after it refuses to trust the model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .attestation import (
    AttestationState,
    AttestationStore,
    VerificationContext,
    VerificationEvent,
    destination_digest,
    request_id_for,
)
from .clock import SystemClock
from .compare import diff_claims
from .extract import get_extractor
from .normalize import NormalizedText, normalize_text
from .policy import decide
from .records import Vendor
from .reference import reference_version
from .schema import Decision, Extraction, Finding
from .tokens import Token, find_tokens
from .validate import ValidatedClaim, ValidationResult, check_old_values, validate_extraction


@dataclass
class Ablation:
    """Evaluation-only switches that disable one safeguard at a time.

    These exist so the evaluation can show what each safeguard is worth. They
    default to off, and the product path never sets them. Turning one on makes
    the gate strictly weaker - that is the point, and it is why the ablated
    rows are expected to look worse.
    """

    name: str = "none"
    disable_destination_scan: bool = False
    disable_evidence_validation: bool = False


@dataclass
class PipelineResult:
    case_id: str
    vendor_id: str
    decision: Decision
    extraction: Extraction
    validation: ValidationResult
    tokens: list[Token]
    nt: NormalizedText
    extractor: str
    elapsed_ms: float
    expected: str | None = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    # What this request is bound to, and where the human-verification step stands.
    verification: VerificationContext | None = None
    attestation: AttestationState | None = None

    @property
    def correct(self) -> bool | None:
        if self.expected is None:
            return None
        return self.decision.decision == self.expected

    @property
    def unsafe(self) -> bool | None:
        """Expected HOLD, but the gate did not hold it. The only error that can lose money."""
        if self.expected is None:
            return None
        return self.expected == "HOLD" and self.decision.decision != "HOLD"

    @property
    def false_hold(self) -> bool | None:
        """Expected to go through, but a human was asked to look at it. Costs time, not money."""
        if self.expected is None:
            return None
        return self.expected != "HOLD" and self.decision.decision == "HOLD"


def _trust_everything(ex: Extraction, nt: NormalizedText) -> ValidationResult:
    """Ablation F. Accept the model's output without the closed-world check.

    Used only to measure what evidence validation is worth. Every claim is
    admitted, including values that are not in the email at all.
    """
    result = ValidationResult(intent=ex.intent, intent_evidenced=True)
    result.intent_span_norm = (0, min(len(nt.text), 40)) or None
    result.intent_span_raw = nt.to_raw_span(*result.intent_span_norm) if result.intent_span_norm else None
    for claim in ex.claims:
        result.claims.append(ValidatedClaim(claim=claim, verified=True, violations=["ablation"]))
    return result


def email_to_text(email: dict) -> str:
    return (
        f"From: {email.get('from','')}\n"
        f"Reply-To: {email.get('reply_to','')}\n"
        f"Subject: {email.get('subject','')}\n"
        f"Received: {email.get('received_at','')}\n\n"
        f"{email.get('body','')}"
    )


def run_case(
    case: dict,
    vendors: dict[str, Vendor],
    extractor_mode: str | None = None,
    extractor_fn=None,
    ablation: Ablation | None = None,
    clock=None,
    store: AttestationStore | None = None,
    presented_event: VerificationEvent | None = None,
) -> PipelineResult:
    """Run one case.

    `clock` is the injected time source for reference freshness; it defaults to
    the system clock and is pinned by tests and by the evaluation.

    `store` and `presented_event` drive the human-verification step. When an
    event is presented against a decision that requires attestation, the store
    decides whether it is accepted and burns it either way. A rejected
    attestation is recorded and never changes the decision - it can neither
    release a hold nor manufacture a clear.
    """
    started = time.perf_counter()
    vendor = vendors[case["vendor_id"]]
    raw = email_to_text(case["email"])
    nt = normalize_text(raw)
    tokens = find_tokens(nt)

    error: str | None = None
    notes: list[str] = []

    extract = extractor_fn or get_extractor(extractor_mode)
    try:
        extraction = extract(nt, vendor)
    except Exception as exc:  # noqa: BLE001
        error = f"extractor_error: {exc}"
        extraction = Extraction(intent="unverifiable", intent_evidence="", summary=error)

    # Ablation F: skip the closed-world check and admit everything the model
    # produced. Evaluation only - the product path never sets an ablation.
    if ablation is not None and ablation.disable_evidence_validation:
        validation = _trust_everything(extraction, nt)
        notes.append("ablation:evidence_validation_disabled")
    else:
        validation = validate_extraction(extraction, nt)
    record_values = {f: vendor.current(f) for f in {c.claim.field for c in validation.claims}}
    notes.extend(check_old_values(validation.claims, record_values))
    notes.extend(f"validator:{v}" for v in validation.violations)

    diffs = diff_claims(validation.claims, vendor)
    clock = clock or SystemClock()
    decision = decide(vendor, extraction.intent, validation, diffs, tokens, nt,
                      case["email"], ablation=ablation, clock=clock)

    # Fail closed before anything else reads the decision.
    if error:
        decision.decision = "HOLD"
        decision.reasons.append("extractor_failed_fail_closed")
        decision.attestation_required = True
        decision.attestation_status = "PENDING"

    # --- what an attestation would have to be bound to --------------------
    # Derived by code from the diff and from the record on file. The model's
    # description of the destination is deliberately not an input: a binding the
    # model can influence is not a binding.
    context = VerificationContext(
        vendor_id=vendor.vendor_id,
        request_id=request_id_for(case, nt.text),
        destination_digest=destination_digest(diffs, vendor),
        reference_version=reference_version(vendor),
    )
    attestation = AttestationState(context=context)

    if presented_event is not None:
        outcome = (store if store is not None else AttestationStore()).consume(
            presented_event, context, required=decision.attestation_required
        )
        attestation.status = "SATISFIED" if outcome.accepted else "REJECTED"
        attestation.code = outcome.code
        attestation.message = outcome.message
        attestation.event_id = presented_event.event_id
        decision.attestation_status = attestation.status
        decision.attestation_code = outcome.code
        if not outcome.accepted:
            # Recorded, never acted on. A rejected attestation cannot release a
            # hold, and it also cannot be used to argue the gate stricter than
            # the evidence supports - so it is a finding, not a hold trigger.
            decision.findings.append(
                Finding(
                    code=outcome.code,
                    severity="info",
                    message=outcome.message,
                    independent_of_model=True,
                )
            )
            decision.reasons.append("attestation_rejected")
    else:
        attestation.status = "PENDING" if decision.attestation_required else "NOT_REQUIRED"
        decision.attestation_status = attestation.status
        decision.attestation_code = ""

    return PipelineResult(
        case_id=case["id"],
        vendor_id=vendor.vendor_id,
        decision=decision,
        extraction=extraction,
        validation=validation,
        tokens=tokens,
        nt=nt,
        extractor=(extractor_mode or "injected"),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        expected=case.get("expected_decision"),
        notes=notes,
        error=error,
        verification=context,
        attestation=attestation,
    )
