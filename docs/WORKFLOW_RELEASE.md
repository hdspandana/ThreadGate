> Latest continuation: see [STORAGE_EVALUATION_PROGRESS.md](STORAGE_EVALUATION_PROGRESS.md).
> Research/packet targeted tests passed; full current release gate is BLOCKED by
> missing Streamlit under the storage budget. No new release ZIP was built. Historical
> release results below are retained, not substituted for this continuation.

# Current end-to-end engineering release workflow

This is the current operating guide for the 2026-10-25 continuation. Prior assurance,
product-validation and submission reports are historical. Progress and exact phase
failures are in `WORKFLOW_PROGRESS.md`. Final commit identity is embedded in the
release ZIP; its adjacent manifest and the final external report bind final results
to that commit without a self-referential commit hash in committed prose.

## 1. Verdict and trustworthy baseline

Local synthetic demonstration: supported by executed tests/browser checks. Research
evaluation infrastructure: available, but **real Gemini performance unmeasured**.
Public production deployment: **not approved or established**.

Baseline was rerun, not copied: clean `engineering-assurance` at
`6736b0884ed9d05e6f983fdbaec7238e972b7a76`, fresh lock installation,
**779 passed in 54.82s**, zero skips; all 10 baseline release steps passed. Original
dirty main was not reset/switched/overwritten. The restored session has no remote
configured; public main was read via HTTPS, not changed. GitHub connector unsupported;
no GitHub token variable present, no push attempted.

Current collection: **826 tests** (38 added by the preceding end-to-end pass,
3 by the evaluation/readiness continuation, 3 packet-integrity cases by the storage-budgeted continuation, 3 stdlib CI-hardening cases). A green collector
is not a passing run; executed final gate results are retained separately.

## 2. Commands and evidence

