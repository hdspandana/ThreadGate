diff --git a/README.md b/README.md
index 3c01bd3..32d7ef9 100644
--- a/README.md
+++ b/README.md
@@ -2,192 +2,93 @@
 
 **AI interprets the email. Code verifies the change against the record. A human attests before anything executes.**
 
-An action-level gate for payment-detail change requests that arrive by email.
+An action-level gate for vendor payment-detail change requests that arrive by email.
 
----
+- **Live demo:** https://threadgate-ptxsbmfkqobnh8ai7arwv4.streamlit.app/
+- **Code:** https://github.com/hdspandana/ThreadGate
+- **Track:** AI + Cybersecurity (ForgeHacks 2026)
 
-## The problem, stated as the track asks it
+> **This is a security prototype, not a production banking control.** All financial identifiers are synthetic demo data. It processes one pasted email at a time, does no OCR or attachment inspection, has no banking integration, and never executes a payment.
 
-Fraud enabled by AI.
+---
 
-AI makes fraudulent email *fluent*. That matters because the traditional tell —
-bad grammar, odd phrasing, a strange greeting — is gone, so **any control that
-judges the wording of a message gets weaker every year**. What does not get
-weaker is checking the *thing the email asks you to do* against a record you
-already hold: if the email asks you to pay a different bank account, no amount
-of good writing makes that account the one on file.
+## The problem
 
-ThreadGate is built on that split. The model's job is to read the email. The
-code's job is to compare what the email asks for against the vendor record, and
-to decide. The model never gets a vote on the verdict.
+Fraud enabled by AI. AI makes fraudulent email *fluent*, so the old tells (bad grammar, odd greetings) are gone and any control that judges the **wording** of a message gets weaker every year.
 
-The loss event in invoice-redirection fraud is not the email. It is the changed
-bank detail reaching the payment run. So that is what gets gated.
+What does not get weaker is checking **what the email asks you to do** against a record you already hold. If an email asks you to pay a different bank account, no amount of good writing makes that account the one on file. The loss in invoice-redirection fraud is not the email; it is the changed bank detail reaching the payment run. So that is what ThreadGate gates.
 
 ## What it does
 
-Paste in a vendor email. ThreadGate returns one of three decisions:
+Paste a vendor email. ThreadGate returns one of three decisions:
 
 | Decision | Meaning |
 | --- | --- |
-| **HOLD** | Cannot execute without out-of-band human verification. A diff against the record is shown, plus a callback checklist. |
-| **REVIEW** | A change was identified and it matches the record on file — a pre-registered alternate, or a field that is not a payment destination. A human still attests before anything executes. |
+| **HOLD** | Cannot proceed without out-of-band human verification. Shows the diff against the record and a callback checklist. |
+| **REVIEW** | A change was identified and it matches the record (a pre-registered alternate, or a field that is not a payment destination). A human still attests before anything executes. |
 | **CLEAR** | **No change was identified by this prototype.** Nothing to gate. |
 
-Three things about that table, because they are the difference between a gate
-and a score:
-
-- **CLEAR is not an approval.** It means this prototype did not identify a
-  change to gate. It does not mean the email is safe, legitimate, or fraud-free,
-  and it is never rendered in a colour or wording that suggests otherwise.
-- **REVIEW is not a release either.** The change matched the record, which is
-  necessary but not sufficient; a human still attests before anything executes.
-- **HOLD** is a request for out-of-band verification, not an accusation. Most
-  held mail will turn out to be legitimate; the cost of a hold is a phone call,
-  and the cost of a miss is the money.
+- **CLEAR is not an approval.** It does not mean the email is safe, legitimate or fraud-free.
+- **REVIEW is not a release.** Matching the record is necessary, not sufficient.
+- **HOLD is a request to verify, not an accusation.** A hold costs a phone call; a miss costs the money.
 
-The escalation only ever runs one way: `CLEAR` → `REVIEW` → `HOLD`. No trigger
-can move a decision back down it.
+Decisions only ever escalate: `CLEAR` → `REVIEW` → `HOLD`. No trigger moves one back down.
 
 ## How it works
 
 ```
-email ──▶ normalise ──▶ token finder ──┐            (code)
-                                       │
-       ┌───────────────────────────────┴──────────┐
-       │  Gemini: "what change does this ask for?" │  (model - interpretation only)
-       └───────────────────────────────┬──────────┘
-                                       ▼
-                            evidence validator     (code - closed world)
-                                       ▼
-                         comparator / diff vs record (code)
-                                       ▼
-                              invariants            (code - never sees the model)
-                                       ▼
-                             policy engine          (code - monotone)
-                                       ▼
-                            CLEAR / REVIEW / HOLD
+email ─▶ normalise ─▶ token finder ─┐                 (code)
+                                    │
+      ┌─────────────────────────────┴───────────┐
+      │ Gemini: "what change does this ask for?" │      (model: interpretation only)
+      └─────────────────────────────┬───────────┘
+                                    ▼
+                         evidence validator            (code: closed world)
+                                    ▼
+                       comparator: diff vs record      (code)
+                                    ▼
+                    invariants ─▶ policy engine        (code: monotone)
+                                    ▼
+                          CLEAR / REVIEW / HOLD
 ```
 
