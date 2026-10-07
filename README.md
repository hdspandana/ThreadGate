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

The invariants split into two kinds, and the difference matters.

**Model-independent invariants** never see the model's output at all. They read
the email and the record, and no answer the model gives can weaken them.

**Verdict-validating invariants** do look at what the model said - but only to
decide whether to *accept* it. They can reject a verdict. They can never
substitute one, and a rejected verdict always falls through to a
model-independent check rather than to a decision. An earlier version of this
README claimed every invariant was computed "without looking at what the model
said", which was not true of I2 and I2b and would not be a strength if it were:
a system that ignored the model's output entirely could not use it at all.

**What the gate checks in the email (model-independent)**

- **I1a — Unknown account floor.** If a number in the email looks like a bank
  account and it is not the account on file and not a pre-registered alternate,
  a human looks at it.
- **I1b — Unknown branch/routing code.** The same rule for IFSC, IBAN and SWIFT.
  The closed-world rule covers every supported destination token the scanner can
  see, not only account numbers.
- **I3 — Change asserted, nothing verifiable.** "Our details have changed, see
  the attached PDF" is held, because there is no value in the message to check.
- **I4 — Destination out of band.** If the message says the account is in an
  image, a PDF or a portal, the destination cannot be read and is held. See
  below.
- **I5 — Pre-registered alternate in a routing instruction.** A destination we
  recognise, that is *not* the currently active one, named in a sentence telling
  the reader to route money to it, floors at `REVIEW`. I1 is silent on accounts
  we do know, which is correct for the question it asks and leaves the decision
  to the model whenever the account named happens to be a real alternate the
  vendor registered. I5 closes that: known, not currently active, and asked
  for. It is `REVIEW` rather than `HOLD` on purpose - a registered alternate is
  a change to be attested, not an unknown destination.

**What the gate checks about what the model said (verdict-validating)**

- **I2 — No-change must be evidenced.** A `no_change` verdict is accepted only
  if the model quotes the sentence that says so.