Use a fresh venv and the lock, not untested dependency upgrades:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/release_check.py --require-history
# Independently available checks:
.venv/bin/python -m pytest -o addopts='' -q
.venv/bin/python eval/assurance_eval.py
.venv/bin/python scripts/attack_report.py
.venv/bin/python scripts/assurance_mutations.py
.venv/bin/python scripts/recovery_check.py
```

The release gate runs pytest/JUnit, kill-gate, working-tree/history secret scanning,
legacy offline evaluation, separated assurance development evaluation, attack
matrix, reason-checked mutations, isolated recovery, compilation, packaging and
archive/manifest verification: **12 steps**. Step reports include exact argv, exit
code and PASS/FAIL/WARN. On timeout no previous exit code is reused.

Browser commands (provider-independent):

```bash
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python scripts/browser_smoke.py
.venv/bin/python scripts/browser_attack_smoke.py
.venv/bin/python scripts/recovery_check.py --browser
```

Optional tools remain isolated from runtime:

```bash
python -m venv .venv/tools
.venv/tools/bin/pip install -r requirements-assurance.txt
.venv/tools/bin/python -m pyflakes src app scripts eval
.venv/tools/bin/python -m pip_audit -r requirements.lock --disable-pip --no-deps --format json --output data/runs/dependencies.json
```

No separate type checker or web production-bundle build is configured; Python
compilation and actual Streamlit startup are exercised. Docker/remote CI are not
substituted by static validation. Raw current outputs are under
`data/runs/workflow-20261025/`; selected safe synthetic evidence is copied into
`workflow-evidence/`. Full test identifiers and statuses are in gate JUnit output.
No real credentials, DBs or participant records are included.

## 3. AI evaluation — protocol, actual samples and limitations

Supported default model remains **gemini-2.5-flash**, HTTP timeout 30,000ms, total
per-extraction budget 90,000ms, at most three outer attempts. Bounded SDK calls are
not a guarantee of a maximum currency bill. No model was silently substituted.
**Key absent, zero provider calls, no measured Gemini accuracy/latency/tokens/cost.**
Missing-key smoke and live-development commands exited 2 before calling Gemini.

Private setup: `python scripts/init_env.py` creates an ignored placeholder `.env`;
edit it locally or set the supported private environment/hosting secret store.
Never put a key in chat, shell arguments, source, logs or screenshots. Environment
configuration wins over dotenv. Never commit `.env` or Streamlit secrets.

```bash
# Stage 1: one low-cost synthetic provider integration case (optional --cases 3).
python scripts/live_check.py --cases 1
# Stage 2: 32 frozen development cases, explicitly paid/opt-in.
python eval/assurance_eval.py --live --confirm-cost
# Review development failures before this explicit operator acknowledgement.
python eval/assurance_eval.py --freeze-config data/runs/frozen.json --development-report data/runs/assurance-evaluation.json --confirm-development-reviewed
# Stage 3: ONLY the 16 reserved heldout cases, not development+heldout.
python eval/assurance_eval.py --live --confirm-cost --split heldout --freeze-file data/runs/frozen.json --confirm-heldout-final-run
```

Development: 32 cases / 16 categories. Heldout: 16 distinct cases / 16 categories,
**not interpreted in this review**. Labels/digests unchanged. Both sets are small,
synthetic, authored with design knowledge and not independently representative.
Protocol tests read split metadata and simulate reports in temporary folders;
those tests are not live-provider or heldout-performance evidence.

The freeze binds application/control code, evaluator, record content, lock, corpus
manifest, model/settings and SDK plus the reviewed development evidence hash.
Changed source/config/evidence refuses final evaluation. A local exclusive marker
consumes the heldout digest **before** calls, including failures/interruption;
concurrent/repeated runs refuse it. If tuning follows a consumed result, preserve
that result and commission a new independent evaluation set. Deleting/recomputing
local freeze/ledger defeats these unsigned guards; no external provenance claim.

Metric helpers refuse unequal result counts and invalid decisions rather than
silently truncating via zip. Exact field accuracy scores normalized sets of
annotated requested values per case-field; sparse extra fields are diagnostics.
Intent recall requires literal change_request (unverifiable is a miss). Invalid/
incomplete counts errors, missing annotated fields or unverified claims, distinct
from correctness. Full-gate change recall means non-CLEAR on a positive label,
not correct extraction or callback authenticity. Rates have explicit numerator/
denominator; zero samples produce null, not perfect rates. Raw Gemini extraction
and full gate reuse one extraction, not two billed calls.

Actual offline development diagnostics, **not model performance**:

| Metric | Count / denominator |
|---|---:|
| Normalized rules baseline: exact decision / false CLEAR | 30/32; 2/30 |
| Offline test-double raw exact annotated fields | 18/26 |
| Offline test-double intent recall / false negatives | 22/28; 6/28 |
| Offline invalid/unverified or incomplete extraction | 4/32 |
| Full offline gate exact decision | 32/32 |
| Full offline false CLEAR / missed HOLD | 0/30; 0/28 |
| Full offline false HOLD / false REVIEW | 0/4; 0/30 |
| Gemini raw extraction / Gemini gate | BLOCKED, zero samples |

JSON retains measured local elapsed time separately from unavailable provider
latency, configuration/schema/corpus/code hashes and SDK version. Billing cost is
null; token observations, if available later, may omit failed billed calls.
Offline zero provider errors is not a provider-reliability measurement.

## 4. Security assurance and meaningful fixes

Actual newly red safety tests: five malformed adapter outputs escaped the guarded
extraction boundary, and overlapping masks exposed a long identifier suffix.
Pre-fix **6 failed, 3 passed**. Schema revalidation now occurs inside the fail-closed
boundary; masking merges intersecting spans first. All affected tests passed after
fixes. Evidence claims are about these exact boundaries, not universal security.

Attack Lab: 48 actual pipeline runs over 16 development representatives and three
deterministic extractors; every row has ID/engine, expected/actual, PASS/FAIL,
interpretation/reference/diff/controls and limitation. **0 unsafe releases / 48**;
these are simulated attacks, not actual Gemini compromises or external incidents.
Seven mutations are counted caught only when JUnit names the intended failed test
and matches the intended assertion/reason; unrelated failures/setup errors are not
kills. Actual **7/7** caught; not whole-program mutation coverage.

Existing role/session/MFA/account-disable, stale revision/reference, content binding,
idempotency/concurrency and replay invariants remain. Source and full reference
content are bound to authenticated attestations; exact case revision/actor/assignment
are transaction checked. **VERIFIED is an authenticated verification attestation,
not payment authorization and not proof an external callback occurred.**

The local audit chain/head and receipt anchors detect bounded tampering, missing
links/truncation and changed/missing receipt/event content against that saved head.
A privileged writer can rewrite the whole store/head, or restore a historical
snapshot. External anchoring and authoritative post-backup replay reconciliation
are required for stronger protection. Never call this tamper-proof.

## 5. Browser and human workflow

Executed Chromium checks: analyst → save/assign → separate verifier → reinspection/
attestation → auditor export, masked/revealed values, 390px audit view, actual
keyboard Username→Password tab order, visible focus/Enter submission, missing-key
visible failure/no silent offline fallback, role-specific absent write controls,
Attack Lab/download, and actual restored-product login/export. HOLD remains HOLD
after workflow VERIFIED. No provider call used; no auth bypass added.

This is partial accessibility evidence, not a full keyboard-only journey, contrast
certification or screen-reader audit. Human participants: **0**. Consent, synthetic
tasks, observations and a blank feedback form: `USABILITY_PROTOCOL.md`. No invented
user success rates, comments or satisfaction. Masking is not full PII scrubbing;
free text/names and values while editing may remain visible. Do not screen-share
private input. Only deliberately revealed built-in synthetic data appears in the
included comparison screenshots.

## 6. Deployment, backup and recovery

`recovery_check.py` creates only temporary synthetic accounts/store, records an
actual authenticated attestation, calls the online backup CLI, copies to a distinct
offline restored file, checks session stripping, MFA preservation/pending cleanup,
state/receipt integrity and read-only CLI, idempotency and replay rejection, then
retention keeping original gate/receipt/tombstone evidence. `--browser` actually
starts the shipped product on that restored DB and downloads its matching verified
case bundle. Temporary secrets/files are destroyed; no production DB is touched.

Schema-3 backups now check chain/receipts before and after copying and refuse
corruption with sanitized error/exit 1 and removal of partial output. Legacy
pre-migration backup remains possible without a chain-integrity claim. Backups
contain active MFA seeds/password hashes: restricted encrypted storage is still
required. An old snapshot can lose post-backup replay history: stop writers,
restore privately, reconcile external authority before resuming financial work.
This local exercise is not a host/region disaster-recovery drill.

Docker unavailable: build/config/run/OS-image scan NOT RUN. Remote CI, public DNS/
TLS/WebSocket/origin deployment, external identity and real hosting NOT RUN. Exact
operator checks remain in `deployment/README.md` and `.github/workflows/verify.yml`.
Local role/rate/session controls are not distributed abuse prevention or enterprise
SoD. Scrypt production work-factor sizing, seed encryption, external vendor-master
transactions/identity, multi-tenant/distributed storage and IP/cost enforcement
remain production prerequisites. No public service/resources provisioned.

## 7. Supply chain and release provenance

Current pip-audit: 60 exact lock entries, **0 reported known advisories**, exit 0;
not proof of no vulnerabilities. Unhashed artifact warning retained. Runtime lock
not blindly upgraded. Existing Python/Caddy tags resolved to registry-verified
manifest digests; existing GitHub action tags resolved to actual commit SHAs and
pinned. Checkout credential persistence disabled. Actual pin/source provenance is
recorded in workflow evidence; image pinning does not prove a container build.

Actual actionlint v1.7.12 workflow validation: exit 0; binary archive SHA256 checked
against GitHub's published digest before use. Remote CI execution not claimed.
Package artifacts/Go modules/runtime downloads still depend on their supply-chain
trust; unsigned local reports are not independent signatures.

`package_release.py --require-clean` requires clean committed source, excludes
ignored/untracked hitchhikers even if under included folders, and byte-checks
payloads against committed blobs. `verify_release.py --require-commit` checks
archive/manifest sizes, CRC/readability, entry hashes/identity, duplicate/path/private
file exclusions and committed source correspondence without extracting paths.
The manifest is unsigned: obtain the expected hash through a trusted channel.
Both compressed and unpacked limits are strictly below 128,000,000 bytes.

Final release procedure after the applicable precommit gate:

```bash
python scripts/package_release.py --require-clean
python scripts/verify_release.py --require-commit
# Repeat packaging and byte-compare its output, then extract to a NEW directory.
# In that directory, create a fresh venv/install lock, run release_check.py and
# the three browser workflows above. No Git history => secret-audit WARN and
# one history-dependent pytest skip, not an invented history PASS.
```

Final branch/commit, byte counts, file count, checksum and fresh extraction results
are recorded in the final external report and adjacent manifest. Review branch
only; no main merge/force-push or authenticated remote publishing performed.

## 8. Changed files and tests

Focused changes: eval/assurance_eval and live_check (protocol/single smoke), pipeline
(adapter validation), presentation (overlap-safe masking), assurance_mutations
(reason checks), backup/recovery and browser scripts, package/verify_release and
release_check, CI/immutable inputs, current setup/evaluation/recovery documentation.
Three new test modules add **38** cases without changing frozen data or weakening
existing tests. Targeted runs, expected initial reds and resolutions are recorded
in the progress log; all final outcomes must be read from actual gate evidence.

## 9. Remaining actions and learning

1. Privately add provider key, single smoke, development, inspect failures, freeze,
   then once-only separate heldout. Zero current Gemini results; 16 heldout cases
   cannot establish general effectiveness even after a future run.
2. Run actual Docker/remote CI/public TLS and restore-to-host exercises on authorized
   infrastructure. Publish only the feature branch after reviewing changes and
   establishing private Git authentication; no main merge authorized here.
3. Independent financial/security review, external identity/vendor-master/audit/replay
   authority, encrypted backups/seeds and distributed abuse/cost control before
   financial production use. Local authenticated accounts do not prove distinct people.
4. Conduct consented human/accessibility work; current automation is not participant
   research. Optional vendor CSV ingestion remains deferred to safe change control.

Important distinction: extraction correctness, escalation correctness and actual
workflow correctness are different measurements. Good escalation can conceal weak
extraction; fail-closed schema failures must be counted, not silently treated as AI
success. Reproducible files and hashes establish correspondence, not authenticity
against a privileged rewriter. Honest blocked results are more useful than invented
accuracy or deployment claims.


## Evaluation/readiness continuation

See [EVALUATION_REVIEW.md](EVALUATION_REVIEW.md) before interpreting field/intent
metrics: original labels are immutable but not independently adjudicated, and
forwarded-history extraction semantics are disputed. Evaluator v3 carries these
claim limitations without excluding cases or improving denominators. No expansion
was fabricated as independent evidence. Current readiness progress is in
[EVALUATION_READINESS_PROGRESS.md](EVALUATION_READINESS_PROGRESS.md).

Independent reviewer intake: [INDEPENDENT_REVIEW_HANDOFF.md](INDEPENDENT_REVIEW_HANDOFF.md).
Concise demonstration: [SYNTHETIC_DEMO.md](SYNTHETIC_DEMO.md). Neither a security audit
nor a participant study has occurred. Public compose now enforces MFA literally
rather than inheriting local optional-MFA 0; Docker execution remains unavailable.