-The same thing as a trust-boundary diagram, with the one edge that does not
-exist drawn explicitly: **`docs/architecture.svg`**. The model sits in the
-untrusted half; the dashed line is the boundary; the crossed-out arrow from the
-model to the verdict is the whole design.
-
-Five screenshots of the running app are in `docs/screenshots/` — a benign
-release, the canonical hold, a prompt-injection hold, the negation case where
-the rules baseline is wrong, and the corpus table. They are captures, not
-mockups, and every number in them was produced by the pipeline at capture time.
-`scripts/capture_screenshots.py` regenerates them.
-
-### Why this is not a wrapper
-
-Three things sit between the model's output and the decision.
-
-**1. The evidence validator (the closed-world rule).** The model may only emit
-structured claims, and every claim must carry a quote. A claim is admitted only
-if the quote is found verbatim in the email *and* the value it reports is
-locatable in the email or in that quote. A value the model produced from memory
-or inference is dropped, not repaired. Hallucination is not a risk score to be
-thresholded here; it is a claim that never enters the pipeline.
-
-**2. A deterministic policy the AI cannot override.** The decision rule is
-monotone. Triggers can move a request towards `HOLD`; none can move it towards
-`CLEAR`. The model's contribution enters as verified claims, and a verified
-claim can add a hold trigger but can never remove one.
-
-**3. A measured comparison against a rules-only baseline**, plus two adversarial
-harnesses that measure the system with the model working against it. All three
-are below and all are reproducible with one command.
-
-### The security model
-
-The invariants split into two kinds, and the difference matters.
-
-**Model-independent invariants** never see the model's output at all. They read
-the email and the record, and no answer the model gives can weaken them.
-
-**Verdict-validating invariants** do look at what the model said - but only to
-decide whether to *accept* it. They can reject a verdict. They can never
-substitute one, and a rejected verdict always falls through to a
-model-independent check rather than to a decision. An earlier version of this
-README claimed every invariant was computed "without looking at what the model
-said", which was not true of I2 and I2b and would not be a strength if it were:
-a system that ignored the model's output entirely could not use it at all.
-
-**What the gate checks in the email (model-independent)**
-
-- **I1a — Unknown account floor.** If a number in the email looks like a bank
-  account and it is not the account on file and not a pre-registered alternate,
-  a human looks at it.
-- **I1b — Unknown branch/routing code.** The same rule for IFSC, IBAN and SWIFT.
-  The closed-world rule covers every supported destination token the scanner can
-  see, not only account numbers.
-- **I3 — Change asserted, nothing verifiable.** "Our details have changed, see
-  the attached PDF" is held, because there is no value in the message to check.
-- **I4 — Destination out of band.** If the message says the account is in an
-  image, a PDF or a portal, the destination cannot be read and is held. See
-  below.
-- **I5 — Pre-registered alternate in a routing instruction.** A destination we
-  recognise, that is *not* the currently active one, named in a sentence telling
-  the reader to route money to it, floors at `REVIEW`. I1 is silent on accounts
-  we do know, which is correct for the question it asks and leaves the decision
-  to the model whenever the account named happens to be a real alternate the
-  vendor registered. I5 closes that: known, not currently active, and asked
-  for. It is `REVIEW` rather than `HOLD` on purpose - a registered alternate is
-  a change to be attested, not an unknown destination.
-
-**What the gate checks about what the model said (verdict-validating)**
-
-- **I2 — No-change must be evidenced.** A `no_change` verdict is accepted only
-  if the model quotes the sentence that says so.
-- **I2b — The quote must support the verdict.** Added after an ablation found
-  the hole: a steered model can return `no_change` with a quote copied verbatim
-  from the email, which passes I2 because the words really are there. I2b
-  requires the quoted sentence to assert that nothing is changing, **in the
-  payment domain**. It does not accept retraction vocabulary ("disregard the
-  earlier mail", "no action required", "that was a phish"), because an attacker
-  only has to append one such sentence to an email carrying a live change to
-  manufacture a quote I2b would accept.
-- **I2c — A confirmation request must justify itself the same way.** The
-  quote has to ask for confirmation and must not issue a change in the same
-  breath. `confirmation_request` used to be accepted on any verbatim quote,
-  which made it the cheapest route past the gate.
-- **I6 — The claimed value must be inside the quote offered for it.** See
-  "evidence binding" below.
-
-**What the gate checks about the record it is comparing against**
-
-The gate is only as good as the record it checks against, so the record is an
-input to the decision, not a given.
-
-- **R1 — Reference version lineage.** A verification made against v1 of a record
-  is refused against v2. The record moved on, so the old verification no longer
-  describes it, and inheriting it would release a change on the strength of a
-  check that was never performed against the new destination.
-- **R2 — A degraded reference never clears.** A record last confirmed longer ago
-  than its freshness window is `STALE` and floors at REVIEW. A record with no
-  payment destination on file at all is `MISSING`, and a payment-destination
-  change against a `MISSING` record is HOLD. Neither state can produce CLEAR.
-  Freshness is read from an injected clock, so it is a deterministic input
-  rather than a hidden dependency on the wall clock.
-- **R3 — Single-use verification events.** A human attestation is bound to a
-  request id, a digest of the destination, and the reference version it was made
-  against. It is refused if presented a second time, or against any other
-  request, destination, record version or vendor. A failed presentation burns
-  the event, so it cannot be retried with a better guess — see the trade-off
-  below.
+The model sits in one box and everything after it refuses to trust it. The trust boundary is drawn in `docs/architecture.svg`; the arrow from the model to the verdict does not exist.
+
+1. **The model sees the email and nothing else.** Not the vendor record, not the account on file. It returns structured claims, each with a quote. It has no field in which to say a change is "safe". This is enforced in code and by test, not only by the prompt.
+2. **Evidence validation (closed world).** A claim is admitted only if its quote appears verbatim in the email and its value is locatable in the email or the quote. Anything produced from memory or inference is dropped, not repaired.
+3. **A policy the model cannot override.** Triggers can move a request towards `HOLD`; none can move it towards `CLEAR`. A verified claim can add a hold trigger but never remove one.
+
+If the model fails, times out or is missing, the gate fails closed to `HOLD`.
+
+## Security model
+
+Two kinds of invariant, and the difference matters.
+
+**Model-independent invariants** read the email and the record. Nothing the model says can weaken them.
+
+- **I1a: Unknown account floor.** An account-like number that is not the account on file and not a pre-registered alternate goes to a human. A number explicitly labelled as an account always counts, whatever words (such as "invoice" or "ref") sit near it, because the sender controls those words.
+- **I1b: Unknown branch or routing code.** The same rule for IFSC, IBAN and SWIFT.
+- **I3: Change asserted, nothing verifiable.** "Our details have changed, see the attached PDF" is held: there is no value to check.
+- **I4: Destination out of band.** If the account is said to be in an image, PDF or portal, it cannot be read and is held.
+- **I5: Pre-registered alternate in a routing instruction.** A known alternate that is not currently active, named in a sentence telling the reader to route money to it, floors at `REVIEW`.
+
+**Verdict-validating invariants** read what the model said, only to decide whether to *accept* it. They can reject a verdict, never substitute one, and a rejected verdict falls through to a model-independent check.
+
+- **I2: No-change must be evidenced.** A `no_change` verdict needs a quoted sentence.
+- **I2b: The quote must support the verdict.** It must say nothing is changing in the payment domain and carry no live instruction itself. Retraction wording ("disregard the earlier mail") is not accepted, and no *other* sentence in the email may carry a live instruction to route payments.
+- **I2c: A confirmation request must justify itself the same way.** It must ask for confirmation without issuing a change.
+- **I6: The claimed value must be inside the quote offered for it.**
+
+**Record invariants.** The gate is only as good as the record, so the record is an input.
+
+- **R1: Reference version lineage.** A verification made against v1 of a record is refused against v2.
+- **R2: A degraded reference never clears.** A record past its freshness window is `STALE` and floors at `REVIEW`; a record with no payment destination is `MISSING` and holds a destination change. Freshness comes from an injected clock.
+- **R3: Single-use verification events.** An attestation is bound to a request id, a destination digest and a record version. It is refused if presented twice or against anything else. Event ids are compared after normalising case, whitespace and invisible characters.
 
   **Verification events are single-use within the prototype's active verification store; durable distributed replay protection is outside this prototype.**
-  The guarantee is a single-process one: it is neither a replicated
-  guarantee nor a durable one, and it is not described as either anywhere
-  in these documents.
 
 **All fourteen invariants, and the tests that hold them**
 
-The count is written down rather than implied, because a number like "eleven of
-fourteen" is exactly the sort of thing that quietly goes stale.
-
 | # | Invariant | Enforced by |
 | --- | --- | --- |
 | 1 | No supported non-reference destination can CLEAR | `test_a_destination_we_cannot_read_is_never_cleared` |
@@ -207,352 +108,123 @@ fourteen" is exactly the sort of thing that quietly goes stale.
 
 ### The burn-on-reject trade-off
 
-A rejected presentation **consumes** the single-use verification event by
-design. Once an event id has been presented it is burned, whether the outcome
-was accept or reject, and no later presentation of that id can ever succeed.
+A rejected presentation **consumes** the event, just as an accepted one does. A failed attempt is information: whoever presented an event against the wrong request has shown they do not hold a valid one, and letting them keep it for a better-targeted second guess would turn the store into an oracle.
 
-The reason is that a failed attempt is itself information. Whoever presented it
-against the wrong request, destination or record version has demonstrated that
-they do not hold a valid event for this context. Letting them keep it for a
-second, better-targeted guess would turn the store into an oracle: each
-rejection would narrow down which binding was wrong, and the event would stay
-usable in the meantime.
+The cost is real: a genuine presentation that fails for a benign reason (a mistyped request id, a record that moved to a new version a moment earlier) cannot be retried with the same event. The operator mints a new one. That usability cost is accepted in exchange for removing the probing channel.
 
-The cost is deliberate, and it is worth stating plainly rather than burying:
-
-- a genuine presentation that fails for a benign reason — a mistyped request id,
-  an attestation minted moments before the record moved to a new version —
-  **cannot simply be retried with the same event**;
-- the operator must mint a new verification event and perform the check again.
+## Evaluation
 
-That is a real usability cost, and it is accepted in exchange for removing the
-probing channel. For a control whose only job is to be hard to reuse, an
-operator inconvenience is the right side of the trade.
+Three sets, reported separately because they mean different things.
 
----
+| Set | Cases | What it is | What may be quoted from it |
+| --- | --- | --- | --- |
+| `v1` | 20 | **Primary pre-frozen benchmark**, written before any evaluation was run. | Performance claims. |
+| `stress` | 20 | **Adversarial set**, written after the first evaluation. | Robustness only. |
+| `combined` | 40 | Both together. **A stress evaluation, not an unbiased benchmark.** | No single accuracy number. |
 
-Invariants 8, 9 and 12 are the three that were, until this change, listed as
-not built. They are implemented now; `tests/test_verification_and_lineage.py`
-is their regression file, and each was sabotage-verified.
-
-### What the gate does not do
-
-- **No OCR, no attachment parsing, no image analysis.** Opening an
-  attacker-supplied file to inspect it is not a control, it is an exposure. When
-  the destination is not in the text, I4 holds it and the checklist tells the
-  analyst to get the value over the phone. TG-034 is exactly this case: the new
-  account is in an image, the only number in the text is the one already on
-  file, so nothing looks wrong until you notice that the destination was never
-  readable. It holds under every extractor, including a steered model.
-- **No risk score.** Invoice value, vendor age, payment history and similar
-  signals are deliberately absent. A numeric risk score can be argued with,
-  tuned until it stops firing, and eventually waved through. A destination check
-  cannot. An amount is reported to the analyst and decides nothing — the
-  amount-based ceiling heuristic that was here earlier was removed for this
-  reason.
-- **No URL scanning, threat intelligence, embeddings, or vector search.** None
-  of it is needed to answer the only question this gate asks.
-- **Scope is explicit in the code.** `DESTINATION_FIELDS` is what the closed-world
-  rule protects. Changes to instruction fields (currency, terms) and contact
-  fields (advice mailbox, contact person, phone) are reported and policy-checked,
-  but they are not what the gate is for, and none of them produce a score.
-  `tests/test_scope.py` fails the build if any of that drifts.
+Three outcomes are counted separately because they cost different things:
 
-## Evaluation
+- **unsafe**: a case labelled `HOLD` came back softer. The only error that loses money.
+- **non-CLEAR release** (Non-CLR): a case labelled `REVIEW` or `HOLD` came back `CLEAR`. Also a bypass, and invisible to `unsafe`.
+- **false hold**: a case that should have gone through was sent to a human. Costs review time.
 
-Three sets, reported separately, because they mean different things.
+`Safety %` is the narrow measure (of cases that should be *held*, how many were). `No-bypass %` is the wide one (of cases the gate should *stop*, how many it stopped). Neither may be quoted without the other.
 
-| Set | Cases | What it is | What may be quoted from it |
-| --- | --- | --- | --- |
-| `v1` | 20 | **Primary pre-frozen benchmark.** Written before any evaluation was run. | Performance claims. |
-| `stress` | 20 | **Adversarial stress set.** Written *after* the first evaluation, from attack patterns and from failure modes visible in the design. | Robustness only. |
-| `combined` | 40 | Both together. **A stress evaluation, not an unbiased benchmark.** | Nothing as a single accuracy number. |
-
-Three outcomes are counted separately, because they cost different things:
-
-- **unsafe** — a case labelled `HOLD` came back softer. The only error that can
-  lose money.
-- **non-CLEAR release** — a case the gate was supposed to stop (labelled
-  `REVIEW` or `HOLD`) came back `CLEAR`. Also a bypass, and *not* visible in the
-  unsafe count: no hold was released, so nothing looks wrong.
-- **false hold** — a case that should have gone through was sent to a human.
-  Costs review time.
-
-The two permissive failures get two percentages, and neither may be quoted
-without the other. `safety %` is the narrow one: of the cases that should have
-been *held*, how many were. `no-bypass %` is the wide one: of every case the
-gate should have *stopped*, how many it stopped. A system can read `safety %`
-100% while waving `REVIEW`-labelled cases through - that is exactly how the
-pre-registered-alternate bypass scored as a clean run - so the tables below show
-both columns side by side, and `python eval/run_eval.py` prints a warning naming
-every case that came back `CLEAR` when it should not have.
-
-### Set 1 — frozen_v1, primary pre-frozen benchmark (20 cases)
+### frozen_v1: primary benchmark (20 cases)
 
 | System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
 | --- | --- | --- | --- | --- | --- | --- |
 | Rules-only baseline (raw text) | 50.0% | 2 | 3 | 83.3% | 80.0% | 7 |
 | Rules-only baseline + normalisation | 60.0% | 0 | 1 | 100.0% | 93.3% | 7 |
-| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
 | ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
-| ThreadGate, model steered to say "no change" | 70.0% | **0** | **0** | 100.0% | 100.0% | 6 |
-| ThreadGate, steered model forging a verbatim quote | 70.0% | **0** | **0** | 100.0% | 100.0% | 6 |
-| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |
-
-Every row marked *pending — not yet run* needs a `GEMINI_API_KEY`. None has
-been run, so none is filled in: the three ablations and the model-alone
-baseline are all model-backed, and there is no offline substitute for them. Do
-not fill them from the offline test double — that row is a regression guard, not
-a model result.
+| ThreadGate, steered model (says "no change", or forges a verbatim quote) | 70.0% | **0** | **0** | 100.0% | 100.0% | 6 |
+| ThreadGate with Gemini, model-alone baseline, two ablations | *pending — not yet run* | | | | | |
 
-### Set 2 — stress additions, written after the first run (20 cases)
+### stress: adversarial additions (20 cases)
 
 | System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
 | --- | --- | --- | --- | --- | --- | --- |
 | Rules-only baseline (raw text) | 60.0% | 2 | 3 | 84.6% | 81.2% | 5 |
 | Rules-only baseline + normalisation | 70.0% | 0 | 1 | 100.0% | 93.8% | 5 |
-| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
 | ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
-| ThreadGate, model steered to say "no change" | 80.0% | **0** | **0** | 100.0% | 100.0% | 4 |
-| ThreadGate, steered model forging a verbatim quote | 80.0% | **0** | **0** | 100.0% | 100.0% | 4 |
-| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |
-
-### Set 3 — combined, stress evaluation only (40 cases)
+| ThreadGate, steered model (says "no change", or forges a verbatim quote) | 80.0% | **0** | **0** | 100.0% | 100.0% | 4 |
+| ThreadGate with Gemini, model-alone baseline, two ablations | *pending — not yet run* | | | | | |
 
-Not an unbiased benchmark. Shown for completeness and for the category view.
+### combined: stress evaluation only (40 cases)
 
 | System | Accuracy | Unsafe | Non-CLR | Safety % | No-bypass % | False holds |
 | --- | --- | --- | --- | --- | --- | --- |
 | Rules-only baseline (raw text) | 55.0% | 4 | 6 | 84.0% | 80.6% | 12 |
 | Rules-only baseline + normalisation | 65.0% | 0 | 2 | 100.0% | 93.5% | 12 |
-| **ThreadGate (Gemini)** | *pending — not yet run* | | | | | |
 | ThreadGate, offline test double | 100.0% | 0 | 0 | 100.0% | 100.0% | 0 |
-| ThreadGate, model steered to say "no change" | 75.0% | **0** | **0** | 100.0% | 100.0% | 10 |
-| ThreadGate, steered model forging a verbatim quote | 75.0% | **0** | **0** | 100.0% | 100.0% | 10 |
-| The model alone, deciding the verdict (evaluation baseline, never a code path in the gate) | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: independent destination scan removed | *pending — not yet run* | | | | | |
-| ThreadGate, ablation: evidence validation removed | *pending — not yet run* | | | | | |
+| ThreadGate, steered model (says "no change", or forges a verbatim quote) | 75.0% | **0** | **0** | 100.0% | 100.0% | 10 |
+| ThreadGate with Gemini, model-alone baseline, two ablations | *pending — not yet run* | | | | | |
 
-### Where the reading is actually needed
+**Every Gemini row is pending.** The Gemini run, the model-alone baseline and the two ablations (independent destination scan removed, evidence validation removed) all need a `GEMINI_API_KEY` and have not been run. They are not filled from the offline test double: that row is a regression guard, not a model result.
 
-Per-category accuracy on the combined set. `u` counts unsafe outcomes (a hold that was released); `n` counts non-CLEAR releases (a case the gate should have stopped that came back CLEAR).
-Categories are assigned in `data/cases/categories.json`, which was written
-after both sets were frozen, so it annotates cases without relabelling them.
-This table is generated from `results/latest.json` by `python eval/run_eval.py`;
-if you change a case, re-run the evaluation before trusting it.
+**The steered-model rows are the point.** A model that is fully compromised (always reporting `no_change`, in one variant forging a verbatim quote to justify it) releases nothing:
 
-| Category | cases | rules_raw | rules_norm | offline | compromised | compromised_q |
-| --- | --- | --- | --- | --- | --- | --- |
-| ambiguity | 1 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| benign_low_risk_field | 4 | 0 (u0 n0) | 0 (u0 n0) | 100 (u0 n0) | 0 (u0 n0) | 0 (u0 n0) |
-| benign_preregistered | 2 | 0 (u0 **n2**) | 0 (u0 **n2**) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| contradiction | 2 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| cross_message | 2 | 50 (u0 n0) | 50 (u0 n0) | 100 (u0 n0) | 50 (u0 n0) | 50 (u0 n0) |
-| direct_change | 6 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| mention_vs_request | 6 | 17 (u0 n0) | 17 (u0 n0) | 100 (u0 n0) | 50 (u0 n0) | 50 (u0 n0) |
-| negation | 2 | 0 (u0 n0) | 0 (u0 n0) | 100 (u0 n0) | 0 (u0 n0) | 0 (u0 n0) |
-| obfuscation | 5 | 20 **(u4 n4)** | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| prompt_injection | 5 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| quoted_forwarded | 1 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| social_engineering | 2 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-| tokenless_implicit | 2 | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) | 100 (u0 n0) |
-
-Read that table carefully, because two rows flatter the baseline:
-
-- `prompt_injection`, `social_engineering` and `direct_change` score 100% for
-  the rules baseline **because it holds everything**, not because it detects
-  anything. That is the same behaviour that produces 0% on the benign
-  categories. Accuracy averages the two out; the category view does not.
-- `obfuscation` is the one category where normalisation alone closes the gap:
-  20% with 4 unsafe becomes 100% with 0. Character-level evasion is a code
-  problem, and it is solved in `normalize.py`, not by the model.
-
-The categories where reading is genuinely required are **mention_vs_request**
-(talking about a destination vs asking for it to change), **negation** (reading
-"not" in context) and **cross_message** (telling a quoted or forwarded
-instruction from the live one, inside the single message being processed).
-Those are the rows the model is for.
-
-`cross_message` is named for what it is: **quoted and forwarded content inside a
-single message** - a `>`-quoted earlier mail, or a forwarded block. It is not
-correlation across separate emails. ThreadGate processes one message at a time
-and holds no state between them; there is no thread store and no cross-message
-memory.
-
-### The baseline is not a strawman
-
-It is two rules: flag an 11–18 digit number that is not on file, and flag change
-language co-occurring with a payment noun. That is a fair stand-in for a
-first-pass control. It can never return `REVIEW`, so every legitimate change
-costs a manual review, and it cannot read negation, so "we are *not* changing
-our bank details" and "please change our bank details" are the same string to
-it. Running the same rules over normalised text is reported as a separate row so
-that the two effects do not get conflated.
-
-### The steered-model rows are the point
-
-A model that has been fully compromised — always reporting `no_change`, in one
-variant not even bothering to justify it, in the other forging a verbatim quote
-from the email — releases nothing. Across both frozen sets under both harnesses:
-
-| | count |
+| Across both frozen sets, both harnesses | count |
 | --- | --- |
 | unsafe hold releases (expected `HOLD`, got softer) | **0** |
 | non-CLEAR releases (expected `REVIEW`/`HOLD`, got `CLEAR`) | **0** |
 | false holds (a human asked to look unnecessarily) | 10 of 40 |
 
