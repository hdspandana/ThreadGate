# Historical engineering assurance review

> Historical evidence for the preceding release at `6736b08`. Current behavior, totals and commands: [WORKFLOW_RELEASE.md](WORKFLOW_RELEASE.md). Old combined-heldout commands below are no longer accepted. This record is preserved, not represented as a current run.

Review date: **2026-10-25, Asia/Calcutta**. Execution-host timestamps are UTC and may show October 24. This is an engineering review, **not an independent security audit, real-model certification or production approval**. Evidence in `assurance-evidence/` is synthetic or environment metadata.

## 1. Executive assessment

The existing architecture is preserved: AI interprets; deterministic evidence validation, reference comparison and escalation controls decide; an authenticated person records an attestation. Nothing executes or approves payment.

Implemented in the isolated upgrade: safe pasted-input identifiers and bounds; fail-closed unknown vendors; full source/full reference-content attestation bindings; conservative malformed-account handling; schema-3 local audit hash chain, head and verification receipts; read-only integrity CLI; frozen categorized evaluation corpus with reserved holdout; separate extraction/gate metrics and request-local provider observations; reproducible Attack Lab; default destination masking, semantic side-by-side character-diff rendering and explicit reveal; clean-commit release identity.

**Readiness: reviewable offline candidate. Not validated for real financial use.** Real Gemini samples, independent participants, public TLS, remote CI and Docker execution are unavailable. Optional CSV vendor-master import is deliberately deferred: changing trusted financial reference data needs an authenticated, independently reviewed ingestion/change-control design, not a late feature addition.

## 2. Baseline, branch and source identity

- Original `main` / public main: `5c5e387f2c3f49df6b61e5794bc2647b311cd54d`.
- Original working tree had 14 modified tracked files and additional untracked upgrades. No reset, cleanup or main commit was used.
- Copied 133 nonignored source files into `/home/user/ThreadGate-assurance`, branch **`engineering-assurance`**. The original source files remain untouched.
- Fresh `requirements.lock` installation, CPython 3.13.16: **723 passed in 46.64s**, zero skips at baseline.
- Prior ZIP: 1,984,778 bytes, SHA256 `8fff64936a856af5d7fdda42da299b80247a1fa0be80e6fbbe349cd87594cee3`. Its included source bytes matched the original local working tree, not public HEAD.
- The final source commit is embedded in ZIP-root `RELEASE_IDENTITY.json` and recorded by the adjacent release manifest. This avoids putting a self-referential commit/hash inside committed source prose. Dirty precommit packages are explicitly marked **uncommitted-not-a-commit-release** and are not the final release.
- The upgrade integrates previously uncommitted product work as well as these assurance changes; it is not represented as a tiny patch over the public prototype.

## 3. Gemini validation, samples and cost

**Actual successful Gemini samples: 0. Actual provider calls in this review: 0. No measured provider cost or latency.** Missing-key smoke and opt-in evaluator each exited 2 before any call. Their exact outputs are retained. Offline latency is local test-double latency only.

Small smoke: `python scripts/live_check.py` sends three synthetic cases, up to three attempts each. Model defaults to `gemini-2.5-flash`, HTTP timeout 30,000ms and total per-extraction budget 90,000ms. Retries are bounded; permanent client errors are not retried. No silent offline fallback is used. Key configuration belongs only in private environment/ignored secret files; never chat, source, logs or reports.

After a matching model/schema/extractor-code/SDK/config smoke PASS within 24 hours:

```bash
python eval/assurance_eval.py --live --confirm-cost
# Only an explicitly chosen final run; never tune prompts on this split:
python eval/assurance_eval.py --live --confirm-cost --include-heldout --confirm-heldout-final-run
```

Development has **32 cases / 16 categories**. Heldout has **16 distinct cases / 16 categories** and remains unexecuted. Labels and corpus digests were frozen before the new evaluator ran. Heldout is guarded by explicit flags; prompts were not tuned on it. Both splits were synthetically authored with knowledge of the design: **not independently authored validation, not representative real-world error rates**. Gold labels/reference data are not passed to Gemini. Identity-ambiguity cases explicitly mark the selected vendor unresolved; the system does not magically infer vendor identity from account similarity.

Categories: no-change, destination change, ambiguous/unavailable destination, conflicting instructions, forwarded/stale instructions, prompt injection, unresolved vendor identity, Unicode/fullwidth/confusables, malformed identifier, missing record, multiple changes, duplicate/replay wording, legitimate-looking one-character change, registered alternate, HTML/signature, truncated/attachment-only content. Actual replay is tested at the service layer, not claimed from duplicate-wording classification.

