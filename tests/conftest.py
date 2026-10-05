"""Shared fixtures.

The test suite must run with no network and no API key, so everything here uses
the frozen case set and the vendor record from data/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.records import load_cases, load_vendors  # noqa: E402


@pytest.fixture(scope="session")
def vendors():
    return load_vendors(ROOT / "data" / "records" / "vendor_master.json")


@pytest.fixture(scope="session")
def cases():
    """The primary pre-frozen benchmark."""
    return load_cases(ROOT / "data" / "cases" / "frozen_v1.json")


@pytest.fixture(scope="session")
def case_by_id(cases):
    return {c["id"]: c for c in cases}


@pytest.fixture(scope="session")
def cases_all():
    """v1 plus the adversarial stress tranche - the combined stress set."""
    return load_cases(ROOT / "data" / "cases" / "frozen_v2.json")


@pytest.fixture(scope="session")
def case_by_id_all(cases_all):
    return {c["id"]: c for c in cases_all}


@pytest.fixture(scope="session")
def vendor(vendors):
    return vendors["V-1001"]
