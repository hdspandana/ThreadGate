# Start here: code → test → key → push → deploy

This release is a locally tested **single-organisation / single-persistent-host**
workspace. You do not need to share an API key with anyone. The offline suite and
release checks need no key. Live provider access, your domain/TLS, remote CI and
actual hosting can only be validated on the systems you configure.

## 1. Put the source into your repository

Work on a branch in a clone of your existing repository; do not replace its `.git`.
Check for existing work before copying the new files.

```bash
git clone https://github.com/hdspandana/ThreadGate.git
cd ThreadGate
git switch -c product-ready
```

Extract the supplied ZIP separately and copy the **contents** of its `ThreadGate/`
folder into this clone. The ZIP deliberately contains no Git history, secrets,
virtual environment, database or dependency installation.

## 2. Install and complete every offline check

Use CPython 3.13. On Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
python scripts/doctor.py
python scripts/release_check.py --require-history
```

On Windows activate with `.venv\Scripts\Activate.ps1` (PowerShell). The exact lock
was resolved and clean-install tested on Linux/Python 3.13; on another platform,
use `pip install -r requirements.txt` if the lock cannot resolve, then run the full
checks. No cross-platform clean-install claim is made.

The release command runs preflight, the entire test suite, the security kill gate,
tree/history credential scan, offline evaluation, source compilation and source ZIP
packaging. It removes API credentials from child processes and prevents dotenv/cloud
secrets from being loaded by offline tests. Logs are in `data/runs/release-check/`.
A failed step stops the run. This does not make network requests to Gemini.

Without a clone, omit `--require-history`: the scanner can warn that history is
unavailable, never claim it was checked. Before pushing, repeat from the clone
with `--require-history`.

## 3. Explore the authenticated flow without a key

```bash
python scripts/manage_workspace.py --username owner
python scripts/serve.py
```

Use the password prompt (14–256 characters). No default account is bundled.
The operator bootstrap is refused after first setup.

1. **Administrator:** sign in, create separate analyst / verifier / auditor accounts.
2. **Each user:** change their initial password in My account; optionally enrol an
   authenticator. MFA setup displays a private secret/provisioning URI—never share it.
3. **Analyst:** New investigation → Offline → choose a synthetic scenario → Inspect
   → view field diff, evidence and controls → Save to shared inbox.
4. **Analyst or administrator:** open case → assign an active verifier username.
5. **Assigned verifier:** open case → preview current destination/evidence → complete
   a **synthetic walkthrough** of the callback/destination steps → re-inspect and attest.
6. **Auditor:** review the case timeline and Workspace audit; export metadata.

For a genuine request, only attest after actually doing the callback and checking
its exact destination. Synthetic walkthroughs are not evidence of a real callback.
`VERIFIED` never changes HOLD to CLEAR and never authorises or executes payment.

The separate unauthenticated Attack Lab is **synthetic demo only**:

```bash
python scripts/serve.py --demo --port 8502
```

Do not use that demo to handle real financial data. Offline is a deterministic
extractor test double, not Gemini performance.

## 4. Add your key later, in one private file

```bash
python scripts/init_env.py
```

Edit the created `.env` locally. Replace the placeholder on the `GEMINI_API_KEY`
line. Do not put the value in `.env.example`, source code, screenshots, shell
arguments, a Git commit or a chat. Restart the application after changing it.
The file is Git-ignored, excluded from Docker builds and excluded from the ZIP.

Environment variables take precedence over `.env`; hosting can also use Streamlit
secrets. The model defaults to `gemini-2.5-flash`, override `THREADGATE_MODEL` if your
provider account requires another supported model. Provider availability is not
guaranteed by this release.

```bash
python scripts/doctor.py --require-key
python scripts/live_check.py
```

Doctor checks configuration without an API request. Live check explicitly sends
three **synthetic** cases (HOLD / REVIEW / CLEAR) through the real Gemini path and
fails on an API/schema error or expected-decision mismatch. It pins the benchmark
date, writes a privacy-minimised result to `data/runs/live-smoke.json`, and exits
2 if configuration is missing, 1 for a failing check, 0 for a pass.

**A configured key is not a passing live check.** Invalid keys, unavailable models,
quota failures and malformed output must remain failures, not successful offline
fallbacks. Inspect the output before continuing.

## 5. Complete the real evaluation, then review acceptance

**This is opt-in and can make hundreds of paid model requests plus retries.**

```bash
python eval/run_eval.py --require-gemini
python scripts/check_live_report.py
```

The second command rejects missing/invalid live Gemini results and measured unsafe
HOLD or REVIEW/HOLD→CLEAR releases on the three existing corpus sets. It does not
require AI-only or deliberately weakened ablations to satisfy the gate's rules.
Review false holds, latency, actual SDK/model version and the finite sample size
as well. Passing this corpus is not a guarantee of field performance.

To test a smaller live subset first:

```bash
python eval/run_eval.py --sets v1 --systems rules_raw rules_norm gemini
```

That subset alone does **not** pass the full-report acceptance check.

When investigating with a real key, select Gemini. New investigations default to
Gemini when a configured key is available; a previously selected engine may remain
selected in the current browser session. Verifier preview and final reinspection
can each make a paid request. A changed binding or degraded reference is rejected.

## 6. Recheck and push

```bash
python scripts/release_check.py --require-history
git status --short
git diff --check
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Complete authenticated ThreadGate workspace and release tooling"
git push -u origin product-ready
```

Review the staged files before committing. The scanner's explicit local-secret
mode skips only ignored, untracked `.env` / Streamlit secrets (or explicit local
ignore rules in a source ZIP); it still rejects tracked secret files and scans
all available committed history. It does not excuse a secret in a different file.

Open a pull request and inspect both offline and container CI jobs. The workflow
contains a real image-build, hardened-container storage/identity smoke and health
check. Those jobs have not run remotely in this sandbox. Add the provider key as
a repository/environment secret named `GEMINI_API_KEY` only if you want the optional
manual `run_live` workflow. It is never used on normal push/pull-request jobs.

## 7. Deploy with persistent storage

```bash
docker compose build
docker compose run --rm app python scripts/manage_workspace.py --username owner
docker compose up -d
```

The container uses the pinned dependencies, a non-root account, read-only app root,
writeable `/tmp` and persistent `/data`. Compose exposes the app on host loopback
only. A fresh deployment needs its own bootstrap; your local database is not in
the image or ZIP. Do not mount an untrusted or shared-network SQLite file.

For public HTTPS, configure real DNS and `THREADGATE_DOMAIN` in the private `.env`,
allow inbound 80/443, and run:

```bash
docker compose -f compose.yaml -f deployment/compose.public.yaml config --quiet
docker compose -f compose.yaml -f deployment/compose.public.yaml up -d --build
```

The Caddy overlay persists certificate state and proxies WebSockets. Real domain,
certificate issuance and hosting still need your deployment test. Add network/IP
abuse controls; Caddy here is not a distributed rate limiter.

After rotating an environment key, recreate the app so Compose reloads it:

```bash
docker compose up -d --force-recreate app
```

Use the same `-f` overlay arguments when managing the public deployment.

## 8. Backup and recovery before handling real data

See `deployment/README.md`. The online backup tool strips sessions and pending MFA
enrollments, but contains password hashes and active MFA seeds: encrypt/restrict it.
Stop writers before restoration. An old backup also rolls back consumed-event
knowledge; a real financial workflow needs authoritative reconciliation before
resuming. Do not delete volumes accidentally with `docker compose down -v`.

Local-operator lost-account recovery is available in `scripts/recover_account.py`;
it is not a public recovery endpoint. Keep OS/database access tightly restricted.

## What still is not claimed

Terminal-case metadata retention is available as a dry-run-first local-operator
command: `python scripts/retention.py --days 90`; add `--apply` only after policy
approval and a backup. It preserves replay tombstones and audit/actor records,
so it is not full identity erasure or an automated deletion scheduler.

No real bank/ERP integration, payment release/execution, SSO/enterprise federation,
multi-tenant isolation, externally anchored
immutable audit, automatic retention scheduling/full identity erasure or distributed database/abuse control.
No independent holdout, accounts-payable user study, savings figure or field fraud
rate was invented. Independent security review is needed before real financial use.

The source and tests are ready for **your** key/configuration and deployment
verification—not a claim that your unconfigured infrastructure has already passed.

## Additional key-free product completion

The shared inbox now has status counts, literal-text search, state/assignment
filters and stable 25-row pages (no silent 500-case UI ceiling). Opening a case
also offers a verification/audit bundle from one database snapshot. Actor/event
identifiers are sensitive metadata; exports are not digitally signed.

My account now lists live sessions and supports revoking one session or all other
sessions. These are session records, not verified device identities.

Set `THREADGATE_REQUIRE_MFA=1` in the private environment and restart/recreate the
app to enforce authenticator enrollment across the organisation. Non-enrolled
accounts can sign in only to account/MFA setup and process information; sensitive
service methods also reject them. MFA cannot be disabled through the account UI
while policy is required. Enrol administrators before enabling this policy; local
operator recovery remains available for a lost authenticator. Default `0` keeps
MFA optional. Invalid policy values fail closed.

The investigation UI mints a submission key on Inspect; retries of the same Save
return the same case and audit action. Reusing that key with a changed request,
destination, engine, decision or title is rejected. New inspections intentionally
get new keys, so this is retry protection, not a claim that duplicate emails across
all users can never create separate cases. Keys and hashed fingerprints are
retained as tombstones, including after metadata retention.

For a real Chromium regression with no model key:

```bash
pip install -r requirements-browser.txt
python -m playwright install --with-deps chromium
python scripts/browser_smoke.py
```

It uses temporary synthetic accounts/data, blocks external browser requests,
pins reference time in a test-only wrapper and removes API credentials from the
test server. It exercises login, investigation, save, assignment, independent
verification, auditor review and JSON download. The actual product has no
test-password or test-clock bypass. CI includes the same browser job.
See `docs/KEYLESS_COMPLETION.md` for this release's changes.


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
