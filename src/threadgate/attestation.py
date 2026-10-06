"""Single-use verification events.

A decision is not the end of the control: once the gate says REVIEW or HOLD, a
human has to verify the change out of band and attest that they did. This
module makes that attestation a *verifiable object* rather than a tick box.

A verification event is bound to four things, and is refused if any one of them
does not match the request it is presented against:

    request_id          - the specific request it was minted for
    destination_digest  - the destination that was verified, not merely "a change"
    reference_version   - the version of the record the human checked against
    verification_event_id - itself, so it can only ever be used once

The fourth binding is what makes it single-use. The third is what stops a
verification made against v1 of a vendor record from being replayed after the
record moves to v2: the record changed, so the old verification no longer
describes it, and inheriting it would let a change slip through on the strength
of a check that was never performed against the new destination.

What this is NOT: there is no signature, no key material and no certificate.
None of this is cryptographic proof that a particular human did a particular
thing - that would need PKI, which is out of scope. What it enforces is that a
verification, once minted for one (request, destination, record version),
cannot be reused anywhere else. That is a binding and a single-use property,
enforced in code, and it is exactly what is claimed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .compare import DESTINATION_FIELDS, normalize_value
from .records import Vendor
from .schema import FieldDiff

# Outcome codes. `ATTESTATION_ACCEPTED` is the only accepting one; every other
# code means the human-verification requirement is still outstanding.
ACCEPTED = "ATTESTATION_ACCEPTED"
REPLAY = "ATTESTATION_REPLAY"
REQUEST_MISMATCH = "ATTESTATION_REQUEST_MISMATCH"
DESTINATION_MISMATCH = "ATTESTATION_DESTINATION_MISMATCH"
REFERENCE_VERSION_MISMATCH = "ATTESTATION_REFERENCE_VERSION_MISMATCH"
VENDOR_MISMATCH = "ATTESTATION_VENDOR_MISMATCH"
NOT_REQUIRED = "ATTESTATION_NOT_REQUIRED"
EMPTY_EVENT_ID = "ATTESTATION_EMPTY_EVENT_ID"

REJECTION_CODES = frozenset(
    {REPLAY, REQUEST_MISMATCH, DESTINATION_MISMATCH,
     REFERENCE_VERSION_MISMATCH, VENDOR_MISMATCH, NOT_REQUIRED, EMPTY_EVENT_ID}
)


def destination_digest(diffs: list[FieldDiff], vendor: Vendor) -> str:
    """A stable digest of the destination this request would pay to.

    Derived entirely from code: the comparator's field-level diff plus the
    record on file. The model's own description of the destination is not an
    input, because a digest the model can influence is not a binding.

    Where a destination field was verified as changing, the requested value is
    used; where nothing changed, the record's own values are used, so that a
    "no change" request still binds to the destination it was checked against.
    """
    pairs: list[list[str]] = []
    for d in sorted(diffs, key=lambda x: x.field):
        if d.field not in DESTINATION_FIELDS:
            continue
        value = d.new_value if d.changed else d.old_value
        pairs.append([d.field, normalize_value(d.field, value)])
    if not pairs:
        for f in sorted(DESTINATION_FIELDS):
            current = vendor.current(f)
            if current:
                pairs.append([f, normalize_value(f, current)])
    canonical = json.dumps(pairs, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def request_id_for(case: dict, normalized_text: str = "") -> str:
    """The identifier a verification event is bound to.

    A frozen case carries an id. A pasted email does not, so its id is derived
    from the text itself - the same email always yields the same request id,
    and a different email never does.
    """
    case_id = str(case.get("id") or "").strip()
    if case_id:
        return case_id
    body = normalized_text if normalized_text else json.dumps(case, sort_keys=True)
    return "req-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class VerificationContext:
    """What the gate is currently deciding. Derived by code, never supplied."""

    vendor_id: str
    request_id: str
    destination_digest: str
    reference_version: str


@dataclass(frozen=True)
class VerificationEvent:
    """The human's attestation, and everything it was minted against.

    `attested_by` and `attested_at` are recorded for the audit trail. They are
    not part of the binding: who attested does not change what they attested to.
    """

    event_id: str
    vendor_id: str
    request_id: str
    destination_digest: str
    reference_version: str
    attested_by: str = ""
    attested_at: str = ""

    @property
    def binding(self) -> tuple[str, str, str, str]:
        return (self.vendor_id, self.request_id,
                self.destination_digest, self.reference_version)


@dataclass(frozen=True)
class AttestationOutcome:
    accepted: bool
    code: str
    message: str
    consumed: bool


class AttestationStore:
    """Single-use store. Each event id may be presented once, ever.

    A rejected presentation still burns the event. That is deliberate: an
    attacker who tries an event against the wrong request has demonstrated
    they do not hold a valid one, and letting them keep it for a second, better
    guess would turn the store into an oracle.

    The store is per-process by design. It is not a distributed ledger and
    makes no claim to survive a restart on its own; `dump` / `restore` exist so
    a deployment that needs durability can persist it.
    """

    def __init__(self, used: dict[str, tuple[str, str, str, str]] | None = None) -> None:
        self._used: dict[str, tuple[str, str, str, str]] = dict(used or {})

    def consume(self, event: VerificationEvent, context: VerificationContext,
                required: bool = True) -> AttestationOutcome:
        """Present an event against a context. Returns, and records, the outcome."""
        if not required:
            # Nothing to attest to, so the event is not examined and not burned.
            return AttestationOutcome(
                False, NOT_REQUIRED,
                "This request needs no attestation: no change was identified, "
                "so there is nothing for a human to verify.",
                consumed=False,
            )
        if not str(event.event_id or "").strip():
            return AttestationOutcome(
                False, EMPTY_EVENT_ID,
                "The verification event has no id and cannot be bound to anything.",
                consumed=False,
            )

        if event.event_id in self._used:
            return AttestationOutcome(
                False, REPLAY,
                f"Verification event {event.event_id} has already been used. A "
                "verification is single-use: it cannot be presented twice, and it "
                "cannot be reused for another request.",
                consumed=True,
            )

        # Burn it now. Every path from here is a rejection, and a failed attempt
        # must not leave the event available for a second try.
        self._used[event.event_id] = event.binding

        if event.vendor_id != context.vendor_id:
            return AttestationOutcome(
                False, VENDOR_MISMATCH,
                f"Verification event {event.event_id} was minted for vendor "
                f"{event.vendor_id}, not {context.vendor_id}.",
                consumed=True,
            )
        if event.request_id != context.request_id:
            return AttestationOutcome(
                False, REQUEST_MISMATCH,
                f"Verification event {event.event_id} was minted for request "
                f"{event.request_id}, not {context.request_id}. A verification "
                "belongs to one request and cannot be carried to another.",
                consumed=True,
            )
        if event.destination_digest != context.destination_digest:
            return AttestationOutcome(
                False, DESTINATION_MISMATCH,
                f"Verification event {event.event_id} was minted against a "
                "different destination. The destination changed, so the "
                "verification does not cover it.",
                consumed=True,
            )
        if event.reference_version != context.reference_version:
            return AttestationOutcome(
                False, REFERENCE_VERSION_MISMATCH,
                f"Verification event {event.event_id} was made against reference "
                f"{event.reference_version}, but the record on file is now "
                f"{context.reference_version}. The record has moved on, so the "
                "verification no longer describes it and a new one is required.",
                consumed=True,
            )

        return AttestationOutcome(
            True, ACCEPTED,
            f"Verification event {event.event_id} accepted once for request "
            f"{context.request_id} against reference {context.reference_version}.",
            consumed=True,
        )

    # -- introspection -----------------------------------------------------
    def used_event_ids(self) -> frozenset[str]:
        return frozenset(self._used)

    def has_used(self, event_id: str) -> bool:
        return event_id in self._used

    def __len__(self) -> int:
        return len(self._used)

    # -- optional durability ------------------------------------------------
    def dump(self) -> list[dict[str, Any]]:
        """Serialisable record of every consumed event, for persistence."""
        return [
            {"event_id": eid, "vendor_id": b[0], "request_id": b[1],
             "destination_digest": b[2], "reference_version": b[3]}
            for eid, b in sorted(self._used.items())
        ]

    @classmethod
    def restore(cls, rows: list[dict[str, Any]] | None) -> "AttestationStore":
        used = {}
        for row in rows or []:
            eid = str(row.get("event_id") or "").strip()
            if not eid:
                continue
            used[eid] = (
                str(row.get("vendor_id", "")),
                str(row.get("request_id", "")),
                str(row.get("destination_digest", "")),
                str(row.get("reference_version", "")),
            )
        return cls(used)


@dataclass
class AttestationState:
    """What the pipeline records about the human-verification step."""

    status: str = "NOT_REQUIRED"      # NOT_REQUIRED | PENDING | SATISFIED | REJECTED
    code: str = ""
    message: str = ""
    context: VerificationContext | None = None
    event_id: str = ""
    notes: list[str] = field(default_factory=list)
