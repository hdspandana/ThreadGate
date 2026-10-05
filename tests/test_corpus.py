"""Guards on the frozen corpus itself.

Labels are load-bearing: the evaluation is meaningless if a case is malformed or
if the set silently changes after numbers have been quoted from it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from threadgate.extract import offline_extract
from threadgate.pipeline import run_case

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "group", "title", "vendor_id", "expected_decision", "tests", "email"}


def _load(name: str):
    return json.loads((ROOT / "data" / "cases" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["frozen_v1.json", "frozen_v2.json"])
def test_every_case_is_well_formed(name):
    data = _load(name)
    ids = [c["id"] for c in data["cases"]]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in data["cases"]:
        missing = REQUIRED - set(c)
        assert not missing, f"{c.get('id')}: missing {missing}"
        assert c["expected_decision"] in {"HOLD", "REVIEW", "CLEAR"}
        assert set(c["email"]) >= {"from", "reply_to", "subject", "body"}
        assert c["email"]["body"].strip()


def test_v2_is_v1_plus_a_second_tranche():
    v1 = {c["id"] for c in _load("frozen_v1.json")["cases"]}
    v2 = {c["id"] for c in _load("frozen_v2.json")["cases"]}
    assert v1 < v2
    assert len(v2) == 40


def test_v2_has_all_three_decisions_represented():
    from collections import Counter

    counts = Counter(c["expected_decision"] for c in _load("frozen_v2.json")["cases"])
    assert counts["HOLD"] >= 20 and counts["CLEAR"] >= 5 and counts["REVIEW"] >= 3


@pytest.mark.parametrize("name", ["frozen_v1.json", "frozen_v2.json"])
def test_offline_double_matches_every_label(name, vendors):
    """Regression guard on both sets. The test double, not the claimed result."""
    wrong = []
    for c in _load(name)["cases"]:
        r = run_case(c, vendors, extractor_fn=offline_extract)
        if r.decision.decision != c["expected_decision"]:
            wrong.append(f"{c['id']} exp={c['expected_decision']} got={r.decision.decision}")
    assert wrong == [], "\n".join(wrong)


def test_every_vendor_referenced_by_a_case_exists(vendors):
    for name in ("frozen_v1.json", "frozen_v2.json"):
        for c in _load(name)["cases"]:
            assert c["vendor_id"] in vendors, c["id"]
