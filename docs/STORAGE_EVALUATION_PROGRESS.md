# Storage-budgeted evaluation continuation — 2026-10-25

## Storage contract and baseline checkpoint

Platform quota verification: **BLOCKED**. Available tools expose filesystem sizes,
not an account/artifact-quota API or dashboard. Thus neither filesystem `df` nor this
log certifies the owner's platform usage. Owner reports 128 MB total/103 MB used;
MB versus MiB and whether retained artifacts/conversation count cannot be verified.
Environment snapshot guidance excludes environments/caches/generated directories,
but is not a live quota counter. Use decimal 128,000,000 as the stricter ceiling;
reserve 5,000,000; additional operations capped at 20,000,000. Stop on adverse quota
information. Do not infer permission to consume the 20 GB shown by `df`.

Measured before writes: snapshot-eligible logical files 108,297,485 bytes, 2,377
files (credential exclusions not subtracted); whole workspace allocated 114,435,072
bytes. Conservative baseline uses the larger allocated value: 13,564,928 remaining,
8,564,928 usable after reserve. Logical usage is ~103.28 MiB, plausibly the owner's
103 figure, but not confirmed. `/tmp/arena-workspace` is the backing workspace, not
a separate quota entitlement. Virtualenvs/caches from the prior session are absent.
Shared Git metadata lives in original `ThreadGate/.git` (~4 MB pack), not the 1 KB
worktree pointer; preserve it and all original source/history. Source active tree
~22 MiB, data/runs ~13 MiB, release ~3.5 MiB. Multiple earlier scratch extractions
are ~9–11 MiB each; retained because their full disposition was not established.

Individually verified cleanup: SHA256-equal disposable reproduction scratch ZIPs
`data/runs/workflow-20261025/first-final.zip` (3,604,976 bytes) and
`data/runs/assurance/reproducibility-first.zip` (2,933,870 bytes) removed ONLY after
comparison with retained `/home/user/ThreadGate-End-to-End-Release.zip` and
`ThreadGate-Engineering-Assurance.zip`. No deliverable/source/evidence/history or
original workspace deleted. Freed 6,538,846 logical bytes; allocated after cleanup
107,889,664 bytes. Conservative headroom now 20,110,336, usable 15,110,336 after
reserve; operational ceiling is min(this headroom, 20 MB additional).

Preflight estimates: research metadata/CSV at most 1 MB read in memory, no raw data
saved; new docs/packet/tests <150 KB, Git objects <300 KB; final ZIP <4 MB,
manifest/report <150 KB; clean extraction <5.5 MB if still safe. Full runtime install
includes absent pyarrow, streamlit and SDK and cannot be assumed to fit; estimate
wheel/unpacked sizes before any installation. Avoid duplicate final ZIP: reuse
canonical release path only, prior delivered ZIP retained elsewhere. One final build
only; supported gate includes packaging so do not package separately during development.
Reserve 250 KB for final evidence/report. Check bytes again before install/build/extract.

## Phase 0 — PASS inspection, quota counter BLOCKED
Actual `engineering-assurance` at b03ca2e9cb3ee44c9649d1d5ab77e7a05884fcb7,
initially clean; remotes empty. GitHub connector unsupported; no authenticated push
route established. Read current progress/review/release scripts and previous final
report. Historical 820/819 test results are not current results. Global Python 3.13.16
has pytest/pydantic but lacks dotenv, pyotp, Streamlit, Google SDK and pyarrow.
No dependency install or full extraction started. Next: finish source suitability
assessment, then blinded packet; preserve original labels/metrics.

## Phase 1 — PASS suitability assessment
`docs/benchmarks/SUITABILITY-v1.md` records pinned source, bytes/SHA256, schemas,
class counts, notebook rubric/generation, rights limits and task-level decisions.
Bounded in-memory source reads only; no dataset/archive persisted. BEC-1 20/20
messages overlap BEC-2, neither has destination/reference gold; DOI is same source.
ABH 2026 benchmark is synthetic 300/150+150, artifact access/license unresolved.
No external adapter or score justified. Research is not independent validation.

## Phase 2 — PASS preparation, human adjudication BLOCKED
Prepared versioned 3-case packet with account aliases, opaque review IDs, whitelisted
email fields only; coordinator mapping/hashes separate from reviewer distribution.
Instructions define active/history/hypothetical/cancelled/ambiguous/unchanged roles,
field evidence, vendor identity uncertainty and two-reviewer/third-adjudicator process.
Original annotations/results unchanged. No reviewer or consensus fabricated.
`PYTHONDONTWRITEBYTECODE=1 python -m pytest -o addopts= -p no:cacheprovider -q tests/test_annotation_review_packet.py`: 3 passed, 0.03s.

## Phase 3 — PASS efficient preparation; no compatible external gold
Only metadata and sanitized derivatives stored; no raw external messages, model
outputs or redundant v1 export added. Original hashes tested; no denominator/scoring
change. Runtime dependency metadata inspected before installing: Streamlit wheel
~9.8 MB and pyarrow wheels up to ~57 MB, plus expansion/dependencies. Full locked
runtime installation cannot safely fit this operational budget; do not start it.
Two exact locked helpers (dotenv/pyotp) total <100 KB compressed; reserve 1 MB peak
for minimal target install, no cache/no dependencies. It enables broad offline tests,
not a claimed complete runtime/fresh install. Next: missing-key smoke and regression.
All phases at starting commit b03ca2e9; only new documented files/scripts/tests dirty.

