"""Consistent local SQLite backup, using the online backup API.

The output includes password hashes and active MFA seeds: store it privately.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.config import load_environment
from threadgate.audit_integrity import verify_all


def main():
    load_environment(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT/'data/runs/workspace.sqlite3')))
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    source,target = Path(args.db).resolve(),Path(args.output).resolve()
    if not source.is_file() or source==target or target.exists():
        raise SystemExit('Source must exist; output must be a different, new private file.')
    target.parent.mkdir(parents=True,exist_ok=True)
    # Create privately before opening SQLite; never overwrite an existing file.
    fd = os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        src = sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        src.row_factory=sqlite3.Row
        dst = sqlite3.connect(target)
        dst.row_factory=sqlite3.Row
        try:
            src.execute('BEGIN')
            schema=src.execute('PRAGMA user_version').fetchone()[0]
            if schema>=3:verify_all(src)
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            # A restored backup must not reactivate historical sessions.
            dst.execute('DELETE FROM sessions')
            if dst.execute("SELECT 1 FROM sqlite_master WHERE name='user_mfa'").fetchone():
                dst.execute("UPDATE user_mfa SET pending='',pending_until=0")
            if schema>=3:verify_all(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()
    except Exception:
        target.unlink(missing_ok=True)
        print('Backup failed storage/integrity checks; no backup retained.')
        return 1
    if schema<3:print('Legacy schema: audit chain authenticity/integrity was not available to check.')
    print('Private backup created; sessions stripped. Retain on encrypted, access-controlled storage.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
