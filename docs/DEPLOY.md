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
- Run the corpus button (40 cases). With the model, expect no `unsafe` in the
  ThreadGate row and no `unsafe` in either compromised row.

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

## Notes

- The app is stateless; it writes nothing to disk and stores nothing about the
  emails it processes.
- The emails in the demo are synthetic. Do not paste real vendor mail into a
  public deployment.
- Free Community Cloud apps sleep when idle; expect a cold start of ~30s for
  the first judge who opens the link.
