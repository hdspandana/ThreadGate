"""Merge frozen_v1 with the second tranche into a single frozen set.

Freezing is a script rather than a hand edit so that the corpus can be audited:
v1 stays untouched on disk, and what was added, and when, is in the additions
file. Run once, then never again - the output is frozen.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data" / "cases" / "frozen_v1.json"
ADDITIONS = ROOT / "data" / "cases" / "frozen_v2_additions.json"
OUT = ROOT / "data" / "cases" / "frozen_v2.json"


def main() -> int:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    additions = json.loads(ADDITIONS.read_text(encoding="utf-8"))

    ids = [c["id"] for c in v1["cases"]]
    for c in additions["cases"]:
        if c["id"] in ids:
            print(f"duplicate id {c['id']}", file=sys.stderr)
            return 1
        ids.append(c["id"])

    merged = dict(v1)
    merged["version"] = "frozen_v2"
    merged["frozen_at"] = datetime.now(timezone.utc).date().isoformat()
    merged["status"] = "FROZEN - 40 cases. v1 plus a second tranche written after the first run."
    merged["cases"] = v1["cases"] + additions["cases"]

    from collections import Counter

    merged["composition"] = dict(Counter(c["expected_decision"] for c in merged["cases"]))
    OUT.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} with {len(merged['cases'])} cases: {merged['composition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
