# ThreadGate

**AI interprets the email. Code verifies the change against the record. A human attests before anything executes.**

An action-level gate for payment-detail change requests that arrive by email.

---

## The problem, stated as the track asks it

Fraud enabled by AI.

AI makes fraudulent email *fluent*. That matters because the traditional tell —
bad grammar, odd phrasing, a strange greeting — is gone, so **any control that
judges the wording of a message gets weaker every year**. What does not get
weaker is checking the *thing the email asks you to do* against a record you
already hold: if the email asks you to pay a different bank account, no amount
of good writing makes that account the one on file.

ThreadGate is built on that split. The model's job is to read the email. The
code's job is to compare what the email asks for against the vendor record, and
to decide. The model never gets a vote on the verdict.

The loss event in invoice-redirection fraud is not the email. It is the changed
bank detail reaching the payment run. So that is what gets gated.

## What it does

Paste in a vendor email. ThreadGate returns one of three decisions:

| Decision | Meaning |
| --- | --- |
| **HOLD** | Cannot execute without out-of-band human verification. A diff against the record is shown, plus a callback checklist. |
| **ALLOW** | The change is pre-registered or low-risk and the destination is already verified. |
| **NO_CHANGE** | The email asks for nothing. Nothing to gate. |

`HOLD` is a review state, not an accusation. Most held mail will turn out to be
legitimate; the cost of a hold is a phone call, and the cost of a miss is the
money.

## How it works

```
email ──▶ normalise ──▶ token finder ──┐            (code)
                                       │
       ┌───────────────────────────────┴──────────┐
       │  Gemini: "what change does this ask for?" │  (model - interpretation only)
       └───────────────────────────────┬──────────┘
                                       ▼
                            evidence validator     (code - closed world)
                                       ▼
                         comparator / diff vs record (code)
                                       ▼
                              invariants            (code - never sees the model)
                                       ▼
                             policy engine          (code - monotone)
                                       ▼
                            ALLOW / HOLD / NO_CHANGE
```

### Why this is not a wrapper

Three things sit between the model's output and the decision.

**1. The evidence validator (the closed-world rule).** The model may only emit
structured claims, and every claim must carry a quote. A claim is admitted only
if the quote is found verbatim in the email *and* the value it reports is
locatable in the email or in that quote. A value the model produced from memory
or inference is dropped, not repaired. Hallucination is not a risk score to be
thresholded here; it is a claim that never enters the pipeline.

**2. A deterministic policy the AI cannot override.** The decision rule is
monotone. Triggers can move a request towards `HOLD`; none can move it towards
`ALLOW`. The model's contribution enters as verified claims, and a verified
claim can add a hold trigger but can never remove one.

**3. A measured comparison against a rules-only baseline**, and an adversarial
harness that measures the system with the model working against it. Both are
below, both are reproducible with one command.

### The security model, in one sentence each

- **AI-independent floor (I1).** If a number in the email looks like a bank
  account and it is not the account on file and not a pre-registered alternate,
  a human looks at it. The model is not asked.
- **No-change must be evidenced (I2).** A `no_change` verdict is accepted only
  if the model quotes the sentence that says so.
- **The quote must support the verdict (I2b).** Added after an ablation found
  the hole: a steered model can return `no_change` with a quote copied verbatim
  from the email, which passes I2 because the words really are there. I2b
  requires the quoted sentence to actually assert that nothing is changing.
- **Change asserted, nothing verifiable (I3).** "Our details have changed, see
  the attached PDF" is held as unverifiable, because there is no value in the
  message to check.

## Evaluation

**40 frozen cases** (`data/cases/frozen_v2.json`), labelled with the decision a
competent payments controller would reach from the email plus the vendor
record. Composition: 11 true changes, 9 no-change/mention traps, 6 benign
changes, 11 adversarial, 2 token-less requests, 1 forwarded-attack.

The set was written in two tranches. The first 20 were written alongside the
system, which is a weakness, so the second 20 were written afterwards from
attack patterns and from the failure modes I could already see in my own design
— soft-hyphen splitting, fullwidth digits, a Cyrillic look-alike in the word
"account", an injection hidden in a signature block, a new account placed in an
image while the text shows the account already on file. `frozen_v1.json` is
kept untouched so the difference is auditable.

Two error types are counted separately, because they cost different things:

- **unsafe** — a case that should be held was not. This is the only error that
  can lose money.
