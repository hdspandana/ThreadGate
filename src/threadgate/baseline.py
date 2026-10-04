"""Rules-only baseline, for the measured comparison.

This is the control every claim in the README is measured against. It is written
to be a fair stand-in for a first-pass control, not a strawman:

  R1  an 11-18 digit run anywhere in the raw subject+body whose last four digits
      are not the account on file and not a pre-registered alternate -> HOLD
  R2  a change-ish verb anywhere in the text AND a payment noun anywhere in the
      text -> HOLD
  else NO_CHANGE

Two properties are worth stating out loud because they are the point of the
comparison:

  * It can never return ALLOW. A rules engine of this shape has no way to say
    "this change is one we already approved", so every true change costs a
    manual review even when it is legitimate.
  * R2 is a bag of words. It cannot read negation, so "we are not changing our
    bank details" and "please change our bank details" are the same string to it.

`rules_only_normalized` is the same rule set run over normalised text. It exists
to separate two effects honestly: how much of the gap is just character
normalisation (which any team can add for free), and how much needs the model.
"""

from __future__ import annotations

import re

from .normalize import normalize_text
from .records import Vendor
from .schema import Decision

# Separator-tolerant so that "5010 0234 5598 21" is one number to R1, while a
# zero-width space or a U+2011 hyphen still breaks it in the raw text. That
# asymmetry is exactly what the TG-016 / TG-017 pair measures.
RAW_ACCOUNT = re.compile(r"(?<!\d)\d[\d\s.\-]{6,}\d(?!\d)")
_ACCOUNT_DIGITS = re.compile(r"[\s.\-]")

CHANGE_WORD = re.compile(r"\b(chang|updat|amend|revis|replac|switch|modif|correct|new )\w*\b", re.IGNORECASE)
ENTITY_WORD = re.compile(
    r"\b(account|a\s*/\s*c|acct|bank|beneficiary|ifsc|iban|payment|remit|details)\w*\b", re.IGNORECASE
)


def rules_only(case: dict, vendor: Vendor, normalized: bool = False) -> Decision:
    email = case["email"]
    body = f"{email.get('subject','')}\n{email.get('body','')}"
    text = normalize_text(body).text if normalized else body

    # R1 - unknown account number
    for m in RAW_ACCOUNT.finditer(text):
        digits = _ACCOUNT_DIGITS.sub("", m.group(0))
        if 11 <= len(digits) <= 18 and not vendor.is_known_account(digits):
            return Decision(
                decision="HOLD",
                reasons=["rule:unknown_account_number"],
                attestation_required=True,
            )

    # R2 - change language near a payment field
    if CHANGE_WORD.search(text) and ENTITY_WORD.search(text):
        return Decision(
            decision="HOLD",
            reasons=["rule:change_language_near_payment_field"],
            attestation_required=True,
        )

    return Decision(decision="NO_CHANGE", reasons=["rule:no_trigger"])


def rules_only_normalized(case: dict, vendor: Vendor) -> Decision:
    return rules_only(case, vendor, normalized=True)
