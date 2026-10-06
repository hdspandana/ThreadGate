"""The reference: which version of the vendor record is on file, and is it usable.

The gate is only as good as the record it checks against. Two things can be
wrong with that record before a single word of the email is read:

  * it can be **stale** - on file, but last confirmed long enough ago that it
    should not be trusted to still describe the vendor's destination;
  * it can be **missing** - there is no payment destination on file at all, so
    there is nothing to verify a requested destination against.

And one thing identifies it: a **version**. A verification performed against
v1 of a record says nothing about v2, so an attestation carries the version it
was made against and is refused if the record has moved on.

This module never writes to the record. Reference updates are a human
operation performed out of band after the callback; ThreadGate reads the
version and refuses to inherit verification across it. Automatic reference
updates are deliberately not built.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from .clock import SystemClock, as_of
from .records import Vendor
from .schema import Finding

ReferenceState = Literal["CURRENT", "STALE", "MISSING"]

# How long a record may go unconfirmed before it stops being current. A vendor
# record that has not been re-confirmed in this long is not evidence of where
# the money should go today.
DEFAULT_FRESHNESS_DAYS = 90

# The fields that make a record usable as a payment destination. If none of
# these is on file there is nothing to verify a requested destination against,
# which is what MISSING means. Note that blanking one of them is NOT MISSING:
# a record with no account number but a known IFSC and beneficiary is degraded
# and is handled by the existing closed-world escalation, not by this module.
DESTINATION_REFERENCE_FIELDS = (
    "account_number",
    "iban",
    "swift",
    "ifsc",
    "beneficiary_name",
)


def reference_version(vendor: Vendor) -> str:
    """The version of the record on file.

    An unversioned record is a real state - it means the version is unknown and
    no attestation can be bound to it - so this returns a stable marker rather
    than inventing a version number.
    """
    raw = vendor.data.get("reference_version")
    value = str(raw).strip() if raw is not None else ""
    return value or "unversioned"


def reference_updated_at(vendor: Vendor) -> date | None:
    """When the record was last confirmed, or None if that is not recorded."""
    raw = vendor.data.get("reference_updated_at")
    if raw in (None, ""):
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        # An unparseable date cannot be trusted as proof of freshness.
        return None


def reference_freshness_days(vendor: Vendor) -> int:
    raw = vendor.data.get("reference_freshness_days")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_FRESHNESS_DAYS
    return value if value >= 0 else DEFAULT_FRESHNESS_DAYS


def has_destination_on_file(vendor: Vendor) -> bool:
    return any((vendor.current(f) or "").strip() for f in DESTINATION_REFERENCE_FIELDS)


def reference_age_days(vendor: Vendor, clock=None) -> int | None:
    """Days since the record was last confirmed. None means unrecorded."""
    updated = reference_updated_at(vendor)
    if updated is None:
        return None
    return (as_of(clock or SystemClock()) - updated).days


def reference_state(vendor: Vendor, clock=None) -> ReferenceState:
    """CURRENT, STALE or MISSING, with the clock injected.

    The ordering matters. MISSING is checked first: a record with no
    destination on file cannot be "stale but usable", because there is nothing
    usable on it. Freshness is then evaluated, and an *absent* confirmation
    date is treated as stale - an unrecorded date is not proof of recency, and
    assuming otherwise would let a record be current by omission.
    """
    if not has_destination_on_file(vendor):
        return "MISSING"
    age = reference_age_days(vendor, clock)
    if age is None or age > reference_freshness_days(vendor):
        return "STALE"
    return "CURRENT"


def reference_finding(state: ReferenceState, vendor: Vendor, age: int | None,
                      forces_hold: bool) -> Finding | None:
    """The finding describing a non-current reference. None when CURRENT."""
    if state == "CURRENT":
        return None
    if state == "MISSING":
        message = (
            f"No payment destination is on file for {vendor.display_name}. There is "
            "nothing to verify the requested destination against, so it cannot be "
            "released on the strength of this record."
        )
    else:
        when = f"last confirmed {age} days ago" if age is not None else "never confirmed"
        message = (
            f"The record on file for {vendor.display_name} was {when}, past the "
            f"{reference_freshness_days(vendor)}-day confirmation window. It is not "
            "treated as current evidence of the destination."
        )
    return Finding(
        code=f"R_{state}_REFERENCE",
        severity="hold" if forces_hold else "info",
        message=message,
        independent_of_model=True,
    )
