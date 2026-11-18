"""Local operator bootstrap: python scripts/manage_workspace.py --username owner

Prompts for a password without accepting it in shell arguments or environment.
Subsequent accounts are created by an authenticated administrator in the UI.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from threadgate.workspace import Workspace
from threadgate.config import load_environment


def main():
    load_environment(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--db', default=os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT / 'data/runs/workspace.sqlite3')))
    args = parser.parse_args()
    password = getpass.getpass('Initial administrator password (14+ characters): ')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    try:
        Workspace(args.db).bootstrap(args.username,password)
    except Exception as exc:
        raise SystemExit(str(exc)) from None
    print('Workspace initialised. Sign in and create separate analyst and verifier accounts.')


if __name__ == '__main__':
    main()
