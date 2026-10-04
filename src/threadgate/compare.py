"""Comparator: turn verified claims into a field-level diff against the record.

Nothing here is probabilistic. `normalize_value` strips presentation (spaces,
separators, case, currency symbols) so that "5010 0234 5598 21" and
"50100234559821" compare equal, then compares against what is on file.
"""

from __future__ import annotations

import re

from .records import Vendor
from .schema import FieldDiff
from .validate import ValidatedClaim

FIELD_RISK: dict[str, str] = {
    "account_number": "high",
    "ifsc": "high",
    "iban": "high",
    "swift": "high",
    "beneficiary_name": "high",
    "bank_name": "medium",
    "branch": "medium",
    "currency": "medium",
    "amount": "medium",
    "payment_terms": "low",
    "remittance_email": "low",
    "contact_person": "low",
    "contact_phone": "low",
    "other": "unknown",
}

NUMERIC = {"account_number", "amount", "contact_phone"}
CODE = {"ifsc", "iban", "swift"}


def normalize_value(field: str, value: str | None) -> str:
    if value is None:
        return ""
    v = str(value).strip()
    if field in NUMERIC:
        return re.sub(r"[^\d]", "", v)
    if field in CODE:
        return re.sub(r"[^0-9A-Za-z]", "", v).upper()
    if field == "currency":
        return re.sub(r"[^A-Za-z]", "", v).upper()
    if field in {"remittance_email", "contact_person", "contact_phone"}:
        return re.sub(r"\s+", "", v).lower()
    return re.sub(r"\s+", " ", v).strip().lower()


def _amount_value(value: str | None) -> float | None:
    if not value:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def diff_claims(claims: list[ValidatedClaim], vendor: Vendor) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for vc in claims:
        if not vc.verified:
            continue
        c = vc.claim
        current = vendor.current(c.field)
        new_norm = normalize_value(c.field, c.new_value)
        old_norm = normalize_value(c.field, current)
        if not new_norm:
            continue

        changed = new_norm != old_norm
        risk = FIELD_RISK.get(c.field, "unknown")
        pre_registered = False
        note = ""

        if c.field == "account_number":
            if vendor.is_known_account(new_norm):
                pre_registered = True
                status = vendor.account_status(new_norm) or ""
                note = f"matches record ({status or 'known'})"
                risk = "low" if status.startswith("allowlisted") else "low"
            elif changed:
                note = f"last4 {old_norm[-4:]} -> {new_norm[-4:]}"

        if c.field == "remittance_email" and changed:
            if vendor.is_verified_domain(c.new_value or ""):
                note = "destination domain already verified for this vendor"
                risk = "low"
            else:
                note = "destination domain NOT on the verified list"
                risk = "high"

        amount_value: float | None = None
        if c.field == "amount":
            # An amount is per-invoice, not a standing field on the vendor
            # record, so quoting one is not a change to anything on file. A
            # payment reminder that mentions INR 320,000 is not asking for the
            # record to change. The amount is carried through as a risk
            # modifier instead: above the vendor's typical ceiling it escalates
            # on its own (see policy.P_AMOUNT_ABOVE_CEILING).
            amount_value = _amount_value(c.new_value)
            ceiling = vendor.typical_max_amount()
            changed = False
            risk = "low"
            note = (
                f"{amount_value:,.0f} mentioned (typical ceiling {ceiling:,.0f})"
                if amount_value is not None
                else "amount mentioned"
            )

        if c.field == "currency" and changed:
            note = f"{old_norm} -> {new_norm}"

        diffs.append(
            FieldDiff(
                field=c.field,
                old_value=current,
                new_value=c.new_value,
                changed=changed,
                risk=risk,
                pre_registered=pre_registered,
                note=note,
                amount_value=amount_value,
            )
        )
    return diffs
