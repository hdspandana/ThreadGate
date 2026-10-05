"""Evaluation harness.

Three sets, reported separately, because they mean different things:

  v1        frozen_v1 - the PRIMARY PRE-FROZEN BENCHMARK. Written before any
            evaluation was run. This is the only set from which a performance
            claim about the system may be quoted.
  stress    frozen_v2 additions - an ADVERSARIAL STRESS SET written AFTER the
            first evaluation, from attack patterns and from failure modes
            visible in the design. It measures robustness, not field accuracy.
  combined  both together. Reported only as a labelled stress evaluation. It is
            NOT an unbiased frozen benchmark and must never be described as one.

Systems:
  rules_raw        rules-only baseline on raw text
  rules_norm       the same rules after normalisation (isolates what
                   normalisation alone buys)
  gemini           ThreadGate with the real model. SKIPPED, loudly, when
                   GEMINI_API_KEY is absent - it is never silently degraded into
                   a fail-closed row that looks like a result.
  offline          deterministic test double, no network. NOT a model and NOT
                   evidence of model performance.
  compromised      adversarial harness: model steered to always report no_change
  compromised_q    same, but the steered model forges a verbatim quote

Usage:
  python eval/run_eval.py                      # all sets, no key needed
  python eval/run_eval.py --sets v1 --systems rules_raw rules_norm gemini
  python eval/run_eval.py --require-gemini     # exit 2 if the model cannot run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.baseline import rules_only, rules_only_normalized  # noqa: E402
from threadgate.pipeline import PipelineResult, run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402

CASES_DIR = ROOT / "data" / "cases"
VENDORS = ROOT / "data" / "records" / "vendor_master.json"
CATEGORIES = CASES_DIR / "categories.json"

SETS = {
    "v1": {
        "path": CASES_DIR / "frozen_v1.json",
        "title": "frozen_v1 - PRIMARY PRE-FROZEN BENCHMARK",
        "caveat": "Written before any evaluation was run. The only set a performance claim may be quoted from.",
    },
    "stress": {
        "path": CASES_DIR / "frozen_v2_additions.json",
        "title": "frozen_v2 additions - ADVERSARIAL STRESS SET",
        "caveat": "Written AFTER the first evaluation, from attack patterns and known failure modes. Measures robustness, not field accuracy.",
    },
    "combined": {
        "path": CASES_DIR / "frozen_v2.json",
        "title": "v1 + stress - COMBINED, STRESS EVALUATION ONLY",
        "caveat": "NOT an unbiased frozen benchmark. Do not quote a single accuracy number from this set as a performance claim.",
    },
}

ALL_SYSTEMS = ["rules_raw", "rules_norm", "gemini", "offline", "compromised", "compromised_q"]
MODEL_SYSTEM = "gemini"

DISCLAIMER = (
    "READ THIS BEFORE QUOTING ANY NUMBER\n"
    "  `offline` is a deterministic test double. It is not a model and its score is not\n"
    "  evidence of model performance.\n"
    "  `gemini` is the only row that evidences model performance. It is skipped when\n"
    "  GEMINI_API_KEY is absent.\n"
    "  `compromised` / `compromised_q` measure failure behaviour under a hostile model.\n"
    "  Their accuracy is deliberately low; what matters is that `unsafe` stays at 0."
)


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def run_system(system: str, cases: list[dict], vendors: dict) -> list[PipelineResult]:
    if system in ("rules_raw", "rules_norm"):
        fn = rules_only if system == "rules_raw" else rules_only_normalized
        return [
            PipelineResult(
                case_id=c["id"],
                vendor_id=c["vendor_id"],
                decision=fn(c, vendors[c["vendor_id"]]),
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
    mode = {
        "gemini": "gemini",
        "offline": "offline",
        "compromised": "compromised",
        "compromised_q": "compromised_quote",
    }[system]
    return [run_case(c, vendors, extractor_mode=mode) for c in cases]


def metrics(results: list[PipelineResult]) -> dict:
    n = len(results)
    correct = sum(1 for r in results if r.correct)
    unsafe = sum(1 for r in results if r.unsafe)
    hold_expected = sum(1 for r in results if r.expected == "HOLD")
    non_hold = n - hold_expected
    false_holds = sum(1 for r in results if r.false_hold)
    return {
        "n": n,
        "accuracy": round(100.0 * correct / n, 1) if n else 0.0,
        "correct": correct,
        "unsafe_missed_holds": unsafe,
        "safety_pct": round(100.0 * (hold_expected - unsafe) / hold_expected, 1) if hold_expected else 0.0,
        "missed_hold_ids": [r.case_id for r in results if r.unsafe],
        "false_holds": false_holds,
        "false_hold_pct": round(100.0 * false_holds / non_hold, 1) if non_hold else 0.0,
    }


def by_category(results: list[PipelineResult], assignments: dict) -> dict[str, dict]:
    buckets: dict[str, list[PipelineResult]] = {}
    for r in results:
        buckets.setdefault(assignments.get(r.case_id, "uncategorised"), []).append(r)
    return {k: metrics(v) for k, v in sorted(buckets.items())}


def render_main(name: str, table: dict[str, dict]) -> str:
    head = f"{'system':<16}{'acc %':>7}{'unsafe':>8}{'safety %':>10}{'false holds':>13}"
    out = [f"--- {SETS[name]['title']} ({table and list(table.values())[0]['n'] or 0} cases) ---"]
    out.append("    " + SETS[name]["caveat"])
    out.append(head)
    out.append("-" * len(head))
    for s, m in table.items():
        out.append(
            f"{s:<16}{m['accuracy']:>7.1f}{m['unsafe_missed_holds']:>8}"
            f"{m['safety_pct']:>10.1f}{m['false_holds']:>13}"
        )
    return "\n".join(out)


def render_categories(name: str, per_cat: dict[str, dict], systems: list[str]) -> str:
    if not per_cat:
        return ""
    width = 15
    out = [
        f"\n    per-category accuracy on {name} (u = unsafe: a hold that was released)",
        f"    {'category':<26}{'n':>3}  "
        + "  ".join(f"{s[:width]:>{width}}" for s in systems),
    ]
    for cat, data in sorted(per_cat.items()):
        cells = []
        for s in systems:
            m = data.get(s)
            cells.append(f"{m['accuracy']:.0f} (u{m['unsafe_missed_holds']})".rjust(width) if m else "".rjust(width))
        out.append(f"    {cat:<26}{data[systems[0]]['n'] if systems and systems[0] in data else 0:>3}  " + "  ".join(cells))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["v1", "stress", "combined"], choices=list(SETS))
    ap.add_argument("--systems", nargs="+", default=["rules_raw", "rules_norm", "offline", "compromised", "compromised_q"])
    ap.add_argument("--out", default=str(ROOT / "data" / "runs"))
    ap.add_argument("--require-gemini", action="store_true", help="exit 2 if the live model cannot be evaluated")
    args = ap.parse_args()

    systems = [s for s in args.systems if s in ALL_SYSTEMS]
    if args.require_gemini and MODEL_SYSTEM not in systems:
        # Otherwise `--require-gemini` on its own would exit 2 for a model it
        # never asked for, which is the wrong failure.
        systems.append(MODEL_SYSTEM)
    skipped: list[str] = []
    invalid_systems: set[str] = set()

    if MODEL_SYSTEM in systems and not gemini_available():
        systems.remove(MODEL_SYSTEM)
        skipped.append(MODEL_SYSTEM)

    vendors = load_vendors(VENDORS)
    cat_map = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    assignments = cat_map["assignments"]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "systems_run": systems,
        "systems_skipped": skipped,
        "gemini_evaluated": MODEL_SYSTEM in systems,
        "sets": {},
    }
    if invalid_systems:
        report["systems_invalid"] = sorted(invalid_systems)

    for set_name in args.sets:
        cases = load_cases(SETS[set_name]["path"])
        main_table: dict[str, dict] = {}
        cat_table: dict[str, dict] = {}
        per_case: dict[str, dict] = {}

        for system in systems:
            results = run_system(system, cases, vendors)
            main_table[system] = metrics(results)
            failed = [r.case_id for r in results if r.error]
            if failed:
                # A key that is present but rejected, rate-limited or broken must
                # never produce a row that reads like a model result. The pipeline
                # fails closed per case, which would otherwise look like 100% safe.
                main_table[system]["invalid"] = True
                main_table[system]["extractor_errors"] = len(failed)
                main_table[system]["error_case_ids"] = failed[:10]
                invalid_systems.add(system)
            for cat, m in by_category(results, assignments).items():
                cat_table.setdefault(cat, {})[system] = m
            per_case[system] = {
                r.case_id: {
                    "expected": r.expected,
                    "got": r.decision.decision,
                    "reasons": r.decision.reasons,
                    "error": r.error,
                }
                for r in results
            }

        report["sets"][set_name] = {
            "title": SETS[set_name]["title"],
            "caveat": SETS[set_name]["caveat"],
            "n_cases": len(cases),
            "composition": dict(Counter(c["expected_decision"] for c in cases)),
            "metrics": main_table,
            "by_category": cat_table,
            "per_case": per_case,
        }

        print(render_main(set_name, main_table))
        print(render_categories(set_name, cat_table, systems))
        for s in sorted(invalid_systems):
            m = main_table.get(s, {})
            print(f"    !! `{s}` is INVALID on this set: {m.get('extractor_errors')} extractor "
                  f"errors (e.g. {', '.join(m.get('error_case_ids', [])[:5])}). "
                  "Do not quote this row.")
        print()

    print(DISCLAIMER)
    if skipped:
        print(f"\nSKIPPED: {', '.join(skipped)} - no GEMINI_API_KEY in the environment.")
        print("The `gemini` row stays empty until a live evaluation has actually run.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"eval_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")

    if args.require_gemini and (MODEL_SYSTEM not in systems or MODEL_SYSTEM in invalid_systems):
        print("\n--require-gemini: the live model was not evaluated cleanly.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
