"""Orchestration: one email in, one Decision out.

    normalise -> tokenise (code) -> extract (model) -> validate (code)
              -> compare (code) -> invariants (code) -> policy (code)

The model is one box in the middle. Everything before it prepares untrusted
text; everything after it refuses to trust the model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .compare import diff_claims
from .extract import get_extractor
from .normalize import NormalizedText, normalize_text
from .policy import decide
from .records import Vendor
from .schema import Decision, Extraction
from .tokens import Token, find_tokens
from .validate import ValidationResult, check_old_values, validate_extraction


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
) -> PipelineResult:
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

    validation = validate_extraction(extraction, nt)
    record_values = {f: vendor.current(f) for f in {c.claim.field for c in validation.claims}}
    notes.extend(check_old_values(validation.claims, record_values))
    notes.extend(f"validator:{v}" for v in validation.violations)

    diffs = diff_claims(validation.claims, vendor)
    decision = decide(vendor, extraction.intent, validation, diffs, tokens, nt, case["email"])

    if error:
        decision.decision = "HOLD"
        decision.reasons.append("extractor_failed_fail_closed")
        decision.attestation_required = True

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
    )
