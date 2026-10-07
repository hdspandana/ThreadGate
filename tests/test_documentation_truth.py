"""Documentation is a claim about the code, and claims go stale.

A judge reads the README and the Devpost description before they read anything
else, and both quote specific test names as the evidence for specific security
properties. A renamed test silently turns "enforced by
`test_a_hold_trigger_can_never_produce_a_clear`" into a statement about a test
that no longer exists, and nothing in the suite notices, because the suite does
not read the README.

These tests do. They are cheap, they fail loudly, and they cover the specific
false claims that were actually in these documents and had to be corrected.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

DOCS = ["README.md", "docs/DEVPOST.md", "docs/VIDEO_AND_DEMO.md", "PRIOR_WORK.md"]


def doc(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# every test named in the docs has to exist
# ---------------------------------------------------------------------------
def _collected_test_names() -> set[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-o", "addopts="],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    return set(re.findall(r"<Function (test_[a-z0-9_]+)", out))


@pytest.mark.parametrize("name", DOCS[:2])
def test_every_test_named_in_the_docs_exists(name):
    """A doc that cites a test that no longer exists is citing nothing."""
    body = doc(name)
    names = sorted(set(re.findall(r"`(test_[a-z0-9_]+)`", body)))
    if not names:
        pytest.skip(f"{name} cites no test names")
    have = _collected_test_names()
    missing = [n for n in names if n not in have]
    assert missing == [], f"{name} cites tests that do not exist: {missing}"


def test_the_readme_cites_tests_for_every_invariant():
    """The README's evidence column is the whole point of that table."""
    body = doc("README.md")
    names = sorted(set(re.findall(r"`(test_[a-z0-9_]+)`", body)))
    assert len(names) >= 20, f"only {len(names)} tests cited"


def test_the_fourteen_invariant_table_is_complete():
    """The README writes the count down; make sure it stays true."""
    block = doc("README.md").split(
        "**All fourteen invariants, and the tests that hold them**", 1
    )[1].split("### The burn-on-reject", 1)[0]
    rows = re.findall(r"^\| (\d+) \|", block, re.MULTILINE)
    assert len(rows) == 14, f"the table has {len(rows)} rows but claims fourteen"
    assert rows == [str(i) for i in range(1, 15)]


# ---------------------------------------------------------------------------
# specific false claims that were in these files
# ---------------------------------------------------------------------------
def test_nothing_claims_every_invariant_ignores_the_model():
    """I2, I2b and I2c read the model's output. That was asserted as false."""
    readme = doc("README.md")
    assert "computed without looking at what the model said" not in readme
    assert "without looking at what the model" not in doc("docs/DEVPOST.md")
    # and the correction is present
    assert "Model-independent invariants" in readme
    assert "Verdict-validating invariants" in readme


def test_nothing_claims_the_production_model_sees_the_record():
    devpost = doc("docs/DEVPOST.md")
    for phrase in ("and a summary of the record", "email and a summary",
                   "summary of the vendor record", "VENDOR ON FILE"):
        assert phrase not in devpost, phrase
    assert "the email and nothing else" in devpost


def test_nothing_claims_a_deployment_that_does_not_exist():
    readme = doc("README.md")
    assert not re.search(r"^Deployed:", readme, re.MULTILINE)
    assert "no public deployment" in readme


def test_the_prior_work_statement_names_the_right_hackathon():
    text = doc("PRIOR_WORK.md")
    assert "ForgeHacks Online 2026" in text
    assert "AI + Cybersecurity track" in text
    assert "Agent.ai / Devpost hackathon" not in text


def test_the_prior_work_statement_is_about_the_project_not_the_author():
    """"No prior work existed" must not read as "I have no background"."""
    text = doc("PRIOR_WORK.md")
    assert "No prior ThreadGate repository, prototype, dataset, or write-up existed." in text
    lowered = text.lower()
    assert "prior experience brought" in lowered
    # and it must not open with the bare word that invites the wrong reading
    assert not re.search(r"^Nothing\.", text.split("## What existed")[1], re.MULTILINE)


def test_the_hackathon_window_matches_the_official_deadline():
    text = doc("PRIOR_WORK.md")
    assert "2026-10-03" in text and "2026-10-10" in text


