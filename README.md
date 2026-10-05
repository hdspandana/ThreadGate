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
| **REVIEW** | A change was identified and it matches the record on file — a pre-registered alternate, or a field that is not a payment destination. A human still attests before anything executes. |
| **CLEAR** | **No change was identified by this prototype.** Nothing to gate. |

Three things about that table, because they are the difference between a gate
and a score:

- **CLEAR is not an approval.** It means this prototype did not identify a
  change to gate. It does not mean the email is safe, legitimate, or fraud-free,
  and it is never rendered in a colour or wording that suggests otherwise.
- **REVIEW is not a release either.** The change matched the record, which is
  necessary but not sufficient; a human still attests before anything executes.
- **HOLD** is a request for out-of-band verification, not an accusation. Most
  held mail will turn out to be legitimate; the cost of a hold is a phone call,
  and the cost of a miss is the money.

The escalation only ever runs one way: `CLEAR` → `REVIEW` → `HOLD`. No trigger
can move a decision back down it.

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
                            CLEAR / REVIEW / HOLD
```

The same thing as a trust-boundary diagram, with the one edge that does not
exist drawn explicitly: **`docs/architecture.svg`**. The model sits in the
untrusted half; the dashed line is the boundary; the crossed-out arrow from the
model to the verdict is the whole design.

Five screenshots of the running app are in `docs/screenshots/` — a benign
release, the canonical hold, a prompt-injection hold, the negation case where
the rules baseline is wrong, and the corpus table. They are captures, not
mockups, and every number in them was produced by the pipeline at capture time.
`scripts/capture_screenshots.py` regenerates them.

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
`CLEAR`. The model's contribution enters as verified claims, and a verified
claim can add a hold trigger but can never remove one.

**3. A measured comparison against a rules-only baseline**, plus two adversarial
harnesses that measure the system with the model working against it. All three
are below and all are reproducible with one command.

### The security model

Every invariant below is computed without looking at what the model said.

- **I1a — Unknown account floor.** If a number in the email looks like a bank
  account and it is not the account on file and not a pre-registered alternate,
  a human looks at it.
- **I1b — Unknown branch/routing code.** The same rule for IFSC, IBAN and SWIFT.
  The closed-world rule covers every supported destination token the scanner can
  see, not only account numbers.
- **I2 — No-change must be evidenced.** A `no_change` verdict is accepted only if
  the model quotes the sentence that says so.
- **I2b — The quote must support the verdict.** Added after an ablation found the
  hole: a steered model can return `no_change` with a quote copied verbatim from
  the email, which passes I2 because the words really are there. I2b requires the
  quoted sentence to actually assert that nothing is changing. Verdict and
  justification have to agree.
- **I3 — Change asserted, nothing verifiable.** "Our details have changed, see
  the attached PDF" is held, because there is no value in the message to check.
- **I4 — Destination out of band.** If the message says the account is in an
  image, a PDF or a portal, the destination cannot be read and is held. See
  below.

### What the gate does not do

- **No OCR, no attachment parsing, no image analysis.** Opening an
  attacker-supplied file to inspect it is not a control, it is an exposure. When
  the destination is not in the text, I4 holds it and the checklist tells the
  analyst to get the value over the phone. TG-034 is exactly this case: the new
  account is in an image, the only number in the text is the one already on
  file, so nothing looks wrong until you notice that the destination was never
  readable. It holds under every extractor, including a steered model.
- **No risk score.** Invoice value, vendor age, payment history and similar
  signals are deliberately absent. A numeric risk score can be argued with,
  tuned until it stops firing, and eventually waved through. A destination check
  cannot. An amount is reported to the analyst and decides nothing — the
  amount-based ceiling heuristic that was here earlier was removed for this
  reason.
- **No URL scanning, threat intelligence, embeddings, or vector search.** None
  of it is needed to answer the only question this gate asks.
- **Scope is explicit in the code.** `DESTINATION_FIELDS` is what the closed-world
  rule protects. Changes to instruction fields (currency, terms) and contact
  fields (advice mailbox, contact person, phone) are reported and policy-checked,
  but they are not what the gate is for, and none of them produce a score.
  `tests/test_scope.py` fails the build if any of that drifts.

## Evaluation

Three sets, reported separately, because they mean different things.

| Set | Cases | What it is | What may be quoted from it |
| --- | --- | --- | --- |
| `v1` | 20 | **Primary pre-frozen benchmark.** Written before any evaluation was run. | Performance claims. |
| `stress` | 20 | **Adversarial stress set.** Written *after* the first evaluation, from attack patterns and from failure modes visible in the design. | Robustness only. |
| `combined` | 40 | Both together. **A stress evaluation, not an unbiased benchmark.** | Nothing as a single accuracy number. |

Two error types are counted separately, because they cost different things:

- **unsafe** — a case that should be held was not. The only error that can lose
  money.
- **false hold** — a case that should have gone through was sent to a human.
  Costs review time.

### Set 1 — frozen_v1, primary pre-frozen benchmark (20 cases)

| System | Accuracy | Unsafe | False holds |
| --- | --- | --- | --- |
| Rules-only baseline (raw text) | 50.0% | 2 | 7 |
| Rules-only baseline + normalisation | 60.0% | 0 | 7 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 |
| ThreadGate, model steered to say "no change" | 65.0% | **0** | 6 |
| ThreadGate, steered model forging a verbatim quote | 65.0% | **0** | 6 |

### Set 2 — stress additions, written after the first run (20 cases)

| System | Accuracy | Unsafe | False holds |
| --- | --- | --- | --- |
| Rules-only baseline (raw text) | 60.0% | 2 | 5 |
| Rules-only baseline + normalisation | 70.0% | 0 | 5 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 |
| ThreadGate, model steered to say "no change" | 75.0% | **0** | 4 |
| ThreadGate, steered model forging a verbatim quote | 75.0% | **0** | 4 |

### Set 3 — combined, stress evaluation only (40 cases)

Not an unbiased benchmark. Shown for completeness and for the category view.

| System | Accuracy | Unsafe | False holds |
| --- | --- | --- | --- |
| Rules-only baseline (raw text) | 55.0% | 4 | 12 |
| Rules-only baseline + normalisation | 65.0% | 0 | 12 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 |
| ThreadGate, model steered to say "no change" | 70.0% | **0** | 10 |
| ThreadGate, steered model forging a verbatim quote | 70.0% | **0** | 10 |

### Where the reading is actually needed

Per-category accuracy on the combined set. `u` counts unsafe outcomes.

| Category | n | rules_raw | rules_norm | offline | compromised | compromised_q |
| --- | --- | --- | --- | --- | --- | --- |
| mention_vs_request | 6 | 17 | 17 | 100 | 50 | 50 |
| negation | 2 | 0 | 0 | 100 | 0 | 0 |
| cross_message | 3 | 67 | 67 | 100 | 67 | 67 |
| obfuscation | 5 | 20 **(u4)** | 100 | 100 | 100 | 100 |
| contradiction_ambiguity | 3 | 100 | 100 | 100 | 100 | 100 |
| tokenless_implicit | 2 | 100 | 100 | 100 | 100 | 100 |
| explicit_change | 6 | 100 | 100 | 100 | 100 | 100 |
| prompt_injection | 5 | 100 | 100 | 100 | 100 | 100 |
| social_engineering | 2 | 100 | 100 | 100 | 100 | 100 |
| benign_preregistered | 2 | 0 | 0 | 100 | 0 | 0 |
| benign_low_risk_field | 4 | 0 | 0 | 100 | 0 | 0 |

Read that table carefully, because two rows flatter the baseline:

- `prompt_injection`, `social_engineering` and `explicit_change` score 100% for
  the rules baseline **because it holds everything**, not because it detects
  anything. That is the same behaviour that produces 0% on the benign
  categories. Accuracy averages the two out; the category view does not.
- `obfuscation` is the one category where normalisation alone closes the gap:
  20% with 4 unsafe becomes 100% with 0. Character-level evasion is a code
  problem, and it is solved in `normalize.py`, not by the model.

The categories where reading is genuinely required are **mention_vs_request**
(talking about a destination vs asking for it to change), **negation** (reading
"not" in context) and **cross_message** (which end of a thread is live). Those
are the rows the model is for.

### The baseline is not a strawman

It is two rules: flag an 11–18 digit number that is not on file, and flag change
language co-occurring with a payment noun. That is a fair stand-in for a
first-pass control. It can never return `REVIEW`, so every legitimate change
costs a manual review, and it cannot read negation, so "we are *not* changing
our bank details" and "please change our bank details" are the same string to
it. Running the same rules over normalised text is reported as a separate row so
that the two effects do not get conflated.

### The steered-model rows are the point

A model that has been fully compromised — always reporting `no_change`, in one
variant not even bothering to justify it, in the other forging a verbatim quote
from the email — buys **zero** unsafe outcomes. It buys friction: accuracy falls
and legitimate mail goes to a human instead. The gate fails closed. This is
enforced by tests, not by hoping: `test_no_unsafe_outcomes_anywhere` runs both
harnesses over both sets.

### Reproducing

```bash
python eval/run_eval.py                       # all three sets, no key needed
python eval/run_eval.py --sets v1 --systems rules_raw rules_norm gemini
python eval/run_eval.py --require-gemini      # exit 2 if the model cannot run
```

**With no `GEMINI_API_KEY` the live system is skipped, loudly.** It is never
silently degraded into a fail-closed row that could be mistaken for a result.

## Honest limits

Read this part.

- **The `offline` row is a test double, not a model.** It is a rules engine with
  a JSON interface so that tests and CI run without a key. Its 100% is a
  regression guard and proves nothing about model performance. The `gemini` row
  is the only one that does, and it is empty until a live evaluation has run.
- **40 cases is a demo, not an evaluation.** Half the set was written with the
  system already in front of me. It is enough to show the mechanism and to catch
  regressions. It is not evidence of a field error rate, and none is claimed.
- **The floor only covers destinations it can see.** I1a/I1b catch an
  unrecognised account number or branch code. Risk in other fields — a
  beneficiary rename, a currency switch — is caught by the model's reading, and
  a steered model can suppress it. I3 and I4 partially cover this. It is the
  real boundary of the design.
- **A token-less request is the weakest case.** If the destination is outside the
  text and the model also fails to report the change language, there is no
  AI-independent evidence at all. Only the human attestation closes it.
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
python scripts/kill_gate.py # 17 go/no-go checks; read this before trusting anything
python -m pytest            # 80 tests, no network needed
python scripts/secret_scan.py   # nothing credential-like in the tree or history
python eval/run_eval.py     # writes results/; model rows skip cleanly without a key
python eval/run_eval.py --require-gemini   # exits 2 if any model row was skipped
streamlit run app/streamlit_app.py
```

