"""Start the Streamlit demo without depending on a POSIX shell.

`scripts/serve.sh` does the same job on Linux and macOS, but it needs `bash` and
a `python3` on PATH, so on Windows it is not runnable at all - and the demo is
the part of this project a judge is most likely to actually open. This launcher
uses the interpreter that is running it (`sys.executable`), so a Windows venv
works with:

    python scripts/serve.py

It also reinstalls the declared dependencies first if Streamlit is missing, which
makes it safe to run in a fresh environment or a sandbox that does not persist
installed packages between sessions.

    python scripts/serve.py            # 0.0.0.0:8501
    python scripts/serve.py --port 9000
    python scripts/serve.py --no-install   # never touch the environment
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "streamlit_app.py"
REQUIREMENTS = ROOT / "requirements.txt"


def streamlit_available() -> bool:
    return importlib.util.find_spec("streamlit") is not None


def install_requirements() -> None:
    print("installing dependencies...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "-r", str(REQUIREMENTS)],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8501")))
    ap.add_argument("--address", default="0.0.0.0")
    ap.add_argument("--no-install", action="store_true",
                    help="fail instead of installing missing dependencies")
    args = ap.parse_args()

    if not streamlit_available():
        if args.no_install:
            print("streamlit is not installed; run: "
                  f"{Path(sys.executable).name} -m pip install -r requirements.txt",
                  file=sys.stderr)
            return 1
        install_requirements()

    cmd = [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.address", args.address,
        "--server.port", str(args.port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    print(f"starting: {' '.join(cmd)}", flush=True)
    # exec on POSIX so signals reach Streamlit directly; a child process on
    # Windows, where os.exec* is not a drop-in replacement.
    if os.name == "posix":
        os.execv(sys.executable, cmd)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
