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
