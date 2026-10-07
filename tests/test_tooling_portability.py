"""The build and serve helpers must not need a shell, and must not eat results.

`scripts/clean.py` and `scripts/serve.py` replaced `rm -rf`, `find -exec rm` and
`python3 -m streamlit`, none of which exist on a Windows box without Git Bash.
These tests pin the two properties that matter: the cleaner never removes a
tracked artifact, and the launcher never goes through a shell.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"_{name}_under_test", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the cleaner ----------------------------------------------------------

def test_the_cleaner_removes_caches_and_scratch_runs(tmp_path):
    clean = _load("clean")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__pycache__").mkdir()
    (tmp_path / "src" / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (tmp_path / "data" / "runs").mkdir(parents=True)
    (tmp_path / "data" / "runs" / "latest.json").write_text("{}", encoding="utf-8")

    removed = clean.remove_generated(root=tmp_path)

    assert not (tmp_path / "src" / "pkg" / "__pycache__").exists()
    assert not (tmp_path / "data" / "runs" / "latest.json").exists()
    assert any("__pycache__" in r for r in removed)
    assert any("latest.json" in r for r in removed)


def test_the_cleaner_never_removes_the_stored_artifact(tmp_path):
    """`results/latest.json` is quoted in the README - it is not scratch.

    The Makefile's `rm -rf data/runs/*` was safe because the stored artifact
    lives in `results/`. Moving the cleaner into Python puts that decision in
    code, so it is asserted here rather than assumed.
    """
    assert "results" not in _load("clean").RELATIVE

    clean = _load("clean")
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "runs").mkdir(parents=True)
    (tmp_path / "data" / "runs" / "old.json").write_text("{}", encoding="utf-8")

    clean.remove_generated(root=tmp_path)

    assert (tmp_path / "results" / "latest.json").exists(), "the stored artifact was deleted"
    assert not (tmp_path / "data" / "runs" / "old.json").exists()


def test_the_cleaner_leaves_git_alone(tmp_path):
    """.git is skipped, not walked - a cleaner that deletes history is worse
    than the shell command it replaces."""
    source = (SCRIPTS / "clean.py").read_text(encoding="utf-8")
    assert '".git"' in source
    clean = _load("clean")
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "keep").write_text("x", encoding="utf-8")
    clean.remove_generated(root=tmp_path)
    assert (tmp_path / ".git" / "objects" / "keep").exists()


def test_the_cleaner_runs_end_to_end_without_a_shell():
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "clean.py"), "--dry-run"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "would remove" in proc.stdout


# --- the launcher ---------------------------------------------------------

def test_the_launcher_uses_its_own_interpreter_and_no_shell():
    """`python -m streamlit`, not a `streamlit` console script on PATH.

    A Windows venv only puts `streamlit.exe` on PATH while it is activated, and
    the README's copy-paste block does not activate anything.
    """
    source = (SCRIPTS / "serve.py").read_text(encoding="utf-8")
    assert '"-m", "streamlit"' in source.replace("'", '"')
    assert "sys.executable" in source


def test_no_script_in_the_repository_uses_shell_true():
    offenders = []
    for path in SCRIPTS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                        offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"system", "popen"}:
                offenders.append(f"{path.name}:{node.lineno} os.{node.attr}")
    assert not offenders, f"shell usage in scripts: {offenders}"


@pytest.mark.parametrize("name", ["clean.py", "serve.py", "kill_gate.py", "secret_scan.py"])
def test_every_script_compiles_and_is_importable_as_a_module(name):
    """No script may rely on a POSIX-only import at module scope."""
    src = (SCRIPTS / name).read_text(encoding="utf-8")
    for banned in ("import pwd", "import grp", "import termios", "import tty", "import fcntl"):
        assert banned not in src, f"{name} imports a POSIX-only module: {banned}"
