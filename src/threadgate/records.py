"""The record: the authoritative vendor master, loaded from JSON.

This is the thing an attacker wants to change. Everything in the pipeline is
oriented around one question: does what the email asks for match what is
already on file?

`is_known_account` is the heart of the AI-independent floor. It takes a
normalised digit string and answers whether it is the current account, an
allowlisted alternate, or a known alias. It never asks the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "account_number": ("bank", "account_number"),
    "ifsc": ("bank", "ifsc"),
    "swift": ("bank", "swift"),
    "bank_name": ("bank", "bank_name"),
    "branch": ("bank", "branch"),
    "beneficiary_name": ("bank", "beneficiary_name"),
    "account_type": ("bank", "account_type"),
    "currency": ("payment_defaults", "currency"),
    "payment_terms": ("payment_defaults", "payment_terms"),
    "remittance_email": ("verified_contacts", "remittance_email"),
    "contact_person": ("verified_contacts", "contact_person"),
    "contact_phone": ("verified_contacts", "contact_phone"),
}


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


@dataclass
class Vendor:
    data: dict
    vendor_id: str = ""
    display_name: str = ""
    _known_accounts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.vendor_id = self.data.get("vendor_id", "")
        self.display_name = self.data.get("display_name", self.data.get("legal_name", ""))
        self._known_accounts = {}
        current = self.current("account_number")
        if current:
            self._known_accounts[_digits(current)] = "current"
        for alt in self.data.get("allowlisted_accounts", []) or []:
            num = _digits(alt.get("account_number", ""))
            if num:
                self._known_accounts[num] = "allowlisted:" + str(alt.get("registered_at", ""))

    # -- lookups ---------------------------------------------------------
    def current(self, field_name: str) -> str | None:
        path = FIELD_PATHS.get(field_name)
        if not path:
            return None
        node: object = self.data
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return None if node is None else str(node)

    def is_known_account(self, value: str) -> bool:
        return _digits(value) in self._known_accounts

    def account_status(self, value: str) -> str | None:
        return self._known_accounts.get(_digits(value))

    def verified_domains(self) -> list[str]:
        return [d.lower() for d in self.data.get("verified_domains", []) or []]

    def is_verified_domain(self, candidate: str) -> bool:
        cand = (candidate or "").strip().lower()
        if "@" in cand:
            cand = cand.rsplit("@", 1)[-1]
        for dom in self.verified_domains():
            if cand == dom or cand.endswith("." + dom):
                return True
        return False

    def typical_max_amount(self) -> float:
        try:
            return float(self.data.get("payment_defaults", {}).get("typical_max_amount", 0))
        except (TypeError, ValueError):
            return 0.0


def load_vendors(path: str | Path) -> dict[str, Vendor]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {vid: Vendor(data={**v, "vendor_id": vid}) for vid, v in raw["vendors"].items()}


def load_cases(path: str | Path) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return raw["cases"]
