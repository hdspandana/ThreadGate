# Prior work statement

Hackathon: **Agent.ai / Devpost hackathon, AI + Cybersecurity track**
Hackathon window: **2026-10-03 12:00 EDT → 2026-10-10 12:00 EDT**
(2026-10-03 21:30 IST → 2026-10-10 21:30 IST)

## What existed before the hackathon started

Nothing. There was no prior repository, prototype, dataset, or write-up for
ThreadGate. The workspace used for this project was empty at the start of the
event. Every file in this repository — the case corpus, the token finder, the
evidence validator, the comparator, the invariant layer, the policy engine, the
rules-only baseline, the evaluation harness, the Streamlit UI, the README, and
the video script — was written inside the hackathon window.

The first commit in this repository is dated **after** the 2026-10-03 12:00 EDT
start time. See `git log --reverse` for the timestamp on commit 1.

## What is reused (and is not my own work)

These are third-party and open-source building blocks, used under their
respective licences and credited in the README:

- Google Gemini (`google-genai` SDK) — the language model used for the
  interpretation step only.
- Pydantic — schema definition and validation of model output.
- Streamlit — the demo UI.
- pytest — the test suite.
- Publicly published, well-known facts about business-email-compromise (BEC)
  and invoice-redirection fraud, used to design the case corpus. No
  proprietary or confidential data from any employer or client is used.

## Synthetic data

All vendors, bank accounts, IFSC codes, email addresses, invoice numbers and
email bodies in `data/` are **fabricated for this demo**. No real customer,
vendor, or bank record is used. Account numbers are made up and deliberately
formatted to look like a plausible Indian corporate account number.

## AI assistance

An AI coding assistant was used as a pair-programming tool during the
hackathon, which the rules permit. The design, the case corpus, the evaluation
methodology and all decisions about what to build are my own; the assistant
wrote code under my direction. This is disclosed rather than hidden because the
submission is about making AI output auditable, and it would be inconsistent to
be less transparent about my own process.
