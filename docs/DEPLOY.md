# Deploying to Streamlit Community Cloud

Target: a permanent public URL for the Devpost submission, with the API key
stored as a secret rather than in the repo.

## Before you start

- The repo must be public on GitHub. Devpost judges need to read the code.
- Confirm nothing sensitive is committed:
  ```bash
  git ls-files | xargs grep -l "AIza" || echo "clean"
  git check-ignore .env .streamlit/secrets.toml
  ```
  `.env` and `.streamlit/secrets.toml` are both in `.gitignore`.

## Steps

1. Push the repository to GitHub (public).
2. Sign in at https://share.streamlit.io with the same GitHub account.
3. **New app** → repository `threadgate`, branch `main`, main file path:
   `app/streamlit_app.py`
4. Click **Advanced settings → Secrets** and paste exactly:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
   Save. The app restarts and picks it up; the sidebar shows
   `API key: configured (ends ...xxxx)`.
5. `requirements.txt` is at the repository root, which Community Cloud picks up
   automatically. No `packages.txt` is needed — there are no apt dependencies.

## Verifying the deployment

- Sidebar shows `API key: configured`.
- Pick `TG-001` → **HOLD**, with `50100234559821` highlighted red and the
  record account `****4455` shown in the diff.
- Switch the extractor to `compromised_quote` → `TG-001` still **HOLD**. This is
  the claim the submission rests on; check it on the deployed URL, not just
  locally.
- Press **Run 20 cases across every system** (the default case set is `v1`, the
  primary benchmark). With the key configured the table must gain four rows that
  were previously listed as skipped — `gemini`, `ai_only`, `hybrid_no_scan`,
  `hybrid_no_validation` — and the skip warning must disappear. If it does not,
  the secret is not reaching the app; check the secret name is exactly
  `GEMINI_API_KEY`.
- Expect `unsafe` = 0 in the `gemini` row and in both compromised rows. Any
  non-zero `unsafe` is named in red beneath the table with its case IDs; treat
  that as a blocking defect, not a rounding error.
- Switch the case set to the combined set and re-run to see the stress numbers.
  Those are the only rows that may be quoted as stress results, never as field
  accuracy.

## If the key is missing at deploy time

The app still runs. `api_key()` returns `None`, the sidebar warns, and the
pipeline fails **closed**: an extractor error produces `HOLD` with reason
`extractor_failed_fail_closed`. A missing model must never look like a safe
email.

## Local equivalent

```bash
cp .env.example .env      # add GEMINI_API_KEY
streamlit run app/streamlit_app.py
```

`.env` is read via `python-dotenv` at import time and is gitignored.

## Re-capturing the screenshots

The screenshots in `docs/screenshots/` were captured from a running instance
with **no API key set**, so they show the `offline` test double and a
`Skipped without an API key` warning. That is honest, but it is not the shot you
want on the submission page.

Once the key is configured on the deployment:

```bash
python scripts/capture_screenshots.py --base-url https://<your-app>.streamlit.app --extractor gemini
```

That overwrites the five PNGs in place with captures of the real model path.
Verify afterwards that the corpus table has the `gemini` row populated. If you
capture locally instead, the same command against `http://127.0.0.1:8501` works
provided `GEMINI_API_KEY` is exported in that shell.

## Notes

- The app is stateless; it writes nothing to disk and stores nothing about the
  emails it processes.
- The emails in the demo are synthetic. Do not paste real vendor mail into a
  public deployment.
- Free Community Cloud apps sleep when idle; expect a cold start of ~30s for
  the first judge who opens the link.
- Capturing screenshots needs playwright plus its system libraries
  (`pip install playwright && playwright install --with-deps chromium`). The
  sandbox this was built in needed those installed before chromium would launch.
