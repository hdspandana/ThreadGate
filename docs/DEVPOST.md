# Devpost submission — draft

**Status: draft. Nothing here quotes a model result that has not been measured.**
Every `[[FILL …]]` marker is a gap that must be closed before submitting. Numbers
that appear without a marker have been reproduced by `python eval/run_eval.py`.

---

## Title

**ThreadGate — an action-level gate for AI-written payment-change emails**

## Short description

AI made fraudulent email fluent, so judging the wording no longer works.
ThreadGate judges the change instead: a model reads the email, code verifies the
requested bank detail against the vendor record, and a human attests before
anything executes. The model never gets a vote on the verdict — when it is
steered to lie, the gate fails closed.

## Track

AI + Cybersecurity

## Links

- GitHub repo: `[[FILL: public repo URL]]`
- Demo video (public YouTube, 2–4 min): `[[FILL: video URL]]`
- Live deployment: `[[FILL: Streamlit Community Cloud URL]]`
- Screenshots: captured, `docs/screenshots/`. Five real captures of the running
  app, not mockups — each verdict asserted against the live DOM before saving:
  1. `01_pre_registered_REVIEW.png` — TG-012, a change to an account already
     on file. The gate returns REVIEW, not HOLD; holding these is pure review
     cost.
  2. `02_destination_change_HOLD.png` — TG-001, the 4455 → 9821 diff, with the
     red "not on file" highlight and the callback checklist.
  3. `03_prompt_injection_HOLD.png` — TG-015, where the email instructs the
     assistant to report no change.
  4. `04_negation_CLEAR.png` — TG-007, the rules-only baseline holds it and the
     gate returns CLEAR.
  5. `05_evaluation_comparison.png` — the corpus table plus the per-category
     breakdown.

  Every shot shows one of exactly three words: **CLEAR / REVIEW / HOLD**.
- Architecture diagram: `docs/architecture.svg` at the repository root of
  `docs/`. It renders on GitHub and Devpost. `[[FILL: if the form insists on a
  raster upload, export with
  `python -c "import cairosvg; cairosvg.svg2png(url='docs/architecture.svg', write_to='docs/architecture.png', output_width=1160)"`]]`

Both the screenshots and the diagram must be re-taken after the real Gemini run
— see "Before submitting" below.

---

## Written description

### 1. The problem, and who has it

Fraud enabled by AI.

Business email compromise works because a payment clerk receives a fluent,
correctly-branded email from a supplier they have paid a hundred times, asking
them to update a bank account. Every year the email gets better written and
every tell that trained staff rely on — awkward phrasing, odd greetings, a
strange domain — gets weaker. The attacker does not need the email to look
suspicious; they only need the changed bank detail to reach the payment run.

Who has it: accounts-payable teams, the shared-service centres that process
vendor payments, and the treasury and controller functions that own the loss
when it goes wrong. Secondarily, the vendors themselves, whose mailboxes get
compromised and whose name gets used.

The gap this project targets is narrow and specific. Most defences sit on the
*message*: spam filters, phishing classifiers, prompt-injection screens. Those
matter, and this project assumes they have already failed — that a hostile
email is sitting in an inbox. The question ThreadGate asks is the one that
decides the loss: **does what this email asks me to do match what I already have
on file, and if not, does a human have to look at it?**

### 2. Technical approach and components

**Stack:** Python, Google Gemini (`gemini-2.5-flash`) for interpretation only,
Pydantic for output contracts, Streamlit for the demo, pytest for the 80-test
suite. No embeddings, no vector store, no OCR, no URL scanning, no threat feed.

The pipeline is deliberately asymmetric. The model sits in exactly one box, and
everything downstream of it refuses to trust it:

```
email → normalise → token finder → [Gemini: what change does this ask for?]
      → evidence validator → comparator vs vendor record → invariants → policy
      → CLEAR / REVIEW / HOLD
```

1. **Normalisation with offset preservation.** Zero-width spaces, soft hyphens,
   U+2011 hyphens, fullwidth digits and Cyrillic look-alikes are folded away
   while a character map is kept back to the raw text, so findings still
   highlight in the original email. Adversarial numbers stop being invisible.
2. **Deterministic token finder.** Finds account-like numbers, IFSC/IBAN/SWIFT
   codes, amounts and phones with spans, refusing to classify a number as an
   account when nearby context says it is an invoice, a phone or a password.
3. **The model.** Given the email and a summary of the record, Gemini returns
   structured claims, each with a verbatim quote. It is never asked whether the
   change is safe, and it has no field in which to say so.
4. **Evidence validator — the closed-world rule.** A claim is admitted only if
   its quote is found verbatim in the email and its value is locatable in the
   email or in that quote. Anything the model produced from memory or inference
   is dropped, not repaired.
5. **Comparator.** Normalises presentation and produces a field-level diff
   against the vendor record.
6. **Invariants — computed without looking at the model.**
   - *I1a/I1b*: any account number or branch code in the email that is not on
     file and not a pre-registered alternate is a hold.
   - *I2*: a `no_change` verdict must be quoted.
   - *I2b*: the quote must actually support the verdict.
   - *I3*: change asserted with nothing verifiable is a hold.
   - *I4*: if the destination is in an image, PDF or portal, it is unverifiable
     and held — the app does no OCR and never opens attachments.
7. **Policy engine — monotone.** Triggers can move a request towards `HOLD`;
   none can move it towards `CLEAR`. A verified claim can add a hold trigger but
   can never remove one. The ladder only ever runs one way:
   `CLEAR` → `REVIEW` → `HOLD`. There is deliberately no risk score: invoice value,
   vendor age and similar signals are absent by design, because a score can be
   argued with and a destination check cannot.

