# Evaluation design review — agent review v1, 2026-10-25

**Status: design review completed; independent label adjudication NOT CONDUCTED.**
This is not an accuracy result, security audit or label certification. Original
`development.json`, `heldout.json` and `manifest.json` remain byte-identical to
`e3ddd73efe6f486352ab2a4e94c7a4f4e95c8037`; new portable digest regressions check that.
Case-level notes/provenance: `evaluation-readiness-evidence/corpus-review-v1.json`.
No replacement labels or exclusions were applied to existing metrics.

## What was actually reviewed

Reviewed all 32 development and 16 heldout authored examples/annotations, actual
scoring/provider/freeze code, prior evidence and documentation. Reading heldout for
this requested design review is **not an inference/scoring run**; no model/gate
was run on it, no prompts/rules/settings were tuned against it and its consumption
ledger was not changed. It is now explicitly not blind to the engineering reviewer.
Do not claim independent, unseen distribution validation from this set.

| Property | Development | Heldout |
|---|---:|---:|
| Cases / category families | 32 / 16 | 16 / 16 |
| HOLD / REVIEW / CLEAR labels | 28 / 2 / 2 | 14 / 1 / 1 |
| Annotated account case-field pairs | 24 | 12 |
| Annotated remittance-email case-field pairs | 2 | 1 |
| Cases with no requested-field annotations | 8 | 4 |

There are zero exact cross-split email duplicates. However, **all 16 development
pairs contain the same core body**, and heldout reuses all 16 semantic families,
reference setup and destinations with paraphrasing. Distinct text is not an
independent population sample. The two development variants are correlated, not
32 independent trials. Heavy HOLD weighting and only 4 non-HOLD development labels
make false-HOLD estimates particularly weak. The heldout's 2 non-HOLD examples do
not establish useful precision for that rate either.

## Annotation-quality concerns — original labels preserved

- **Forwarded/stale history (AS-dev-05-1/2, AS-hel-05-1):** current instructions say
  unchanged, while old quoted destination and current on-file account are both
  annotated as requested values and `change_requested=true`. That is a plausible
  conservative HOLD policy fixture, but disputed extraction/active-intent gold.
  A model correctly distinguishing current from quoted history can be penalized.
  Independent reviewers must settle the task definition; do not silently relabel,
  remove these cases or tune a prompt to imitate a questionable annotation.
- **Conflicting instructions:** gold asks for both alternatives. Explicit abstention
  can also be sensible. Define option extraction vs abstention before accuracy claims.
- **Malformed identifiers:** fidelity to a malformed literal and deciding it is
  unusable are different tasks. Both must remain separate from financial escalation.
- **Ambiguous/truncated requests:** safe unverifiable/abstaining output can lose literal
  change_request recall despite a correct HOLD. That metric is author-label agreement,
  not a direct measure of unsafe release.
- **Sparse gold:** account and remittance email are the only scored field families.
  No representative scoring for IBAN, IFSC, SWIFT, beneficiary, amount, currency,
  payment terms, bank/branch or contacts. Missing gold is not automatically a true
  negative; extra predicted fields do not establish hallucination/precision rates.
- **No-change:** only one narrow benign template family. False-positive extraction,
  benign forwarding, ordinary signatures and realistic benign financial language are
  underrepresented. More synthetic duplicates would not solve representativeness.

## Coverage and difficult cases

Useful regression families include explicit/one-character changes, multiple changes,
injection, HTML text, Unicode/fullwidth/confusables, malformed identifiers, ambiguity,
conflicts, quoted history, registered alternate and attachment/truncation wording.
But attachment/OCR is not actually executed. Missing/vendor-ambiguity cases use a
caller-selected unresolved sentinel, not identity inference or a misselected valid
vendor. Duplicate/replay wording tests an email classification, not actual service
idempotency/replay; those are separately covered by workspace tests.

Header/authentication variants, diverse valid vendors/countries/destinations,
field-complete annotations, legitimate alternates, difficult benign messages,
realistic thread semantics and independently authored adversarial cases are gaps
in the AI corpus, even when deterministic unit tests cover some of those properties.
No general fraud effectiveness, phishing prevention, population error rate or
production safety claim is supported.

## Claims and scores allowed now

Existing numerator/denominator metrics are retained for reproducible agreement with
immutable author-defined labels, including disputed cases. No filtered "improved"
score is substituted. Evaluator v3 now emits a `corpus_assurance` block with label
review status, decision/field distribution, dispute IDs and claim limitations.
Raw extraction, deterministic gate and authenticated workflow results remain separate.
A source-code fingerprint change invalidates old freezes, as intended.

Allowed: "on these exact synthetic fixtures/configuration the observed outcomes
were ..." with denominators and these qualifications. Not allowed: "Gemini is X%
accurate" without an actual provider run, or a broad accuracy claim even after a
small preliminary heldout run. Zero samples means no provider rate. Token observations
and latency do not establish billed currency cost or real-world financial control.
Freezing confirms configuration/evidence correspondence, **not label endorsement**.

## Prospective expansion specification — no new dataset manufactured

A new independently authored set is needed for stronger claims. No expansion was
fabricated here: adding agent-authored labels would not close independence.
Before populating a separately versioned set:

1. Independent annotation lead defines active requested changes, quoted history,
   unchanged mentions, multiple options, abstention and complete field scope.
2. Two permission-safe/synthetic annotators work blind to outputs; a separate
   adjudicator resolves disagreements and records rationale/review status.
3. Separate extraction gold from conservative gate-policy expectations and trusted
   reference preconditions. Keep optional abstention scoring explicit, not post hoc.
4. Include diverse benign/difficult cases and all intended fields/vendors/currencies;
   size from the claim/error tolerance, not an arbitrary impressive case count.
5. Record authorship, permissions, deduplication/family grouping, source/reference
   versions, annotation agreement, original bytes and fixed scoring rules. Split by
   family/source, not paraphrase. Do not leak final examples into development.
6. Version as a new corpus/manifest; retain v1 labels and results unchanged. If an
   evaluated heldout triggers tuning, preserve its consumed evidence and use a new
   independent final set. A privileged writer can defeat the local ledger; no
   external provenance guarantee is claimed.

## Exact private live sequence

Key absence was checked as a boolean only; missing-key smoke/development exit 2.
No key, provider response, successful smoke/freeze or heldout result was invented.

```bash
python scripts/init_env.py
# Edit the ignored .env privately, or use supported private environment/secrets.
# Never put the key in chat, source, command arguments, screenshots or logs.
python scripts/live_check.py --cases 1
python eval/assurance_eval.py --live --confirm-cost
# Inspect extraction failures and unresolved annotation issues before freezing.
python eval/assurance_eval.py --freeze-config data/runs/frozen.json --development-report data/runs/assurance-evaluation.json --confirm-development-reviewed
python eval/assurance_eval.py --live --confirm-cost --split heldout --freeze-file data/runs/frozen.json --confirm-heldout-final-run
```

Default supported model remains gemini-2.5-flash; HTTP timeout 30,000ms, extraction
budget 90,000ms, at most three outer attempts. Actual model/settings/schema/code/SDK
and measured observations are recorded only by an executed live run. Do not rerun
or reset the heldout marker to tune. Independent label adjudication remains pending;
future v1 diagnostic runs must retain the qualifications above.