### Measured development diagnostics — not model performance

| System / metric | Raw count / denominator |
|---|---:|
| Normalized deterministic rules: exact gate label | 30 / 32 |
| Rules: false CLEAR among non-CLEAR labels | 2 / 30 |
| Offline structured test double: exact annotated field sets | 18 / 26 |
| Offline structured test double: change-request intent recall | 22 / 28 |
| Offline structured test double: intent false negatives | 6 / 28 |
| Offline invalid/unverified or incomplete extraction | 4 / 32 |
| Full gate with offline test double: exact label | 32 / 32 |
| Full offline gate: false CLEAR / missed HOLD | 0 / 30; 0 / 28 |
| Full offline gate: false HOLD / false REVIEW | 0 / 4; 0 / 30 |
| Raw Gemini extraction / full Gemini gate | **0 executed; BLOCKED**, no rates |

Field labels are sparse. Accuracy compares normalized sets of requested values for each annotated case-field pair, not individual digit accuracy; an extra unannotated field is diagnostic, not automatically wrong. Intent recall requires literal `change_request`, so `unverifiable` counts as a miss even when the gate appropriately holds. Invalid/incomplete means schema/provider failure, omitted annotated field or an unverified claim; it is distinct from field correctness. Gate change recall means any non-CLEAR on a positive change label, not evidence of correct interpretation. A fail-closed provider failure can hold every case and must not be confused with good extraction.

JSON reports contain numerator, denominator and rate (null for zero samples), schema/provider/timeout failures, conditional false CLEAR/HOLD/REVIEW and missed-HOLD rates, median/p95 elapsed time, schema/code/corpus hashes, SDK/model/config and observed token counts. Each live extraction is reused for its full gate result, not billed twice for the two metrics. Cost stays null: API responses do not establish billed currency amounts, and token accounting may omit failed calls. Smoke artifacts and reports are unsigned local evidence, not independently authenticated provenance.

## 4. Reproducible adversarial matrix

```bash
python scripts/attack_report.py
python scripts/serve.py --demo --no-install
```

In the synthetic workbench select **Attack Lab → Reproducible 16-category attack matrix → Run synthetic attack matrix**. Inspect input, model interpretation, trusted reference, diff, controls, expected/actual decision and limitation; download the synthetic matrix. Full raw rows: `assurance-evidence/attack-matrix.json`.

**Executed: 48 actual-pipeline runs** = 16 representative development categories × offline, compromised, compromised_quote. **0 / 48 non-CLEAR labels released as CLEAR; 48 / 48 exact labels.** The two compromised extractors are deterministic malicious-output simulations, not observed Gemini compromises. Finite token coverage and correlated fixtures prevent general security claims.

| Attack family | Boundary exercised | Actual local result / remaining limitation |
|---|---|---|
| Injection / forged quote / HTML footer | Independent token scan + quote/value validation | Known unsupported destination stays HOLD under both simulated suppressions; unseen encodings still need testing |
| Fullwidth / Cyrillic confusable | Normalization with raw-span mapping | Synthetic cases HOLD; this is not universal OCR/Unicode coverage |
| Malformed account letters | No silent letter-stripping; independent explicit-label check | Synthetic mixed identifiers HOLD; parser is finite and contextual |
| Missing/unresolved vendor | Trusted-reference availability guard | HOLD even with suppressed change; correct vendor selection remains a trusted caller responsibility |
| Ambiguous / conflicting / forwarded / truncated | Unverifiable-destination and conflicting-token escalation | HOLD; no attachment execution/OCR or message-age inference is claimed |
| Alternate / multi-change / fluent one-character difference | Trusted record comparison and escalation policy | Alternate REVIEW, unsupported destination HOLD; vendor master is synthetic, not bank authority |
| Replayed event / duplicate submit / stale revision | Service authorization, event uniqueness, explicit actor-scoped idempotency key | Covered by deterministic service tests; no global email deduplication claim |
| Failed model/schema / fabricated evidence | Fail-closed extraction and evidence validator | Deterministic/mocked tests only, not real-provider reliability |

Existing adversarial suites cover stale references, normalization, fake values/evidence, role denial, replay, idempotency and concurrency. New targeted mutation checks isolate copies and never change ground truth: **7 attempted / 7 killed**, with each selected baseline passing first (source binding, full reference binding, account letters, audit content hashing, missing-head rebaselining, receipt comparison, transaction rollback). This is not whole-program mutation coverage.

## 5. Verification, replay, audit and recovery

