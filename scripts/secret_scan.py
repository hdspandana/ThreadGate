"""Secret audit for the working tree and the full git history.

Run this before pushing anything public. A key committed three commits ago and
deleted two commits ago is still in the history of a public repository.

    python scripts/secret_scan.py

Exit codes, because "could not check" is not the same as "checked and clean":

    0  tree clean, history clean          -> RESULT: clean
    1  something matched                  -> DO NOT PUSH
    3  tree clean, history not readable   -> no .git (the submitted ZIP) or no
                                             git on PATH (a Windows box without
                                             Git for Windows). Run it from a
                                             clone for the full check.

If anything matches, do not push, and do not rewrite history in a hurry -
report it first.
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
    # Fine-grained personal access tokens use a different prefix from the
    # classic ghp_/gho_/ghs_ forms, and are the ones a push workflow mints.
    ("github-fine-grained-token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("stripe-live-key", re.compile(r"[sr]k_live_[A-Za-z0-9]{20,}")),
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


def _git(args: list[str]) -> tuple[bool, str, str]:
    """Run a read-only git command. Returns (ok, stdout, reason).

    `reason` is empty on success, otherwise one of `git-not-found` (no git
    binary on PATH - the normal case on a Windows box without Git for Windows)
    or `no-repository` (git is installed, but this directory is not a
    repository - the normal case for the submitted ZIP, which has no .git).
    """
    try:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        return False, "", "git-not-found"
    except OSError:  # pragma: no cover - unreadable / not executable
        return False, "", "git-not-found"
    if proc.returncode != 0:
        return False, "", "no-repository"
    return True, proc.stdout, ""


def _git_bytes(args: list[str]) -> tuple[bool, bytes, str]:
    """As `_git`, for blobs that may not be text (screenshots, for instance)."""
    try:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    except (FileNotFoundError, OSError):
        return False, b"", "git-not-found"
    if proc.returncode != 0:
        return False, b"", "no-repository"
    return True, proc.stdout, ""


def scan_history() -> tuple[list[tuple[str, str, str]], str]:
    """Every blob that has ever been committed, in every commit.

    Returns the findings *and* whether the history was actually read. The
    earlier version returned `[("git-error", ...)]` when `git rev-list` failed,
    which counted as a finding: running the documented command from the
    submitted ZIP (no `.git` directory) printed "1 finding(s). DO NOT PUSH."
    while `docs/DEVPOST.md` told the reader it must print `RESULT: clean`.
    An unreadable history is not a leak, and it is not a clean bill of health
    either - it is a third state, reported as one.
    """
    hits: list[tuple[str, str, str]] = []
    ok, out, reason = _git(["rev-list", "--all"])
    if not ok:
        return [], reason
    revs = out.split()
    seen: set[str] = set()
    for rev in revs:
        ok, listing_out, reason = _git(["ls-tree", "-r", rev])
        if not ok:
            return [], reason
        for line in listing_out.splitlines():
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
            ok, raw, reason = _git_bytes(["cat-file", "-p", blob])
            if not ok:
                return [], reason
            try:
                blob_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits.extend(scan_text(blob_text, f"{rev[:8]}:{name}"))
    return hits, "scanned"


def gitignore_covers_secrets() -> bool:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    return all(token in gi for token in (".env", "secrets.toml", "__pycache__"))


HISTORY_REASONS = {
    "no-repository": "not a git repository, so there is no history to read",
    "git-not-found": "git is not installed or not on PATH",
}


def main() -> int:
    tree_hits = scan_working_tree()
    history_hits, history_status = scan_history()
    history_scanned = history_status == "scanned"

    print("=" * 68)
    print("SECRET AUDIT")
    print("=" * 68)
    print(f"\nworking tree : {len(tree_hits)} finding(s)")
    for name, loc, red in tree_hits:
        print(f"  [HIT] {name}  {loc}  ->  {red}")
    if history_scanned:
        print(f"git history  : {len(history_hits)} finding(s) across all commits")
    else:
        print(f"git history  : NOT SCANNED - {HISTORY_REASONS.get(history_status, history_status)}")
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
    if not history_scanned:
        # A clean tree is not the same claim as a clean history. Saying so
        # plainly is the point: three states, three exit codes.
        print(
            "RESULT: tree clean, history NOT SCANNED "
            f"({HISTORY_REASONS.get(history_status, history_status)}). "
            "Run this from a clone of the repository for the full check."
        )
        return 3
    print("RESULT: clean. No credential-like strings in the tree or in any committed blob.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
