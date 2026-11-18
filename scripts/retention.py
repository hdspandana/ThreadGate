"""Local-operator metadata retention. Dry-run by default; never deletes replay tombstones.

Archive only terminal cases older than the chosen policy. Keep audit/actor history,
event identifiers and the original gate decision; this is not full identity erasure.
Back up first and approve your organisation's policy before --apply.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.config import load_environment
from threadgate.workspace import Workspace
TERMINAL=('VERIFIED','NEEDS_REINVESTIGATION','NO_CHANGE_IDENTIFIED')


def archive_terminal(service,days,apply=False):
    if not 1<=days<=36500:
        raise ValueError('Retention days must be 1–36500.')
    with service._db(write=apply) as db:
        rows=db.execute('''SELECT id,report FROM cases WHERE state IN (?,?,?) AND updated_at<?''',
                        (*TERMINAL,service.clock()-days*86400)).fetchall()
        if apply:
            for row in rows:
                report=json.loads(row['report'])
                minimal={'format':'threadgate.archived-case.v1','gate_decision':report['gate_decision'],
                         'workflow_status':'ARCHIVED','privacy':'Investigation metadata removed by local retention policy; audit actors/event tombstones retained.'}
                db.execute("""UPDATE cases SET state='ARCHIVED',vendor_id='',assigned_to='',
                    title='Archived investigation',report=?,context='{}',revision=revision+1,updated_at=? WHERE id=?""",
                    (json.dumps(minimal),service.clock(),row['id']))
                service._audit(db,'local-operator','CASE_METADATA_ARCHIVED',row['id'],retention_days=days)
    return {'mode':'APPLIED' if apply else 'DRY_RUN','eligible_cases':len(rows),
            'retention_days':days,'replay_tombstones_deleted':False,'audit_actors_deleted':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    load_environment(ROOT)
    path=Path(os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT/'data/runs/workspace.sqlite3')))
    if not path.is_file():
        print('Workspace does not exist; nothing changed.')
        return 1
    try:
        print(json.dumps(archive_terminal(Workspace(path),args.days,args.apply),indent=2))
    except Exception:
        print('Retention failed. No successful archival is claimed. Inspect storage and policy configuration.')
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
