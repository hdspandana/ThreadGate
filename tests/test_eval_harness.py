"""The evaluation harness must not manufacture a number it did not measure.

The report is the artefact a judge reads and the artefact the README quotes. A
row built from API errors is the dangerous case: the pipeline fails closed per
case, so an errored run produces HOLD everywhere, which scores as a perfect
safety result. Publishing that as a measurement is worse than publishing nothing.

Three things are pinned here:

  1. errors mark the row INVALID and null its headline figures
  2. `systems_invalid` is populated after evaluation, so it is not always empty
  3. non-CLEAR releases are counted, so a bypass cannot score as a success
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "eval"))

import run_eval  # noqa: E402
from threadgate.clock import fixed  # noqa: E402
from threadgate.extract import offline_extract  # noqa: E402
from threadgate.pipeline import PipelineResult, run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
CLOCK = fixed("2026-10-06")


def _cases(name: str = "frozen_v2.json") -> list[dict]:
    return load_cases(ROOT / "data" / "cases" / name)


def _results(system_extractor=offline_extract, cases=None) -> list[PipelineResult]:
    return [
        run_case(c, VENDORS, extractor_fn=system_extractor, clock=CLOCK)
        for c in (cases or _cases())
    ]


# ---------------------------------------------------------------------------
# 1. metrics on an errored run
# ---------------------------------------------------------------------------
def test_a_clean_run_produces_finite_headline_numbers():
    m = run_eval.metrics(_results())
    assert m["accuracy"] is not None
    assert not m.get("invalid")
    assert m["unsafe_hold_releases"] == 0
    assert m["non_clear_releases"] == 0


def test_an_errored_run_is_marked_invalid_and_has_no_accuracy():
    """The pipeline fails closed, so errors look like a perfect safety score.

    Nulling the headline figures is the only thing that stops that number being
    quoted.
    """
    results = _results()
    results[0].error = "extractor_error: 429 RESOURCE_EXHAUSTED"
    results[1].error = "extractor_error: 429 RESOURCE_EXHAUSTED"
    m = run_eval.metrics(results)
    assert m["invalid"] is True
    assert m["extractor_errors"] == 2
    assert m["accuracy"] is None
    assert m["safety_pct"] is None
    assert m["false_hold_pct"] is None


def test_the_error_count_and_case_ids_are_reported():
    results = _results()
    results[5].error = "extractor_error: timeout"
    m = run_eval.metrics(results)
    assert m["extractor_errors"] == 1
    assert m["error_case_ids"] == ["TG-006"]


def test_an_invalid_row_renders_as_invalid_not_as_a_number():
    results = _results()
    results[0].error = "extractor_error: boom"
    rendered = run_eval.render_main("v1", {"gemini": run_eval.metrics(results)})
    assert "INVALID" in rendered
    assert "100.0" not in rendered


@pytest.mark.parametrize("n_errors", [1, 2, 3])
def test_one_error_is_enough_to_invalidate_a_row(n_errors):
    """A partially-completed model run is not a model result."""
    results = _results()
    for i in range(n_errors):
        results[i].error = "extractor_error: x"
    assert run_eval.metrics(results)["invalid"] is True


# ---------------------------------------------------------------------------
# 2. non-CLEAR releases are counted
# ---------------------------------------------------------------------------
def test_non_clear_releases_are_reported_separately_from_unsafe():
    """A REVIEW labelled case that comes back CLEAR is not an `unsafe`.

    That is exactly why the pre-registered-alternate bypass scored as a clean
    success: no hold was released, because the gate had never held it.
    """
    results = _results()
    target = next(r for r in results if r.expected == "REVIEW")
    target.decision.decision = "CLEAR"
    m = run_eval.metrics(results)
    assert m["non_clear_releases"] == 1
    assert target.case_id in m["non_clear_release_ids"]
    assert m["unsafe_hold_releases"] == 0


def test_a_hold_that_is_released_counts_as_both():
    results = _results()
    target = next(r for r in results if r.expected == "HOLD")
    target.decision.decision = "CLEAR"
    m = run_eval.metrics(results)
    assert m["unsafe_hold_releases"] == 1
    assert m["non_clear_releases"] == 1


# ---------------------------------------------------------------------------
# 3. pairwise comparison
# ---------------------------------------------------------------------------
def test_compare_counts_agreement_and_disagreement():
    a = _results()
    b = _results()
    # make b wrong on three cases where a is right
    for r in b[:3]:
        r.decision.decision = "CLEAR"
    cmp = run_eval.compare(a, b)
    assert cmp["a_wins"] == 3
    assert cmp["b_wins"] == 0
    assert cmp["both_fail"] == 0
    assert cmp["n_compared"] == len(a)


def test_compare_counts_cases_neither_system_gets_right():
    """`both_fail` is the number that bounds the argument for the AI layer."""
    a = _results()
    b = _results()
    for r in a[:2] + b[:2]:
        r.decision.decision = "CLEAR"
    cmp = run_eval.compare(a, b)
    assert cmp["both_fail"] == 2


# ---------------------------------------------------------------------------
# 4. end to end: systems_invalid is populated
# ---------------------------------------------------------------------------
def _run_main(tmp_path: Path, monkeypatch, systems: list[str]) -> dict:
    """Run the harness with model systems enabled but a broken extractor."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-key")
    monkeypatch.setattr(run_eval, "gemini_available", lambda: True)

    def boom(nt, vendor=None, **kw):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    import threadgate.pipeline as pipeline_mod
    real_get_extractor = pipeline_mod.get_extractor

    def patched(mode=None):
        # Only the model-backed modes break; `offline` must still work so the
        # same run can show one clean system next to one invalid one.
        return boom if mode in run_eval.MODEL_SYSTEMS else real_get_extractor(mode)

    monkeypatch.setattr(pipeline_mod, "get_extractor", patched)

    monkeypatch.setattr(
        sys, "argv",
        ["run_eval.py", "--out", str(tmp_path), "--sets", "v1", "--systems", *systems],
    )
    run_eval.main()
    return json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))


