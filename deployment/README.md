# Team workspace deployment

## Local setup (recommended first)

```bash
pip install -r requirements.lock
python scripts/manage_workspace.py --username owner
python scripts/serve.py
```

Bootstrap prompts privately for an administrator password (14–256 characters).
There is no default password or public signup. Bootstrap refuses to run after
initialisation. Then:

1. Sign in as administrator. Create separate `analyst`, `verifier`, `auditor` accounts.
2. Give initial credentials through a secure channel. Users can change passwords
   under My account; changing a password revokes all that user's sessions.
3. Analyst: New investigation → inspect → save to shared inbox.
4. Analyst or administrator: open case → assign active verifier username.
5. Assigned verifier: open case → re-inspect original request against current
   reference → preview current destination/evidence → confirm callback and exact destination →
   re-inspect and record attestation. Live Gemini performs another API call at final
   attestation; a changed interpretation of the destination is rejected.
6. Auditor: inspect case history or Workspace audit, export metadata as needed.

Run `python scripts/serve.py --demo` for the separate unauthenticated **synthetic**
Attack Lab and demo workbench. Do not expose the demo on the same public service
as real data. The default launcher runs the authenticated product UI.

## Container configuration

```bash
docker compose build
docker compose run --rm app python scripts/manage_workspace.py --username owner
docker compose up -d
```

Compose binds the service to **host loopback only**. Connect at
http://localhost:8501 locally. Before any remote access, put an authenticated,
rate-limiting TLS reverse proxy in front, configure WebSocket proxying, and restrict
allowed origins. Keep Streamlit's CORS and XSRF protection enabled. The app has
server-side roles, but no organisation federation or SSO; optional local TOTP MFA is available.

The container runs non-root, has a read-only application filesystem, drops Linux
capabilities and writes workspace data to the named `/data` volume. No image
contains credentials. Keep `.env` and Streamlit secrets out of build contexts.
Containers and compose files are provided but were not built or deployed in this
sandbox; test them on your actual host before relying on them.

## Configuration

- `THREADGATE_WORKSPACE_DB`: database path; default `data/runs/workspace.sqlite3`.
- `GEMINI_API_KEY`: optional, needed only for actual Gemini interpretation.
- `THREADGATE_MODEL`: optional model selection.
- `THREADGATE_DB`: separate synthetic-demo consumed-event database.

The default offline engine is a deterministic test double. Do not label it AI
performance. No successful live Gemini evaluation is bundled. After adding your key, use
`python scripts/live_check.py`, then `python eval/run_eval.py --require-gemini`
and `python scripts/check_live_report.py`. See docs/START_HERE.md for the full flow.

## Backups and recovery

```bash
python scripts/backup_workspace.py --output data/runs/private.sqlite3.backup
```

The online SQLite backup is consistent and strips sessions so restored backups
cannot reactivate those historical logins. It contains password hashes, usernames,
audit records and case metadata; encrypt and restrict it. The script creates the
output privately (0600 on POSIX) and refuses to overwrite files. On Windows apply
appropriate filesystem ACLs as well.

For recovery, stop **all** writers, copy the backup to the configured database
location, preserve owner permissions, then restart. Users must sign in again.
Do not restore into a live service. Test recovery regularly. Old backups also
restore historical consumed-event state: a rollback cannot provide protection
against events consumed after the backup. In a real financial system, reconcile
against an external authoritative event ledger before resuming operations.
Never use `docker compose down -v` unless you intend to delete workspace data.

## Security/operational boundary

- One trusted organisation shares all case metadata. There is no tenant isolation.
- SQLite is for a single persistent host, not a distributed cluster.
- Passwords use salted scrypt; session tokens are random and only their hashes
  are persisted. Sessions expire after eight hours, without sliding renewal.
- Five failed logins lock a username for the 15-minute failure window. Add IP/
  network throttling upstream; local account lockouts can themselves be abused.
- Account disable and password change invalidate sessions. Admin user provisioning
  is trusted; no privileged-admin adversary protection is claimed.
- Audit entries commit with case transitions; they are not externally anchored,
  immutable or proof against a database administrator.
- Cases persist minimal metadata and hashed bindings, not raw emails or destination
  values. Metadata can still be sensitive. Set retention and deletion policies
  for your deployment; autonomous scheduling/full identity erasure is not implemented.
  The local retention command can archive old terminal-case metadata on an approved schedule.
- For pasted requests, the verifier must independently supply the original body;
  the server re-runs the same extractor. If the exact binding cannot be reproduced,
  verification is refused. This is intentional, not silent repair.
- `CURRENT` reference state and matching binding are prerequisites. The local
  synthetic vendor master is not a live ERP or bank authority. Concurrent external
  reference management/transactions are outside this single-host foundation.
- `VERIFIED` records an authenticated user's attestation. It is not payment approval,
  proof of a phone call, an automatic vendor-master update or a payment release.

