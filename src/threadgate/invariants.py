"""AI-independent invariants.

These checks never see the model's output. They exist so that a model which has
been steered, poisoned or simply hallucinated cannot buy an unsafe outcome.

I1 - Unknown account floor. If a number in the email looks like a bank account
     and it is not the account we hold for this vendor, and not one of the
     pre-registered alternates, a human has to look at it. Full stop. The model
     is not asked, and its answer cannot override this.

I2 - No-change must be evidenced. An intent of "no_change" is only accepted if
     the model quotes the sentence that says so. An unevidenced no_change is
     downgraded to `unverifiable` and falls through to the deterministic
     change-act detector.

I3 - Change act with nothing verifiable. If the email asserts a change in
     payment language but the validator admitted no values, hold it. This is the
     token-less request: "new details are in the attached PDF".

What these three do NOT cover is stated plainly in the README: a token-less
request whose change language the model also fails to report has no
AI-independent evidence at all, and only the human attestation step closes it.
"""

from __future__ import annotations

import re

from .records import Vendor
from .schema import Finding
from .tokens import Token, unique_accounts

CHANGE_WORD = re.compile(
    r"\b(chang|updat|amend|revis|replac|switch|modif|correct|transfer|"
    r"use the following|with effect|w\.e\.f|effective)\w*\b",
    re.IGNORECASE,
)

ENTITY_WORD = re.compile(
    r"\b(account|a\s*/\s*c|acct|bank|beneficiary|ifsc|iban|payment|remit|details)\w*\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def account_floor(tokens: list[Token], vendor: Vendor) -> list[Finding]:
    """I1. Unknown account-like numbers present in the email."""
    findings: list[Finding] = []
    for tok in unique_accounts(tokens):
        if vendor.is_known_account(tok.normalized):
            continue
        findings.append(
            Finding(
                code="I1_UNKNOWN_ACCOUNT_TOKEN",
                severity="hold",
                message=(
                    f"Account-like number {tok.masked} appears in this email and is not "
                    f"the account on file for {vendor.display_name} "
                    f"(****{vendor.current('account_number')[-4:]}), and is not a "
                    "pre-registered alternate."
                ),
                snippet=tok.raw.strip(),
                span_norm=(tok.start, tok.end),
                independent_of_model=True,
            )
        )
    return findings


NO_CHANGE_MARKER = re.compile(
    r"(\bnot\b|\bn't\b|\bno\s+changes?\b|\bno\s+new\b|\bnever\b|unchanged|\bremains?\b|"
    r"\bdisregard\b|\bignore\b|\bno\s+action\b|\bas\s+usual\b|\bstands?\b|\bthe\s+same\b|"
    r"\bdid\s+not\b|\bdo\s+not\b|\bdoes\s+not\b|\bhave\s+not\s+changed\b|"
    r"\bnothing\s+(?:is\s+|has\s+|will\s+)?chang|\bthere\s+are\s+no\b|\bwas\s+a\s+phish)",
    re.IGNORECASE,
)


def no_change_justified(quote: str) -> bool:
    """I2b. The quote offered for a `no_change` verdict must actually say so.

    This exists because of an ablation, not a thought experiment. A steered
    model that returns no_change with *no* quote is caught by I2. A steered
    model that returns no_change with a quote copied verbatim from the email
    passes I2 - the words really are in the email - and that variant lost 3 of
    the 12 high-risk cases in the frozen set.

    So the verdict and its justification have to agree. A quote that asserts a
    change, or merely talks about banking, does not support a claim that nothing
    is changing, however verbatim it is.
    """
    return bool(NO_CHANGE_MARKER.search(quote or ""))


def change_act_detected(norm_text: str) -> bool:
    """I3 support. Is there deterministic change language about a payment field?

    Deliberately crude: a change verb and a payment noun inside one sentence.
    It is only ever used to *escalate*, never to clear, so a crude detector
    costs review time but never costs safety.
    """
    for sentence in SENTENCE_SPLIT.split(norm_text or ""):
        if not sentence.strip():
            continue
        if CHANGE_WORD.search(sentence) and ENTITY_WORD.search(sentence):
            return True
    return False


def unverifiable_finding(reason: str) -> Finding:
    return Finding(
        code="I3_UNVERIFIABLE_REQUEST",
        severity="hold",
        message=reason,
        independent_of_model=True,
    )


def authentication_findings(email: dict) -> list[Finding]:
    """Informational only. Passing mail auth is not evidence of a safe change."""
    out: list[Finding] = []
    auth = email.get("auth", {}) or {}
    failed = [k.upper() for k, v in auth.items() if str(v).lower() not in ("pass", "none")]
    if failed:
        out.append(
            Finding(
                code="AUTH_FAILED",
                severity="info",
                message="Mail authentication failed: " + ", ".join(failed),
                independent_of_model=True,
            )
        )
    reply_to = (email.get("reply_to") or "").lower()
    sender = (email.get("from") or "").lower()
    m_from = re.search(r"@([\w.\-]+)", sender)
    m_reply = re.search(r"@([\w.\-]+)", reply_to)
    if m_from and m_reply and m_from.group(1) != m_reply.group(1):
        out.append(
            Finding(
                code="REPLY_TO_DOMAIN_MISMATCH",
                severity="info",
                message=f"Reply-To domain {m_reply.group(1)} differs from sender domain {m_from.group(1)}.",
                independent_of_model=True,
            )
        )
    return out
