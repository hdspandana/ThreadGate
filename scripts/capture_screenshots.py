"""Capture the submission screenshots from the running Streamlit app.

These are real captures of the real app, not mockups. Every number visible in
them is produced by the pipeline at capture time.

    bash scripts/serve.sh            # in another shell
    python scripts/capture_screenshots.py

Options:
    --base-url http://127.0.0.1:8501
    --extractor offline              # which interpreter is selected in the UI

If GEMINI_API_KEY is set, run with `--extractor gemini` to capture the real
model path. Otherwise the app selects the offline test double and the
screenshots must be labelled accordingly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"

# (filename, case id, what the shot is meant to show)
TARGETS = [
    ("01_benign_pre_registered_CLEAR.png", "TG-012",
     "A change to a destination already on file. The gate CLEARs it; holding "
     "these is pure review cost."),
    ("02_destination_change_HOLD.png", "TG-001",
     "The canonical case: the requested account is not the one on file. The "
     "diff and the callback checklist are shown."),
    ("03_prompt_injection_HOLD.png", "TG-015",
     "The email instructs the assistant to report no change. The floor does "
     "not ask the model, so it holds."),
    ("04_semantic_negation_NO_CHANGE.png", "TG-007",
     "The email says it is NOT changing anything. The rules-only baseline "
     "holds it; the gate does not. This is what the model is for."),
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

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.goto(args.base_url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(4000)

        select(page, "Extractor", args.extractor)

        for filename, case_id, _ in TARGETS:
            select(page, "Case", case_id)
            page.wait_for_timeout(1200)
            path = OUT / filename
            page.screenshot(path=str(path), full_page=False)
            captured.append(path)
            print(f"  {filename}  ({case_id})")

        # 5 - the corpus comparison table, on whichever case set is selected
        page.locator("button", has_text="cases across every system").first.click()
        page.wait_for_selector("table", timeout=180_000)
        page.wait_for_timeout(2500)
        path = OUT / "05_evaluation_comparison.png"
        page.screenshot(path=str(path), full_page=True)
        captured.append(path)
        print(f"  {filename if False else '05_evaluation_comparison.png'}  (corpus run)")

        browser.close()

    print(f"\n{len(captured)} screenshot(s) in {OUT}")
    for c in captured:
        print(f"  {c.relative_to(ROOT)}  {c.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