def test_a_model_system_that_errors_appears_in_systems_invalid(tmp_path, monkeypatch):
    """The bug: this key was written before the loop that fills it.

    Placed alongside the other report keys it was always empty - including on
    runs where every model case had failed.
    """
    report = _run_main(tmp_path, monkeypatch, ["gemini"])
    assert "gemini" in report["systems_invalid"]


def test_an_invalid_system_is_never_listed_as_safe(tmp_path, monkeypatch):
    report = _run_main(tmp_path, monkeypatch, ["gemini"])
    assert "gemini" not in report["systems_safe"]


def test_a_clean_offline_run_is_listed_as_safe(tmp_path, monkeypatch):
    report = _run_main(tmp_path, monkeypatch, ["offline"])
    assert report["systems_invalid"] == []
    assert "offline" in report["systems_safe"]


def test_errored_systems_are_reported_per_set_too(tmp_path, monkeypatch):
    report = _run_main(tmp_path, monkeypatch, ["gemini"])
    m = report["sets"]["v1"]["metrics"]["gemini"]
    assert m["invalid"] is True
    assert m["extractor_errors"] > 0


def test_require_gemini_exit_code_reflects_an_errored_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-key")
    monkeypatch.setattr(run_eval, "gemini_available", lambda: True)

    def boom(nt, vendor=None, **kw):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    import threadgate.pipeline as pipeline_mod
    monkeypatch.setattr(
        pipeline_mod, "get_extractor",
        lambda mode=None: boom if mode in run_eval.MODEL_SYSTEMS
        else pipeline_mod.get_extractor(mode),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["run_eval.py", "--out", str(tmp_path), "--sets", "v1",
         "--systems", "gemini", "--require-gemini"],
    )
    assert run_eval.main() == 2


# ---------------------------------------------------------------------------
# 5. eval-all covers every model-backed system
# ---------------------------------------------------------------------------
def test_the_makefile_eval_all_runs_every_model_backed_system():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    block = makefile.split("eval-all:", 1)[1].split("\n\n", 1)[0]
    for system in ("gemini", "ai_only", "hybrid_no_scan", "hybrid_no_validation"):
        assert system in block, f"`make eval-all` does not run {system}"


def test_every_model_backed_system_is_known_to_the_harness():
    for system in ("gemini", "ai_only", "hybrid_no_scan", "hybrid_no_validation"):
        assert system in run_eval.ALL_SYSTEMS
        assert system in run_eval.MODEL_SYSTEMS


# ---------------------------------------------------------------------------
# Item 4 - a non-CLEAR release is a first-class metric, not a hidden one
# ---------------------------------------------------------------------------


