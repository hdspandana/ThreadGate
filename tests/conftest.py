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

from threadgate.clock import SystemClock  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

# The date the frozen corpus, the labels and the stored artifact were all
# produced against. Anything that reads the clock during a test must read this
# rather than the wall clock.
PINNED_TEST_CLOCK = "2026-10-06"


@pytest.fixture(autouse=True)
def _pin_the_default_clock(monkeypatch):
    """Stop the suite from measuring the calendar.

    Tests that care about time pass an explicit clock, but about twenty call
    sites take the default `SystemClock()` and are therefore evaluated against
    whatever today is. The fixture record in data/ was last confirmed
    2026-09-15 and the freshness window is 90 days, so those tests were
    scheduled to start failing on **2026-12-14** - a green suite that turns red
    because a date passed, while the code under test is correct.

    That is not hypothetical: pinning the clock to 2027-06-01 produced six
    failures, e.g. `test_offline_double_matches_every_label[frozen_v1.json]`,
    `test_an_amount_alone_never_produces_a_hold` and
    `test_clear_is_the_only_decision_that_needs_no_human`, all of them
    `assert 'REVIEW' == 'CLEAR'` with findings
    `['nothing_to_gate', 'reference_stale_record']`.

    The live clock's own behaviour is not hidden by this: `SystemClock.now` is
    still wall-clock based and `test_the_live_clock_is_really_wall_clock`
    asserts exactly that. This fixture only changes what a test *sees* when it
    does not ask for a particular time.
    """
    from datetime import datetime, timezone

    pinned = datetime.fromisoformat(PINNED_TEST_CLOCK).replace(tzinfo=timezone.utc)
    monkeypatch.setattr(SystemClock, "now", lambda self: pinned)
    return pinned


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