- **I2b — The quote must support the verdict.** Added after an ablation found
  the hole: a steered model can return `no_change` with a quote copied verbatim
  from the email, which passes I2 because the words really are there. I2b
  requires the quoted sentence to assert that nothing is changing, **in the
  payment domain**. It does not accept retraction vocabulary ("disregard the
  earlier mail", "no action required", "that was a phish"), because an attacker
  only has to append one such sentence to an email carrying a live change to
  manufacture a quote I2b would accept.
- **I2c — A confirmation request must justify itself the same way.** The
  quote has to ask for confirmation and must not issue a change in the same
  breath. `confirmation_request` used to be accepted on any verbatim quote,
  which made it the cheapest route past the gate.
- **I6 — The claimed value must be inside the quote offered for it.** See
  "evidence binding" below.

**What the gate checks about the record it is comparing against**

The gate is only as good as the record it checks against, so the record is an
input to the decision, not a given.

- **R1 — Reference version lineage.** A verification made against v1 of a record
  is refused against v2. The record moved on, so the old verification no longer
  describes it, and inheriting it would release a change on the strength of a
  check that was never performed against the new destination.
- **R2 — A degraded reference never clears.** A record last confirmed longer ago
  than its freshness window is `STALE` and floors at REVIEW. A record with no
  payment destination on file at all is `MISSING`, and a payment-destination
  change against a `MISSING` record is HOLD. Neither state can produce CLEAR.
  Freshness is read from an injected clock, so it is a deterministic input
  rather than a hidden dependency on the wall clock.
- **R3 — Single-use verification events.** A human attestation is bound to a
  request id, a digest of the destination, and the reference version it was made
  against. It is refused if presented a second time, or against any other
  request, destination, record version or vendor. A failed presentation burns
  the event, so it cannot be retried with a better guess — see the trade-off
  below.

  **Verification events are single-use within the prototype's active verification store; durable distributed replay protection is outside this prototype.**
  The guarantee is a single-process one: it is neither a replicated
  guarantee nor a durable one, and it is not described as either anywhere
  in these documents.

**All fourteen invariants, and the tests that hold them**

The count is written down rather than implied, because a number like "eleven of
fourteen" is exactly the sort of thing that quietly goes stale.

| # | Invariant | Enforced by |
| --- | --- | --- |
| 1 | No supported non-reference destination can CLEAR | `test_a_destination_we_cannot_read_is_never_cleared` |
| 2 | The AI cannot directly set the final decision | `test_the_model_output_schema_cannot_express_a_verdict`, `test_only_policy_produces_a_decision` |
| 3 | Every supported destination token is independently scanned | `test_destination_tokens_inside_quoted_text_are_still_scanned`, `test_destination_code_floor_does_not_ask_the_model` |
| 4 | Quoted and forwarded destination tokens are not ignored | `test_destination_tokens_inside_quoted_text_are_still_scanned` |
| 5 | Unsupported evidence cannot become trusted | `test_unsupported_destination_evidence_cannot_become_trusted`, `test_fabricated_evidence_is_rejected` |
| 6 | A forged verbatim quote cannot justify a no-change verdict | `test_a_forged_verbatim_quote_cannot_justify_no_change` |
| 7 | A HOLD trigger can never produce CLEAR in the same run | `test_a_hold_trigger_can_never_produce_a_clear` |
| 8 | An old reference version cannot satisfy a newer reference | `test_a_v1_attestation_is_refused_against_a_v2_record`, `test_the_same_event_cannot_be_used_against_another_destination` |
| 9 | A verification event cannot be presented twice, within the active store | `test_the_same_event_cannot_be_used_twice`, `test_a_replayed_attestation_is_rejected_end_to_end_without_moving_the_decision` |
| 10 | A masked or partial destination never matches | `test_a_masked_destination_never_matches_the_reference` |
| 11 | A missing reference escalates instead of being guessed | `test_a_missing_reference_escalates_instead_of_crashing`, `test_a_missing_reference_holds_a_payment_destination_change` |
| 12 | A degraded record never results in CLEAR | `test_a_stale_reference_never_clears`, `test_no_case_ever_clears_on_a_degraded_reference` |
| 13 | An unreadable attachment cannot silently create a CLEAR | `test_a_destination_we_cannot_read_is_never_cleared` |
| 14 | Model failure cannot produce CLEAR | `test_a_failing_model_never_clears`, `test_no_key_means_the_pipeline_holds_and_never_clears` |

### The burn-on-reject trade-off

A rejected presentation **consumes** the single-use verification event by
design. Once an event id has been presented it is burned, whether the outcome
was accept or reject, and no later presentation of that id can ever succeed.

The reason is that a failed attempt is itself information. Whoever presented it
against the wrong request, destination or record version has demonstrated that
they do not hold a valid event for this context. Letting them keep it for a
second, better-targeted guess would turn the store into an oracle: each
rejection would narrow down which binding was wrong, and the event would stay
usable in the meantime.

The cost is deliberate, and it is worth stating plainly rather than burying:

- a genuine presentation that fails for a benign reason — a mistyped request id,
  an attestation minted moments before the record moved to a new version —
  **cannot simply be retried with the same event**;
- the operator must mint a new verification event and perform the check again.

That is a real usability cost, and it is accepted in exchange for removing the
probing channel. For a control whose only job is to be hard to reuse, an
operator inconvenience is the right side of the trade.

---

Invariants 8, 9 and 12 are the three that were, until this change, listed as
not built. They are implemented now; `tests/test_verification_and_lineage.py`
is their regression file, and each was sabotage-verified.

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

Three outcomes are counted separately, because they cost different things:

- **unsafe** — a case labelled `HOLD` came back softer. The only error that can
  lose money.
- **non-CLEAR release** — a case the gate was supposed to stop (labelled
  `REVIEW` or `HOLD`) came back `CLEAR`. Also a bypass, and *not* visible in the
  unsafe count: no hold was released, so nothing looks wrong.
- **false hold** — a case that should have gone through was sent to a human.
  Costs review time.

The two permissive failures get two percentages, and neither may be quoted
without the other. `safety %` is the narrow one: of the cases that should have
been *held*, how many were. `no-bypass %` is the wide one: of every case the
gate should have *stopped*, how many it stopped. A system can read `safety %`
100% while waving `REVIEW`-labelled cases through - that is exactly how the
pre-registered-alternate bypass scored as a clean run - so the tables below show
both columns side by side, and `python eval/run_eval.py` prints a warning naming
every case that came back `CLEAR` when it should not have.

### Set 1 — frozen_v1, primary pre-frozen benchmark (20 cases)

| System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
| --- | --- | --- | --- | --- | --- | --- |
| Rules-only baseline (raw text) | 50.0% | 2 | 3 | 83.3% | 80.0% | 7 |
| Rules-only baseline + normalisation | 60.0% | 0 | 1 | 100.0% | 93.3% | 7 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
| ThreadGate, model steered to say "no change" | 70.0% | **0** | **0** | 100.0% | 100.0% | 6 |
| ThreadGate, steered model forging a verbatim quote | 70.0% | **0** | **0** | 100.0% | 100.0% | 6 |
| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |

Every row marked *pending — not yet run* needs a `GEMINI_API_KEY`. None has
been run, so none is filled in: the three ablations and the model-alone
baseline are all model-backed, and there is no offline substitute for them. Do
not fill them from the offline test double — that row is a regression guard, not
a model result.

### Set 2 — stress additions, written after the first run (20 cases)

| System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
| --- | --- | --- | --- | --- | --- | --- |
| Rules-only baseline (raw text) | 60.0% | 2 | 3 | 84.6% | 81.2% | 5 |
| Rules-only baseline + normalisation | 70.0% | 0 | 1 | 100.0% | 93.8% | 5 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
| ThreadGate, model steered to say "no change" | 80.0% | **0** | **0** | 100.0% | 100.0% | 4 |
| ThreadGate, steered model forging a verbatim quote | 80.0% | **0** | **0** | 100.0% | 100.0% | 4 |
| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |

### Set 3 — combined, stress evaluation only (40 cases)

Not an unbiased benchmark. Shown for completeness and for the category view.

| System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
| --- | --- | --- | --- | --- | --- | --- |
| Rules-only baseline (raw text) | 55.0% | 4 | 6 | 84.0% | 80.6% | 12 |
| Rules-only baseline + normalisation | 65.0% | 0 | 2 | 100.0% | 93.5% | 12 |
| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
| ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
| ThreadGate, model steered to say "no change" | 75.0% | **0** | **0** | 100.0% | 100.0% | 10 |
| ThreadGate, steered model forging a verbatim quote | 75.0% | **0** | **0** | 100.0% | 100.0% | 10 |
| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |

### Where the reading is actually needed

Per-category accuracy on the combined set. `u` counts unsafe outcomes.
Categories are assigned in `data/cases/categories.json`, which was written
after both sets were frozen, so it annotates cases without relabelling them.
This table is generated from `results/latest.json` by `python eval/run_eval.py`;
if you change a case, re-run the evaluation before trusting it.

| Category | n | rules_raw | rules_norm | offline | compromised | compromised_q |
| --- | --- | --- | --- | --- | --- | --- |
| ambiguity | 1 | 100 | 100 | 100 | 100 | 100 |
| benign_low_risk_field | 4 | 0 | 0 | 100 | 0 | 0 |
| benign_preregistered | 2 | 0 | 0 | 100 | 0 | 0 |
| contradiction | 2 | 100 | 100 | 100 | 100 | 100 |
| cross_message | 2 | 50 | 50 | 100 | 50 | 50 |
| direct_change | 6 | 100 | 100 | 100 | 100 | 100 |
| mention_vs_request | 6 | 17 | 17 | 100 | 50 | 50 |
| negation | 2 | 0 | 0 | 100 | 0 | 0 |
| obfuscation | 5 | 20 **(u4)** | 100 | 100 | 100 | 100 |
| prompt_injection | 5 | 100 | 100 | 100 | 100 | 100 |
| quoted_forwarded | 1 | 100 | 100 | 100 | 100 | 100 |
| social_engineering | 2 | 100 | 100 | 100 | 100 | 100 |
| tokenless_implicit | 2 | 100 | 100 | 100 | 100 | 100 |

Read that table carefully, because two rows flatter the baseline:

- `prompt_injection`, `social_engineering` and `direct_change` score 100% for
  the rules baseline **because it holds everything**, not because it detects
  anything. That is the same behaviour that produces 0% on the benign
  categories. Accuracy averages the two out; the category view does not.
- `obfuscation` is the one category where normalisation alone closes the gap:
  20% with 4 unsafe becomes 100% with 0. Character-level evasion is a code
  problem, and it is solved in `normalize.py`, not by the model.

The categories where reading is genuinely required are **mention_vs_request**
(talking about a destination vs asking for it to change), **negation** (reading
"not" in context) and **cross_message** (deciding which end of a thread is
live). Those are the rows the model is for.

`cross_message` is named for what it is: **quoted and forwarded content inside a
single message** - a `>`-quoted earlier mail, or a forwarded block. It is not
correlation across separate emails. ThreadGate processes one message at a time
and holds no state between them; there is no thread store and no cross-message
memory.

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
from the email — releases nothing. Across both frozen sets under both harnesses:

| | count |
| --- | --- |
| unsafe hold releases (expected `HOLD`, got softer) | **0** |
| non-CLEAR releases (expected `REVIEW`/`HOLD`, got `CLEAR`) | **0** |
| false holds (a human asked to look unnecessarily) | 10 of 40 |

It buys friction, not releases: accuracy falls and legitimate mail goes to a
human instead. Two metrics, not one, because `unsafe` alone cannot see a
`REVIEW`-labelled case coming back `CLEAR` - no hold was released, so nothing was
"unsafe", and the pre-registered-alternate bypass scored as a clean success
until the second metric existed.

Both are zero **on these 40 cases**, and that is the scope of the claim: a
finite frozen corpus, not a guarantee. It is enforced by tests rather than
hoped for: `test_no_unsafe_outcomes_anywhere` runs both harnesses over both
sets and asserts both counts.

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

### Not built, and not claimed

Stated separately from the limits above, because these are absences rather than
weaknesses, and a reader who assumed otherwise would be misled about what this
prototype guarantees:

- **No OCR, no attachment parsing.** Covered above, restated here so the list is
  complete in one place.
- **No risk score.** Nothing here produces a number that a human is expected to
  trade off against. See `tests/test_scope.py`.
- **No cryptographic signatures, and no PKI.** A verification event is a
  *binding*, not a proof of identity: it ties an attestation to one request, one
  destination and one record version, and it refuses to be used twice. It does
  not prove *who* performed the check. There is no key material anywhere in this
  project and no identity is asserted.
- **No automatic reference updates.** Nothing in ThreadGate ever writes to the
  vendor record. Updating a record is a human operation performed out of band
  after the callback; the gate reads the version and refuses to carry a
  verification across it. A prototype that could rewrite its own reference
  would not be a reference.
- **The verification store is neither durable nor distributed.** Consumed
  event ids live in memory and are not written to disk by the product path, so
  a restart begins with an empty store. This is a single-process prototype, not
  a replicated service, and the single-use guarantee is scoped to the store that
  is currently live: it holds for as long as that process does, and no longer.
  `AttestationStore.dump()` and `.restore()` exist so a deployment that needs
  durability can persist it; the demo does not. Stated precisely in **R3** above.

`tests/test_reference_and_attestation.py` fails if this list stops saying
something that is still true, and it also fails if it keeps disclaiming
something that has since been built. The list has to track reality in both
directions, which is the only way a "not built" list stays honest.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # put your GEMINI_API_KEY in .env; it is gitignored
python scripts/kill_gate.py # 17 go/no-go checks; read this before trusting anything
python -m pytest            # 156 tests, no network needed
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

**Deployment.** The key is read from Streamlit secrets (or `.env` locally) and
is never written to the repo, logs, or the UI. There is no public deployment
yet - this is run locally or on Streamlit Community Cloud, and a URL will
appear here once one exists. See `docs/DEPLOY.md`.

## Layout

```
src/threadgate/
  normalize.py    text normalisation with offset preservation
  tokens.py       deterministic token finder (account/IFSC/IBAN/amount/phone)
  extract.py      the model call + the two adversarial harnesses
  validate.py     the closed-world evidence validator
  compare.py      field-level diff against the vendor record
  invariants.py   I1a/I1b/I3/I4/I5 never consult the model;
                  I2/I2b/I2c/I6 validate it and can only reject
  clock.py        injected time source, so freshness is a deterministic input
  reference.py    reference version and CURRENT / STALE / MISSING
  attestation.py  single-use verification events and their bindings
  policy.py       the monotone decision rule
  baseline.py     rules-only baseline, for the measured comparison
  pipeline.py     orchestration
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