class TestNonClearReleasesCannotHideBehindAPerfectSafetyScore:
    """The failure mode: safety 100% on the row, a waved-through case beneath it.

    `unsafe` only counts cases labelled HOLD. A case labelled REVIEW that comes
    back CLEAR is also a gate that did not gate, and reporting only the first
    number is how the pre-registered-alternate bypass read as a clean run.
    """

    def test_metrics_report_the_gated_denominator_and_a_second_percentage(self):
        m = run_eval.metrics(_results())
        assert "gated" in m
        assert "no_bypass_pct" in m
        assert m["gated"] >= sum(1 for r in _results() if r.expected == "HOLD")

    def test_no_bypass_pct_falls_when_a_gated_case_comes_back_clear(self):
        rs = _results()
        clean = run_eval.metrics(rs)

        target = next(r for r in rs if r.expected == "REVIEW")
        object.__setattr__(target.decision, "decision", "CLEAR")
        dirty = run_eval.metrics(rs)

        assert clean["no_bypass_pct"] == 100.0
        assert dirty["no_bypass_pct"] < 100.0
        assert dirty["non_clear_releases"] == 1

    def test_a_perfect_safety_score_does_not_make_a_system_safe_on_its_own(self):
        """The specific claim: unsafe 0 + safety 100% is not sufficient."""
        rs = _results()
        target = next(r for r in rs if r.expected == "REVIEW")
        object.__setattr__(target.decision, "decision", "CLEAR")
        m = run_eval.metrics(rs)

        # The misleading combination this test exists to prevent.
        assert m["unsafe_hold_releases"] == 0
        assert m["safety_pct"] == 100.0
        assert m["non_clear_releases"] == 1
        assert m["no_bypass_pct"] < 100.0

    def test_the_cli_table_shows_both_counts_and_both_percentages(self):
        rendered = run_eval.render_main("v1", {"good": run_eval.metrics(_results())})
        for column in ("non-CLR", "no-bypass %", "safety %", "unsafe"):
            assert column in rendered, column

    def test_the_cli_calls_out_a_non_clear_release_in_words(self):
        """A column is easy to miss; the run has to say it out loud."""
        rs = _results()
        target = next(r for r in rs if r.expected == "REVIEW")
        object.__setattr__(target.decision, "decision", "CLEAR")
        m = run_eval.metrics(rs)

        lines = run_eval.render_warnings({"x": m}, set())
        text = "\n".join(lines)
        assert "returned CLEAR" in text
        assert target.case_id in text

    def test_an_invalid_row_is_announced_too(self):
        rs = _results()
        m = run_eval.metrics(rs)
        m["invalid"] = True
        m["extractor_errors"] = 3
        m["error_case_ids"] = ["TG-001"]
        text = "\n".join(run_eval.render_warnings({"x": m}, {"x"}))
        assert "INVALID" in text


# ---------------------------------------------------------------------------
# Item 5 - an invalid system produces no numbers at all
# ---------------------------------------------------------------------------


def _errored(n: int = 2):
    """Results where the first `n` cases failed in the model layer."""
    rs = _results()
    for r in rs[:n]:
        r.error = "extractor_error: 429 RESOURCE_EXHAUSTED"
    return rs


class TestAnInvalidSystemProducesNoQuotableFigure:
    """The dangerous number is the fake zero, not the missing accuracy.

    The pipeline fails closed, so an errored case becomes a HOLD. Errored cases
    therefore score as perfect safety: unsafe 0, non-CLEAR releases 0. That is
    the strongest claim the table can make, produced by a run that measured
    nothing, and it is the number most likely to be quoted.
    """

    @pytest.mark.parametrize(
        "key",
        [
            "accuracy",
            "safety_pct",
            "no_bypass_pct",
            "false_hold_pct",
            "unsafe_hold_releases",
            "non_clear_releases",
            "false_holds",
        ],
    )
    def test_every_headline_figure_is_nulled(self, key):
        m = run_eval.metrics(_errored())
        assert m["invalid"] is True
        assert m[key] is None, key

    def test_the_fake_zeros_are_gone(self):
        """Before this fix, these read 0 - a perfect result from a broken run.

        `is None` rather than `!= 0`, because the point is that no number is
        published at all. A 0 would have passed the weaker assertion.
        """
        m = run_eval.metrics(_errored())
        assert m["unsafe_hold_releases"] is None
        assert m["non_clear_releases"] is None
        assert m["non_clear_release_ids"] == []

    def test_the_error_count_and_case_ids_survive(self):
        m = run_eval.metrics(_errored(3))
        assert m["extractor_errors"] == 3
        assert len(m["error_case_ids"]) == 3

    def test_an_invalid_row_renders_without_a_number(self):
        rendered = run_eval.render_main("v1", {"gemini": run_eval.metrics(_errored())})
        assert "INVALID" in rendered
        assert "100.0" not in rendered
        assert "0.0" not in rendered

    def test_an_invalid_category_bucket_renders_as_invalid(self):
        """`cat_table[category][system]` is the shape render_categories expects."""
        assignments = {r.case_id: "direct_change" for r in _results()}
        bucket = run_eval.by_category(_errored(), assignments)
        cat_table = {"direct_change": {"gemini": bucket["direct_change"]}}
        rendered = run_eval.render_categories("v1", cat_table, ["gemini"])
        assert "INVALID" in rendered
        assert "100" not in rendered

    def test_a_valid_category_bucket_still_shows_both_counts(self):
        assignments = {r.case_id: "direct_change" for r in _results()}
        bucket = run_eval.by_category(_results(), assignments)
        cat_table = {"direct_change": {"offline": bucket["direct_change"]}}
        rendered = run_eval.render_categories("v1", cat_table, ["offline"])
        assert "(u0 n0)" in rendered

    def test_comparisons_suppressed_is_reported_in_the_json(self):
        """The report has to say a comparison is missing, not silently omit it."""
        src = (ROOT / "eval" / "run_eval.py").read_text(encoding="utf-8")
        assert "comparisons_suppressed" in src
        assert "a not in invalid_systems" in src

    def test_a_valid_system_is_never_marked_invalid(self):
        assert run_eval.metrics(_results()).get("invalid") is None


