"""Reproducible clocks, deterministic failure paths, and honest timeout labels.

Three separate ways this project could publish a number or a message it did not
earn:

  - a benchmark that reads the wall clock, so the app and the CLI disagree and
    neither reproduces the other;
  - a missing API key that reports as a missing dependency, depending on what
    happens to be installed on the machine;
  - a soft UI threshold presented as a network timeout, so the reader believes a
    limit is enforced where none is.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "eval"))

from datetime import date  # noqa: E402

import run_eval  # noqa: E402
from threadgate.clock import SystemClock, as_of, fixed  # noqa: E402
from threadgate.extract import ExtractorError, gemini_extract  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CASES = load_cases(ROOT / "data" / "cases" / "frozen_v1.json")
NT = normalize_text("Please update our bank details. Account 50100234557799.")


# ---------------------------------------------------------------------------
# Item 7 - the benchmark clock is pinned and cannot silently drift
# ---------------------------------------------------------------------------


class TestTheBenchmarkUsesAFixedClock:
    def test_the_cli_pins_a_date(self):
        assert run_eval.EVAL_AS_OF == "2026-10-06"
        clock = fixed(run_eval.EVAL_AS_OF)
        assert clock.now() == clock.now(), "a fixed clock must be idempotent"
        assert as_of(clock).isoformat() == run_eval.EVAL_AS_OF

    def test_the_cli_passes_that_clock_into_every_system(self):
        src = (ROOT / "eval" / "run_eval.py").read_text(encoding="utf-8")
        assert "clock = fixed(args.as_of)" in src
        assert "run_system(system, cases, vendors, clock)" in src

    def test_the_streamlit_benchmark_passes_the_same_pinned_clock(self):
        """The wiring assertion: without this the two surfaces drift apart.

        The benchmark button used to call `run_system` with no clock at all,
        which fell through to the wall clock. Its numbers then moved as real
        time passed, and neither the app nor the CLI could reproduce the other.
        """
        src = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
        assert "run_system(sysname, CASES, VENDORS, clock=EVAL_CLOCK)" in src
        assert "EVAL_CLOCK = fixed(EVAL_AS_OF)" in src

    def test_the_streamlit_single_case_path_still_uses_the_real_clock(self):
        """A deployed demo should judge the record against actual time."""
        src = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
        assert "clock=SystemClock()" in src
        # and the pinned clock is not used there
        assert "run_case(\n        case, VENDORS, extractor_mode=mode, clock=SystemClock()" in src

    def test_a_pinned_clock_reproduces_the_cli_result_exactly(self):
        """The point of pinning: same date in, same decision out, always."""
        from threadgate.pipeline import run_case
        from threadgate.extract import compromised_extract

        clock = fixed("2026-10-06")
        first = [
            run_case(c, VENDORS, extractor_fn=compromised_extract, clock=clock)
            for c in CASES
        ]
        second = [
            run_case(c, VENDORS, extractor_fn=compromised_extract, clock=fixed("2026-10-06"))
            for c in CASES
        ]
        assert [r.decision.decision for r in first] == [r.decision.decision for r in second]

    def test_the_two_clocks_are_different_objects_with_different_jobs(self):
        """One pins, one tracks; both answer `.now()` through the same shape."""
        assert fixed("2026-10-06").now().tzinfo is not None
        assert SystemClock().now().tzinfo is not None
        assert isinstance(as_of(fixed("2026-10-06")), date)
        # A fixed clock does not move; the system clock does.
        assert fixed("2026-10-06").now() == fixed("2026-10-06").now()


# ---------------------------------------------------------------------------
# Item 8 - a missing key reports as a missing key
# ---------------------------------------------------------------------------


class TestAMissingKeyIsDiagnosedBeforeAnythingIsImported:
    """The error must not depend on what happens to be installed.

    Importing the SDK first meant that on a machine without `google-genai`,
    asking for a model result with no key produced "google-genai is not
    installed". Same situation, different message, and the message sent the
    reader after a dependency that was not the problem.
    """

    def test_the_key_is_read_before_the_sdk_is_imported(self):
        src = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
        key_at = src.index('api_key = os.environ.get("GEMINI_API_KEY")')
        import_at = src.index("from google import genai")
        assert key_at < import_at, "the key check must precede the SDK import"

    def test_with_no_key_the_error_names_the_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with pytest.raises(ExtractorError) as exc:
            gemini_extract(NT)
        assert "GEMINI_API_KEY" in str(exc.value)
        assert "not installed" not in str(exc.value)

    def test_the_missing_key_message_is_the_same_every_time(self, monkeypatch):
        """Deterministic: no dependence on SDK availability or prior imports."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        messages = set()
        for _ in range(3):
            with pytest.raises(ExtractorError) as exc:
                gemini_extract(NT)
            messages.add(str(exc.value))
        assert len(messages) == 1

    def test_a_missing_key_does_not_leak_into_a_decision_as_a_model_result(
        self, monkeypatch
    ):
        """The error is an error; the pipeline must not read it as a verdict."""
        from threadgate.pipeline import run_case

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        r = run_case(CASES[0], VENDORS, extractor_fn=gemini_extract, clock=fixed("2026-10-06"))
        assert r.error, "an unconfigured model must be recorded as an error"
        assert r.decision.decision == "HOLD", "and must fail closed"

    def test_availability_is_decided_from_the_environment_not_the_sdk(self):
        """`gemini_available()` must not import anything to answer."""
        src = (ROOT / "eval" / "run_eval.py").read_text(encoding="utf-8")
        fn = src[src.index("def gemini_available"):]
        fn = fn[: fn.index("\n\n")]
        assert "import" not in fn


