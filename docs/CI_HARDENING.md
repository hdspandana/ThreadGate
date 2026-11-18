# Low-storage CI hardening — prepared, NOT remotely executed

## Checkpoint and budget

Started clean on engineering-assurance at f4cfd04e2d0f377a2905b4c8343d94f4ce3f88ab.
Initial allocated workspace 108,111,360 bytes; decimal ceiling 128,000,000,
reserve 5,000,000; usable headroom 14,888,640. Planned changes/commit/report <200 KB,
no installs, downloads, archive builds or extraction. Quota interface unavailable;
these are filesystem accounting, NOT account/artifact quota measurements.

## Implemented scope

Existing verify.yml, not a duplicate workflow: all four checkouts bind github.sha
and full history. A stdlib guard rejects absent/mismatched SHA or dirty checkout,
reports OS/Python and checks both workspace/temp filesystems for >=8 GiB before
installs/build work. This conservative floor covers runtime, Chromium, optional
audit tools, temporary tests and fresh extraction; actual remote adequacy remains
unmeasured. Package builder repeats the capacity check immediately before a real
GitHub workspace archive build. Guard does not certify account retention quotas.

No pip cache. Pytest temporary retention disabled, not test execution. Original full
12-step release gate UNCHANGED; container and all three browser/Attack Lab/recovery
checks precede it. Advisory/static checks precede packaging too. Gate builds one
candidate only after functional checks; explicit --require-commit then fresh
extraction/locked install/full extracted pytest + kill/recovery validate that same
archive without repackaging. Temporary extraction/environment auto-disposed remotely.
The no-Git extraction's existing history limitation must be reported, never hidden.

Only one pinned upload-artifact action remains: ZIP + manifest, success-only after
fresh checks, retention 1 day, additionally requires repository variable
THREADGATE_ARTIFACT_UPLOAD_APPROVED=true. Owner must confirm artifact allowance;
absence of approval means NO upload, not permission to claim publication.
No failure artifacts/raw logs/screenshots/provider reports uploaded. Guard-wrapped
commands suppress raw stdout/stderr and emit exit codes plus gate step/status/exit
metadata; raw output is discarded, not retained as a secret-bearing diagnostic.
This trades detailed tracebacks for privacy; investigate failed steps in an approved
private runner if those compact diagnostics are insufficient. Live job remains
opt-in/protected and follows offline success; no second archive or raw AI export.

## Reviewer data / PUBLIC PUSH BLOCKED

Inspection found a coordinator-only file tracked and reachable in one historical
commit. No mapping contents printed; original mapping, annotations and sanitized
packet preserved. No real reviewer responses found. Secret tree/history scan is
heuristic, not privacy certification. Local history presence does not prove public
exposure; if previously published, assume blinding potentially compromised.

Public CI fails before installs when reachable history includes coordinator-only,
reviewer-responses or private-labels paths. Packaging excludes those paths and the
verifier rejects them, including on private CI. Packet regression still fully tests
its generated mapping; exported source tests validate regeneration when the private
coordinator file is intentionally absent. No skips or original labels changed.

IMPORTANT: workflow guards cannot prevent the Git PUSH itself from exposing history.
Do NOT push this branch/history to the public repository. Archive exclusion and
.gitignore do not erase history or restore blinding; source code and old synthetic
gold can also reconstruct relationships. A genuine fresh/private human-review route
is needed, not a claim that the old packet is now blind. No history rewrite,
untracking/deletion, credential changes, remote configuration or push performed.

## Available local validation

- Standard-library unittest discovery: 3 new regressions PASS; initially one brittle
  source-text count assertion failed (15 vs 12), fixed to inspect the AST's actual
  commands list; final 12-step assertion passes. No test/control weakened.
- Existing packet assertions: 3 PASS, invoked directly (not full pytest).
- Available PyYAML BaseLoader parse and bash -n for every run step: PASS; new helper,
  package/verifier AST parse and git diff --check PASS.
- actionlint absent: NOT RUN, no validator downloaded. No remote expression/schema,
  runner, install, Docker, browser or fresh-extraction execution claimed.
- New test count expected 826 (= historical 823 +3), NOT a full local collection or
  passing gate. Application, evaluation/scoring/prompt, lockfiles and original
  corpus bytes unchanged. Historical results remain historical.

## Exact owner handoff

1. Review complete diff/new commit and approve PRIVATE validation/publication policy.
   Establish credentials privately; never paste them into chat. No authorization or
   authenticated runner available here (connector unsupported, remote unset).
2. Use an explicitly authorized PRIVATE GitHub repository/runner preserving this
   exact commit/history. Check remote branch work before any normal non-force push.
   Do not publish existing history publicly; do not bypass the privacy guard by
   falsifying the repository-private environment variable.
3. Confirm Actions minutes/storage/artifact allowances. Checkout/run the new exact
   feature commit (not f4) with existing workflow; record run URL/attempt, event SHA,
   actual OS/Python and free space. Full default gate must pass with all required
   browser/container/audit checks, not a focused substitute. Any fix needs targeted
   regression then complete rerun at the new SHA.
4. Keep THREADGATE_ARTIFACT_UPLOAD_APPROVED unset until artifact policy is approved;
   set true only to allow the one success-gated PRIVATE ZIP/manifest artifact.
   Inspect actual bytes/counts/checksum/identity and extracted test outcomes/skips.
5. Separate future public distribution requires explicit owner review of historical
   exposure and a fresh/private adjudication plan. No automatic history rewrite,
   main merge, force push or GitHub Release creation. VERIFIED is authenticated
   attestation, not payment authorization or proof an external callback occurred.

Current phase: focused preparation complete, remote execution BLOCKED/NOT RUN.
Final commit/clean status and final storage are recorded in the external existing
report after local commit to avoid self-referential source identity.