New pipeline contexts/events bind vendor ID, request ID, destination digest, reference version, **SHA256 of the full raw email representation**, and **SHA256 of the complete canonical vendor record**. Changed subject/from/reply-to/received/body or same-version contact/domain/alternate changes invalidate verification. UI mint sites include both digests. Legacy manually constructed four-field library contexts remain constructible for compatibility; persisted legacy workspace cases without content digests must be reinvestigated and cannot be verified as if upgraded.

Authorization stays server-side: active independent assigned verifier, current session/MFA policy, exact case revision, current reference and matching freshly derived context. Attestation is an authenticated account's statement, **not proof of a callback, independent human identity or payment approval**. HOLD is not converted to CLEAR. Unauthorized/precondition failures do not mint receipts. Authorized accepted/rejected bound event presentations get single-use event tombstones and audit evidence in one transaction. Retention does not delete replay tombstones.

Schema 3 adds canonical audit row + previous-hash chaining, a local saved head, and verification receipts binding actor/assignment/revision/context/request/reference and the workflow event. Initial migration trusts prior audit rows once. It cannot recover historical integrity retroactively. A schema-3 missing head fails rather than silently trusting a new baseline. Migration fault injection leaves old version/history intact and can retry. Newer schema versions are refused; never downgrade a schema-3 store to old code.

```bash
python scripts/verify_audit.py --db /private/path/workspace.sqlite3
```

Read-only CLI returns JSON PASS/FAIL and exit 0/1. It detects changed audit rows/links, missing links, saved-head mismatch, truncation, changed/missing anchored receipts and altered/missing workflow-event rows. Admin/auditor integrity view and case bundles use the composite check. Case bundles omit source and destination values but contain sensitive actor/ID/time metadata; local chain hashes are not signatures.

**Not tamper-proof:** a privileged writer who rewrites the entire database, chain and head can defeat this checker. There is no external anchor, independently signed receipt or authoritative rollback ledger. Restoring an old full backup also restores old replay history: stop all writers, use restricted/encrypted backups, strip sessions, test restore, reconcile post-backup events with an external authority before financial operation. Transaction fault tests prove case state/event/receipt/chain roll back together locally; they do not prove host disaster recovery.

## 6. User research — protocol, not participant results

**Participants recruited: 0. Human observations: 0. No usability score, success rate, satisfaction, quote or time-on-task is asserted.** Automated browser activity is not user research. The local visual inspection is an engineering heuristic review.

Proposed consented study: recruit 3–5 accounts-payable/finance-operations participants spanning analyst, verifier and auditor responsibilities; use synthetic data, no credentials or real financial identifiers in recordings. Counterbalance task order where useful.

Tasks: (1) interpret CLEAR vs payment approval; (2) locate the exact one-character account change and current reference; (3) select an independently trusted callback contact rather than email replacement details; (4) investigate, assign, return an unverifiable case and attest only after a simulated callback; (5) explain HOLD plus VERIFIED and inspect/share an appropriately minimized audit bundle. Include missing-reference and failed-model scenarios, not just happy paths.

Record independently: completion without assistance, unsafe approval interpretation, missed difference, wrong callback source, accidental reveal/export, errors/recoveries, measured time and participant teach-back. Ask confidence/clarity after—not before—the task. Stop on unsafe assumptions. Keep separate protocol, observation and recommendation fields; no thresholds have been met yet. Template: `assurance-evidence/user-study-template.csv`.

## 7. UX, privacy and actual browser evidence

Navy/violet/cyan retained. Comparison now has semantic table/caption/headers, trusted/requested adjacency, explicit **Different — verify out of band**, and character-level additions/deletions when deliberately revealed. Color is not the only difference cue. Recognized account/code values, long numeric sequences and email addresses are masked in result/source/evidence paths by default, with explicit session reveal. This is **not a complete PII scrubber**; names/free text may remain and text being pasted/edited remains visible. Do not screen-share private input. Raw structured extraction is behind reveal. Matrix exports intentionally contain only the built-in synthetic data.

Current Playwright Chromium runs, not historical screenshots:
- Analyst → save → assign → separate verifier → reinspection → attestation → auditor → JSON bundle download: PASS.
- Destination absent from visible page before reveal and available in the comparison after explicit reveal: PASS.
- Workflow VERIFIED retains gate HOLD: PASS.
- 390px viewport has no page-level horizontal overflow in tested audit view: PASS; not comprehensive mobile/accessibility certification.
- Attack Lab matrix generates and downloads 48 rows in an actual browser: PASS.
- No Streamlit exception element in tested flows. No API key used. Test-only clock is pinned outside shipped entrypoints; no product auth/clock bypass is added.

