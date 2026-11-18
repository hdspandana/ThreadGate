# Continuous engineering workflow — 2026-10-25

Status vocabulary: PASS = executed and met acceptance; FAIL = executed and failed; BLOCKED = unavailable prerequisite; NOT RUN = not executed. Historical reports remain historical; this log governs the current pass.

## A — Baseline: PASS
- Inspected `/home/user/ThreadGate-assurance`, branch `engineering-assurance`, HEAD `6736b0884ed9d05e6f983fdbaec7238e972b7a76`; worktree clean. Original `/home/user/ThreadGate` remains dirty and untouched. No repository remote configured in this restored session; GitHub connector reports unsupported. No push/remote modification attempted.
- Venv absent after environment restoration; recreated and installed `requirements.lock` successfully. Inspected actual source, CI, release/evaluation/browser/backup scripts, lock and prior ZIP/manifest. No code edits before baseline.
- Executed `.venv/bin/python scripts/release_check.py --require-history`: exit 0, 10/10 steps PASS; **779 passed in 54.82s**, zero skips. This includes current secret/history scan, synthetic evaluation, Attack Lab and mutations. Raw output: `data/runs/workflow-20261025/baseline-gate.txt` and `data/runs/release-check/`.
- Checked supported private configuration through `load_environment`/`key_configured`: key presence false, value never printed. Docker executable absent. Live provider, Docker/public host and participant checks BLOCKED; independent work continues.
- Commands discovered: release_check, live_check, assurance_eval, run_eval, attack_report, assurance_mutations, browser_smoke, browser_attack_smoke, backup_workspace, verify_audit, retention, package_release; pytest, compileall, optional pyflakes/pip-audit. No separate TypeScript build or configured type checker.
- Review gaps for next phase: heldout currently combined with development, no persistent consumed-set/freeze guard; metric helpers silently zip unequal lengths; mutation checker treats any FAILED text as a kill; single-case smoke unavailable; full restore-to-auditable-workflow evidence and keyboard checks need strengthening. Verify and fix these focused gaps without changing frozen labels or tuning on heldout.

## B–H — NOT RUN for this pass
Will append executed evidence and failures at each boundary. Historical passes are not substituted for current checks.

## B — Evaluation design: PASS
- Reproduced design gaps: combined development+heldout scoring, no persisted freeze/consumption marker, zip-based metrics accepting mismatched sample lengths.
- Implemented separate splits, conservative source/model/reference/lock/evaluator fingerprint, explicit development-review freeze, exclusive pre-call consumed marker. Any failed/interrupted heldout run stays consumed; changed config/evidence or rerun refused. Guards are unsigned/local, not privileged-writer protection.
- Added 19 protocol/mutation-verdict unit cases; executed: 19 PASS. Original 83 affected assurance/readiness tests PASS. Re-ran development: 32 cases; Attack Lab: 48 runs, 0 unsafe releases. Frozen labels/digests unchanged. Actual heldout never interpreted; protocol fixtures are simulated isolated records, not provider evidence.
- Next: missing-key path and focused safety regressions.

## C — Live Gemini: BLOCKED (offline missing-key checks PASS)
- Supported configuration reports key absent, value never printed. `live_check.py --cases 1` exit 2 and `assurance_eval.py --live --confirm-cost` exit 2; zero calls. Added single-case CLI smoke (optional --cases 3 remains), same supported model/settings. No fabricated provider metrics.
- Private setup and smoke → development → freeze → separate once-only heldout documented. No prompt/rule tuning on heldout.
- Next: continue all offline security/UI/recovery work without waiting for key.

## D — Security regressions: PASS for executed scope
- Added red tests: malformed adapter results (None/empty/string/invalid/constructed model) escaped the guarded extraction boundary; overlapping redaction matches exposed a long identifier suffix. Actual pre-fix run: 6 FAIL, 3 PASS. Fixed by schema revalidation inside guarded boundary and unioning mask spans. Post-fix affected integration run: 107 PASS. Labels unchanged, no safeguards removed.
- Security/lineage/workspace-completion integration: 68 PASS. Targeted recovery/workspace integration: 50 PASS.
- Strengthened mutation verdicts: require JUnit failure from the intended test and expected security assertion/reason; reject setup errors, unrelated failures and text-only FAILED. 7/7 actual targeted mutations caught for matched reasons. Four checker regressions cover false-kill rejection.
- Attack matrix now gives explicit PASS/FAIL per identifier/engine, alongside expected/actual and unsafe-release flags. 48 synthetic runs, 0 unsafe release, not a universal guarantee or real incident evidence.
- Next: actual browser and restore checks.