-It buys friction, not releases: accuracy falls and legitimate mail goes to a
-human instead. Two metrics, not one, because `unsafe` alone cannot see a
-`REVIEW`-labelled case coming back `CLEAR` - no hold was released, so nothing was
-"unsafe", and the pre-registered-alternate bypass scored as a clean success
-until the second metric existed.
+It buys friction, not releases: accuracy falls and legitimate mail goes to a human. Both counts are zero **on these 40 cases**, a finite frozen corpus. That is a measurement, not a guarantee. It is enforced by `test_no_unsafe_outcomes_anywhere` rather than hoped for.
 
-Both are zero **on these 40 cases**, and that is the scope of the claim: a
-finite frozen corpus, not a guarantee. It is enforced by tests rather than
-hoped for: `test_no_unsafe_outcomes_anywhere` runs both harnesses over both
-sets and asserts both counts.
+**Where the model is actually needed.** The rules baseline scores 100% on prompt-injection and direct-change cases only because it holds *everything*, which is also why it scores near 0% on benign ones. Character-level evasion is solved by `normalize.py`, not the model (20% with 4 unsafe becomes 100% with 0). The categories that genuinely need reading are `mention_vs_request` (talking about a destination vs asking to change it), `negation` ("we are *not* changing our bank details") and `cross_message`.
 
