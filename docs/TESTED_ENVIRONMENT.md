# Tested environment

The exact combination this project was verified against, and the sequence used
to verify it. Reproducing this in a clean environment is the check that the
repository installs and runs at all, which is not something the test suite can
prove on its own - the suite only runs *after* an install has succeeded.

## Tested on

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
#   (streamlit run app/streamlit_app.py is equivalent when streamlit is on PATH)
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
