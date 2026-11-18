# Latest key-free product completion

The current release adds service-enforced MFA policy, submission retry protection,
session management, paginated inbox and snapshot case bundles. The full suite and
release checks were repeated in an isolated environment with requirements.lock.
An actual Chromium synthetic analyst → verifier → auditor flow, including the
case-bundle download, passed without provider credentials. Evidence is in
`docs/browser-validation/` and `docs/release-validation/`. This is not a live
Gemini, Docker-host, domain/TLS or remote CI result.

# Current release validation

The key-independent release was installed into a fresh `.venv` using
`requirements.lock` on CPython 3.13.16 / Linux. `scripts/release_check.py
--require-history` passed. Exact locked dependency versions are in the lockfile;
current validation logs are in `docs/release-validation/`. No live provider or
Docker/remote CI/domain test has been claimed. The historical environment notes
below refer to earlier stages, not a replacement for the current lock.

# Tested environment

The exact combination this project was verified against, and the sequence used
to verify it. Reproducing this in a clean environment is the check that the
repository installs and runs at all, which is not something the test suite can
prove on its own - the suite only runs *after* an install has succeeded.

## Authenticated product phases (2026-10-24)

The team workspace was locally tested on Python 3.13.16 with the dependency
versions listed in the workbench section below. The full suite, kill gate,
offline evaluation, source compilation and credential scan were rerun.
Logs are in `docs/product-validation/`. UI regression tests exercise the
analyst → verifier → auditor journey. Docker/Compose were not runtime-tested,
remote CI was not run, and no successful live Gemini evaluation is claimed.

## Workbench verification (2026-10-24)

The upgraded workbench was tested with Python 3.13, Streamlit 1.66.1,
pydantic 2.14.1, google-genai 2.33.0, python-dotenv 1.2.4,
pytest 9.0.3 and rich 15.0.0. The full suite passed, the kill gate passed,
and the tree/history credential scan was clean. Desktop and mobile browser
captures are in `docs/workbench/`. No live Gemini run was performed.

## Original upstream tested combination

| | |
|---|---|
| Python | **3.13.14** |
| pydantic | 2.13.4 |
| google-genai | 2.28.0 |
| streamlit | 1.65.0 |
| python-dotenv | 1.2.4 |
| pytest | 9.0.3 |
| rich | 15.0.0 |

Python 3.11+ is expected to work. It has not been tested on 3.11 or 3.12, so
that is an expectation rather than a claim.

## Verify a clean install

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pytest                   # no network, no API key required
python scripts/kill_gate.py        # go/no-go on the concept
make eval                          # every system except the model
python scripts/serve.py            # serves on http://localhost:8501
#   (streamlit run app/workbench.py is equivalent when streamlit is on PATH)
```

All five must pass before anything is claimed as working.

## What needs a key and what does not

| command | needs `GEMINI_API_KEY` |
|---|---|
| `pytest` | no |
| `python scripts/kill_gate.py` | no |
| `make eval` | no |
| `make eval-all` | **yes** |
| `streamlit run ...` with the `gemini` extractor | **yes** |

Without a key the app still runs: pick the `offline` extractor in the sidebar.
The `gemini` row of the evaluation table stays empty until a live evaluation has
actually been run, and the harness says so rather than filling it in.

## Notes

`playwright` is **not** in `requirements.txt` and is not needed to run or test
the project. It is used only by `scripts/capture_screenshots.py`, which is a
one-off authoring tool for the submission screenshots, not part of the app or
the suite. Install it separately if you want to regenerate them:

```bash
pip install playwright && playwright install --with-deps chromium
python scripts/capture_screenshots.py --extractor offline
```

The tests never drive a browser: every UI assertion is made against the source
or against the pipeline.


## Current workflow supersedes the historical notes above

Install runtime with `python -m pip install -r requirements.lock`. Browser automation
is now maintained separately in `requirements-browser.txt`, not just the old
screenshot authoring helper. `scripts/browser_smoke.py`,
`scripts/browser_attack_smoke.py` and `scripts/recovery_check.py --browser` actually
drive Chromium. Default pytest remains provider/browser-independent. See
`docs/WORKFLOW_RELEASE.md` and `docs/WORKFLOW_PROGRESS.md` for the current measured
runs; older environment notes/results are historical, not fresh validation.