![Masked investigation](assurance-evidence/01-investigation.png)
![Revealed synthetic character diff](assurance-evidence/03-revealed-comparison.png)
![Evidence and next action](assurance-evidence/05-evidence-and-next-action.png)
![Audit integrity view](assurance-evidence/02-audit.png)
![Mobile audit](assurance-evidence/04-mobile-audit.png)
![Synthetic Attack Lab](assurance-evidence/06-attack-lab.png)

CSS adds visible focus treatment; semantic labels and escaped rendering have unit coverage. Screen reader, full keyboard-only flow, comprehensive contrast audit and independent accessibility testing remain unverified. The original research UI is preserved, not represented as the authenticated or privacy-hardened deployment surface.

## 8. Security and deployment review

| Surface | Implementation / actual evidence | Remaining risk / status |
|---|---|---|
| Passwords/bootstrap | Salted scrypt N=16384,r=8,p=1; private interactive first admin, no defaults/public signup | Production password work-factor sizing and enterprise identity review required |
| Roles/separation | Server checks every operation; assigned verifier cannot be creating account; tested denials/concurrency | Admins/people controlling multiple credentials can defeat real-person separation |
| Sessions/revocation | Random tokens, hashed at rest, 8-hour expiry; password/disable/MFA/session revocation tested | No SSO, idle-timeout or distributed session infrastructure |
| MFA | Optional/enforced TOTP, replay counter, enrollment gates and revocation tested; public compose defaults enforcement on | Seeds stored in restricted SQLite/backups, not application-encrypted; trusted host required |
| CSRF/origins | Streamlit CORS + XSRF protection effective settings both true; browser exercised local authenticated flow | Public proxy/origin/TLS behavior and cross-origin penetration testing BLOCKED |
| Abuse controls | Five failed logins / username / 15-minute window; live UI spacing and per-request budgets | No distributed/IP throttling; account-lockout DoS possible; cost control is not a billing quota |
| Persistence/atomicity | SQLite FULL synchronous; serialized writers, revisions, idempotency, receipt/audit rollback tests | One host/organisation, not multi-tenant/replicated; audit verification cost grows with history |
| Privacy/exports | No persisted raw email/destination; metadata-only case bundles; masking and escaped comparison tested | Metadata/hash correlation and free-text PII remain sensitive; identity erasure not implemented |
| Secrets | Working tree and readable Git history scanner: 0 findings | Pattern scan is not proof of absence; local/private deployments need separate secret review |
| Backups/rollback | Online backup, private output, session stripping and existing recovery tests; new migration/fault tests | Host restore drills/encryption/external replay reconciliation not established |
| Container | Nonroot app, read-only FS, dropped capabilities, persistent volume; source/config reviewed | Docker absent: no build/run/config/OS-image scan claimed |
| Public deployment | Caddy reverse proxy, loopback app binding, public MFA-default hardening and security headers supplied | No actual DNS/cert/TLS/remote CI/deployed-host evidence; network throttling not supplied |
| PostgreSQL | No PostgreSQL backend used | N/A, not a claimed test |

No separate payment-approval API exists. Python service arguments are trusted server integration inputs, not untrusted public REST fields. Production integration must derive current context from an authoritative record adapter; caller-supplied `reference_current=True` is not a reference authority. JSON vendor-master edits are not serialized with an external ERP transaction.

## 9. Dependencies and advisory assessment

Executed `pip-audit 2.10.1` against all **60 exact entries in requirements.lock**: **0 reported known advisories**, exit 0. This is the advisory service's point-in-time result, not proof of no vulnerabilities. Full JSON and warning output are retained. Advisory access succeeded; no provider was called. Static `pyflakes 4.0.3` on src/app/scripts/eval and the new regression module: exit 0.

No runtime lock update was required by this scan. Optional `requirements-assurance.txt` pins tooling, not app runtime. Runtime lock lacks package artifact hashes; platform wheels/transitive resolution outside the tested lock need separate validation. Docker Python/Caddy tags and CI actions use mutable major tags rather than immutable digests/SHAs: supply-chain pinning/OS-image advisories remain deployment work. Browser/OS packages were installed for this local check, not independently security-certified. Streamlit is a general application framework, not a financial approval authority.

## 10. ZIP, integrity and commit correspondence

`python scripts/package_release.py --require-clean` only accepts a clean committed Git source worktree. It creates deterministic sorted entries/fixed ZIP timestamps, a source-only archive and an external file SHA256 manifest, with embedded source commit/branch/clean status. Excludes .git, virtual environments, caches, local secrets, runtime databases, backups, runs and build outputs. Both compressed and unpacked size limits are strictly below **128,000,000 bytes**.