-### Reproducing
+`cross_message` is named for what it is: **quoted and forwarded content inside a single message**, such as a `>`-quoted earlier mail or a forwarded block. It is not correlation across separate emails. ThreadGate processes one message at a time and holds no state between them; there is no thread store.
 
-```bash
-python eval/run_eval.py                       # all three sets, no key needed
-python eval/run_eval.py --sets v1 --systems rules_raw rules_norm gemini
-python eval/run_eval.py --require-gemini      # exit 2 if the model cannot run
-```
-
-**With no `GEMINI_API_KEY` the live system is skipped, loudly.** It is never
-silently degraded into a fail-closed row that could be mistaken for a result.
-
-## Honest limits
-
-Read this part.
-
-- **The `offline` row is a test double, not a model.** It is a rules engine with
-  a JSON interface so that tests and CI run without a key. Its 100% is a
-  regression guard and proves nothing about model performance. The `gemini` row
-  is the only one that does, and it is empty until a live evaluation has run.
-- **40 cases is a demo, not an evaluation.** Half the set was written with the
-  system already in front of me. It is enough to show the mechanism and to catch
-  regressions. It is not evidence of a field error rate, and none is claimed.
-- **The floor only covers destinations it can see.** I1a/I1b catch an
-  unrecognised account number or branch code. Risk in other fields — a
-  beneficiary rename, a currency switch — is caught by the model's reading, and
-  a steered model can suppress it. I3 and I4 partially cover this. It is the
-  real boundary of the design.
-- **A token-less request is the weakest case.** If the destination is outside the
-  text and the model also fails to report the change language, there is no
-  AI-independent evidence at all. Only the human attestation closes it.
-- **All financial identifiers are synthetic demo data.** Every vendor, account
-  number, IFSC code, bank and email in `data/` was fabricated for this project.
-  Nothing here was verified against, or obtained from, a real banking system,
-  and no claim in this repository rests on having done so.
-- **No mail-flow integration.** This gates a pasted email. It is not wired to
-  Gmail, Outlook, or an ERP.
-- **Not a replacement for callback verification.** ThreadGate decides *when* a
-  human must verify, and hands them the exact diff and a checklist. The human
-  still makes the call.
-
-### Not built, and not claimed
-
-Stated separately from the limits above, because these are absences rather than
-weaknesses, and a reader who assumed otherwise would be misled about what this
-prototype guarantees:
-
-- **No OCR, no attachment parsing.** Covered above, restated here so the list is
-  complete in one place.
-- **No risk score.** Nothing here produces a number that a human is expected to
-  trade off against. See `tests/test_scope.py`.
-- **No cryptographic signatures, and no PKI.** A verification event is a
-  *binding*, not a proof of identity: it ties an attestation to one request, one
-  destination and one record version, and it refuses to be used twice. It does
-  not prove *who* performed the check. There is no key material anywhere in this
-  project and no identity is asserted.
-- **No automatic reference updates.** Nothing in ThreadGate ever writes to the
-  vendor record. Updating a record is a human operation performed out of band
-  after the callback; the gate reads the version and refuses to carry a
-  verification across it. A prototype that could rewrite its own reference
-  would not be a reference.
-- **The verification store is neither durable nor distributed.** Consumed
-  event ids live in memory and are not written to disk by the product path, so
-  a restart begins with an empty store. This is a single-process prototype, not
-  a replicated service, and the single-use guarantee is scoped to the store that
-  is currently live: it holds for as long as that process does, and no longer.
-  `AttestationStore.dump()` and `.restore()` exist so a deployment that needs
-  durability can persist it; the demo does not. Stated precisely in **R3** above.
-
-`tests/test_reference_and_attestation.py` fails if this list stops saying
-something that is still true, and it also fails if it keeps disclaiming
-something that has since been built. The list has to track reality in both
-directions, which is the only way a "not built" list stays honest.
+**Reproduce:** `python eval/run_eval.py` runs everything that needs no key and writes `results/latest.json`. With no `GEMINI_API_KEY` the live system is skipped loudly, never silently degraded into a fail-closed row that could be mistaken for a result. `--require-gemini` exits 2 if the model could not run.
 
 ## Run it
 
 ```bash
 pip install -r requirements.txt
-cp .env.example .env        # put your GEMINI_API_KEY in .env; it is gitignored
-python scripts/kill_gate.py # 18 go/no-go checks; read this before trusting anything
-python -m pytest            # 611 tests, no network needed
-python scripts/secret_scan.py   # credential scan; exit 1 on a hit, 3 if history is unreadable
-python eval/run_eval.py     # writes results/; model rows skip cleanly without a key
-python eval/run_eval.py --require-gemini   # exits 2 if any model row was skipped
-python scripts/serve.py     # the Streamlit demo (python -m streamlit; no shell needed)
+cp .env.example .env            # optional: GEMINI_API_KEY; .env is gitignored
+python scripts/kill_gate.py     # 18 go/no-go checks
+python -m pytest                # 659 tests, no network needed
+python scripts/secret_scan.py   # tree and git history; exit 1 on a hit, 3 if history is unreadable
+python eval/run_eval.py         # model rows skip cleanly without a key
+python scripts/serve.py         # the Streamlit demo
 ```
 
