# Phased implementation / 2026-10-24

This file distinguishes a tested **product foundation** from a finished production
financial service. The previous release implemented a synthetic demo workbench.
This release adds a separate authenticated team workspace without weakening the
original deterministic gate or claiming payment enforcement.

## The user journey

```text
Local operator bootstraps administrator
    ↓
Administrator creates analyst / verifier / auditor accounts
    ↓
Analyst inspects original request with selected extractor
    ↓
Save minimal case metadata + exact request/destination/reference binding
    ↓
Shared inbox → analyst or administrator assigns an independent verifier
    ↓
Assigned verifier re-inspects original request against current reference
    ├─ cannot complete verification → NEEDS_REINVESTIGATION → new investigation
    └─ current matching binding + callback/destination confirmation
         ↓
       authenticated attestation consumed once + VERIFIED workflow state
         ↓
       case history / auditor review / metadata export
```

**At no stage does VERIFIED turn HOLD into CLEAR or approve/execute payment.**

## Phase 1 — Identity and service-layer permissions

**Implemented and locally tested.**

- Local administrator bootstrap, refused after first setup; no default password.
- Salted scrypt password hashes, random server-side sessions stored as hashes.
- Eight-hour expiry, explicit logout, disable/revocation, password-change revocation.
- Per-account session list, individual revocation and sign-out-other-sessions.
- Optional organisation-wide `THREADGATE_REQUIRE_MFA=1` enforced in service methods;
  non-enrolled users retain access only to enrollment/account recovery functions.
- Five failed login attempts trigger a per-username 15-minute-window lockout.
- Administrator, analyst, verifier and auditor roles enforced in the service layer.
- Accounts can change their own password; admins create and disable users.
- Optional authenticator TOTP MFA: password-protected enrollment, code confirmation,
  enrollment expiry, replay rejection and session revocation on enable/disable.
- Trusted local-operator account recovery, including explicit lost-MFA reset.

Files: `src/threadgate/workspace.py`, `scripts/manage_workspace.py`, `app/product.py`.

**Not implemented:** enterprise IdP/SSO, email-based recovery, role changes,
multi-tenant isolation, distributed/IP rate limiting. Deploy behind restricted TLS
access. Local accounts and optional MFA are a foundation, not enterprise identity readiness.

## Phase 2 — Persistent case workflow

**Implemented and locally tested.**

- Shared, single-organisation inbox backed by SQLite on retained storage.
- Analyst-only case creation; analyst/administrator assignment to active verifier.
- OPEN → ASSIGNED → VERIFIED, or NEEDS_REINVESTIGATION.
- NO_CHANGE_IDENTIFIED records a CLEAR result without implying approval.
- Revision checks reject stale writes, including concurrent assignment attempts.
- Scoped idempotency keys make retrying Save exactly-once for that key.
- Search/state/assignment filters and stable pagination replace the UI list ceiling.
- Raw email/destination values omitted from persisted case payloads. Case reports,
  usernames, identifiers, control codes and destination digests remain sensitive.

**Not implemented:** ERP/mail ingestion, attachment storage, autonomous retention scheduling,
external reference transactions, organisation or per-case access partitions.
A local-operator, dry-run-first retention tool now archives old terminal-case
metadata while preserving replay tombstones and audit/actor history.
An analyst cannot edit a case's binding; a changed request requires a new case.

## Phase 3 — Independent attestation and audit

**Implemented and locally tested.**

- Assigned verifier must be distinct from the originating analyst.
- Original request is re-inspected by the server against the current record.
- Only a CURRENT reference with the exact stored context can be attested.
- Authenticated actor must match the verification event.
- Single-use event, case state/revision and audit entry commit transactionally.
- Rejected binding events are consumed; storage failure rolls the transaction back.
- Concurrent attestation attempts have one winner; no gate decision downgrade.
- Case-specific history readable by workspace members; global audit admin/auditor only.
- Snapshot-consistent case bundles include verification events and case audit entries.
- Online backup tool strips historical sessions from restored backups.

**Not claimed:** cryptographic proof of a callback, tamper-proof database, external
audit anchoring, payment authorisation, payment execution. Restoring an old backup
also rolls back consumed-event knowledge and needs external reconciliation in a
real financial system.

## Phase 4 — Integrated UI and flow

**Implemented and locally tested.**

- Default launcher opens authenticated `app/product.py`.
- Role-specific navigation, login, account security and team administration.
- Analyst investigation and evidence view → shared inbox → assignment → reinspection
  and verification → case timeline / auditor export.
- Midnight navy / violet / cyan styling, responsive layout.
- Previous Attack Lab and evaluation dashboard preserved as a **separate synthetic
  demo** with `python scripts/serve.py --demo`.

UI regressions exercise login gating and the analyst → assigned verifier → auditor
journey. An actual Chromium regression also tests the synthetic flow and JSON
download without a key (`scripts/browser_smoke.py`). Service tests additionally exercise permission bypass attempts directly.
Do not deploy the unauthenticated demo as a route for real-data workflows.

## Phase 5 — Delivery and validation

**Locally validated:** full suite, kill gate, credential scan, source ZIP verification.
The latest logs are in `docs/release-validation/`; the earlier product-phase
logs remain in `docs/product-validation/`. Original workbench screenshots are
in `docs/workbench/`. The package includes a size-enforcing ZIP builder and manifest. New one-command
release checks, clean-environment lockfile validation, opt-in live smoke and
live-report acceptance tooling are described in **docs/START_HERE.md**.

**Configuration created, not runtime-verified here:** non-root Dockerfile,
loopback-only Compose deployment, persistent volume, healthcheck, read-only root
filesystem and operational instructions in `deployment/README.md`. Docker was not
available for an image build/deployment in this environment. CI definition is
included but a successful remote GitHub Actions run is not claimed.

**Still blocked/external:** live Gemini evaluation needs an operator-provided key;
independent holdout authoring and accounts-payable user studies need participants;
production hosting, TLS/domain setup, backups on actual infrastructure, enterprise
identity integration, trusted vendor-master integration and independent security review
remain deployment/product work. No results, savings or field error rates invented.

## Run and review

```bash
pip install -r requirements.txt
python scripts/manage_workspace.py --username owner
python scripts/serve.py
# Optional, separate synthetic demo:
python scripts/serve.py --demo --port 8502
# Checks and source distribution:
python -m pytest
python scripts/kill_gate.py
python scripts/secret_scan.py
python scripts/package_release.py
```

This release is later work than the original hackathon prototype. It does not
retroactively change the historical build-window statement in PRIOR_WORK.md.