def test_cross_message_is_described_as_quoted_content_not_correlation():
    readme = doc("README.md")
    idx = readme.find("cross_message** (deciding which end of a thread is")
    assert idx > 0
    tail = readme[idx: idx + 900]
    assert "single message" in tail
    # Matched without the markdown emphasis, which sits inside the sentence.
    assert "correlation across separate emails" in tail
    assert re.search(r"\bnot\s+correlation", tail), tail


# ---------------------------------------------------------------------------
# safety claims are scoped, not absolute
# ---------------------------------------------------------------------------
def test_safety_claims_are_scoped_to_the_frozen_corpus():
    """Zero unsafe on 40 cases is a measurement, not a guarantee."""
    readme = doc("README.md")
    idx = readme.find("unsafe hold releases (expected `HOLD`, got softer)")
    assert idx > 0, "the safety table is missing"
    tail = readme[idx: idx + 1400]
    assert "on these 40 cases" in tail
    assert "not a guarantee" in tail


def test_both_release_metrics_are_reported():
    """`unsafe` alone cannot see a REVIEW case coming back CLEAR."""
    readme = doc("README.md")
    assert "non-CLEAR releases" in readme
    assert "unsafe hold releases" in readme


@pytest.mark.parametrize(
    "forbidden",
    [
        "tamper-proof", "unbreakable", "foolproof", "bulletproof",
        "mathematically proven", "guaranteed secure", "cannot be bypassed",
    ],
)
def test_no_absolute_security_language(forbidden):
    for name in DOCS:
        assert forbidden.lower() not in doc(name).lower(), f"{name}: {forbidden}"


def test_the_verification_event_is_not_called_a_signature():
    for name in ("README.md", "docs/DEVPOST.md"):
        body = doc(name).lower()
        assert "no cryptographic signatures" in body
        assert "not a proof of identity" in body


# ---------------------------------------------------------------------------
# the numbers in the README match the numbers the harness produces
# ---------------------------------------------------------------------------
def test_the_readme_does_not_state_a_gemini_accuracy():
    """The Gemini row is blank until a live run happens. Do not fill it in."""
    readme = doc("README.md")
    for line in readme.splitlines():
        if "gemini" in line.lower() and "|" in line:
            assert "*pending" in line or "not yet run" in line or "skipped" in line, line


def test_the_offline_double_is_never_presented_as_a_model_result():
    for name in ("README.md", "docs/DEVPOST.md"):
        body = doc(name)
        assert "deterministic test double" in body or "test double" in body


