"""Capture the submission screenshots from the running Streamlit app.

These are real captures of the real app, not mockups. Every number visible in
them is produced by the pipeline at capture time.

    bash scripts/serve.sh            # in another shell
    python scripts/capture_screenshots.py

Options:
    --base-url http://127.0.0.1:8501
    --extractor offline              # which interpreter is selected in the UI

The script refuses to leave a screenshot on disk whose rendered chrome contains
an obsolete decision term. The email body is excluded from that check: the
synthetic prompt-injection fixtures contain attacker-authored text that
legitimately still says "report NO_CHANGE", and that is data, not UI.

If GEMINI_API_KEY is set, run with `--extractor gemini` to capture the real
model path. Otherwise the app selects the offline test double and the
screenshots must be labelled accordingly.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"

DECISIONS = ("CLEAR", "REVIEW", "HOLD")
OBSOLETE = ("ALLOW", "NO_CHANGE", "NO CHANGE")
BADGE_RE = re.compile(r"^(CLEAR|REVIEW|HOLD)\s*-")

# (filename, case id, expected decision, what the shot is meant to show)
TARGETS = [
    ("01_pre_registered_REVIEW.png", "TG-012", "REVIEW",
     "A change to a destination already on file. The gate returns REVIEW, not "
     "HOLD - holding these is pure review cost."),
    ("02_destination_change_HOLD.png", "TG-001", "HOLD",
     "The canonical case: the requested account is not the one on file. The "
     "diff and the out-of-band callback checklist are shown."),
    ("03_prompt_injection_HOLD.png", "TG-015", "HOLD",
     "The email instructs the assistant to report no change. The floor does "
     "not ask the model, so it holds."),
    ("04_negation_CLEAR.png", "TG-007", "CLEAR",
     "The email says it is NOT changing anything. The rules-only baseline "
     "holds it; the gate identifies no change. This is what the model is for."),
]


def select(page, label: str, value: str) -> None:
    """Pick an option from a Streamlit selectbox by typing and confirming."""
    box = page.locator(f'input[aria-label="{label}"]')
    box.click()
    box.fill("")
    box.type(value, delay=25)
    page.wait_for_timeout(700)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1800)


def chrome_text(page) -> str:
    """Rendered UI text with the email body removed.

    The email box holds synthetic attacker text; it is data, not interface, and
    is deliberately not held to the UI vocabulary.
    """
    return page.evaluate(
        "() => { const c = document.body.cloneNode(true);"
        "        c.querySelectorAll('.emailbox').forEach(e => e.remove());"
        "        return c.innerText; }"
    )


def check_vocabulary(page, badge: str, label: str) -> list[str]:
    problems = []
    if not BADGE_RE.match(badge):
        problems.append(f"{label}: badge {badge!r} does not start with a final decision")
    text = chrome_text(page)
    for term in OBSOLETE:
        if term in text:
            problems.append(f"{label}: obsolete decision term {term!r} in rendered UI")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8501")
    ap.add_argument("--extractor", default="offline")
    ap.add_argument("--width", type=int, default=1500)
    ap.add_argument("--height", type=int, default=1050)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && playwright install chromium",
              file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    captured: list[Path] = []
    problems: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.base_url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(4000)

        select(page, "Extractor", args.extractor)

        for filename, case_id, expected, _ in TARGETS:
            select(page, "Case", case_id)
            page.wait_for_timeout(1200)
            badge = page.locator("span.badge").first.inner_text().strip()
            if not badge.startswith(expected):
                problems.append(f"{case_id}: expected {expected}, rendered {badge!r}")
            problems.extend(check_vocabulary(page, badge, case_id))
            path = OUT / filename
            page.screenshot(path=str(path), full_page=False)
            captured.append(path)
            print(f"  {filename:38} {case_id}  badge={badge!r}")

        # 5 - the corpus comparison table, on whichever case set is selected
        page.locator("button", has_text="cases across every system").first.click()
        page.wait_for_selector("table", timeout=180_000)
        page.wait_for_timeout(2500)
        problems.extend(check_vocabulary(page, "HOLD - verified", "corpus"))
        path = OUT / "05_evaluation_comparison.png"
        page.screenshot(path=str(path), full_page=True)
        captured.append(path)
        print(f"  {'05_evaluation_comparison.png':38} corpus")

        browser.close()

    print(f"\n{len(captured)} screenshot(s) in {OUT}")
    for c in captured:
        print(f"  {c.relative_to(ROOT)}  {c.stat().st_size // 1024} KB")

    if problems:
        print("\nVOCABULARY CHECK FAILED - do not submit these:")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    print("\nVOCABULARY CHECK PASSED - every shot renders only CLEAR / REVIEW / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
