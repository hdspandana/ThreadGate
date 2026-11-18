"""Read models for the single-organisation workspace.

Mixed into Workspace so all reads go through the same session/policy checks.
No raw email, destination values, MFA seeds or bearer tokens are exported.
"""
import json
from .audit_integrity import verify_all
from datetime import datetime, timezone

STATES = ('OPEN','ASSIGNED','VERIFIED','NEEDS_REINVESTIGATION','NO_CHANGE_IDENTIFIED','ARCHIVED')


class WorkspaceViews:
    def search_cases(self, token, query='', state='', assigned_to='', page=1, page_size=25):
        if (not isinstance(page,int) or isinstance(page,bool) or not 1<=page<=100000 or
                not isinstance(page_size,int) or isinstance(page_size,bool) or not 1<=page_size<=100):
            raise ValueError('Page must be 1–100000 and page size 1–100.')
        if len(query)>200 or (state and state not in STATES) or len(assigned_to)>80:
            raise ValueError('Invalid inbox filters.')
        clauses,values=[],[]
        if query:
            pattern='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            clauses.append("(id LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' OR vendor_id LIKE ? ESCAPE '\\' OR created_by LIKE ? ESCAPE '\\')")
            values.extend([pattern]*4)
        if state:
            clauses.append('state=?');values.append(state)
        if assigned_to:
            clauses.append('assigned_to=?');values.append(assigned_to)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self._db() as db:
            db.execute('BEGIN')
            self._principal(db,token)
            total=db.execute('SELECT COUNT(*) FROM cases'+where,values).fetchone()[0]
            rows=db.execute('''SELECT id,title,vendor_id,created_by,state,assigned_to,revision,created_at
                FROM cases'''+where+' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                [*values,page_size,(page-1)*page_size])
            items=[dict(r) for r in rows]
        return {'items':items,'total':total,'page':page,'page_size':page_size,
                'pages':max(1,(total+page_size-1)//page_size)}

    def case_counts(self, token):
        with self._db() as db:
            self._principal(db,token)
            counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM cases GROUP BY state')}
        return {state:counts.get(state,0) for state in STATES}

    def export_case(self, token, case_id):
        # One read transaction gives the report, events and audit the same snapshot.
        with self._db() as db:
            db.execute('BEGIN')
            self._principal(db,token)
            case=db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case:
                # Local import avoids a module-initialisation cycle.
                from .workspace import Conflict
                raise Conflict('Case not found.')
            audit_status=verify_all(db)
            receipts=[dict(r) for r in db.execute('SELECT event_id,case_revision,analyst,assigned_verifier,reference_version,recorded_at FROM verification_receipts WHERE event_id IN (SELECT event_id FROM workflow_events WHERE case_id=?)',(case_id,))]
            events=[dict(r) for r in db.execute('SELECT event_id,verifier,outcome,occurred FROM workflow_events WHERE case_id=? ORDER BY occurred,event_id',(case_id,))]
            audit=[dict(r) for r in db.execute('SELECT seq,occurred,actor,action,details FROM audit WHERE case_id=? ORDER BY seq',(case_id,))]
            return {'format':'threadgate.case-bundle.v1','exported_at':datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(),
                'case':{k:case[k] for k in ('id','title','vendor_id','created_by','assigned_to','state','revision','created_at','updated_at')},
                'report':json.loads(case['report']),'verification_events':events,'verification_receipts':receipts,'audit':audit,'audit_integrity':audit_status,
                'limitations':'Snapshot of authenticated statements, not proof of callback, immutable audit or payment authorisation.',
                'privacy':'Contains usernames, case/event identifiers and timestamps. Source emails, destination values/digests and authentication secrets omitted.'}