# ---------------------------------------------------------------------------
# the stated test count is measured, never hand-written
# ---------------------------------------------------------------------------
def _collected_count() -> int:
    """The real number of collected tests, from pytest itself.

    A count typed into a README is a count that is wrong the moment anyone adds
    a test. This reads the number from the collector so the docs can be checked
    against it rather than trusted.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-o", "addopts=", "-q"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, f"could not read a collected count from pytest output:\n{out[-500:]}"
    return int(m.group(1))


# Every place a test count is stated, as (file, regex producing the number).
COUNT_CLAIMS = [
    ("README.md", r"# (\d+) tests, no network needed"),
    ("docs/DEVPOST.md", r"pytest for the (\d+)-test"),
    ("docs/DEVPOST.md", r"final commit \((\d+) tests,"),
]


@pytest.mark.parametrize("name,pattern", COUNT_CLAIMS)
def test_a_stated_test_count_matches_the_collected_count(name, pattern):
    """No documented test count may be guessed.

    These documents previously said 156 while the suite held several hundred.
    The number is now measured against the collector, so it cannot drift again
    without this test failing.
    """
    text = doc(name)
    m = re.search(pattern, text)
    assert m, f"no test count matching {pattern!r} found in {name} - update the pattern"
    stated = int(m.group(1))
    actual = _collected_count()
    assert stated == actual, (
        f"{name} states {stated} tests but pytest collects {actual}. "
        f"Use the collected count."
    )


def test_every_stated_test_count_is_covered_by_a_checked_form():
    """A count in a form nothing checks is an unchecked count.

    The first version of this test simply failed on any "N tests", which meant
    it also failed on the three claims above - correct, but for no reason. It
    now subtracts the spans the specific patterns matched, so it reports only
    genuinely uncovered statements.
    """
    uncovered = []
    for name in DOCS:
        text = doc(name)
        covered = set()
        for _, pattern in [(n, p) for n, p in COUNT_CLAIMS if n == name]:
            covered.update((m.start(), m.end()) for m in re.finditer(pattern, text))
        for m in re.finditer(r"\d{3}\s*\+?\s*tests", text):
            if not any(s <= m.start() and m.end() <= e for s, e in covered):
                uncovered.append(f"{name}: {m.group(0)!r}")
    assert not uncovered, (
        "these test counts are in a form no test checks - add them to "
        f"COUNT_CLAIMS: {uncovered}"
    )


# ---------------------------------------------------------------------------
# the architecture diagram still describes this code
# ---------------------------------------------------------------------------
def test_the_architecture_diagram_does_not_disown_implemented_features():
    """It listed replay protection and version lineage as not implemented.

    Both were implemented. A diagram that says a shipped control does not
    exist is worse than a diagram that omits it: it understates the system to
    anyone who reads it, which is the only audience a diagram has.
    """
    svg = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    not_claimed = " ".join(
        line.strip() for line in svg.splitlines()
        if "Not implemented" in line or "not claimed" in line
    )
    for phrase in ("replay protection", "reference version lineage", "version lineage"):
        assert phrase not in not_claimed, (
            f"the diagram still lists {phrase!r} as not implemented"
        )


def test_the_architecture_diagram_states_the_attestation_caveat():
    """If it claims single-use attestation, it must carry the caveat with it."""
    svg = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    if "single-use" in svg:
        assert "not a cryptographic signature" in svg


def test_the_diagram_matches_the_code_on_what_is_not_implemented():
    """OCR is genuinely absent; assert that, so the claim stays true.

    Checks for an implementation rather than the word. The first version failed
    on the string "ocr" appearing anywhere, including in the comment in
    `invariants.py` that says OCR is *not* performed - the doc was right and the
    test was wrong.
    """
    src = "\n".join(
        (ROOT / "src" / "threadgate" / f).read_text(encoding="utf-8")
        for f in ("invariants.py", "normalize.py", "tokens.py")
    )
    for marker in ("pytesseract", "tesseract", "easyocr", "from PIL import"):
        assert marker not in src.lower(), (
            f"{marker} appeared in src, so OCR is now implemented and the "
            "diagram's claim that it is not is stale"
        )


def test_no_document_cites_a_commit_hash_in_prose():
    """A hash written into prose goes stale on the next commit.

    `docs/VIDEO_AND_DEMO.md` said "what the app actually renders at commit
    6f9125f", which was true when it was written and silently false afterwards.
    Rather than pin a hash that the next commit invalidates, the docs describe
    the frozen build. This test keeps a hash from creeping back in.
    """
    for name in DOCS:
        for m in re.finditer(r"commit `?([0-9a-f]{7,})`?", doc(name)):
            raise AssertionError(
                f"{name} cites commit {m.group(1)} in prose. Describe the build "
                "instead - a hash in a sentence goes stale on the next commit."
            )


def _kill_gate_check_count() -> int:
    """The real number of kill-gate checks, from the gate itself."""
    import subprocess as sp

    out = sp.run(
        [sys.executable, str(ROOT / "scripts" / "kill_gate.py")],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    return len(re.findall(r"^\[(?:PASS|FAIL)\]", out, re.MULTILINE))


def test_the_stated_kill_gate_check_count_matches_the_gate():
    """The gate grew from 17 to 18 checks; the doc said 17.

    Same rule as the test count: measured, not hand-written.
    """
    m = re.search(r"final commit \(\d+ tests, (\d+) kill-gate checks\)",
                  doc("docs/DEVPOST.md"))
    assert m, "the kill-gate claim is missing from DEVPOST"
    assert int(m.group(1)) == _kill_gate_check_count(), (
        f"DEVPOST states {m.group(1)} kill-gate checks but the gate runs "
        f"{_kill_gate_check_count()}"
    )
