# Seven-minute synthetic demonstration — no payment approval

**Purpose:** explain the existing boundaries, not prove Gemini accuracy or production
security. All data/roles/callbacks are synthetic. No real participants or actual
external callback results are implied. Never open a production database for this demo.

## Reproducible automated path

```bash
python -m pip install -r requirements.lock -r requirements-browser.txt
python -m playwright install --with-deps chromium
python scripts/browser_smoke.py --output data/runs/demo-team
python scripts/browser_attack_smoke.py --output data/runs/demo-attack
# Optional separate recovery segment:
python scripts/recovery_check.py --browser --output data/runs/demo-recovery.json
```

These bounded scripts create/destroy temporary synthetic accounts and stores,
start the actual interfaces, and retain only safe summary/screenshots/downloads.
No API key is needed or used. The team/Attack Lab regression pins its reference
clock to 2026-10-06 in a test-only wrapper outside the shipped product, explicitly
reported; no product authentication/clock bypass is added.

## Narrated outline

| Time | Show | Say / verify |
|---|---|---|
| 0:00–0:40 | Separate analyst/verifier/auditor workflow | "AI interprets, code compares/escalates, an authenticated account attests. Nothing executes a payment." |
| 0:40–1:40 | Analyst inspects built-in synthetic TG-001 using offline | "This extractor is a deterministic test double, not Gemini evidence." Inspect extracted evidence and trusted/requested values; distinguish validated claims from guesses. |
| 1:40–2:30 | Masked comparison then explicit reveal | Defaults expose only intended suffixes. Reveal the synthetic destination difference deliberately, then re-hide. Masking is not complete PII removal. |
| 2:30–3:10 | HOLD and control trace | Unknown destination forces escalation independently of model prose. HOLD is not an accusation of fraud. CLEAR would not be payment approval. |
| 3:10–4:00 | Save, assign separate verifier, sign out/in | UI role controls and server assignment/revision checks are distinct. Separate accounts do not prove distinct real people. |
| 4:00–5:00 | Verifier reinspection/preview; simulated callback attestation | "This is a synthetic role-play callback, not a real external call." Use trusted contact on file, never replacement details in the message. Reinspection binds full source/reference/current revision. |
| 5:00–6:00 | Auditor sees VERIFIED workflow alongside HOLD gate, audit/bundle | "VERIFIED is an authenticated verification attestation, not payment authorization or proof a callback occurred." Metadata export is not a signed authenticity certificate. |
| 6:00–7:00 | Attack Lab suppressing model simulation; local integrity view | Show a simulated compromised extractor, not a real Gemini compromise. Audit links detect specified changes against a local head, not privileged full-store rewriting. End with limitations and blockers. |

Optional recovery: show only the recovery script's PASS assertions and a restored
synthetic bundle; do not expose temporary credentials, seed values, DBs or backups.

## Manual local walkthrough if desired

Use a new private demo DB path and stop if it already exists; never delete/reset an
existing workspace to prepare the demonstration. `manage_workspace.py --username
demo-owner` prompts privately. Start `python scripts/serve.py --no-install --address 127.0.0.1` under the same chosen
`THREADGATE_WORKSPACE_DB`, create separate synthetic role accounts in Team
administration and keep their passwords private. Do not show bootstrap/password/
MFA enrollment screens in screenshots. Use a loopback-only listener on your local
machine; no public hosting is authorized by this outline.

Reference freshness is a real input: the manually running product uses current
time. If fixtures become stale, explain the escalation; never edit dates just to
make a demo CLEAR. Use the reproducible wrapper for date-pinned regression evidence.

## Optional live segment — separate, paid, currently BLOCKED

Privately configure a key, then `python scripts/live_check.py --cases 1`. Only call
that a real provider integration result after actual success. Do not substitute
an offline response or replayed JSON while claiming live Gemini. Development and
once-only heldout evaluation follow `EVALUATION_REVIEW.md`; do not run heldout as a
repeated stage demo. Zero current live samples means no accuracy/usage/cost claim.

## Stop and disclose

Stop on raw secret/real financial data, a failed role/binding check, missing reference
or unavailable provider. Show an explicit failure rather than relabelling it success.
No participant study/security audit/deployment approval has occurred. The closing
slide should list actual test scope, pending independent labels, absent key/Docker/
remote CI, host/TLS/security review and usability/accessibility limitations.
