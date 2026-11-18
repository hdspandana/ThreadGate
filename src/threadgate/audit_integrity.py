"""Local audit hash-chain checking, NOT an externally protected trust anchor.

Detects altered rows, broken links, missing chain entries and truncation while the
saved local head remains intact. A privileged database writer can recompute the
entire chain/head. Initial migration trusts existing audit rows as its baseline.
"""
import hashlib
import json

GENESIS = '0' * 64


class AuditIntegrityError(RuntimeError):
    pass


def event_digest(row, previous):
    canonical = json.dumps({'previous':previous,'event':dict(row)},sort_keys=True,
                           separators=(',', ':'),ensure_ascii=True,allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def initialise(db, allow_legacy=True):
    db.executescript('''BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS audit_chain(
        seq INTEGER PRIMARY KEY REFERENCES audit(seq),previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_head(id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS verification_receipts(
            event_id TEXT PRIMARY KEY REFERENCES workflow_events(event_id),
            case_revision INTEGER NOT NULL,analyst TEXT NOT NULL,assigned_verifier TEXT NOT NULL,
            context_hash TEXT NOT NULL,request_digest TEXT NOT NULL,reference_digest TEXT NOT NULL,
            reference_version TEXT NOT NULL,recorded_at REAL NOT NULL);''')
    if db.execute('SELECT 1 FROM audit_head WHERE id=1').fetchone():
        return
    # A schema-3 database must never be re-baselined after a missing head.
    if not allow_legacy or db.execute('SELECT COUNT(*) FROM audit_chain').fetchone()[0]:
        raise AuditIntegrityError('Audit head missing; restore a trusted backup, do not reinitialise.')
    previous,seq=GENESIS,0
    for row in db.execute('SELECT * FROM audit ORDER BY seq').fetchall():
        digest=event_digest(row,previous)
        db.execute('INSERT INTO audit_chain VALUES(?,?,?)',(row['seq'],previous,digest))
        previous,seq=digest,row['seq']
    db.execute('INSERT INTO audit_head VALUES(1,?,?)',(seq,previous))


def verify(db):
    head=db.execute('SELECT seq,hash FROM audit_head WHERE id=1').fetchone()
    if not head:
        raise AuditIntegrityError('Audit head missing.')
    previous,seq,count=GENESIS,0,0
    for row in db.execute('SELECT * FROM audit ORDER BY seq'):
        link=db.execute('SELECT previous_hash,event_hash FROM audit_chain WHERE seq=?',(row['seq'],)).fetchone()
        digest=event_digest(row,previous)
        if not link or link['previous_hash']!=previous or link['event_hash']!=digest:
            raise AuditIntegrityError('Audit event/link mismatch at sequence '+str(row['seq']))
        previous,seq,count=digest,row['seq'],count+1
    if head['seq']!=seq or head['hash']!=previous or db.execute('SELECT COUNT(*) FROM audit_chain').fetchone()[0]!=count:
        raise AuditIntegrityError('Audit truncation, deletion or unexpected chain entries.')
    return {'status':'PASS','events':count,'head_seq':seq,'head_hash':previous,
            'trust':'Local head only; whole-store rewriting with a recomputed head is not detected.'}


def append(db, seq):
    # Verify before extending; do not bless an already damaged chain.
    # The new audit row is not yet chained, so check the old prefix/head explicitly.
    head=db.execute('SELECT seq,hash FROM audit_head WHERE id=1').fetchone()
    row=db.execute('SELECT * FROM audit WHERE seq=?',(seq,)).fetchone()
    if not head or not row or seq<=head['seq']:
        raise AuditIntegrityError('Invalid audit append state.')
    previous=head['hash']
    digest=event_digest(row,previous)
    db.execute('INSERT INTO audit_chain VALUES(?,?,?)',(seq,previous,digest))
    db.execute('UPDATE audit_head SET seq=?,hash=? WHERE id=1',(seq,digest))


def receipt_digest(db,event_id):
    receipt=db.execute('SELECT * FROM verification_receipts WHERE event_id=?',(event_id,)).fetchone()
    event=db.execute('SELECT * FROM workflow_events WHERE event_id=?',(event_id,)).fetchone()
    if not receipt or not event:
        raise AuditIntegrityError('Verification receipt/event missing.')
    return hashlib.sha256(json.dumps({'receipt':dict(receipt),'event':dict(event)},sort_keys=True,
                                    separators=(',', ':'),allow_nan=False).encode()).hexdigest()


def verify_all(db):
    report=verify(db)
    anchored=set()
    for row in db.execute("SELECT details FROM audit WHERE action IN ('VERIFICATION_ACCEPTED','VERIFICATION_REJECTED')"):
        details=json.loads(row['details'])
        if 'receipt_digest' in details:
            event_id=details.get('event_id','')
            if receipt_digest(db,event_id)!=details['receipt_digest']:
                raise AuditIntegrityError('Verification receipt content mismatch.')
            anchored.add(event_id)
    receipts={r[0] for r in db.execute('SELECT event_id FROM verification_receipts')}
    if receipts!=anchored:
        raise AuditIntegrityError('Unanchored verification receipt.')
    report['legacy_events_without_receipts']=db.execute('SELECT COUNT(*) FROM workflow_events').fetchone()[0]-len(receipts)
    return report
