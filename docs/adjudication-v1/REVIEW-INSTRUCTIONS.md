# Active-request semantic review v1 — awaiting independent humans

Send reviewers **only this file, review-input.json and RESPONSE-TEMPLATE.json**.
Do NOT send COORDINATOR-ONLY.json, original annotations, model predictions, old
reports or repository links before initial labels are locked. The repository is
public/reviewer access cannot be technically prevented: record any prior exposure.
This is agent-prepared material, not adjudication, consensus or a new benchmark.
Two related synthetic cases are not two independent sources.

## Task / definitions (proposed protocol, not retroactive gold)

Annotate what the current author requests from the recipient, not whether the
sender is trustworthy. Do not label fraud, CLEAR/HOLD/REVIEW or payment authority.
Read the whole message; distinguish:

- ACTIVE: current instruction the author adopts now, including an explicitly
  re-adopted quoted instruction. Mere inclusion of a quotation is not adoption.
- HISTORICAL_QUOTED: past/forwarded/archive material not currently re-adopted.
- HYPOTHETICAL: example, conditional scenario not asserted to apply now.
- CANCELLED: explicitly withdrawn/superseded request; retain its mention but do not
  treat its destination as the currently requested replacement.
- AMBIGUOUS: incompatible live options/unclear scope, chronology or adoption.
  Preserve alternatives and uncertainty; do not choose an arbitrary final account.
- IRRELEVANT: unrelated signature/footer/other person's non-applicable details.
- UNCHANGED: current affirmation of existing details, not a replacement request.

Assign mention roles separately from overall current intent: CHANGE_REQUEST,
NO_CHANGE, AMBIGUOUS or INSUFFICIENT_CONTEXT. A mention of an account or the verb
"pay" does not alone establish a current change request. Absence of a visible change
is not proof no change occurred in unavailable context. Explain conditional cases.

## Field-level annotation rules

For each relevant mention, record field type, exact sanitized value, role, verbatim
evidence quote, and zero-based start/end body-character offsets (end exclusive;
`body[start:end] == quote`). If evidence is only in a header, specify header key
instead of inventing body offsets. Record all relevant competing mentions separately.
Do not normalise a malformed literal into a different account. Account aliases
ACCOUNT-A/B consistently replace two synthetic numeric accounts: they preserve
semantic identity, not lengths/checksums or character-difference difficulty.

Fields: vendor/company identity; beneficiary; account number; IBAN; IFSC; SWIFT;
bank/branch; remittance email; contact phone; amount; currency; payment terms; other
(specify). Distinguish an organisation named in text from an authenticated vendor.
Vendor identity is UNKNOWN if text does not establish it; never infer a known vendor
ID from a caller's choice, sender domain, an account or a current model prediction.
For destinations, distinguish new requested, current/on-file *as claimed by sender*,
old/historical, alternative and unresolvable roles. Text claiming on-file status does
not authenticate the trusted master. Missing gold/field is not a negative label.
Mark field coverage NOT_PRESENT, PRESENT or UNCERTAIN; UNKNOWN when unavailable
context is needed. Do not hallucinate amounts/currencies/contact details.

For each proposed change, record target field, old value if explicit, proposed new
value(s), effective condition/date if explicit, adopted/current status and supporting
quotes. NO_CHANGE may still include unchanged/current destination mentions. Quoted
old destinations are not automatically new requests. If current unchanged language
conflicts with old text, explain the chronology and competing interpretations rather
than labelling a safe payment. Separate extraction judgment from any future
conservative escalation policy; a policy HOLD cannot repair extraction gold.

## Independent process / conflict resolution

1. Coordinator confirms permission, no sensitive data, protocol v1 and packet hash;
   recruit two independent human reviewers, document relevant expertise/conflicts
   and prior exposure using pseudonymous codes. Do not invent identities/approvals.
2. Reviewers separately fill one response file each, without seeing each other,
   previous gold or predictions. Leave uncertainty explicit. Lock timestamp/hash
   and retain original responses before discussing disagreements.
3. Compare current intent, per-mention field/value/role and evidence separately.
   With only 3 related cases report counts/disagreement details, not a population
   reliability score. No agreement statistic exists until both real responses exist.
4. A third qualified independent adjudicator reviews disagreements and written
   rationales; document adopted rule, alternatives, unresolved uncertainty and
   exposure. No majority vote automatically converts ambiguity into truth.
5. If definitions change, version the protocol and seek fresh independent labels
   consistently across affected cases. Keep original responses/disagreements.
6. Publish any adjudicated labels under a NEW corpus/manifest/version with provenance,
   rights, full-scope annotation/coverage, scoring and denominator policy fixed
   before inference. Never overwrite v1 gold or retrospectively filter hard cases.
   Preserve old results; do not tune on a consumed heldout or call revised scores
   original independent final performance. This packet is not an unseen final set.

Currently: reviewers 0, responses 0, independent adjudications 0, agreement **not
measured**. Human recruitment, labels, rationale and conflict resolution remain due.
