"""Deterministic token finder.

Finds account-like numbers, IFSC/IBAN/SWIFT codes, amounts, emails and phone
numbers in the *normalised* email text, with spans.

Two design points matter:

1. It runs on normalised text, so zero-width spaces and non-ASCII hyphens do
   not hide a number from it. This is a code step, not a model step, and it is
   the reason the injection cases that carry a real number still get caught.

2. It refuses to classify a digit run as an account number unless payment
   context is nearby, and it refuses outright when nearby context says the
   number is an invoice, a phone or a password. Precision here is what buys us
   the right to treat "an account number we do not recognise" as a hard floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import NormalizedText

# A digit run that may contain separators. Must start and end with a digit.
DIGIT_RUN = re.compile(r"(?<![A-Za-z0-9])\+?\d[\d\s.\-]{6,}\d(?![A-Za-z0-9])")

IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")
SWIFT_RE = re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
AMOUNT_RE = re.compile(
    r"(?:(?:INR|USD|EUR|GBP|AED|SGD|Rs\.?|\u20b9|\$|\u20ac|\u00a3)\s?\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

ACCOUNT_CONTEXT = re.compile(
    r"(a\s*/\s*c|a\.c\.|acct|account|account\s*no|iban|sort\s*code|routing|beneficiary)",
    re.IGNORECASE,
)

# Nearby words that mean "this number is not a payment destination".
DENY_CONTEXT = re.compile(
    r"(invoice|inv|purchase\s*order|\bp\.?o\.?\b|order\s*no|gstin|\bgst\b|\bpan\b|"
    r"phone|telephone|mobile|\bcontact\b|pincode|pin\s*code|zip|password|"
    r"\bdate\b|\bref\b|reference|portal|ticket|\bid\b\s*:)",
    re.IGNORECASE,
)

SEPARATORS = re.compile(r"[\s.\-]")


@dataclass
class Token:
    kind: str  # account | ifsc | iban | swift | phone | amount | email | number
    raw: str
    normalized: str
    start: int
    end: int
    last4: str | None = None
    context: str = ""

    @property
    def masked(self) -> str:
        if len(self.normalized) <= 4:
            return self.normalized
        return "*" * (len(self.normalized) - 4) + self.normalized[-4:]


def _digits(value: str) -> str:
    return SEPARATORS.sub("", value)


def find_tokens(nt: NormalizedText) -> list[Token]:
    """Return every payment-relevant token, in normalised coordinates."""
    text = nt.text
    tokens: list[Token] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in consumed)

    # --- account-like numbers -------------------------------------------
    for m in DIGIT_RUN.finditer(text):
        raw = m.group(0)
        if raw.strip().startswith("+"):
            tokens.append(
                Token("phone", raw, _digits(raw), m.start(), m.end(), context="leading plus")
            )
            consumed.append((m.start(), m.end()))
            continue

        digits = _digits(raw)
        if not (8 <= len(digits) <= 19):
            continue

        before = text[max(0, m.start() - 60): m.start()]
        after = text[m.end(): min(len(text), m.end() + 60)]

        if DENY_CONTEXT.search(before[-45:]) or DENY_CONTEXT.search(after[:45]):
            tokens.append(Token("number", raw, digits, m.start(), m.end(), context="denied"))
            consumed.append((m.start(), m.end()))
            continue

        has_context = bool(ACCOUNT_CONTEXT.search(before[-60:]) or ACCOUNT_CONTEXT.search(after[:60]))
        if has_context and 9 <= len(digits) <= 18:
            tokens.append(
                Token("account", raw, digits, m.start(), m.end(), last4=digits[-4:],
                      context=(before[-40:] + "|" + after[:40]).strip())
            )
            consumed.append((m.start(), m.end()))
        else:
            tokens.append(Token("number", raw, digits, m.start(), m.end(), context="no payment context"))

    # --- structured codes ------------------------------------------------
    for kind, rx in (("ifsc", IFSC_RE), ("iban", IBAN_RE), ("swift", SWIFT_RE)):
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            tokens.append(Token(kind, m.group(0), _digits(m.group(0)) or m.group(0), m.start(), m.end()))
            consumed.append((m.start(), m.end()))

    for m in AMOUNT_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        tokens.append(Token("amount", m.group(0), _digits(m.group(0).split()[-1]), m.start(), m.end()))
        consumed.append((m.start(), m.end()))

    for m in EMAIL_RE.finditer(text):
        tokens.append(Token("email", m.group(0), m.group(0).lower(), m.start(), m.end()))
        consumed.append((m.start(), m.end()))

    tokens.sort(key=lambda t: t.start)
    return tokens


def account_tokens(tokens: list[Token]) -> list[Token]:
    return [t for t in tokens if t.kind == "account"]


def unique_accounts(tokens: list[Token]) -> list[Token]:
    seen: set[str] = set()
    out: list[Token] = []
    for t in account_tokens(tokens):
        if t.normalized in seen:
            continue
        seen.add(t.normalized)
        out.append(t)
    return out