Before real financial use: independent security review, enterprise identity integration,
trusted vendor-master integration, retention controls, monitored durable hosting,
backup/restore exercises, external audit anchoring and actual model evaluation.

## Public HTTPS option

Set a real `THREADGATE_DOMAIN` in your private `.env`, point its DNS to the
server and allow inbound TCP 80/443. Then:

```bash
docker compose -f compose.yaml -f deployment/compose.public.yaml config --quiet
docker compose -f compose.yaml -f deployment/compose.public.yaml up -d --build
```

The public overlay fixes `THREADGATE_REQUIRE_MFA` to `1`, even if the local `.env`
template contains `0`. Enrol administrator MFA before using this overlay. Use
the base local compose file only for optional-MFA local demonstrations.

Caddy terminates HTTPS and proxies WebSockets. Its certificate state is persisted
in named volumes. It is not an IP rate limiter; add infrastructure/network abuse
controls before a wide public rollout. The app still binds directly only to
loopback on the host. No domain or ACME deployment was tested in this sandbox.

## Optional account MFA and operator recovery

My account offers authenticator enrollment with a private manual secret or
provisioning URI. Complete setup within ten minutes; enabling/disabling revokes
sessions. Each accepted code is single-use; wait for the next 30-second step
when a fresh code is required after login. Keep server/authenticator clocks synced.
MFA is optional by default. `THREADGATE_REQUIRE_MFA=1` enables organisation-wide
service-layer enforcement; non-enrolled users can access only their account/enrollment
functions until setup is complete. Administrators should enrol before enabling it. Active TOTP
seeds must be available to verify codes; they are stored in the private SQLite
database and included in backups. Use encrypted disks/backups and strict file access.

For a lost password or authenticator, stop the app and use the trusted local
operator command (not a public web recovery endpoint):

```bash
python scripts/recover_account.py --username owner --reset-mfa
```

It prompts privately for a new password, revokes sessions, clears lockout,
optionally clears MFA and records an operator-recovery audit entry. Only a trusted
OS/database operator should have this access. Restart, sign in, then re-enrol MFA.

## Policy-driven metadata retention

```bash
python scripts/retention.py --days 90
# Only after reviewing the dry run, policy and backup:
python scripts/retention.py --days 90 --apply
```

Only old terminal cases are archived. Active OPEN/ASSIGNED cases are untouched.
Report/destination bindings and vendor/assignee metadata are removed from archived
cases; original gate decision, originating account, audit/actor history and consumed
event tombstones remain. This prevents a retention job from reopening replay attacks.
It is not full personal-data erasure or a legal-retention policy. Run under a trusted
operator account or schedule the same command after reviewing your organisation's
requirements. The default is always dry-run; failures roll back the transaction.

## Session controls, retries and upgrade compatibility

My account lists active sessions and permits individual or other-session revocation.
No device identity is inferred from these records. New investigations mint scoped
submission keys: a retry returns its original case, while a changed payload with
the same key is rejected. Independent investigations can still produce separate
cases. Retry-key fingerprints and replay tombstones survive metadata archival,
but an old backup can lose knowledge created after the backup.

The current workspace migrates previous schemas additively to SQLite `user_version=3`
without replacing accounts/cases; it refuses a newer unknown schema. Back up before
upgrading. Do not run older application binaries against an upgraded live database.


### Current assurance evaluation (opt-in)

Use `python scripts/live_check.py` first (one synthetic case by default, paid API call).
Only after PASS: `python eval/assurance_eval.py --live --confirm-cost`.
The newer evaluator separates raw extraction from the full deterministic gate,
records explicit numerator/denominator metrics, provider errors, observed tokens
and latency, and does not estimate billing cost. It reserves the heldout split
unless both final-run flags are supplied. See docs/ENGINEERING_ASSURANCE.md.
Schema 3 adds local audit/receipt integrity; migrate a private copy and retain a
pre-migration backup. Old cases without content digests must be reinvestigated.
Never downgrade a schema-3 database to old application code.


Current protocol: see `docs/WORKFLOW_RELEASE.md`. After reviewing development
errors, freeze with `--freeze-config data/runs/frozen.json --development-report
data/runs/assurance-evaluation.json --confirm-development-reviewed`, then evaluate
**only** heldout with `--live --confirm-cost --split heldout --freeze-file
data/runs/frozen.json --confirm-heldout-final-run`. The old combined flag is refused.
A failed or interrupted heldout attempt is still consumed; preserve its evidence
and require a new independently authored split after tuning.

Python/Caddy images and GitHub actions now use immutable resolved references.
This does not imply a Docker build or remote CI ran. The isolated recovery command
backs up and restores only temporary synthetic stores; it is not a host recovery
drill. Backups of schema-3 stores check audit/receipt integrity before and after
copying and refuse known corruption. Legacy pre-migration backup remains possible
without a claim that a chain was checked. Keep actual backups encrypted/restricted.
