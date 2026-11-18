"""Transactional local replay protection; not an identity or payment service.

SQLite serializes consumers with BEGIN IMMEDIATE. An event, including a rejected
presentation, is committed before a successful outcome is returned. Database
errors propagate: callers must not treat a storage failure as verification.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from .attestation import (AttestationStore, AttestationOutcome, VerificationEvent,
                          VerificationContext, REPLAY)


class SQLiteAttestationStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS consumed_events (
                event_id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL,
                request_id TEXT NOT NULL, destination_digest TEXT NOT NULL,
                reference_version TEXT NOT NULL, outcome TEXT NOT NULL,
                consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def consume(self, event: VerificationEvent, context: VerificationContext,
                required: bool = True) -> AttestationOutcome:
        # Reuse the canonical binding checks rather than introducing a second policy.
        outcome = AttestationStore().consume(event, context, required)
        if not outcome.consumed:
            return outcome
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM consumed_events WHERE event_id=?',
                          (event.event_id,)).fetchone():
                db.rollback()
                return AttestationOutcome(False, REPLAY,
                    'Verification event already consumed; a new verification is required.', True)
            db.execute('''INSERT INTO consumed_events
                (event_id,vendor_id,request_id,destination_digest,reference_version,outcome)
                VALUES (?,?,?,?,?,?)''', (event.event_id, *event.binding, outcome.code))
            db.commit()
            return outcome
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def has_used(self, event_id: str) -> bool:
        with self._connect() as db:
            return db.execute('SELECT 1 FROM consumed_events WHERE event_id=?',
                              (event_id,)).fetchone() is not None

    def __len__(self) -> int:
        with self._connect() as db:
            return db.execute('SELECT COUNT(*) FROM consumed_events').fetchone()[0]
