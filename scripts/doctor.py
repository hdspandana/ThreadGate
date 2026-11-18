"""Local preflight. No API request, no credentials printed."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.config import load_environment,key_configured,check_settings


def inspect(require_key=False):
    load_environment(ROOT)
    failures = check_settings()
    versions = {}
    for name in ['streamlit','pydantic','google-genai','python-dotenv','pytest','rich','pyotp']:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            failures.append('Missing dependency: '+name)
    # Probe a separate disposable database, not the user's live workspace.
    try:
        parent = Path(os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT/'data/runs/workspace.sqlite3'))).parent
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            with closing(sqlite3.connect(str(Path(folder)/'probe.db'))) as db:
                with db:
                    db.execute('CREATE TABLE probe(id INTEGER PRIMARY KEY)')
                    db.execute('INSERT INTO probe VALUES(1)')
                    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    except Exception:
        failures.append('Workspace parent directory is not writable or SQLite probe failed.')
    configured = key_configured()
    if require_key and not configured:
        failures.append('A non-placeholder GEMINI_API_KEY or GOOGLE_API_KEY is required.')
    return {'status':'FAIL' if failures else 'PASS','python':sys.version.split()[0],
            'dependencies':versions,'key_configured':configured,
            'model':os.getenv('THREADGATE_MODEL','gemini-2.5-flash'),
            'live_api_tested':False,'mfa_policy_required':os.getenv('THREADGATE_REQUIRE_MFA','0').lower() in {'1','true'},'errors':failures,
            'warnings':['No network request made. Live model and actual hosting still require validation.']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-key',action='store_true')
    args=parser.parse_args(argv)
    report=inspect(args.require_key)
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
