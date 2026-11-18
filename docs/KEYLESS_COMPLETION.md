# Additional key-free completion

This release builds on the earlier authenticated workspace. It adds working code,
not placeholders for the Gemini key, while preserving the deterministic gate.

## New implementations

### 1. Retry-safe case submission

The investigation UI mints a random submission key for each inspection. Saving the
same payload with the same key returns the original case ID, including after a
restart. The case, submission-key mapping and audit entry commit together. Concurrent
retries create one case and one submission audit action. Changing the normalised
source, binding, extractor, decision or title under that key is rejected.
Keys are scoped to the authenticated analyst. A fresh investigation intentionally
gets a fresh key; this is not global duplicate-email or fraud detection.

### 2. Searchable shared inbox

Status counts, literal-text search, state filters, assigned-to-me filter and stable
pagination are implemented in the service and UI. Ordering includes the case ID to
avoid overlapping pages at equal timestamps. Search uses bound parameters and
escapes SQL LIKE wildcards. Filtered counts and rows share a read snapshot.
The UI no longer silently limits investigation selection to the most recent 500.

### 3. Account session management

My account lists live sessions, expiry times and the current-session marker. Users
can revoke a selected session or all other sessions. Ownership is checked in the
service, so another account's identifier cannot revoke its session. Returned session
IDs are hashes/non-bearer references, not raw login tokens or verified device IDs.
Signing in clears private state left by a previous account in the same browser session.

### 4. Organisation-wide MFA policy

`THREADGATE_REQUIRE_MFA=1` enables server-side enforcement. Non-enrolled users retain
only account/enrollment/recovery functions and process information. Case reads,
search, exports, submissions, verification, global audit and team administration
require completed enrollment. The UI hides those pages too, but is not the security
boundary. Required MFA cannot be disabled through the account workflow. Invalid
policy values prevent workspace startup. Default `0` retains optional MFA.

Initial administrators can sign in and enrol before provisioning the team. Prefer
enrolling administrators before activating enforcement. Lost-factor recovery remains
a trusted local-operator action, not a public web endpoint. This is local TOTP MFA,
not SSO/enterprise federation or protection against a privileged database operator.

### 5. Verification/audit bundles

Case export includes report metadata, workflow state/revision, verification events
and case-specific audit history from one read snapshot. Source email, destination
values/digests and authentication secrets are omitted. Usernames, event/case IDs
and timestamps remain sensitive. The bundle is not digitally signed, immutable,
proof of a callback or payment authorisation.

### 6. Actual browser regression

`scripts/browser_smoke.py` launches the actual Streamlit UI in Chromium, exercises
analyst login → inspect → save → assign → verifier preview/attestation → auditor
review → download case bundle, then checks the persisted workflow and downloaded
report. All accounts/data are temporary and synthetic. It removes API credentials,
blocks external browser requests and pins reference time in a temporary test-only
wrapper. The production application has no test-clock/password bypass.

Browser dependencies are separate from the runtime lock in `requirements-browser.txt`;
the browser binaries and OS packages are installed separately, never put in the ZIP.
A CI browser job runs the same regression. Local successful browser summary and
screenshots are in `docs/browser-validation/`. No remote CI success is claimed.

## Validation

The full unit/UI suite passes locally, including tests for concurrent idempotency,
audit rollback, search injection/wildcards, pagination, session ownership/revocation,
enforced-MFA data access, key reuse with changed requests, export privacy and
account-switch state isolation. The security kill gate, credential scan, offline
evaluation, compilation and package validation are also run. Latest logs are in
`docs/release-validation/`. This does not establish live Gemini performance.

## Migration

SQLite schema version is now `2`. Previous accounts, cases, consumed events and
MFA records are preserved; new tables/indexes are added. A newer unknown schema is
refused. Back up before upgrading and do not run an older binary on the upgraded
live database. Submission-key fingerprints are retained after archival, like replay
tombstones. Restoring an old backup can lose knowledge created since that backup;
real financial operations need authoritative reconciliation before resuming.

## Start

Follow `docs/START_HERE.md`. No new provider key or paid service is required for
these additions. Add your Gemini key locally later, run the provided live checks,
then push and test deployment on your own infrastructure.

## Remaining external or out-of-scope work

Real provider success requires your key/account. Docker/domain/TLS and remote CI
must be validated on the target host. Independent holdout authoring, user studies
and security review require independent participants. Real bank/ERP execution,
SSO, distributed storage, multi-tenant isolation, immutable external audit and
IP/distributed abuse controls are not implemented or implied by these additions.
