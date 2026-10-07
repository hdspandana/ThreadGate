"""Remove generated artifacts - with no shell and no GNU utilities.

The Makefile used to do this with `rm -rf` and
`find . -name __pycache__ -type d -exec rm -rf {} +`, neither of which exists on
Windows. `python scripts/clean.py` does the same work portably, and it is
importable, so a test can call `remove_generated()` and assert what it removes
instead of asserting that a shell command was typed correctly.

It never touches tracked files. Everything it removes is regenerable: caches,
editor droppings, and the scratch run artifacts under `data/runs/`.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories removed wholesale, wherever they are found.
DIR_NAMES = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")

# Paths removed relative to the repository root. `data/runs/` is scratch output
# from local runs; `results/` is NOT in this list - it holds the stored
# evaluation artifact the documentation cites.
RELATIVE = ("data/runs",)

# File suffixes removed wherever they are found.
SUFFIXES = (".pyc", ".pyo")


def remove_generated(root: Path = ROOT, dry_run: bool = False) -> list[str]:
    """Delete generated files and directories under `root`. Returns what went."""
    removed: list[str] = []

    for base, dirnames, filenames in root.walk():
        if base == root / ".git":
            dirnames[:] = []
            continue

        for name in list(dirnames):
            if name in DIR_NAMES:
                target = base / name
                removed.append(str(target.relative_to(root)))
                if not dry_run:
                    shutil.rmtree(target, ignore_errors=True)
                dirnames.remove(name)

        for name in filenames:
            if name.endswith(SUFFIXES):
                target = base / name
                removed.append(str(target.relative_to(root)))
                if not dry_run:
                    target.unlink(missing_ok=True)

    for rel in RELATIVE:
        target = root / rel
        if not target.is_dir():
            continue
        for child in sorted(target.iterdir()):
            if child.name == ".gitkeep":
                continue
            removed.append(str(child.relative_to(root)))
            if not dry_run:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)

    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be removed and change nothing")
    args = ap.parse_args()

    removed = remove_generated(dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    print(f"{verb} {len(removed)} generated path(s)")
    for path in removed[:20]:
        print(f"  {path}")
    if len(removed) > 20:
        print(f"  ... and {len(removed) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