# ---------------------------------------------------------------------------
# Item 9 - a timeout label has to describe a limit that is actually enforced
# ---------------------------------------------------------------------------


class TestTimeoutWordingDescribesARealLimit:
    def test_the_ui_threshold_is_not_called_a_timeout(self):
        """It is an elapsed-time notice. Nothing is cut short by it."""
        src = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
        assert "REQUEST_TIMEOUT_SECONDS" not in src, "the old misleading name is gone"
        assert "SLOW_REQUEST_SECONDS" in src
        block = src[src.index("SLOW_REQUEST_SECONDS * 1000"):]
        block = block[: block.index("st.stop") if "st.stop" in block else 900]
        assert "Nothing timed out" in block
        assert "elapsed" in block.lower()

    def test_there_is_a_real_end_to_end_budget_in_the_extractor(self):
        """The per-request timeout bounds one attempt, not the retry loop."""
        src = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
        assert "THREADGATE_TOTAL_BUDGET_MS" in src
        assert "THREADGATE_HTTP_TIMEOUT_MS" in src

    def test_the_budget_is_checked_before_each_attempt(self):
        src = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
        budget_at = src.index("deadline = time.monotonic()")
        loop_at = src.index("for attempt in range(3):", budget_at)
        check_at = src.index("remaining = deadline - time.monotonic()", loop_at)
        assert budget_at < loop_at < check_at

    def test_the_backoff_never_sleeps_past_the_budget(self):
        src = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
        assert "min(0.6 * (attempt + 1), max(0.0, deadline - time.monotonic()))" in src

    def test_an_exhausted_budget_raises_a_timeout_not_a_generic_failure(self):
        from threadgate.extract import ModelTimeoutError

        src = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
        assert "ModelTimeoutError" in src
        assert "end-to-end budget" in src
        assert issubclass(ModelTimeoutError, TimeoutError)


def test_a_missing_key_still_names_the_key_when_the_sdk_is_absent(monkeypatch):
    """The behavioural half of item 8, with the dependency genuinely missing.

    The source-ordering test proves the check comes first; this proves the
    consequence. `google.genai` is made unimportable, so the old ordering
    would have raised "google-genai is not installed" instead.
    """
    import builtins

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("google"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ExtractorError) as exc:
        gemini_extract(NT)
    assert "GEMINI_API_KEY" in str(exc.value)
    assert "not installed" not in str(exc.value)


# ---------------------------------------------------------------------------
# the suite's default clock is pinned; the live clock is still the live clock
# ---------------------------------------------------------------------------
def test_the_suite_runs_on_the_pinned_clock_not_the_calendar():
    """The autouse fixture must actually be in effect.

    Without it, every test that takes the default `SystemClock()` is measured
    against today, and the frozen record goes stale on a date rather than
    because anything changed. If someone deletes the fixture, this fails.
    """
    from threadgate.clock import as_of

    assert as_of(SystemClock()).isoformat() == "2026-10-06"


