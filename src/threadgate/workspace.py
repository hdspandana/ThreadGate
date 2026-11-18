"""Small-team product foundation: local identity and transactional case workflow.

This service owns authorisation, not the UI. Every operation revalidates a
server-side session and current account status. SQLite is for one persistent host,
not a replicated multi-region deployment. Audit history is transactional, not an
externally anchored tamper-proof log. No operation executes or approves payment.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
import pyotp
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from .attestation import AttestationStore, VerificationContext
from .reporting import case_report
from .workspace_views import WorkspaceViews
from . import audit_integrity as integrity

ROLES = frozenset({'admin', 'analyst', 'verifier', 'auditor'})
SESSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW = 15 * 60
MAX_FAILURES = 5


class AccessDenied(Exception):
    pass


class Conflict(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def password_hash(password: str, salt: bytes | None = None) -> str:
    if not 14 <= len(password) <= 256:
        raise ValueError('Use a password of 14 to 256 characters.')
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return salt.hex() + ':' + digest.hex()


def password_matches(password: str, encoded: str) -> bool:
    if len(password) > 256:
        return False
    try:
        salt, _ = encoded.split(':')
        # Login accepts any candidate length without leaking password policy via exceptions.
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(encoded.split(':')[1], digest.hex())
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Workspace(WorkspaceViews):
    def __init__(self, path: str | Path, clock=time.time, require_mfa=None):
        self.path = str(path)
        self.clock = clock
        policy = os.getenv('THREADGATE_REQUIRE_MFA','0').strip().lower()
        if require_mfa is None and policy not in {'0','1','false','true'}:
            raise ValueError('THREADGATE_REQUIRE_MFA must be 0/1 or false/true.')
        self.require_mfa = policy in {'1','true'} if require_mfa is None else bool(require_mfa)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self._db() as db:
            old_version = db.execute('PRAGMA user_version').fetchone()[0]
            if old_version > 3:
                raise Conflict('Workspace schema is newer than this application. Do not downgrade.')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','analyst','verifier','auditor')),
                active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS user_mfa (
                username TEXT PRIMARY KEY REFERENCES users(username),
                secret TEXT NOT NULL DEFAULT '', last_counter INTEGER NOT NULL DEFAULT -1,
                pending TEXT NOT NULL DEFAULT '', pending_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username),
                expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_failures (
                username TEXT NOT NULL, occurred REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS failures_by_user ON login_failures(username,occurred);
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, created_by TEXT NOT NULL,
                title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                state TEXT NOT NULL, assigned_to TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
                report TEXT NOT NULL, context TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS submission_keys (
                username TEXT NOT NULL REFERENCES users(username),
                key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                case_id TEXT NOT NULL REFERENCES cases(id), PRIMARY KEY(username,key));
            CREATE INDEX IF NOT EXISTS cases_by_created ON cases(created_at,id);
            CREATE INDEX IF NOT EXISTS cases_by_assignment ON cases(assigned_to,state);
            CREATE TABLE IF NOT EXISTS workflow_events (
                event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                verifier TEXT NOT NULL, outcome TEXT NOT NULL, occurred REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, occurred REAL NOT NULL,
                actor TEXT NOT NULL, action TEXT NOT NULL, case_id TEXT NOT NULL,
                details TEXT NOT NULL);
            ''')
            integrity.initialise(db,allow_legacy=old_version<3)
            db.execute('PRAGMA user_version=3')

    @contextmanager
    def _db(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _audit(self, db, actor, action, case_id='', **details):
        integrity.verify(db)
        cursor = db.execute('INSERT INTO audit(occurred,actor,action,case_id,details) VALUES(?,?,?,?,?)',
                   (self.clock(), actor, action, case_id, json.dumps(details, sort_keys=True)))
        integrity.append(db,cursor.lastrowid)

    def _principal(self, db, token, roles=None, allow_enrolment=False):
        row = db.execute('''SELECT u.username,u.role FROM sessions s JOIN users u
            ON u.username=s.username WHERE s.token_hash=? AND s.expires>? AND u.active=1''',
            (_token_hash(token), self.clock())).fetchone()
        if row is None or (roles and row['role'] not in roles):
            raise AccessDenied('Session expired, account disabled, or permission denied.')
        if self.require_mfa and not allow_enrolment:
            factor = db.execute('SELECT secret FROM user_mfa WHERE username=?',(row['username'],)).fetchone()
            if not factor or not factor['secret']:
                raise AccessDenied('Organisation policy requires MFA enrollment before workspace access.')
        return Principal(row['username'], row['role'])

    def principal(self, token):
        with self._db() as db:
            return self._principal(db, token, allow_enrolment=True)

    def bootstrap(self, username, password):
        """Local operator-only first-account setup; never exposed as a public UI."""
        self._valid_username(username)
        encoded = password_hash(password)
        with self._db(write=True) as db:
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise Conflict('Workspace already initialised. Use an authenticated administrator.')
            db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)', (username,encoded,'admin'))
            self._audit(db, username, 'WORKSPACE_BOOTSTRAPPED')

    @staticmethod
    def _valid_username(username):
        if not (3 <= len(username) <= 80) or not all(c.isascii() and (c.isalnum() or c in '._-@') for c in username):
            raise ValueError('Username: 3–80 ASCII letters, digits, dot, underscore, hyphen or @.')

    def create_user(self, token, username, password, role):
        self._valid_username(username)
        if role not in ROLES:
            raise ValueError('Unknown role.')
        encoded = password_hash(password)
        with self._db(write=True) as db:
            p = self._principal(db, token, {'admin'})
            if db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                raise Conflict('Account already exists.')
            db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,encoded,role))
            self._audit(db,p.username,'USER_CREATED',username=username,role=role)

    def disable_user(self, token, username):
        with self._db(write=True) as db:
            p = self._principal(db, token, {'admin'})
            if p.username == username:
                raise Conflict('Administrators cannot disable their own account.')
            if not db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                raise Conflict('Account not found.')
            db.execute('UPDATE users SET active=0 WHERE username=?',(username,))
            db.execute('DELETE FROM sessions WHERE username=?',(username,))
            self._audit(db,p.username,'USER_DISABLED',username=username)

    def users(self, token):
        with self._db() as db:
            self._principal(db, token, {'admin'})
            return [dict(r) for r in db.execute('SELECT username,role,active FROM users ORDER BY username')]

    def login(self, username, password, otp=""):
        # Generic failure and a per-username window. A reverse proxy must additionally
        # limit source/IP requests; this is not a distributed abuse-prevention service.
        if len(username) > 80 or len(password) > 256:
            raise AccessDenied('Invalid credentials or temporarily locked account.')
        token = secrets.token_urlsafe(32)
        accepted = False
        with self._db(write=True) as db:
            now = self.clock()
            db.execute('DELETE FROM login_failures WHERE occurred<?',(now-LOGIN_WINDOW,))
            db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
            failures = db.execute('SELECT COUNT(*) FROM login_failures WHERE username=?',(username,)).fetchone()[0]
            user = db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            # Fixed dummy salt/hash keeps nonexistent-account password work comparable.
            encoded = user['password_hash'] if user else ('00'*16+':'+'00'*32)
            valid = password_matches(password, encoded)
            mfa = db.execute('SELECT * FROM user_mfa WHERE username=?',(username,)).fetchone()
            counter = int(now // 30)
            if mfa and mfa['secret']:
                valid = (valid and counter > mfa['last_counter'] and
                         pyotp.TOTP(mfa['secret']).verify(str(otp),for_time=now,valid_window=0))
            if failures < MAX_FAILURES and user and user['active'] and valid:
                if mfa and mfa['secret']:
                    db.execute('UPDATE user_mfa SET last_counter=? WHERE username=?',(counter,username))
                db.execute('DELETE FROM login_failures WHERE username=?',(username,))
                db.execute('INSERT INTO sessions VALUES(?,?,?)',(_token_hash(token),username,now+SESSION_SECONDS))
                self._audit(db,username,'LOGIN')
                accepted = True
            else:
                db.execute('INSERT INTO login_failures VALUES(?,?)',(username,now))
                self._audit(db,'anonymous','LOGIN_DENIED')
        if not accepted:
            raise AccessDenied('Invalid credentials or temporarily locked account.')
        return token

    def own_sessions(self, token):
        with self._db() as db:
            p = self._principal(db,token,allow_enrolment=True)
            rows = db.execute('SELECT token_hash,expires FROM sessions WHERE username=? AND expires>? ORDER BY expires DESC,token_hash',
                              (p.username,self.clock()))
            return [{'session_id':r['token_hash'],'expires_at':r['expires'],
                     'current':r['token_hash']==_token_hash(token)} for r in rows]

    def revoke_session(self, token, session_id):
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            deleted = db.execute('DELETE FROM sessions WHERE username=? AND token_hash=?',
                                 (p.username,session_id)).rowcount
            if not deleted:
                raise Conflict('Session not found for this account.')
            self._audit(db,p.username,'SESSION_REVOKED',current=session_id==_token_hash(token))

    def revoke_other_sessions(self, token):
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            deleted = db.execute('DELETE FROM sessions WHERE username=? AND token_hash<>?',
                                 (p.username,_token_hash(token))).rowcount
            self._audit(db,p.username,'OTHER_SESSIONS_REVOKED',count=deleted)
            return deleted

    def mfa_status(self, token):
        with self._db() as db:
            p = self._principal(db,token,allow_enrolment=True)
            row = db.execute('SELECT secret FROM user_mfa WHERE username=?',(p.username,)).fetchone()
            return bool(row and row['secret'])

    def begin_mfa(self, token, password):
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            row = db.execute('SELECT password_hash FROM users WHERE username=?',(p.username,)).fetchone()
            if not password_matches(password,row['password_hash']):
                raise AccessDenied('Current password is incorrect.')
            existing = db.execute('SELECT secret FROM user_mfa WHERE username=?',(p.username,)).fetchone()
            if existing and existing['secret']:
                raise Conflict('MFA already enabled.')
            secret = pyotp.random_base32()
            db.execute("""INSERT INTO user_mfa(username,pending,pending_until) VALUES(?,?,?)
                ON CONFLICT(username) DO UPDATE SET pending=excluded.pending,pending_until=excluded.pending_until""",
                (p.username,secret,self.clock()+600))
            self._audit(db,p.username,'MFA_ENROLMENT_STARTED')
            return secret

    def confirm_mfa(self, token, otp):
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            row = db.execute('SELECT * FROM user_mfa WHERE username=?',(p.username,)).fetchone()
            now = self.clock()
            if (not row or not row['pending'] or row['pending_until'] <= now or
                    not pyotp.TOTP(row['pending']).verify(str(otp),for_time=now,valid_window=0)):
                raise AccessDenied('Invalid or expired enrollment code.')
            db.execute("UPDATE user_mfa SET secret=pending,pending='',pending_until=0,last_counter=? WHERE username=?",
                       (int(now//30),p.username))
            db.execute('DELETE FROM sessions WHERE username=?',(p.username,))
            self._audit(db,p.username,'MFA_ENABLED')

    def disable_mfa(self, token, password, otp):
        if self.require_mfa:
            raise AccessDenied('Organisation policy does not permit disabling MFA.')
        with self._db(write=True) as db:
            p = self._principal(db,token)
            user = db.execute('SELECT password_hash FROM users WHERE username=?',(p.username,)).fetchone()
            row = db.execute('SELECT * FROM user_mfa WHERE username=?',(p.username,)).fetchone()
            now = self.clock()
            if (not row or not row['secret'] or not password_matches(password,user['password_hash']) or
                    int(now//30) <= row['last_counter'] or
                    not pyotp.TOTP(row['secret']).verify(str(otp),for_time=now,valid_window=0)):
                raise AccessDenied('Password or fresh authenticator code incorrect.')
            db.execute('DELETE FROM user_mfa WHERE username=?',(p.username,))
            db.execute('DELETE FROM sessions WHERE username=?',(p.username,))
            self._audit(db,p.username,'MFA_DISABLED')

    def change_password(self, token, old_password, new_password):
        encoded = password_hash(new_password)
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            row = db.execute('SELECT password_hash FROM users WHERE username=?',(p.username,)).fetchone()
            if not password_matches(old_password,row['password_hash']):
                raise AccessDenied('Current password is incorrect.')
            db.execute('UPDATE users SET password_hash=? WHERE username=?',(encoded,p.username))
            db.execute('DELETE FROM sessions WHERE username=?',(p.username,))
            self._audit(db,p.username,'PASSWORD_CHANGED')

    def logout(self, token):
        with self._db(write=True) as db:
            p = self._principal(db,token,allow_enrolment=True)
            db.execute('DELETE FROM sessions WHERE token_hash=?',(_token_hash(token),))
            self._audit(db,p.username,'LOGOUT')

    def submit(self, token, result, title='Payment-change investigation', submission_key=None):
        if not result.verification:
            raise ValueError('Pipeline verification context required.')
        c = result.verification
        context = asdict(c)
        report = case_report(result)
        report['limitations'] = 'Local authenticated account attestation is not proof of callback or payment authorisation. No payment execution.'
        # Store only minimal metadata. No raw email or bank destination values.
        if submission_key is not None and (not isinstance(submission_key,str) or not 16<=len(submission_key)<=128):
            raise ValueError('Submission key must be 16–128 characters.')
        fingerprint = hashlib.sha256(json.dumps({'context':context,'gate':result.decision.decision,
            'extractor':result.extractor,'title':str(title)[:120],
            'source_digest':hashlib.sha256(result.nt.text.encode()).hexdigest()},sort_keys=True).encode()).hexdigest()
        case_id = str(uuid.uuid4())
        with self._db(write=True) as db:
            p = self._principal(db,token,{'analyst'})
            if submission_key:
                previous = db.execute('SELECT fingerprint,case_id FROM submission_keys WHERE username=? AND key=?',(p.username,submission_key)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise Conflict('Submission key was already used for a different investigation.')
                    return previous['case_id']
            now = self.clock()
            db.execute('''INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (case_id,result.vendor_id,p.username,str(title)[:120],now,now,
                 'OPEN' if result.decision.attestation_required else 'NO_CHANGE_IDENTIFIED','',1,
                 json.dumps(report),json.dumps(context)))
            if submission_key:
                db.execute('INSERT INTO submission_keys VALUES(?,?,?,?)',(p.username,submission_key,fingerprint,case_id))
            self._audit(db,p.username,'CASE_SUBMITTED',case_id,gate_decision=result.decision.decision)
        return case_id

    def list_cases(self, token):
        with self._db() as db:
            self._principal(db,token)
            return [dict(r) for r in db.execute('SELECT id,title,vendor_id,created_by,state,assigned_to,revision,created_at FROM cases ORDER BY created_at DESC LIMIT 500')]

    def get_case(self, token, case_id):
        with self._db() as db:
            self._principal(db,token)
            row = db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not row:
                raise Conflict('Case not found.')
            out = dict(row)
            out['report'] = json.loads(out['report'])
            out['context'] = json.loads(out['context'])
            return out

    def assign(self, token, case_id, verifier, revision):
        with self._db(write=True) as db:
            p = self._principal(db,token,{'admin','analyst'})
            case = db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case or case['revision'] != revision or case['state'] not in {'OPEN','ASSIGNED'}:
                raise Conflict('Case changed or is not assignable. Refresh it.')
            if p.role == 'analyst' and case['created_by'] != p.username:
                raise AccessDenied('Only the originating analyst or administrator can assign.')
            user = db.execute("SELECT 1 FROM users WHERE username=? AND role='verifier' AND active=1",(verifier,)).fetchone()
            if not user or verifier == case['created_by']:
                raise Conflict('Choose a different, active verifier.')
            db.execute("UPDATE cases SET assigned_to=?,state='ASSIGNED',revision=revision+1,updated_at=? WHERE id=?",(verifier,self.clock(),case_id))
            self._audit(db,p.username,'CASE_ASSIGNED',case_id,verifier=verifier)

    def verify(self, token, case_id, revision, event, current_context, callback_confirmed,
               destination_confirmed, reference_current):
        """Accept authenticated attestation, not a payment approval.

        current_context and reference_current must be freshly derived by the trusted
        server pipeline/record adapter, never by a browser or the model alone.
        The browser UI exposes neither service arguments nor a verification API.
        """
        outcome = None
        with self._db(write=True) as db:
            p = self._principal(db,token,{'verifier'})
            case = db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case or case['revision'] != revision or case['state'] != 'ASSIGNED':
                raise Conflict('Case changed or is not awaiting verification. Refresh it.')
            if case['assigned_to'] != p.username or case['created_by'] == p.username:
                raise AccessDenied('Only the assigned independent verifier may attest.')
            if not (callback_confirmed and destination_confirmed):
                raise Conflict('Both verification steps must be explicitly confirmed.')
            stored = VerificationContext(**json.loads(case['context']))
            if (not reference_current or stored != current_context or
                    stored.reference_version in {'', 'unversioned'}):
                raise Conflict('Reference or destination changed/degraded. Submit a new investigation.')
            if not stored.request_digest or not stored.reference_digest:
                raise Conflict('Legacy case lacks content bindings; submit a fresh investigation.')
            if event.attested_by != p.username:
                raise AccessDenied('Verification actor must match the authenticated account.')
            # Canonical binding validator. All writes, including replay consumption,
            # state transition and audit entry, commit together.
            outcome = AttestationStore().consume(event,stored)
            if db.execute('SELECT 1 FROM workflow_events WHERE event_id=?',(event.event_id,)).fetchone():
                raise Conflict('Verification event already used.')
            if not outcome.consumed:
                raise Conflict(outcome.message)
            db.execute('INSERT INTO workflow_events VALUES(?,?,?,?,?)',
                (event.event_id,case_id,p.username,outcome.code,self.clock()))
            if outcome.accepted:
                db.execute("UPDATE cases SET state='VERIFIED',revision=revision+1,updated_at=? WHERE id=?",(self.clock(),case_id))
            binding_hash = hashlib.sha256(json.dumps(asdict(stored),sort_keys=True).encode()).hexdigest()
            db.execute('INSERT INTO verification_receipts VALUES(?,?,?,?,?,?,?,?,?)',
                (event.event_id,revision,case['created_by'],case['assigned_to'],binding_hash,
                 stored.request_digest,stored.reference_digest,stored.reference_version,self.clock()))
            self._audit(db,p.username,'VERIFICATION_ACCEPTED' if outcome.accepted else 'VERIFICATION_REJECTED',case_id,
                code=outcome.code,event_id=event.event_id,receipt_digest=integrity.receipt_digest(db,event.event_id))
        return outcome

    def return_for_reinvestigation(self, token, case_id, revision):
        with self._db(write=True) as db:
            p = self._principal(db,token,{'verifier'})
            case = db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case or case['revision'] != revision or case['state'] != 'ASSIGNED':
                raise Conflict('Case changed or is not awaiting verification.')
            if case['assigned_to'] != p.username or case['created_by'] == p.username:
                raise AccessDenied('Only the assigned independent verifier may return this case.')
            db.execute("UPDATE cases SET state='NEEDS_REINVESTIGATION',revision=revision+1,updated_at=? WHERE id=?",(self.clock(),case_id))
            self._audit(db,p.username,'RETURNED_FOR_REINVESTIGATION',case_id)

    def audit_integrity(self, token):
        with self._db() as db:
            db.execute('BEGIN')
            self._principal(db,token,{'admin','auditor'})
            return integrity.verify_all(db)

    def audit(self, token, case_id=None):
        with self._db() as db:
            p = self._principal(db,token)
            integrity.verify_all(db)
            # All members may read case-specific history. Workspace-wide activity is privileged.
            if case_id is None and p.role not in {'admin','auditor'}:
                raise AccessDenied('Workspace audit requires administrator or auditor role.')
            rows = db.execute('SELECT * FROM audit WHERE case_id=? ORDER BY seq',(case_id,)) if case_id else db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 1000')
            return [dict(row) for row in rows]
