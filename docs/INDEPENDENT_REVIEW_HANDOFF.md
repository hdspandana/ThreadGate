# Independent security-review handoff — prepared, not conducted

**Reviewer engaged: none. Independent findings/sign-off: none.** This package enables
review; engineering tests and this checklist are not a security audit. Use only a
fresh synthetic workspace, no production data/keys. No public scanning, exploitation,
deployment or production modification is authorized by this document.

## Scope and boundaries

- Assets: local identity/password hashes, active TOTP seeds/sessions, trusted vendor
  master, case revisions/assignments, request/reference/destination digests, audit
  head/receipts, backups, source and release artifacts.
- Untrusted input: email/headers, model interpretation, browser submissions and
  stale/replayed events. Model output never authorizes or executes a payment.
- Trusted integrations: server-derived current context/reference state and selected
  vendor identity; the Python service is not a public verification REST API.
- Privileged boundaries: OS/database operators and people controlling multiple
  credentials can defeat local person-separation/authenticity assumptions. Local
  head/ledger/manifest rewriting and old-backup rollback need external protection.
- Deployment: one organisation/host, SQLite, local accounts, no payment/ERP execution.
  No multi-tenant/distributed guarantees. Public TLS/container/remote CI are untested
  here. MFA seeds/backups need encryption and restricted access outside this app.

## Reproducible evidence for reviewer

Read `WORKFLOW_PROGRESS.md`, `EVALUATION_READINESS_PROGRESS.md`, `WORKFLOW_RELEASE.md`,
`EVALUATION_REVIEW.md`, the final external status report and embedded release identity.
Do not treat earlier report timestamps/counts as a current run.

```bash
python scripts/release_check.py --require-history   # from a Git worktree
python scripts/browser_smoke.py                    # optional browser dependencies
python scripts/browser_attack_smoke.py
python scripts/recovery_check.py --browser         # temporary synthetic restore
python scripts/verify_release.py --require-commit  # committed-blob correspondence
```

Install runtime from requirements.lock, browser tools from requirements-browser.txt.
An extracted ZIP lacks Git history: it must report that limitation, not pass a
history scan. Unit/attack cases are synthetic, not external penetration evidence.
Never use real financial inputs to make prettier screenshots or test assertions.

## Review questions / acceptance evidence — unchecked

| Boundary | Reviewer should challenge | Required evidence, not supplied sign-off |
|---|---|---|
| Model/evidence | Invalid/empty/malicious or low-confidence extraction; missing key, timeout; fabricated quotes/values | Confirm fail-closed behavior, no model verdict/approval path; inspect error/log privacy |
| Identity/reference | Wrong valid vendor selection, unresolved/stale/changed reference, same-version full-record mutation | Distinguish caller trust from actual authority; reproduce binding failures |
| Roles/revisions | Unassigned/same originating account, stale revision, concurrent submit/verify, event replay | Server denial/atomicity, not just hidden UI buttons; determine real-person SoD gaps |
| Auth/MFA | Expiry, disable, password/session/MFA revocation, TOTP replay, public enforcement, recovery/bootstrap | Challenge credential policy, abuse resistance and encrypted seed/backup needs |
| Audit/receipt | Changed row/link/head, truncation, altered/missing receipt/event; legacy migration | Bounded detection/transaction rollback; demonstrate privileged whole-store rewrite limitation |
| Privacy/exports | Default masking/reveal, source/evidence/metadata/errors, receipt/hash correlation | Enumerate visible/retained PII; no claim that masking is a complete scrubber |
| Backup/retention | Restore to separate file, old sessions/MFA, preserved case/receipt/replay, corruption | Exercise product on restore; external post-backup reconciliation and real-host recovery remain required |
| Build/supply chain | Lock/artifact hashes, immutable refs, secret scan, archive/commit identity | Verify independent expected hash; no inference that pinning proves images safe |
| Network/host | TLS/origins/WebSockets/XSRF, public MFA, monitoring/storage, IP/cost limits | Authorized staging measurements; no production probing or exposure here |

Public compose now fixes MFA to 1: local `.env` optional-MFA 0 must not override it.
This is source/static regression evidence, not proof the compose deployment ran.
The deployment guide's current schema is 3; do not downgrade upgraded stores.

## Reviewer output template — blank

Reviewer/organisation ___; independence/conflicts ___; date/source commit ___;
review scope/exclusions ___; authorized environment/data ___;
issue ID/severity ___; affected boundary ___; exact reproducer ___;
expected/observed outcome ___; evidence location with secrets removed ___;
exploit preconditions ___; impact/uncertainty ___; remediation/retest ___;
residual risk owner ___; accepted/deferred/rejected claim ___; signature ___ .

No field is filled as an actual finding or approval until an independent reviewer
performs the work. Confirm consent/permission before collecting identifying details.

## Non-negotiable wording

**VERIFIED is an authenticated verification attestation, not payment authorization
and not proof that an external callback occurred.** CLEAR is not an authenticity
certificate. Synthetic zero unsafe releases is bounded regression evidence only.
This release is not declared production-ready.

Usability study is separate: `USABILITY_PROTOCOL.md` already provides consent,
synthetic tasks, observations, withdrawal/recording and blank feedback forms. It
remains unconducted (0 participants); developer/browser automation is not user research.