## Phase 4 / dependency diagnosis checkpoint
Supported missing-key smoke exit 2, no provider call. New packet tests pass.
Initial mixed targeted suite: 14 pass/11 fail, all failures missing google-genai
metadata; full suite: 766 pass/25 fail/32 errors, dependency-related SDK/UI paths.
Do not change tests or claim a passing gate. Streamlit actual wheel 10,364,948 bytes,
unpacked 29,150,064: alone exceeds 20 MB operations. Bounded HTTP Range reads of
wheel central directory established sizes without downloading full wheels.
SDK wheel 1,222,487, unpacked 5,866,843; google-auth 267,911/956,261. A direct
prefix install (not --target double copy), no cache/bytecode/dependency resolution,
plus exact locked small support packages has a conservative 12 MB peak estimate.
Preflight allocated 108,320,256; 19,679,744 left, 14,679,744 usable after reserve.
Thus bounded SDK install fits; full UI runtime still BLOCKED. Reserve final report
and avoid new release packaging if final gate remains blocked. Diagnose and rerun
all tests; retain compact initial failure counts rather than verbose traceback dumps.

## Storage pressure checkpoint — no further installs/builds
After bounded SDK/support install: allocated workspace 119,515,136; remaining
8,484,864, reserve 5,000,000, operational headroom 3,484,864. SDK environment
9,131,187 logical bytes; do not install Streamlit or create an extraction now.
Inspection also found pytest retention had accumulated 24,514,560 allocated bytes
OUTSIDE snapshot root in `/tmp/pytest-of-user/{pytest-2,pytest-3,pytest-4}`. These
individually inspected, user-owned disposable fixture directories were removed
after preserving test summaries; no original project/Git metadata/evidence removed.
This is not counted by the documented workspace snapshot, but absent a platform
quota counter, all-phase peak compliance cannot be certified. Earlier full-test
fixture peak was not premeasured: do not present this as verified quota compliance.
No further space-intensive task is started. Existing scratch extractions/deliverables
remain untouched. Small report/commit transactions have reserved space.

## Phase 5 — focused PASS, full gate BLOCKED / executed failures disclosed
- Corrected current collection documentation 820→823 after 3 new tests exposed three
  documentation-truth failures. Original historical executed counts unchanged.
- Added missing exact locked tenacity (wheel <50 KB, <250 KB planned expansion) after
  diagnosing SDK import errors. No production code/test weakening or new skips.
- Final focused packet/documentation/model-failure/evaluation suites: **96 passed
  in 8.21s**, including previously failing SDK-dependent paths. 25 packet/evaluation
  tests separately passed in 0.41s. Provider-failure tests use a fake client, not Gemini.
- Last full-suite attempt BEFORE those final dependency/doc fixes: **778 passed,
  13 failed, 32 errors in 45.08s**. Three failures were stale count docs (fixed),
  32 errors missing tenacity (fixed and targeted retested); nine UI tests and one
  preflight test remain blocked by absent Streamlit. No later full green run claimed.
- Required `python scripts/release_check.py --require-history`: exit 1, preflight
  FAIL specifically Missing dependency: streamlit; stopped before tests/packaging.
  Environment blocker, not a release PASS. Full lock install cannot fit: Streamlit
  unpacked 29 MB alone exceeds operational budget, before pyarrow/dependencies.
- Missing-key smoke exit 2 confirmed; supported loader boolean false, private secrets
  file absent. Real provider calls/usage/cost/latency 0/not measured. No live dev,
  successful freeze or heldout inference. Private setup remains EVALUATION_REVIEW.md.

## Phase 6 — verified research checkpoint, NOT a new release
Research/packet are useful independent of the blocked complete runtime. No adapter
or external performance metric invented. No product safety code or original gold
changed. New final ZIP/extraction NOT RUN because the gate is not green and full
fresh install cannot safely fit. Canonical prior release/manifest retained at b03ca2e9;
never represent them as packaging the new research commit. No reproducibility claim
for a new archive. GitHub remotes empty, connector unsupported, token variables/
credential helper/SSH agent absent: push BLOCKED, no push or main merge attempted.
Docker absent; remote CI, public TLS, external identity, human studies and independent
security review remain NOT RUN. Next: provision adequate authorized test storage/
locked runtime and independent humans before declaring a feature release.
- Additional bounded in-memory checks: kill gate exit 0 (18 invariants); Attack Lab
  actual synthetic pipeline 48 runs/0 unsafe releases, provider_called=false;
  offline original development 32 cases. Only compact aggregate evidence saved in
  benchmarks/validation-checkpoint-v1.json, no duplicate raw messages/model exports.
- Secret/tree/history scan exit 0; new script AST parse PASS; diff whitespace PASS.
  Prior b03 archive still verifies 238 committed entries, unchanged; it is NOT a
  release of this continuation. No new release/ZIP reproducibility claim.

Final precommit cleanup checkpoint: SDK prefix installed by this pass removed only
after validation, pins/results retained. Verbose new dependency/trace logs compacted
to checkpoint JSON; prior results/deliverables preserved. Allocated workspace
108,254,720 bytes; decimal remaining 19,745,280; 5,000,000 reserve.
Final packet rerun PASS; final commit/report will state exact identity outside source.
No further installation, full-suite retry, archive or extraction starts.
