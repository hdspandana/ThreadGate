# Video script and demo sequence

Everything below describes what the app actually renders at commit `6f9125f`.
The narration quotes the real badge text, the real diff values and the real
checklist items, so nothing has to be invented on camera.

**Read this before recording:** run the app with `GEMINI_API_KEY` set and the
**`gemini`** extractor selected. Recording with the `offline` test double and
calling it Gemini would be a false claim about the model. If the key is not
available in time, record with `offline` and say the words "test double" out
loud on screen — do not let the footage imply a live model.

---

## Part 1 — The 3-minute script

Target 185–195 seconds of narration, ~145 words per minute.

### 0:00–0:22 — The problem

**On screen:** title card, then the app landing on TG-001.

> "AI makes fraudulent emails fluent. Every tell a payments clerk is trained on
> — awkward phrasing, a strange domain, an odd greeting — gets weaker every
> year. So screening the *wording* is a losing game.
> This asks a different question: does what this email asks me to *do* match
> what I already have on file? That question doesn't depend on how good the
> writing is."

### 0:22–0:32 — The one sentence that matters

**On screen:** the architecture diagram, `docs/architecture.svg`. Pause on the
crossed-out arrow from the model to the verdict.

> "AI interprets the email. Code verifies the change against the record. A human
> attests before anything executes. The model never gets a vote on the verdict —
> there is no arrow from it to the decision, and that's drawn deliberately."

### 0:32–1:15 — The canonical case

**On screen:** TG-001. Show the email, the red highlight on `50100234559821`,
then the **Diff against the record** table and the **Before anything executes**
checklist.

> "Here's a payment-detail change. The email is unremarkable — that's the point.
> The account on file ends 4455. The email asks for 9821.
> ThreadGate returns HOLD, and it hands over the exact diff and a callback
> checklist: call the vendor on the number already on file, not any number in
> this email; read the account back digit by digit; two-person approval.
> HOLD is a review state, not an accusation. Most held mail turns out to be
> legitimate."

### 1:15–1:50 — What the model is actually for

**On screen:** switch to TG-007. Pause on the caption line
"rules-only baseline says **HOLD**" beneath a **CLEAR** badge.

> "This one says: we are *not* changing our bank details. The word 'changing'
> sits next to the word 'account', so a rules baseline holds it — false hold.
> The gate reads the negation and identifies no change.
> That's the honest case for the AI here: it isn't catching fraud rules can't
> see. It's removing holds a human shouldn't have to make. The rules baseline
> is at 0% on this category and 17% on mention-versus-request."

### 1:50–2:20 — The claim the whole submission rests on

**On screen:** TG-001, then switch the Extractor to **`compromised_quote`**.
The badge must stay **HOLD**.

> "Now the interesting part. I'm going to switch the interpreter to a harness
> that is *steered to lie* — it always reports 'no change', and in this variant
> it forges a verbatim quote from the email to justify it.
> Still HOLD. Across both case sets, zero unsafe hold releases and zero
> non-CLEAR releases - on these forty cases.
> Why? Because the account floor never asks the model. It scans the email
> itself. A model that has been fully compromised buys friction, not releases."

### 2:20–2:40 — The limit, said out loud

**On screen:** TG-034. Highlight the checklist item about the attachment.

> "And the limit, because it matters. This email hides the new account inside an
> image, with a decoy known account in the text. ThreadGate does no OCR and
> never opens attachments — so the safe answer is HOLD, never CLEAR. If the
> destination isn't in text, the text pipeline cannot verify it."

### 2:40–2:56 — The numbers, and what they aren't

**On screen:** press **Run 20 cases across every system**, show the table and
the per-category breakdown.

> "Forty synthetic cases. The rules baseline gets 50% on the pre-frozen set with
> two unsafe; normalisation fixes the evasion cases but not the reading ones.
> The steered model: zero unsafe and zero non-CLEAR releases, every time -
> on these forty cases. That is the scope of the claim, and I'd rather state
> the limit than overstate the result."
> `[INSERT: ThreadGate-with-Gemini accuracy and unsafe count, read from
> results/latest.json after the real run]`
> This is a gate, not a score. There's no risk score in it, and none is coming.
> Code is in the repo; everything here is reproducible with one command."

### 2:56–3:10 — What the human does next, and why it can't be carried elsewhere

**On screen:** TG-001's **Before anything executes** checklist, then the
**Human verification** panel showing `PENDING`, and the **The record this was
checked against** panel.