-`secret_scan.py` has three outcomes, because "could not check" is not "checked
-and clean": **0** prints `RESULT: clean` (tree *and* history), **1** means
-something matched — do not push, and **3** means the tree is clean but there was
-no history to read: either you are running from the ZIP, which has no `.git`, or
-`git` is not on `PATH`. Run it from a clone for the full claim.
+The key is read from Streamlit secrets (or `.env` locally) and is never written to the repo or logs. The sidebar reports only whether a key is *configured*, never any part of it. Without a key the app still runs with the `offline` extractor; with `gemini` selected and no key, every case fails closed to `HOLD`. Deployment notes are in `docs/DEPLOY.md`.
 
-To regenerate the screenshots in `docs/screenshots/` from a running app:
+## Layout
 
-```bash
-pip install playwright && playwright install --with-deps chromium
-python scripts/capture_screenshots.py --extractor gemini
+```
+src/threadgate/   normalize, tokens, extract (model call + adversarial harnesses),
+                  validate, compare, invariants, actions, reference, attestation,
+                  policy, baseline, pipeline
+data/             synthetic vendor master and the frozen case sets
+eval/             evaluation harness          results/   stored report
+app/              Streamlit demo              scripts/   kill gate, secret scan, serve
+docs/             architecture diagram, screenshots, deployment and submission notes
 ```
 
-**Deployment.** The key is read from Streamlit secrets (or `.env` locally) and
-is never written to the repo, logs, or the UI. There is no public deployment
-yet - this is run locally or on Streamlit Community Cloud, and a URL will
-appear here once one exists. See `docs/DEPLOY.md`.
+The screenshots in `docs/screenshots/` were captured with the offline test double, not Gemini. `docs/screenshots/MANIFEST.json` records the extractor and source for each.
 
-## Layout
+## Honest limits
 
-```
-src/threadgate/
-  normalize.py    text normalisation with offset preservation
-  tokens.py       deterministic token finder (account/IFSC/IBAN/amount/phone)
-  extract.py      the model call + the two adversarial harnesses
-  validate.py     the closed-world evidence validator
-  compare.py      field-level diff against the vendor record
-  invariants.py   I1a/I1b/I3/I4/I5 never consult the model;
-                  I2/I2b/I2c/I6 validate it and can only reject
-  clock.py        injected time source, so freshness is a deterministic input
-  reference.py    reference version and CURRENT / STALE / MISSING
-  attestation.py  single-use verification events and their bindings
-  policy.py       the monotone decision rule
-  baseline.py     rules-only baseline, for the measured comparison
-  pipeline.py     orchestration
-data/cases/      frozen_v1 (benchmark), additions (stress), categories.json
-data/records/    synthetic vendor master
-eval/            evaluation harness and reports
-app/             Streamlit demo
-scripts/         kill gate, secret audit, screenshot capture,
-                 serve.py + clean.py (portable, no shell needed)
-docs/            architecture.svg, screenshots/, deployment + submission notes
-```
+- **The `offline` row is a test double, not a model.** It is a rules engine with a JSON interface so tests run without a key. Its 100% proves nothing about model performance.
+- **40 cases is a demo, not a field evaluation.** Half the set was written with the system already in front of the author. It shows the mechanism and catches regressions; no field error rate is claimed.
+- **The floor only covers destinations the scanner can see.** Risk in other fields (a beneficiary rename, a currency switch) depends on the model's reading, and a steered model can suppress it. I3 and I4 partly cover this. It is the real boundary of the design.
+- **A token-less request is the weakest case.** If no account number appears and the wording is not one the deterministic action layer recognises (for example "we have moved to a new bank"), a model that also suppresses the change leaves no independent evidence. Only human attestation closes it.
+- **Synthetic data only.** Every vendor, account, IFSC code and email in `data/` was fabricated. No real bank, account or banking system was involved in any result.
+- **Not a replacement for callback verification.** ThreadGate decides *when* a human must verify and hands them the diff and a checklist. The human makes the call.
 
-## Track
+### Not built, and not claimed
 
-Devpost hackathon, **AI + Cybersecurity** track.
+- **No OCR and no attachment parsing.** Opening an attacker-supplied file is an exposure, not a control. A destination in an image is held, never read.
+- **No risk score.** Invoice value, vendor age and payment history are absent by design: a score can be argued with, a destination check cannot.
+- **No cryptographic signatures and no PKI.** A verification event is a *binding*, not a proof of identity. It ties an attestation to one request, one destination and one record version. It does not show who performed the check.
+- **No automatic reference updates.** Nothing in ThreadGate writes to the vendor record. Updating it is a human operation after the callback.
+- **No mail-flow integration, no URL scanning, no threat feed, no embeddings.**
+- **The verification store is in memory.** It is neither durable nor distributed; a restart begins empty.
 
-Complementary to ingestion-side filtering: tools that screen incoming mail for
-prompt injection and phishing sit *upstream* of this. ThreadGate assumes a
-hostile email has already arrived and gates the *action* it requests.
+`tests/test_reference_and_attestation.py` fails if this list stops being true, in either direction.
 
 ## Prior work
 
diff --git a/docs/DEVPOST.md b/docs/DEVPOST.md
index c29c110..8bf7eb3 100644
--- a/docs/DEVPOST.md
+++ b/docs/DEVPOST.md
@@ -80,7 +80,7 @@ on file, and if not, does a human have to look at it?**
 ### 2. Technical approach and components
 
 **Stack:** Python, Google Gemini (`gemini-2.5-flash`) for interpretation only,
-Pydantic for output contracts, Streamlit for the demo, pytest for the 611-test
+Pydantic for output contracts, Streamlit for the demo, pytest for the 659-test
 suite. No embeddings, no vector store, no OCR, no URL scanning, no threat feed.
 
 The pipeline is deliberately asymmetric. The model sits in exactly one box, and
@@ -194,8 +194,8 @@ Measured, and reproducible with `python eval/run_eval.py`:
 | Rules-only baseline (raw) | 50.0% | 2 | 60.0% | 2 |
 | Rules-only baseline + normalisation | 60.0% | 0 | 70.0% | 0 |
 | ThreadGate (Gemini) | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` |