def test_the_live_clock_is_really_wall_clock(monkeypatch):
    """The pin must not be achieved by breaking `SystemClock`.

    A fixture that pinned the clock by rewriting the production class would
    hide a real regression in the live path - the app would then decide against
    a frozen date forever. This drops the pin for the duration of one test and
    checks that `SystemClock.now()` still tracks the wall clock, in UTC.
    """
    from datetime import datetime, timedelta, timezone

    monkeypatch.undo()  # remove `_pin_the_default_clock` for this test only

    before = datetime.now(timezone.utc)
    got = SystemClock().now()
    after = datetime.now(timezone.utc)

    assert got.tzinfo is not None, "the live clock returned a naive datetime"
    assert got.utcoffset() == timedelta(0), got.utcoffset()
    assert before - timedelta(seconds=5) <= got <= after + timedelta(seconds=5), got


def test_a_stale_record_is_still_stale_when_a_clock_says_so():
    """Pinning the default must not remove the ability to test staleness.

    The fix for the calendar dependency is a default, not a removal: an
    explicit clock still drives the state, so the stale and missing behaviours
    remain reachable and are still covered - at 2027-06-01 the same record is
    STALE, which is what `test_verification_and_lineage.py` asserts.
    """
    from threadgate import reference as ref
    from threadgate.records import load_vendors

    vendors = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
    vendor = vendors["V-1001"]
    assert ref.reference_state(vendor, fixed("2026-10-06")) == "CURRENT"
    assert ref.reference_state(vendor, fixed("2027-06-01")) == "STALE"
    assert ref.reference_state(vendor, SystemClock()) == "CURRENT", (
        "the pinned default reads 2026-10-06, three weeks after the record was "
        "confirmed - if this says STALE the fixture is not being applied"
    )


# ---------------------------------------------------------------------------
# the secret audit: "could not check" is not "checked and clean"
# ---------------------------------------------------------------------------
def _secret_scan_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_secret_scan_for_test", ROOT / "scripts" / "secret_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_tree(tmp_path):
    """A directory shaped like the submission: no .git, but a real .gitignore."""
    (tmp_path / ".gitignore").write_text(
        ".env\nsecrets.toml\n__pycache__\n", encoding="utf-8")
    return tmp_path


def test_a_missing_history_is_reported_as_unscanned_not_as_a_finding(tmp_path, monkeypatch):
    """The submitted ZIP has no .git, and that must not read as a leak.

    The earlier version turned `git rev-list` failing into a finding, so running
    the documented command from the ZIP printed "1 finding(s). DO NOT PUSH."
    while DEVPOST said it must print `RESULT: clean`.
    """
    scan = _secret_scan_module()
    monkeypatch.setattr(scan, "ROOT", _minimal_tree(tmp_path))
    monkeypatch.setattr(scan, "scan_history", lambda: ([], "no-repository"))

    code = scan.main()
    assert code == 3, "an unscanned history must not exit 0"

    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        scan.main()
    out = buf.getvalue()
    assert "DO NOT PUSH" not in out, out
    assert "NOT SCANNED" in out, out
    assert "RESULT: clean." not in out, (
        "the tree-only result must not be printed as the full clean result"
    )


def test_no_git_on_path_does_not_traceback(tmp_path, monkeypatch):
    """A Windows box without Git for Windows has no `git` binary at all."""
    scan = _secret_scan_module()
    monkeypatch.setattr(scan, "ROOT", _minimal_tree(tmp_path))

    def no_git(args):
        return False, "", "git-not-found"

    monkeypatch.setattr(scan, "_git", no_git)

    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = scan.main()
    out = buf.getvalue()
    assert code == 3, out
    assert "not installed or not on PATH" in out, out
    assert "DO NOT PUSH" not in out, out


def test_the_clean_result_is_still_reported_when_history_is_readable():
    """The strong claim has to remain reachable, or the fix traded one bad
    message for another: from a clone, `RESULT: clean` and exit 0."""
    import io
    import contextlib

    repo = ROOT / ".git"
    if not repo.exists():
        pytest.skip("not a clone - the full-history claim cannot be checked here")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _secret_scan_module().main()
    assert code == 0, buf.getvalue()
    assert "RESULT: clean" in buf.getvalue()
    assert "NOT SCANNED" not in buf.getvalue()
