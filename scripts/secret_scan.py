"""Secret audit for the working tree and the full git history.

Run this before pushing anything public. A key committed three commits ago and
deleted two commits ago is still in the history of a public repository.

    python scripts/secret_scan.py

Exit code 1 if anything matches. If it does, do not push, and do not rewrite
history in a hurry - report it first.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Patterns that indicate a real credential, not the name of one.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("assigned-gemini-key", re.compile(r"GEMINI_API_KEY\s*=\s*[\"']?[A-Za-z0-9_\-]{16,}")),
    ("assigned-google-key", re.compile(r"GOOGLE_API_KEY\s*=\s*[\"']?[A-Za-z0-9_\-]{16,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-\.]{24,}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
]

# Files that legitimately mention key names without holding one.
ALLOWLIST_SUFFIXES = {".md", ".example", ".txt", ".ini", ".toml"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "results", "data/runs"}

# A placeholder is fine; a real value is not.
PLACEHOLDER = re.compile(r"(your[-_]?key[-_]?here|xxxx+|placeholder|changeme|<[a-z_]+>)", re.IGNORECASE)


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.search(value))


def scan_text(text: str, location: str) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            snippet = m.group(0)
            if _is_placeholder(snippet):
                continue
            # Never print the whole matched secret.
            redacted = snippet[:6] + "..." + f"<{len(snippet)} chars>"
            line_no = text[: m.start()].count("\n") + 1
            hits.append((name, f"{location}:{line_no}", redacted))
    return hits


def scan_working_tree() -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if rel.name.startswith(".env") and rel.suffix not in ALLOWLIST_SUFFIXES:
            hits.append(("env-file-present", str(rel), "a .env file exists and would be committed"))
        if rel.name == "secrets.toml":
            hits.append(("streamlit-secrets", str(rel), "secrets.toml exists and would be committed"))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits.extend(scan_text(text, str(rel)))
    return hits


def scan_history() -> list[tuple[str, str, str]]:
    """Every blob that has ever been committed, in every commit."""
    hits: list[tuple[str, str, str]] = []
    try:
        revs = subprocess.run(["git", "rev-list", "--all"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.split()
    except subprocess.CalledProcessError:
        return [("git-error", "rev-list failed", "unable to scan history")]
    seen: set[str] = set()
    for rev in revs:
        listing = subprocess.run(["git", "ls-tree", "-r", rev], cwd=ROOT,
                                 capture_output=True, text=True)
        for line in listing.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            blob = parts[2]
            name = parts[3]
            key = f"{blob}:{name}"
            if key in seen:
                continue
            seen.add(key)
            if Path(name).name in {"secrets.toml"} or (
                Path(name).name.startswith(".env") and Path(name).suffix != ".example"
            ):
                hits.append(("secret-file-in-history", f"{rev[:8]}:{name}",
                             "a secret file was committed at some point"))
                continue
            # Binary blobs (PNG screenshots, for instance) must not crash the
            # audit; decode lossily and let the patterns find nothing.
            raw = subprocess.run(["git", "cat-file", "-p", blob], cwd=ROOT,
                                 capture_output=True).stdout
            try:
                blob_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits.extend(scan_text(blob_text, f"{rev[:8]}:{name}"))
    return hits


def gitignore_covers_secrets() -> bool:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    return all(token in gi for token in (".env", "secrets.toml", "__pycache__"))


def main() -> int:
    tree_hits = scan_working_tree()
    history_hits = scan_history()

    print("=" * 68)
    print("SECRET AUDIT")
    print("=" * 68)
    print(f"\nworking tree : {len(tree_hits)} finding(s)")
    for name, loc, red in tree_hits:
        print(f"  [HIT] {name}  {loc}  ->  {red}")
    print(f"git history  : {len(history_hits)} finding(s) across all commits")
    for name, loc, red in history_hits:
        print(f"  [HIT] {name}  {loc}  ->  {red}")

    print(f"\n.gitignore covers secrets: {gitignore_covers_secrets()}")
    example = ROOT / ".env.example"
    if example.exists():
        text = example.read_text(encoding="utf-8")
        print(f".env.example is placeholder-only: {_is_placeholder(text)}")

    total = len(tree_hits) + len(history_hits)
    print()
    if total:
        print(f"RESULT: {total} finding(s). DO NOT PUSH. Report before touching history.")
        return 1
    print("RESULT: clean. No credential-like strings in the tree or in any committed blob.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
