# ThreadGate / Workbench upgrade

## Start here

```bash
python -m venv .venv
# Activate the environment using your platform's command.
pip install -r requirements.txt
python scripts/serve.py --demo
```

Open the displayed address, normally http://localhost:8501. The default launcher now opens the authenticated `app/product.py`;
`--demo` opens `app/workbench.py`. For hosting the synthetic demo only, set `app/workbench.py` as its entrypoint.
For the authenticated product foundation, use `app/product.py`.
See docs/PHASES.md for the subsequent product phases.
The original research interface is preserved at `app/streamlit_app.py`.

The default engine is **offline**, a deterministic test double. It needs no key.
For Gemini, configure `GEMINI_API_KEY` in a local .env or Streamlit secrets and
choose the live engine. `THREADGATE_MODEL` optionally selects the model.
No keys are included. Never publish your .env or secrets.toml.

## What changed

- Midnight navy, violet and cyan responsive workbench with separate investigation,
  Attack Lab, evaluation and explanation views.
- Inspect explicitly; input or engine changes invalidate the displayed result.
  Selecting a page does not automatically call a paid model.
- Exact finding spans highlighted in escaped source text; field-level destination
  comparison, verified quotes and control trace remain available.
- Attack Lab uses existing compromised / compromised_quote simulation harnesses.
  They are not described as live-model attacks or a new independent benchmark.
- Trusted-record callback walkthrough. Synthetic events are clearly marked as
  unauthenticated. There is no payment approval or release action.
- Transactional local SQLite consumed-event store, with commit-before-acceptance,
  unique event identifiers and serialized consumers. Rejections burn an event.
- Privacy-minimised JSON case export omits raw email, quotations, destination
  values and contact details. It retains case/vendor identifiers and control codes.
- Checked-in evaluation dashboard explicitly reports whether Gemini was evaluated.
- Regression tests for storage restart, concurrency, mismatched bindings, storage
  failure, exports, pasted-email binding and workbench page interactions.
- CI and a reproducible, size-enforced source ZIP packager.

## Durability boundary

`THREADGATE_DB` sets the database path; the default is
`data/runs/attestations.sqlite3`. The folder is excluded from source archives.
Back it with persistent local storage. The store survives process restart on the
same retained filesystem, not deletion or ephemeral-host redeployment. It is not
a distributed service; do not put SQLite on an unsupported network filesystem.
A storage error is not accepted verification. Do not run with an unwritable or
untrusted database location. Backups and retention remain operator responsibilities.

The legacy `AttestationStore` and original research UI retain their documented
in-memory semantics. Only the workbench uses the new persistent adapter by default.
The existing deterministic pipeline and CLEAR / REVIEW / HOLD semantics are unchanged.

## What is deliberately not claimed

No authenticated verifier identity, RBAC, independent proof of callback, bank/ERP
connection, payment execution, live mail ingestion, attachment OCR, automatic
reference update or production approval. A typed or synthetic identity is not an
authenticated principal. Demo events are labelled `DEMO / unauthenticated`.
Do not use the public UI as an authorisation boundary.

Gemini evaluation still requires an actual key and successful completed run:

```bash
python eval/run_eval.py --require-gemini
```

No fresh independent holdout was fabricated in this upgrade. Existing corpus cases
remain development/demo evidence, not a production fraud rate. Future work should
freeze independently authored cases before measuring performance. The workbench
uses real current time for investigations; benchmark dates remain pinned by the
existing evaluation harness. Old references can therefore be STALE during live use.

## Three-minute walkthrough

1. Investigate: select a destination-change case; inspect with the offline test
   double. Explain that this is simulation, not measured AI performance.
2. Show the record-to-request diff, highlighted text, verified quotes and controls.
3. Attack Lab: select a compromised extractor and inspect an unknown-destination
   request. Show which deterministic findings survive manipulated interpretation.
4. Verification: use the trusted contact, tick the synthetic walkthrough steps,
   record a demo event, then test replay. The gate decision does not downgrade.
5. Download the privacy-minimised report. Open Evaluation and show the explicit
   live-model status and limitations.

## Verification and packaging

```bash
python -m pytest
python scripts/kill_gate.py
python scripts/secret_scan.py
python scripts/package_release.py
```

The packager includes allowlisted source/configuration/docs/data/test files and
excludes Git history, virtual environments, dependencies, caches, local secrets,
run databases and generated release archives. It rejects symlinks, enforces a
128,000,000-byte limit on BOTH compressed ZIP and total uncompressed contents,
and writes a manifest with per-file SHA-256 values. Keep the archive and manifest
together. Dependencies are installed separately; this is a source distribution.