## E — Workflow and UI: PASS for executed scope; human study BLOCKED
- Actual Chromium: analyst → verifier → auditor, masked/revealed comparison, bundle export and 390px audit view PASS. Added and executed real keyboard tab-order/focus/Enter-login checks, missing-key visible failure/no fallback, and role-specific absent controls. Full keyboard-only journey/screen-reader audit not claimed.
- Current Attack Lab browser/download PASS. Restored-store browser login + matching VERIFIED case/HOLD gate + integrity-checked bundle PASS. No provider call or real participant involved.
- Human usability remains unconducted; consent/task/observation/feedback forms prepared. Next: supply chain and final regression.

## F — Supply chain/deployment/recovery: PASS for available checks, external checks BLOCKED
- pip-audit against 60 locked entries: exit 0, no reported known advisories; unhashed-lock warnings retained. Pyflakes exit 0 after removing one unused new-test import. No blanket dependency upgrade.
- Resolved existing action major tags to actual remote commit SHAs and Python/Caddy tags to registry digests; pinned them, disabled checkout credential persistence. Actual tag/digest provenance recorded; Docker build NOT RUN (no executable).
- Downloaded actionlint v1.7.12, verified published SHA256 before execution; actual workflow validation exit 0. Remote CI/public TLS/domain/identity deployment NOT RUN; no resources provisioned. Public main read by ls-remote; no remote configured or GitHub token variable; connector unsupported. No push attempted.
- New synthetic recovery exercise actually backed up, restored to a different temporary file, checked old-session rejection, active MFA preservation/pending cleanup, case state, receipts, read-only CLI, idempotency, replay denial and retention. Optional actual product browser on restored DB PASS. Temporary secrets/DBs destroyed, no production DB touched.
- Backup now verifies schema-3 chain/receipts before and after copy, refuses corruption with sanitized failure/exit 1 and deletes partial target; legacy backup remains possible without integrity claim. Corruption regression PASS and original source DB unchanged. This is not host disaster recovery or external rollback reconciliation.
- Added archive/manifest verifier and strict package filtering to committed paths; tests: 9 PASS before added corrupt-backup regression, then recovery/workspace integration 50 PASS. Repeated package tests and tamper/identity/size tests run in isolated fixture repos.
- Next: full final release gate; current collector measured 817. Commit only after applicable gate and archive/browser checks.

## G — Full regression and independent candidate verification: PASS (available scope)
- Final-code precommit release gate: exit 0, 12/12 steps PASS, **817 passed in 60.28s**, zero skips. Earlier expanded runs passed at 54.57s/56.81s; final raw summary/JUnit copied as precommit evidence, not relabelled as committed-source evidence.
- Actual archive/manifest verifier PASS. Added previously omitted `.gitattributes` to required source packaging; targeted package tests PASS and full gate rerun. Added privacy-safe per-case extraction metrics/latency/observations so future development failure analysis is not limited to final gate labels; protocol tests and full gate rerun.
- Extracted latest candidate into a second new directory, fresh lock/browser installation: release gate exit 0, **816 passed, 1 skipped in 51.64s**. The sole skipped full-history scanner test requires .git; secret-history step WARN, not false PASS. All other candidate steps PASS.
- From that extraction: actual browser-team, Attack Lab and restored-product browser workflows each exit 0. No key/provider call; no production data. Final archive will be rebuilt/byte-verified after commit, then independently checked again.
- Dependency/secret/static/actionlint findings: no advisory finding; unhashed-lock warning remains; secret/history scan exit 0; static exit 0 after one unused-import fix. Docker/live/public deployment/human checks remain explicitly BLOCKED/NOT RUN.

## H — Review and synchronization
- Reviewed focused diffs, immutable action/image provenance and required files. Current documentation supersedes historical commands/counts; frozen labels unchanged. All feasible precommit gates now pass. Stage/review only intended feature-branch files; original dirty main remains untouched.
- Local commit, final clean-source package identity, repeated-build/hash/committed-blob checks and postcommit/extracted evidence are generated after this log is committed. The final external report/manifest record their actual new commit/hash/status (not a self-referential placeholder in committed source).
- Remote publishing BLOCKED: connector unsupported, no configured remote/authenticated Git credentials established; no GitHub token variable, no push/main merge/force-push. Independent human/security assessment and infrastructure prerequisites remain genuine external work.