To regenerate the screenshots in `docs/screenshots/` from a running app:

```bash
pip install playwright && playwright install --with-deps chromium
python scripts/capture_screenshots.py --extractor gemini
```

Deployed: the key is read from Streamlit secrets (or `.env` locally) and is
never written to the repo, logs, or the UI. See `docs/DEPLOY.md`.

## Layout

```
src/threadgate/
  normalize.py   text normalisation with offset preservation
  tokens.py      deterministic token finder (account/IFSC/IBAN/amount/phone)
  extract.py     the model call + the two adversarial harnesses
  validate.py    the closed-world evidence validator
  compare.py     field-level diff against the vendor record
  invariants.py  I1a/I1b/I2/I2b/I3/I4 - never consult the model
  policy.py      the monotone decision rule
  baseline.py    rules-only baseline, for the measured comparison
  pipeline.py    orchestration
data/cases/      frozen_v1 (benchmark), additions (stress), categories.json
data/records/    synthetic vendor master
eval/            evaluation harness and reports
app/             Streamlit demo
scripts/         kill gate, secret audit, screenshot capture
docs/            architecture.svg, screenshots/, deployment + submission notes
```

## Track

Devpost hackathon, **AI + Cybersecurity** track.

Complementary to ingestion-side filtering: tools that screen incoming mail for
prompt injection and phishing sit *upstream* of this. ThreadGate assumes a
hostile email has already arrived and gates the *action* it requests.

## Prior work

Everything here was built during the hackathon window. See `PRIOR_WORK.md`.
