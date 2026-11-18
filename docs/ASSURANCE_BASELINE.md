# Engineering assurance baseline

- Inspected 2026-10-25 (user local date); execution host clock reports 2026-10-24 UTC.
- Original branch: `main`; HEAD `5c5e387f2c3f49df6b61e5794bc2647b311cd54d`.
- Public main (`git ls-remote`): same HEAD. Public repository does **not** contain the uncommitted upgrades.
- Original working tree: 14 modified tracked files, no staged changes, plus untracked product/evaluation/deployment/test files. Copied 133 nonignored files into isolated `engineering-assurance` worktree; original files left untouched.
- Fresh CPython 3.13.16 venv, installed `requirements.lock`; baseline: **723 passed** (46.64s). No skipped tests.
- Existing ZIP: 1,984,778 bytes; all its source entries matched original working-tree files. It was a working-tree artifact, not a release of public HEAD.
- No provider key configured; no Docker executable. Real model, Docker, public TLS, remote CI, PostgreSQL and independent participant testing are not locally established.

## Reviewed surfaces

Core: normalize → token finder → extractor → evidence validator → comparator → invariants/policy → attestation. JSON vendor master and injected freshness clock. Product: workspace role/session/MFA checks; submit/idempotency, assign/revision, verify/replay, audit writer/read models, retention and backup. Streamlit entrypoints: authenticated product, unauthenticated synthetic workbench/Attack Lab, original research UI. There is no separate REST approval/payment API. SQLite is single-host, single organisation; no PostgreSQL suite exists.

## Demonstrated review gaps to address

1. Pipeline return indexes `case['id']`, although pasted input omits it; unknown vendor lookup raises before fail-closed processing.
2. Verification contexts bind a version string but not complete request/reference contents; same-version reference edits or reused fixture identifiers can escape the intended lineage contract.
3. Audit is transactional but has no tamper-detection tooling. Bundles carry only a snapshot, not an external integrity anchor.
4. Existing evaluation does not separately score raw extraction, has no reserved held-out annotations, and lacks reliable token/cost observations.
5. Sensitive field values appear unmasked in the product's comparison/source output. No independent usability observations were collected.
6. ZIP builder does not establish a clean final-commit identity.

Existing commands: `scripts/release_check.py`, `scripts/live_check.py`, `eval/run_eval.py`, `scripts/check_live_report.py`, `scripts/browser_smoke.py`, `scripts/kill_gate.py`, `scripts/secret_scan.py`, `scripts/package_release.py`; runtime `scripts/serve.py`; CI in `.github/workflows/verify.yml`. Evidence commands/outcomes for this upgrade are recorded in the final assurance report, not inferred from historical documents.