- **false hold** — a case that should have gone through was sent to a human.
  Costs review time.

| System | Accuracy | Unsafe | Safety | False holds |
| --- | --- | --- | --- | --- |
| Rules-only baseline (raw text) | 55.0% | 4 | 84.0% | 12 |
| Rules-only baseline + normalisation | 65.0% | 0 | 100% | 12 |
| **ThreadGate (Gemini)** | *pending — see below* | | | |
| ThreadGate, model steered to say "no change" | 70.0% | **0** | 100% | 10 |
| ThreadGate, steered model forging a verbatim quote | 70.0% | **0** | 100% | 10 |

Reproduce:

```bash
python eval/run_eval.py --cases data/cases/frozen_v2.json \
    --systems rules_raw rules_norm gemini compromised compromised_q
```

**The baseline is not a strawman.** It is two rules: flag an 11–18 digit number
that is not on file, and flag change language co-occurring with a payment noun.
That is a fair stand-in for a first-pass control. It can never return `ALLOW`,
so every legitimate change costs a manual review, and it cannot read negation,
so "we are *not* changing our bank details" and "please change our bank
details" are the same string to it. Running the same rules over normalised text
is reported separately so the two effects do not get conflated: normalisation
alone fixes the obfuscation cases and none of the intent cases.

**The steered-model rows are the point.** A model that has been fully
compromised — always reporting `no_change`, in one variant not even bothering
to justify it, in the other forging a verbatim quote from the email — buys
**zero** unsafe outcomes. It buys friction: accuracy falls to 65% and six
legitimate emails go to a human instead. The gate fails closed.

**ThreadGate (Gemini) is pending** because the evaluation must be run against
the real model before any number is quoted here. The `offline` extractor in the
repo is a deterministic test double so the test suite runs without a key; it is
a rules engine with a JSON interface and its score is *not* the result being
claimed.

## Honest limits

Read this part.

- **40 cases is a demo, not an evaluation.** It is a set I designed, and half of
  it was written with the system already in front of me, so a high score on it
  partly measures my ability to anticipate my own system. It is enough to show
  the mechanism and to catch regressions. It is not evidence of a field error
  rate, and none is claimed.
- **The floor only covers the loss event.** I1 catches an unrecognised account
  number. Risk that lives in other fields — a beneficiary rename, a currency
  switch, a token-less request — is caught by the model's reading, and a steered
  model can suppress it. I3 partially covers this. It is the real boundary of
  the design.
- **The vendor record is synthetic.** All vendors, accounts, IFSC codes and
  emails in `data/` are fabricated.
- **No mail-flow integration.** This gates a pasted email. It is not wired to
  Gmail, Outlook, or an ERP.
- **Not a replacement for callback verification.** ThreadGate decides *when* a
  human must verify, and hands them the exact diff and a checklist. The human
  still makes the call.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # put your GEMINI_API_KEY in .env; it is gitignored
python scripts/kill_gate.py # go/no-go checks; read this before trusting anything
python -m pytest            # 54 tests, no network needed
python eval/run_eval.py --cases data/cases/frozen_v2.json --systems rules_raw rules_norm offline
streamlit run app/streamlit_app.py
```

Deployed: the key is read from Streamlit secrets (or `.env` locally) and is
never written to the repo, logs, or the UI. See `docs/DEPLOY.md` for the
Streamlit Community Cloud steps.

## Layout

```
src/threadgate/
  normalize.py   text normalisation with offset preservation
  tokens.py      deterministic token finder (account/IFSC/IBAN/amount/phone)
  extract.py     the model call + the two adversarial harnesses
  validate.py    the closed-world evidence validator
  compare.py     field-level diff against the vendor record
  invariants.py  I1/I2/I2b/I3 - the checks that never see the model
  policy.py      the monotone decision rule
  baseline.py    rules-only baseline, for the measured comparison
  pipeline.py    orchestration
data/cases/      frozen case set
data/records/    synthetic vendor master
eval/            evaluation harness and reports
app/             Streamlit demo
```

## Track

Devpost hackathon, **AI + Cybersecurity** track.

Complementary to ingestion-side filtering: tools that screen incoming mail for
prompt injection and phishing sit *upstream* of this. ThreadGate assumes a
hostile email has already arrived and gates the *action* it requests.

## Prior work

Everything here was built during the hackathon window. See `PRIOR_WORK.md`.