def test_the_documentation_explains_both_permissive_metrics():
    """Item 4: the README table must carry both columns, not just unsafe."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count("Non-CLR") >= 3, "all three set tables need the column"
    assert readme.count("No-bypass %") >= 3
    assert "non-CLEAR release" in readme


# ---------------------------------------------------------------------------
# Item 6 - the checked-in artifact corresponds to the current code
# ---------------------------------------------------------------------------


class TestTheStoredReportMatchesTheCurrentCode:
    """`results/latest.json` is quoted by the README.

    An artifact generated by an older commit is a public number that no current
    build can reproduce, which is the same failure as the stale test count in a
    different file. The check is behavioural rather than a commit hash in the
    JSON: a hash would go stale on the next commit, whereas recomputing the
    runnable rows catches the thing that actually matters.
    """

    @pytest.fixture(scope="class")
    def stored(self):
        path = ROOT / "results" / "latest.json"
        assert path.exists(), "results/latest.json is missing - run eval/run_eval.py"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_report_records_the_pinned_evaluation_date(self, stored):
        assert stored["as_of"] == run_eval.EVAL_AS_OF

    def test_no_model_row_is_filled_without_a_key(self, stored):
        """No fabricated Gemini numbers, ever."""
        assert stored["gemini_evaluated"] is False
        for sysname in ("gemini", "ai_only", "hybrid_no_scan", "hybrid_no_validation"):
            assert sysname not in stored["sets"]["v1"]["metrics"], (
                f"{sysname} has a row in the stored report with no key present"
            )

    @pytest.mark.parametrize("system", ["rules_raw", "rules_norm", "offline", "compromised"])
    def test_the_stored_metrics_reproduce_from_the_current_code(self, stored, system):
        """Recompute the row; if it differs, the artifact is from an older build."""
        cases = load_cases(ROOT / "data" / "cases" / "frozen_v1.json")
        fresh = run_eval.metrics(
            run_eval.run_system(system, cases, VENDORS, clock=CLOCK)
        )
        saved = stored["sets"]["v1"]["metrics"][system]
        for key in ("accuracy", "unsafe_hold_releases", "non_clear_releases", "false_holds"):
            assert fresh[key] == saved[key], (
                f"{system}.{key}: code says {fresh[key]}, "
                f"results/latest.json says {saved[key]} - regenerate the artifact"
            )

    def test_the_stored_report_carries_both_safety_metrics(self, stored):
        for name, table in stored["sets"].items():
            for system, m in table["metrics"].items():
                if m.get("invalid"):
                    continue
                assert "unsafe_hold_releases" in m, (name, system)
                assert "non_clear_releases" in m, (name, system)
                assert "no_bypass_pct" in m, (name, system)

    def test_every_run_system_is_classified_and_unsafe_ones_are_not_hidden(
        self, stored
    ):
        """Three legitimate states, and no fourth.

        safe     - ran, measured, zero unsafe and zero non-CLEAR releases
        invalid  - ran, but errored; no figure may be quoted
        measured-but-unsafe - ran, and released something it should not have

        The third is not a bug in the classification - `rules_raw` genuinely
        waves cases through on the obfuscation category, and that is the result
        the evaluation exists to report. What would be a bug is a system that
        ran and appears in none of the three, or one that released a case while
        still being listed safe.
        """
        for system in stored["systems_run"]:
            listed_safe = system in stored["systems_safe"]
            listed_invalid = system in stored["systems_invalid"]
            if listed_invalid:
                continue
            released = any(
                table["metrics"].get(system, {}).get("unsafe_hold_releases")
                or table["metrics"].get(system, {}).get("non_clear_releases")
                for table in stored["sets"].values()
            )
            if listed_safe:
                assert not released, f"{system} is listed safe but released a case"
            else:
                assert released, (
                    f"{system} ran, is not listed invalid, is not listed safe, and "
                    f"released nothing - the classification is inconsistent"
                )