> "And then a person. The gate doesn't update anything — it hands over the exact
> diff and a callback script: call the number already on file, not any number in
> the email; read the account back digit by digit; two-person approval.
> When they attest, that verification is bound to this request, this
> destination, and this version of the record. Present it twice and it's
> refused. Carry it to another request and it's refused. Move the record to v2
> and the v1 verification stops counting — the record moved on, so the old check
> no longer describes it. And if the record is stale or empty, nothing clears in
> the first place.
> Two limits left: there's no signature, so this proves nothing about *who*
> verified, and the store is per-process, so it doesn't survive a restart."
> Those last two sentences are limits, and saying them is worth more than
> hiding them.

---

## Where the real Gemini numbers go

After `python eval/run_eval.py --require-gemini`, open `results/latest.json`
and fill these three places. Nothing else in the script needs changing.

| Place | What to read | What to say |
| --- | --- | --- |
| 1:15–1:50, the negation beat | n/a | unchanged — the AI value story does not depend on a score |
| 2:40–2:56, the numbers beat | `sets.v1.metrics.gemini` | "ThreadGate with the real model gets X% on the pre-frozen set with Y unsafe" |
| 2:40–2:56, optional | `sets.v1.metrics.ai_only` vs `gemini` | "the same model, deciding instead of interpreting, gets Z%" |
| 2:40–2:56, optional | `hybrid_no_scan`, `hybrid_no_validation` | "remove the destination scan and accuracy drops to A%; remove evidence validation and it drops to B%" |

**Do not** fill any of these from the `offline` row, from the `compromised`
rows, or from anything other than `results/latest.json`. The offline double is a
regression guard, not a model.

---

## Part 2 — Demo sequence (click-by-click)

Record at 1500x1050, browser at default zoom.

**Setup**

1. `cp .env.example .env`, add `GEMINI_API_KEY=...`
2. `streamlit run app/streamlit_app.py`
3. Confirm the sidebar reads `API key: configured (ends ...xxxx)`.

**Shot 1 — landing / TG-001**

- Case set: `frozen_v1 - PRIMARY PRE-FROZEN BENCHMARK` (default)
- Extractor: `gemini`
- Case: `TG-001 - Plain account-number change, fluent AI-written prose  [HOLD]`
- Expand **What the model returned, and what the validator admitted** — this is
  the single most persuasive panel in the app: the model's raw output on one
  side, what the validator admitted on the other.

**Shot 2 — TG-007 (the negation case)**

- Case: `TG-007`
- Pause on the caption: `rules-only baseline says **HOLD**` under a CLEAR badge.

**Shot 3 — the steered model**

- Case: back to `TG-001`
- Extractor: `compromised_quote`
- The badge must not change. Say so.

**Shot 4 — TG-034 (image-hidden)**

- Extractor: back to `gemini`
- Case: `TG-034`
- Read the second checklist item aloud.

**Shot 5 — the corpus**

- Press **Run 20 cases across every system**
- Wait for the table, then the per-category table
- Switch Case set to `v1 + stress - COMBINED, STRESS EVALUATION ONLY` and re-run
  only if you want the 40-case view — and if you do, say on camera that it is a
  stress evaluation, not a benchmark.

---

## Part 3 — Things not to say on camera

- Do not say CLEAR means "safe", "approved", "verified" or "not fraud". It means
  **no change was identified by this prototype**. The badge says so; the UI has
  no green state anywhere, on purpose.
- Do not say the model "catches what rules can't". It doesn't — on obfuscation,
  rules plus normalisation is the thing that works. The model's contribution is
  fewer false holds and the token-less cases.
- Do not quote a Gemini number that isn't in `results/latest.json`.
- Do not describe the 40-case combined set as a benchmark.
- Do not claim OCR, attachment parsing, URL scanning or threat intelligence.
  They are not there, and the diagram says so.
- Do not call a verification event a signature, a certificate, or proof of
  identity. It is a *binding*: single-use, tied to one request, one destination
  and one record version. There is no key material anywhere in the project.
- Do not say the attestation store is durable. Consumed event ids live in
  memory; a restart starts empty. `dump()` / `restore()` exist, the demo does
  not use them.
- Do not say ThreadGate updates the vendor record. It never writes to it —
  updating a record is a human operation done out of band after the callback.

---

## Part 4 — Reproducing the screenshots

```bash
python scripts/capture_screenshots.py --extractor gemini
```

Overwrites the five PNGs in `docs/screenshots/` with captures of the real model
path and refuses to save any shot whose rendered chrome contains an obsolete
decision term. Keep the no-key captures as internal evidence only; they are not
Gemini screenshots and must never be labelled as such.