-| ThreadGate, model steered to say "no change" | 65.0% | **0** | 75.0% | **0** |
-| ThreadGate, steered model forging a verbatim quote | 65.0% | **0** | 75.0% | **0** |
+| ThreadGate, model steered to say "no change" | 70.0% | **0** | 80.0% | **0** |
+| ThreadGate, steered model forging a verbatim quote | 70.0% | **0** | 80.0% | **0** |
 | The model alone, deciding the verdict | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` |
 | ThreadGate, ablation: independent scan removed | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` |
 | ThreadGate, ablation: evidence validation removed | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` | `[[FILL: NOT RUN]]` |
@@ -326,7 +326,7 @@ of model behaviour, and must not be captioned as Gemini output. Re-running
    **2** if any model system was skipped, so a silently absent key cannot look
    like a completed run. Output lands in `results/`.
 2. Re-run `python scripts/kill_gate.py` and `python -m pytest`; both must be
-   green on the final commit (611 tests, 18 kill-gate checks).
+   green on the final commit (659 tests, 18 kill-gate checks).
 3. `git log --reverse` — the first commit must be dated after 2026-10-03 12:00
    EDT / 21:30 IST.
 4. Confirm no key is committed: `python scripts/secret_scan.py` must print
diff --git a/src/threadgate/actions.py b/src/threadgate/actions.py
index ceb0b2a..509f0e7 100644
--- a/src/threadgate/actions.py
+++ b/src/threadgate/actions.py
@@ -322,6 +322,35 @@ def has_live_change_or_routing_action(text: str) -> bool:
     )
 
 
+# Verbs that appear in TRANSFER_VERB only because "change X to Y" can reroute
+# money. Used as nouns - "any change to our bank details" - they match the
+# transfer pattern without instructing anything. They are excluded where the
+# text being read is a whole email rather than one quoted sentence.
+_CHANGE_TYPE_LEAD = re.compile(
+    r"^(?:change|changing|update|updating|amend|amending|revise|revising|"
+    r"replace|replacing)\b",
+    re.IGNORECASE,
+)
+
+
+def has_live_money_routing_action(text: str) -> bool:
+    """A live instruction that moves money somewhere, read over a whole email.
+
+    Only `transfer` and `flow` actions count, and a `transfer` match that is led
+    by a change-type verb does not: over a full message those are mostly
+    descriptions of process ("any change to our bank details will be confirmed
+    by a call"), and counting them would hold legitimate no-change mail. Negated
+    and conditional actions are not live, as everywhere else in this module.
+    """
+    for a in find_actions(text):
+        if not a.live or a.kind not in ("transfer", "flow"):
+            continue
+        if a.kind == "transfer" and _CHANGE_TYPE_LEAD.match(text[a.start:a.end]):
+            continue
+        return True
+    return False
+
+
 def link_actions_to_destinations(
     text: str, tokens, max_distance: int = 140
 ) -> list[RoutingLink]:
diff --git a/src/threadgate/attestation.py b/src/threadgate/attestation.py
index 99cadd1..14e7e7b 100644
--- a/src/threadgate/attestation.py
+++ b/src/threadgate/attestation.py
@@ -30,6 +30,7 @@ from __future__ import annotations
 
 import hashlib
 import json
+import unicodedata
 from dataclasses import dataclass, field
 from typing import Any
 
@@ -104,6 +105,21 @@ class VerificationContext:
     reference_version: str
 
 
+def canonical_event_id(event_id: object) -> str:
+    """The key a verification event is burned under.
+
+    An id is the same id however it is spelled. Compatibility-normalise it,
+    drop invisible format characters (zero-width spaces, soft hyphens), strip
+    whitespace and case-fold. Without this the burn was keyed on the raw string,
+    so "EV-1 " or "ev-1" was a different, unused event. Folding more than is
+    strictly needed is the safe direction: a collision costs minting one more
+    event, a miss is a replay.
+    """
+    text = unicodedata.normalize("NFKC", str(event_id or ""))
+    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
+    return text.strip().casefold()
+
+
 @dataclass(frozen=True)
 class VerificationEvent:
     """The human's attestation, and everything it was minted against.
@@ -149,6 +165,9 @@ class AttestationStore:
 
     def __init__(self, used: dict[str, tuple[str, str, str, str]] | None = None) -> None:
         self._used: dict[str, tuple[str, str, str, str]] = dict(used or {})
+        # The id as first presented, for reporting. The burn is keyed on the
+        # canonical form; this only keeps introspection readable.
+        self._shown: dict[str, str] = {}
 
     def consume(self, event: VerificationEvent, context: VerificationContext,
                 required: bool = True) -> AttestationOutcome:
@@ -161,14 +180,15 @@ class AttestationStore:
                 "so there is nothing for a human to verify.",
                 consumed=False,
             )
-        if not str(event.event_id or "").strip():
+        key = canonical_event_id(event.event_id)
+        if not key:
             return AttestationOutcome(
                 False, EMPTY_EVENT_ID,
                 "The verification event has no id and cannot be bound to anything.",
                 consumed=False,
             )
 
-        if event.event_id in self._used:
+        if key in self._used:
             return AttestationOutcome(
                 False, REPLAY,
                 f"Verification event {event.event_id} has already been used. A "
@@ -179,7 +199,8 @@ class AttestationStore:
 
         # Burn it now. Every path from here is a rejection, and a failed attempt
         # must not leave the event available for a second try.
-        self._used[event.event_id] = event.binding
+        self._used[key] = event.binding
+        self._shown[key] = str(event.event_id)
 
         if event.vendor_id != context.vendor_id:
             return AttestationOutcome(
@@ -223,10 +244,10 @@ class AttestationStore:
 
     # -- introspection -----------------------------------------------------
     def used_event_ids(self) -> frozenset[str]:
-        return frozenset(self._used)
+        return frozenset(self._shown.get(k, k) for k in self._used)
 
     def has_used(self, event_id: str) -> bool:
-        return event_id in self._used
+        return canonical_event_id(event_id) in self._used
 
     def __len__(self) -> int:
         return len(self._used)
@@ -235,7 +256,7 @@ class AttestationStore:
     def dump(self) -> list[dict[str, Any]]:
         """Serialisable record of every consumed event, for persistence."""
         return [
-            {"event_id": eid, "vendor_id": b[0], "request_id": b[1],
+            {"event_id": self._shown.get(eid, eid), "vendor_id": b[0], "request_id": b[1],
              "destination_digest": b[2], "reference_version": b[3]}
             for eid, b in sorted(self._used.items())
         ]
@@ -243,17 +264,21 @@ class AttestationStore:
     @classmethod
     def restore(cls, rows: list[dict[str, Any]] | None) -> "AttestationStore":
         used = {}
+        shown = {}
         for row in rows or []:
-            eid = str(row.get("event_id") or "").strip()
+            eid = canonical_event_id(row.get("event_id"))
             if not eid:
                 continue
+            shown[eid] = str(row.get("event_id"))
             used[eid] = (
                 str(row.get("vendor_id", "")),
                 str(row.get("request_id", "")),
                 str(row.get("destination_digest", "")),
                 str(row.get("reference_version", "")),
             )
-        return cls(used)
+        store = cls(used)
+        store._shown = shown
+        return store
 
 
 @dataclass
diff --git a/src/threadgate/policy.py b/src/threadgate/policy.py
index 2d0875b..f584f58 100644
--- a/src/threadgate/policy.py
+++ b/src/threadgate/policy.py
@@ -18,6 +18,7 @@ Decision surface:
 
 from __future__ import annotations
 
+from .actions import has_live_money_routing_action
 from .invariants import (
     alternate_routing_floor,
     confirmation_request_justified,
@@ -216,8 +217,49 @@ def decide(
     else:
         no_change_accepted = False
 
+    # An accepted "nothing to do" verdict is a statement about the quoted
+    # sentence. It says nothing about the rest of the email, so the same shared
+    # action layer is applied to everything outside the quote: a model that
+    # quotes the harmless sentence must not be able to leave a live instruction
+    # about where money goes in another sentence unexamined. Only money-moving
+    # routing actions are used (`has_live_money_routing_action`). Generic change
+    # verbs are deliberately left out: applied to the whole email they fire on
+    # descriptions of process and on future-tense reassurance in legitimate
+    # no-change mail (frozen cases TG-009, TG-011 and TG-026), which would turn
+    # those into holds. Negated and conditional routing language is not live.
+    conflicting_instruction = False
+    if no_change_accepted and validation.intent_span_norm:
+        start, end = validation.intent_span_norm
+        outside = nt.text[:start] + "\n" + nt.text[end:]
+        if has_live_money_routing_action(outside):
+            conflicting_instruction = True
+            no_change_accepted = False
+            findings.append(
+                Finding(
+                    code="I2D_CONFLICTING_INSTRUCTION_OUTSIDE_QUOTE",
+                    severity="info",
+                    message=(
+                        "The model reports nothing to do and its quote supports that, but "
+                        "another sentence in the email carries a live instruction about where payments go "
+                        "instruction. The verdict is not accepted."
+                    ),
+                    snippet=quote[:200],
+                    span_norm=validation.intent_span_norm,
+                )
+            )
+
     unverifiable = False
-    if not no_change_accepted and not validation.verified_claims:
+    if conflicting_instruction and not validation.verified_claims:
+        unverifiable = True
+        findings.append(
+            unverifiable_finding(
+                "The email contains a payment change or routing instruction that sits "
+                "outside the sentence the model relied on, and no value in it could be "
+                "verified against the record."
+            )
+        )
+        reasons.append("unverifiable_no_values")
+    elif not no_change_accepted and not validation.verified_claims:
         # Nothing survived validation, and the model is not credibly saying
         # "nothing to do". Either it admits it cannot read the values, or it
         # claims a change it could not point at, or deterministic change
diff --git a/src/threadgate/tokens.py b/src/threadgate/tokens.py
index 4ad8fa0..b4760b9 100644
--- a/src/threadgate/tokens.py
+++ b/src/threadgate/tokens.py
@@ -10,9 +10,11 @@ Two design points matter:
    the reason the injection cases that carry a real number still get caught.
 
 2. It refuses to classify a digit run as an account number unless payment
-   context is nearby, and it refuses outright when nearby context says the
-   number is an invoice, a phone or a password. Precision here is what buys us
-   the right to treat "an account number we do not recognise" as a hard floor.
+   context is nearby, and it refuses when nearby context says the number is an
+   invoice, a phone or a password - but only when the number carries no explicit
+   account label. A labelled account number is always an account, because the
+   sender controls which words sit near it. Precision here is what buys us the
+   right to treat "an account number we do not recognise" as a hard floor.
 """
 
 from __future__ import annotations
@@ -97,18 +99,22 @@ def find_tokens(nt: NormalizedText) -> list[Token]:
         before = text[max(0, m.start() - 60): m.start()]
         after = text[m.end(): min(len(text), m.end() + 60)]
 
-        if DENY_CONTEXT.search(before[-45:]) or DENY_CONTEXT.search(after[:45]):
-            tokens.append(Token("number", raw, digits, m.start(), m.end(), context="denied"))
-            consumed.append((m.start(), m.end()))
-            continue
-
         has_context = bool(ACCOUNT_CONTEXT.search(before[-60:]) or ACCOUNT_CONTEXT.search(after[:60]))
+
+        # An explicit account label wins over a deny-list word. The sender writes
+        # the email, so the sender decides whether "ref", "invoice" or "contact"
+        # sits near the number; if that could demote a labelled account number,
+        # one parenthesised "(ref: ...)" would switch the independent floor off.
+        # The cost of the other direction is a false hold, which is a phone call.
         if has_context and 9 <= len(digits) <= 18:
             tokens.append(
                 Token("account", raw, digits, m.start(), m.end(), last4=digits[-4:],
                       context=(before[-40:] + "|" + after[:40]).strip())
             )
             consumed.append((m.start(), m.end()))
+        elif DENY_CONTEXT.search(before[-45:]) or DENY_CONTEXT.search(after[:45]):
+            tokens.append(Token("number", raw, digits, m.start(), m.end(), context="denied"))
+            consumed.append((m.start(), m.end()))
         else:
             tokens.append(Token("number", raw, digits, m.start(), m.end(), context="no payment context"))
 
diff --git a/tests/test_deny_context_bypass.py b/tests/test_deny_context_bypass.py
new file mode 100644
index 0000000..ec44a2f
--- /dev/null
+++ b/tests/test_deny_context_bypass.py
@@ -0,0 +1,98 @@
+"""A deny-list word must not switch the independent account floor off.
+
+The floor's claim is that an account number the record does not know about is a
+hold *whatever the model said*. That only holds if the token finder still sees
+the number. `tokens.DENY_CONTEXT` demotes a digit run to a plain `number` when
+words such as "invoice", "ref" or "contact" sit nearby, and before this fix it
+did so even when the same run was explicitly labelled "account". The sender
+writes the email, so the sender chooses whether such a word is nearby: one
+parenthesised "(ref: ...)" after the number was enough to make every extractor,
+including a steered model, return CLEAR.
+
+These tests pin the corrected behaviour in both directions:
+
+* an explicitly labelled account number is an account, whatever else is nearby;
+* numbers with no account label (invoice, PO, phone) are still not accounts, so
+  the precision the deny list exists for is preserved.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from threadgate.normalize import normalize_text
+from threadgate.pipeline import email_to_text, run_case
+from threadgate.tokens import find_tokens
+
+UNKNOWN_ACCOUNT = "50100234559821"  # not the account on file for V-1001, not an alternate
+
+# Each body states an explicit account label and an unknown account, plus a
+# word from the deny list somewhere inside the 45-character window.
+DENY_WORD_BODIES = {
+    "invoice_in_sentence": (
+        "Please remit invoice INV-2201 to the new account "
+        f"{UNKNOWN_ACCOUNT} instead of the old one."
+    ),
+    "ref_after_number": (
+        f"From today our new account is {UNKNOWN_ACCOUNT} (ref: October remittance)."
+    ),
+    "reference_before_number": (
+        f"As per reference letter, please pay to account {UNKNOWN_ACCOUNT} from now on."
+    ),
+    "contact_before_number": (
+        f"Contact me if questions. Pay to account {UNKNOWN_ACCOUNT} from now on."
+    ),
+    "portal_after_number": (
+        f"Update our account to {UNKNOWN_ACCOUNT}, as shown in the portal."
+    ),
+}
+
+EXTRACTORS = ("offline", "compromised", "compromised_quote")
+
+
+def _case(body: str) -> dict:
+    return {
+        "id": "REG-DENY",
+        "vendor_id": "V-1001",
+        "email": {
+            "from": "Meera Iyer <meera.iyer@northwind.example>",
+            "reply_to": "meera.iyer@northwind.example",
+            "subject": "Payments",
+            "received_at": "2026-10-06T09:12:00+05:30",
+            "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
+            "body": f"Hi team,\n\n{body}\n\nMeera",
+        },
+    }
+
+
+@pytest.mark.parametrize("name", sorted(DENY_WORD_BODIES))
+def test_a_deny_word_does_not_demote_a_labelled_account_number(name):
+    case = _case(DENY_WORD_BODIES[name])
+    tokens = find_tokens(normalize_text(email_to_text(case["email"])))
+    kinds = {t.normalized: t.kind for t in tokens if t.normalized == UNKNOWN_ACCOUNT}
+    assert kinds == {UNKNOWN_ACCOUNT: "account"}, (name, kinds)
+
+
+@pytest.mark.parametrize("extractor", EXTRACTORS)
+@pytest.mark.parametrize("name", sorted(DENY_WORD_BODIES))
+def test_a_deny_word_cannot_release_an_unknown_account(vendors, name, extractor):
+    """Includes both steered-model harnesses: the floor must not ask the model."""
+    result = run_case(_case(DENY_WORD_BODIES[name]), vendors, extractor_mode=extractor)
+    assert result.decision.decision == "HOLD", (
+        name, extractor, result.decision.decision, result.decision.reasons
+    )
+
+
+@pytest.mark.parametrize(
+    "text",
+    [
+        "Invoice number 4400123456789 is attached for October.",
+        "Purchase order 9988776655 was raised on 3 October.",
+        "Please call our mobile 9845012345 if anything is unclear.",
+        "Our GSTIN reference 2900123456789 is on the invoice.",
+    ],
+)
+def test_numbers_with_no_account_label_are_still_not_accounts(text):
+    """The precision the deny list exists for is preserved."""
+    tokens = find_tokens(normalize_text(text))
+    assert [t for t in tokens if t.kind == "account"] == [], text
diff --git a/tests/test_documentation_truth.py b/tests/test_documentation_truth.py
index fd4ff48..2696e83 100644
--- a/tests/test_documentation_truth.py
+++ b/tests/test_documentation_truth.py
@@ -112,10 +112,14 @@ def test_nothing_claims_the_production_model_sees_the_record():
     assert "the email and nothing else" in devpost
 
 
-def test_nothing_claims_a_deployment_that_does_not_exist():
+LIVE_URL = "https://threadgate-ptxsbmfkqobnh8ai7arwv4.streamlit.app/"
+
+
+def test_the_readme_links_the_real_deployment_and_no_stale_denial():
+    """The app is deployed; the README must say so, and must not deny it."""
     readme = doc("README.md")
-    assert not re.search(r"^Deployed:", readme, re.MULTILINE)
-    assert "no public deployment" in readme
+    assert LIVE_URL in readme
+    assert "no public deployment" not in readme.lower()
 
 
 def test_the_prior_work_statement_names_the_right_hackathon():
diff --git a/tests/test_event_id_replay_variants.py b/tests/test_event_id_replay_variants.py
new file mode 100644
index 0000000..558be62
--- /dev/null
+++ b/tests/test_event_id_replay_variants.py
@@ -0,0 +1,81 @@
+"""A single-use event is single-use however its id is spelled.
+
+The store burns an event id on presentation. Before this fix the burn was keyed
+on the id exactly as presented, while the empty-id check already stripped
+whitespace - so the same event, re-presented as `"EV-1 "`, `"ev-1"` or with a
+zero-width character inside it, was a different key and was accepted a second
+time against the same request, destination and record version. The guarantee
+"each event id may be presented once, ever" did not hold.
+
+The key is now canonical: compatibility-normalised, format characters removed,
+whitespace stripped and case-folded. Folding more aggressively than strictly
+necessary is the safe direction, because the cost of two ids colliding is that
+a second, distinct event has to be minted, and the cost of the opposite is a
+replay.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from threadgate.attestation import (
+    ACCEPTED,
+    EMPTY_EVENT_ID,
+    REPLAY,
+    AttestationStore,
+    VerificationContext,
+    VerificationEvent,
+)
+
+CTX = VerificationContext("V-1001", "REQ-1", "DIG-1", "v1")
+
+
+def _event(event_id: str) -> VerificationEvent:
+    return VerificationEvent(event_id, "V-1001", "REQ-1", "DIG-1", "v1")
+
+
+VARIANTS = {
+    "trailing_space": "EV-1 ",
+    "leading_space": " EV-1",
+    "trailing_newline": "EV-1\n",
+    "lowercase": "ev-1",
+    "fullwidth": "\uff25\uff36-1",
+    "zero_width_inside": "EV\u200b-1",
+    "soft_hyphen_inside": "E\u00adV-1",
+}
+
+
+@pytest.mark.parametrize("name", sorted(VARIANTS))
+def test_a_respelled_event_id_is_a_replay(name):
+    store = AttestationStore()
+    assert store.consume(_event("EV-1"), CTX).code == ACCEPTED
+    outcome = store.consume(_event(VARIANTS[name]), CTX)
+    assert outcome.accepted is False, (name, outcome.code)
+    assert outcome.code == REPLAY, (name, outcome.code)
+
+
+@pytest.mark.parametrize("name", sorted(VARIANTS))
+def test_has_used_agrees_with_consume(name):
+    store = AttestationStore()
+    store.consume(_event("EV-1"), CTX)
+    assert store.has_used(VARIANTS[name]) is True
+
+
+def test_an_id_made_only_of_invisible_characters_is_empty():
+    store = AttestationStore()
+    outcome = store.consume(_event("\u200b\u200b"), CTX)
+    assert outcome.code == EMPTY_EVENT_ID
+    assert len(store) == 0
+
+
+def test_a_restored_store_still_rejects_respelled_ids():
+    first = AttestationStore()
+    first.consume(_event("EV-1"), CTX)
+    restored = AttestationStore.restore(first.dump())
+    assert restored.consume(_event("ev-1 "), CTX).code == REPLAY
+
+
+def test_distinct_ids_are_still_independent():
+    store = AttestationStore()
+    assert store.consume(_event("EV-1"), CTX).code == ACCEPTED
+    assert store.consume(_event("EV-2"), CTX).code == ACCEPTED
diff --git a/tests/test_hidden_conflicting_instruction.py b/tests/test_hidden_conflicting_instruction.py
new file mode 100644
index 0000000..c52daf9
--- /dev/null
+++ b/tests/test_hidden_conflicting_instruction.py
@@ -0,0 +1,97 @@
+"""A generic "nothing is changing" quote must not shield a change made elsewhere.
+
+I2b checks that the *quoted* sentence says nothing is changing and carries no
+live instruction of its own. It did not look at the rest of the email. A model
+- or a steered one - could quote the harmless sentence and leave a routing
+instruction in another sentence of the same message unexamined:
+
+    Our bank details remain unchanged. However, going forward please pay into
+    our new account at Axis Bank.
+
+The quote is genuine and says "unchanged", the second sentence names no digit
+run for the scanner to find, and the verdict was accepted: CLEAR.
+
+The deterministic action layer that I5, I2b and I2c already share can see the
+second sentence. These tests require it to be consulted for the rest of the
+email as well, and require that doing so does not turn legitimate no-change or
+retraction mail into holds.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from threadgate.pipeline import run_case
+from threadgate.schema import Extraction
+
+NO_CHANGE_QUOTE = "Our bank details remain unchanged."
+CONFIRM_QUOTE = "Can you confirm you have our correct bank details on file?"
+
+HIDDEN = {
+    "tokenless_new_account": (
+        f"{NO_CHANGE_QUOTE} However, going forward please pay into our new "
+        "account at Axis Bank; we will send the number by phone."
+    ),
+    "payments_should_now_go": (
+        f"{NO_CHANGE_QUOTE} Payments should now be made to our Axis Bank account."
+    ),
+}
+
+
+def _case(body: str) -> dict:
+    return {
+        "id": "REG-HIDDEN",
+        "vendor_id": "V-1001",
+        "email": {
+            "from": "Meera Iyer <meera.iyer@northwind.example>",
+            "reply_to": "meera.iyer@northwind.example",
+            "subject": "Payments",
+            "received_at": "2026-10-06T09:12:00+05:30",
+            "auth": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
+            "body": f"Hi team,\n\n{body}\n\nMeera",
+        },
+    }
+
+
+def _model(intent: str, quote: str):
+    return lambda nt, vendor: Extraction(
+        intent=intent, intent_evidence=quote, summary="x", claims=[]
+    )
+
+
+@pytest.mark.parametrize("name", sorted(HIDDEN))
+def test_no_change_quote_cannot_hide_a_routing_instruction(vendors, name):
+    result = run_case(
+        _case(HIDDEN[name]), vendors, extractor_fn=_model("no_change", NO_CHANGE_QUOTE)
+    )
+    assert result.decision.decision == "HOLD", (name, result.decision.reasons)
+
+
+def test_confirmation_quote_cannot_hide_a_routing_instruction(vendors):
+    body = (
+        f"{CONFIRM_QUOTE} Also, from next month please pay into our new account "
+        "at Axis Bank."
+    )
+    result = run_case(
+        _case(body), vendors, extractor_fn=_model("confirmation_request", CONFIRM_QUOTE)
+    )
+    assert result.decision.decision == "HOLD", result.decision.reasons
+
+
+@pytest.mark.parametrize(
+    "body",
+    [
+        # no-change, negated change language elsewhere
+        f"{NO_CHANGE_QUOTE} We are not changing our bank details this quarter.",
+        # retraction of an earlier request
+        f"{NO_CHANGE_QUOTE} Please disregard my earlier request to change our account.",
+        # "change to" used as a noun in a description of process (frozen TG-026)
+        f"{NO_CHANGE_QUOTE} Going forward, any change to our bank details will be "
+        "confirmed by a call from me before it takes effect.",
+        # ordinary business content around the quote
+        f"{NO_CHANGE_QUOTE} Invoice INV-2201 covers October services; payment terms are as agreed.",
+    ],
+)
+def test_legitimate_no_change_mail_still_clears(vendors, body):
+    result = run_case(_case(body), vendors, extractor_fn=_model("no_change", NO_CHANGE_QUOTE))
+    assert result.decision.decision == "CLEAR", (body, result.decision.reasons)
