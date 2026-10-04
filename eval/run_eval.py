"""Evaluation harness.

Runs every system over the frozen case set and writes a report.

Systems:
  rules_raw        rules-only baseline on the raw text
  rules_norm       the same rules after normalisation (isolates what
                   normalisation alone buys)
  gemini           ThreadGate with the real model
  compromised      ThreadGate with a model steered to always say no_change
  compromised_q    same, but the steered model forges a verbatim quote
  offline          the deterministic test double (no network); reported for
                   completeness, never quoted as the result

Usage:
  python eval/run_eval.py --systems rules_raw rules_norm gemini compromised compromised_q
  python eval/run_eval.py --systems rules_raw offline          # no key needed
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.baseline import rules_only, rules_only_normalized  # noqa: E402
from threadgate.pipeline import PipelineResult, run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

CASES = ROOT / "data" / "cases" / "frozen_v1.json"
VENDORS = ROOT / "data" / "records" / "vendor_master.json"

ALL_SYSTEMS = ["rules_raw", "rules_norm", "gemini", "offline", "compromised", "compromised_q"]


def run_system(system: str, cases: list[dict], vendors: dict) -> list[PipelineResult]:
    if system == "rules_raw":
        return [
            PipelineResult(
                case_id=c["id"],
                vendor_id=c["vendor_id"],
                decision=rules_only(c, vendors[c["vendor_id"]]),
                extraction=None,
                validation=None,
                tokens=[],
                nt=None,
                extractor=system,
                elapsed_ms=0.0,
                expected=c["expected_decision"],
            )
            for c in cases
        ]
    if system == "rules_norm":
        return [
            PipelineResult(
                case_id=c["id"],
                vendor_id=c["vendor_id"],
                decision=rules_only_normalized(c, vendors[c["vendor_id"]]),
                extraction=None,
                validation=None,
                tokens=[],
                nt=None,
                extractor=system,
                elapsed_ms=0.0,
                expected=c["expected_decision"],
            )
            for c in cases
        ]
    mode = {"gemini": "gemini", "offline": "offline",
            "compromised": "compromised", "compromised_q": "compromised_quote"}[system]
    return [run_case(c, vendors, extractor_mode=mode) for c in cases]


def metrics(results: list[PipelineResult]) -> dict:
    n = len(results)
    correct = sum(1 for r in results if r.correct)
    unsafe = sum(1 for r in results if r.unsafe)
    false_holds = sum(1 for r in results if r.false_hold)
    hold_expected = sum(1 for r in results if r.expected == "HOLD")
    non_hold_expected = n - hold_expected
    missed_holds = [r.case_id for r in results if r.unsafe]
    return {
        "n": n,
        "accuracy": round(100.0 * correct / n, 1) if n else 0.0,
        "correct": correct,
        "unsafe_missed_holds": unsafe,
        "safety_pct": round(100.0 * (hold_expected - unsafe) / hold_expected, 1) if hold_expected else 0.0,
        "missed_hold_ids": missed_holds,
        "false_holds": false_holds,
        "false_hold_pct": round(100.0 * false_holds / non_hold_expected, 1) if non_hold_expected else 0.0,
    }


def group_breakdown(results: list[PipelineResult]) -> dict[str, dict]:
    groups: dict[str, list[PipelineResult]] = {}
    for r in results:
        g = r.case_id and next(
            (c["group"] for c in CASES_OBJ if c["id"] == r.case_id), "unknown"
        )
        groups.setdefault(g, []).append(r)
    return {g: metrics(rs) for g, rs in sorted(groups.items())}


def render_table(all_metrics: dict[str, dict]) -> str:
    head = f"{'system':<14}{'acc %':>7}{'unsafe':>8}{'safety %':>10}{'false holds':>13}{'fh %':>7}"
    lines = [head, "-" * len(head)]
    for name, m in all_metrics.items():
        lines.append(
            f"{name:<14}{m['accuracy']:>7.1f}{m['unsafe_missed_holds']:>8}"
            f"{m['safety_pct']:>10.1f}{m['false_holds']:>13}{m['false_hold_pct']:>7.1f}"
        )
    return "\n".join(lines)


def main() -> int:
    global CASES_OBJ
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=["rules_raw", "rules_norm", "offline"])
    ap.add_argument("--cases", default=str(CASES))
    ap.add_argument("--out", default=str(ROOT / "data" / "runs"))
    args = ap.parse_args()

    cases = load_cases(args.cases)
    CASES_OBJ = cases
    vendors = load_vendors(VENDORS)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_metrics: dict[str, dict] = {}
    per_case: dict[str, dict] = {}

    for system in args.systems:
        if system not in ALL_SYSTEMS:
            print(f"unknown system {system}; expected one of {ALL_SYSTEMS}", file=sys.stderr)
            return 2
        results = run_system(system, cases, vendors)
        all_metrics[system] = metrics(results)
        all_metrics[system]["by_group"] = group_breakdown(results)
        per_case[system] = {
            r.case_id: {
                "expected": r.expected,
                "got": r.decision.decision,
                "reasons": r.decision.reasons,
                "notes": r.notes,
                "error": r.error,
            }
            for r in results
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_set": Path(args.cases).name,
        "n_cases": len(cases),
        "systems": args.systems,
        "metrics": all_metrics,
        "per_case": per_case,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"eval_{stamp}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(render_table(all_metrics))
    print()
    for system in args.systems:
        missed = all_metrics[system]["missed_hold_ids"]
        if missed:
            print(f"{system}: missed HOLD on {', '.join(missed)}")
    print(f"\nwrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
