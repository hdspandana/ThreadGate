"""Read-only local audit/receipt integrity check. Does not attest external authenticity."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.audit_integrity import verify_all


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True)
    args=parser.parse_args(argv)
    try:
        db=sqlite3.connect(Path(args.db).resolve().as_uri()+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        with db:
            db.execute('BEGIN')
            result=verify_all(db)
        db.close()
    except Exception as exc:
        print(json.dumps({'status':'FAIL','error_type':type(exc).__name__,'message':'Integrity check failed or schema unavailable; do not rely on this audit.'}))
        return 1
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