**What makes it more than a wrapper** is that the model's output is a hypothesis
about the email rather than a decision about the request. Three things stand
between it and the verdict: the validator, a policy the model cannot override,
and a measured comparison against a rules-only baseline.

### 3. Real-world impact, and what was measured

Impact, stated narrowly: ThreadGate does not detect fraud. It decides **when a
payment-detail change cannot be executed without a human verifying it
out-of-band**, and it hands that human the exact diff and a callback checklist.
Every hour an AP team spends on false holds is real cost, so the goal is to hold
the requests that matter and release the ones that do not.

Three sets are reported separately, because they mean different things:
`v1` is the primary pre-frozen benchmark written before any evaluation was run;
`stress` is an adversarial set written afterwards; `combined` is both, reported
only as a stress evaluation.

Measured, and reproducible with `python eval/run_eval.py`:

| System | v1 accuracy | v1 unsafe | stress accuracy | stress unsafe |
| --- | --- | --- | --- | --- |
| Rules-only baseline (raw) | 50.0% | 2 | 60.0% | 2 |
| Rules-only baseline + normalisation | 60.0% | 0 | 70.0% | 0 |
| ThreadGate (Gemini) | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` |
| ThreadGate, model steered to say "no change" | 65.0% | **0** | 75.0% | **0** |
| ThreadGate, steered model forging a verbatim quote | 65.0% | **0** | 75.0% | **0** |
| The model alone, deciding the verdict | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` |
| ThreadGate, ablation: independent scan removed | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` |
| ThreadGate, ablation: evidence validation removed | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` | `[[FILL]]` |

The last three rows are the argument that this is not a wrapper. `ai_only` is
the same model with no gate — it exists only to be compared against, and it is
not reachable from the product. The two ablations remove one safeguard each;
whatever accuracy they lose is what that safeguard was worth. Do not submit
until all four rows are filled from a real run.

**`unsafe` is the only error that can lose money** — a case that should be held
that was not. `false hold` costs a phone call.

Two results are worth stating plainly:

- **The gate fails closed.** A model that has been fully steered — always
  reporting no change, in one variant forging a verbatim quote from the email to
  justify it — produces **zero** unsafe outcomes across both sets. Accuracy
  drops and legitimate mail goes to a human instead. This is enforced by tests,
  not by hoping.
- **The rules baseline is not beaten on everything, and that matters.** It
  scores 100% on the injection and urgency categories because it holds
  *everything*, which is the same behaviour that gives it 0% on the benign
  categories and 17% on "mentions payment details but requests nothing". The
  per-category table in the README is the honest view; the headline accuracy
  averages those out.

**Limits, stated here as prominently as anywhere:** 40 synthetic cases is a
demo, not a field evaluation, and half of them were written with the system
already in front of me. The AI-independent floor only covers destinations the
text scanner can see. A token-less request whose change language the model also
suppresses has no independent evidence at all — only human attestation closes
it. There is no mail-flow integration and no OCR, by design.

---

## Video (2–4 min, public on YouTube)

Structure planned for ~3 minutes:

1. **0:00–0:25** — the problem. AI-written payment-change mail looks perfect;
   the loss comes from the changed bank detail.
2. **0:25–1:10** — the HOLD scenario, evidence highlights, the 4455 ≠ 9821 diff.
3. **1:10–1:50** — the negation case, with the rules-only column getting it
   wrong.
4. **1:50–2:30** — the steered model tries to force `CLEAR` and the gate still
   HOLDs. This is the claim the submission rests on.
5. **2:30–2:50** — the image-hidden-account case: no OCR, so it must not clear.
6. **2:50–3:00** — the evaluation table and the honest-limits box.

**"What this proves and does not"** box, included verbatim in the video and the
README:

> Proves: a model steered to say "no change" cannot suppress a bank account or
> branch code that appears in the email, because the floor never asks the model.
> Does not prove: that the model's reading is reliable, that these numbers
> transfer to the field, or that a token-less request can be caught without a
> human.

## Submission checklist

- [x] Title, short description, track
- [ ] Public YouTube video, 2–4 min
- [ ] Public GitHub repo with this README
- [x] Written description in three parts (above)
- [x] Screenshots captured — re-capture with `--extractor gemini` after the real
      run
- [x] Architecture diagram — `docs/architecture.svg`
- [ ] Deployment link
- [ ] All team members listed: `[[FILL: Devpost handles]]`
- [x] Statement that the project was built during the hackathon (`PRIOR_WORK.md`)

## Before submitting

1. Run `python eval/run_eval.py --require-gemini` with the key set, and replace
   every `[[FILL]]` in the tables above with the measured row. The command exits
   **2** if any model system was skipped, so a silently absent key cannot look
   like a completed run. Output lands in `results/`.
2. Re-run `python scripts/kill_gate.py` and `python -m pytest`; both must be
   green on the final commit (80 tests, 17 kill-gate checks).
3. `git log --reverse` — the first commit must be dated after 2026-10-03 12:00
   EDT / 21:30 IST.
4. Confirm no key is committed: `git ls-files | xargs grep -l AIza` must be
   empty. `python scripts/secret_scan.py` checks the tree and the full history.
5. Re-capture the screenshots against the real model path
   (`python scripts/capture_screenshots.py --extractor gemini`) so the corpus
   shot shows a populated `gemini` row instead of a skip warning, then commit
   the refreshed PNGs.
6. Push the public repo and deploy to Community Cloud; fill in the repo,
   video and deployment URLs above.