Final size, archive SHA256 and final commit are recorded in `release/TeamWorkspace-manifest.json` and the user-facing final report. Two final package builds are compared byte-for-byte. Final archive entries are compared to committed blobs, not just a mutable working tree. Extracted installation/workflow verification is recorded separately; an archive has no Git history, so its scanner reports WARN/history unavailable, never false history PASS.

## 11. Exact verification and statuses

Commands run from the assurance worktree using `.venv/bin/python` unless noted. Current collector: **779 tests**, including 56 new parametrized regression cases. Existing assertions/labels are preserved; minting fixtures gain required digest fields, and schema/test-count expectations reflect the implementation.

| Command | Observed result / evidence |
|---|---|
| `python -m venv .venv; .venv/bin/python -m pip install -r requirements.lock` | Fresh baseline installation succeeded |
| `python -m pytest -o addopts='' -q` (baseline) | 723 passed, 46.64s |
| Existing suite after first binding/audit changes | 723 passed each run |
| New focused assurance module | Initial 2 fixture-path errors corrected; focused 54 passed before two added parameter cases |
| First full expanded suite | 776 passed / 3 failed: stale documentation test counts; updated counts, no weakened tests |
| `python eval/assurance_eval.py` | Exit 0, 32 development cases; heldout unrun |
| `python scripts/attack_report.py` | Exit 0, 48 synthetic runs, 0 unsafe releases |
| `python scripts/assurance_mutations.py` | Exit 0, 7/7 targeted mutations killed; initial target-string mismatch fixed before successful run |
| `python scripts/browser_smoke.py` | Exit 0; current authenticated flow, masking/reveal, mobile view and export PASS |
| `python scripts/browser_attack_smoke.py` | Exit 0; actual Attack Lab/download PASS |
| `python -m playwright install chromium` / `install-deps chromium` | Succeeded; initial browser failed missing libnspr4, dependency installation resolved it |
| `.venv/tools/bin/python -m pip_audit -r requirements.lock --disable-pip --no-deps --format json --output data/runs/assurance/dependency-audit.json` | Exit 0; 60 packages, no reported advisories; unhashed-lock warning retained |
| `.venv/tools/bin/python -m pyflakes src app scripts eval tests/test_engineering_assurance.py` | Exit 0 |
| `python scripts/secret_scan.py --allow-local-secrets` | Exit 0; working tree and readable Git history, 0 findings |
| `python scripts/live_check.py` | Exit 2, BLOCKED/missing private key, no calls |
| `python eval/assurance_eval.py --live --confirm-cost` | Exit 2, BLOCKED/key + passing-smoke prerequisite, no calls |
| `python scripts/release_check.py --require-history` | Exit 0, 10/10 steps PASS; 779 tests passed, zero skips (53.63s on final precommit gate); raw evidence retained |
| Extracted `python scripts/release_check.py` | Exit 0: 778 passed, 1 skipped (51.28s); only full-history scanner test skips without .git. History step WARN; both extracted browser workflows PASS |

The final report and copied raw gate summaries are the authority for final test duration, extraction status, packaging hash and commit. No skipped live test is silently counted as a passed provider test. Remote workflows are configured, not asserted executed.

## 12. Prioritized blockers / next operator actions

1. **Before any real model claim:** privately add a key, small smoke first, inspect errors/tokens/billing, explicitly opt in to development evaluation, then one reserved heldout final run. Preserve untuned labels, report raw numerator/denominator extraction and gate results separately, including failed calls. No accuracy claim can currently be made for Gemini.
2. **Before financial use:** independent security and financial-control review; authoritative vendor identity/master integration; external integrity/replay authority; trusted person identity/SoD; host/backup encryption and seed protection; safe ingestion/change approval. The local hash chain is not an authenticity service.
3. **Before public deployment:** actual Docker build/config/persistence tests; immutable supply-chain pins; real TLS/origin/WebSocket checks; monitored persistent hosting and IP/distributed abuse/cost limits; enforced MFA, restore rehearsal and CI execution. No push/deployment was performed here.
4. **Before usability/accessibility claims:** run the consented human protocol and keyboard/screen-reader/contrast checks; record observations rather than engineering opinions. Current screenshots/automation demonstrate only the tested synthetic flows.
5. Optional CSV import and larger corpus expansion remain deferred; prioritize independent validation over feature count. Do not use this application to execute, approve or automatically update payment destinations.
