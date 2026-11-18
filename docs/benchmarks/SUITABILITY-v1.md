# External benchmark suitability v1 — 2026-10-25

**Decision: no candidate supplies verified gold for ThreadGate field extraction or
safe-change decisions. No external performance score, adapter or raw dataset added.**
Independent authorship of a synthetic source is not independent human adjudication
and does not make its labels applicable to another task.

## Sources inspected, without archive downloads

1. [r-dube/bec](https://github.com/r-dube/bec), pinned to
   [b6cc4f0439694ce175fa688b7faf361eba30d359](https://github.com/r-dube/bec/tree/b6cc4f0439694ce175fa688b7faf361eba30d359).
   Inspected recursive GitHub tree metadata first, then bounded in-memory CSV,
   generator/validator notebook and license reads. No raw messages saved or redistributed.
2. Dube, *Building a business email compromise research dataset with large language
   models*, [DOI 10.1007/s11416-024-00544-y](https://doi.org/10.1007/s11416-024-00544-y),
   published January 2, 2025. Publisher abstract/data-availability/notes accessible;
   full article subscription-gated, not purchased. Data availability points to (1),
   so these are **one dataset source, not two independent benchmarks**.
3. Nagarajan and Ramachandran, *An AI-Agent Framework for Accounting in Law Firms:
   Process Automation, Trust-Account Controls and Integrated Cybersecurity*,
   [ABH 2026, pp.98–114, DOI 10.5220/0015184700005051](https://www.scitepress.org/publishedPapers/2026/151847/pdf/index.html).
   Inspected accessible rendered paper, especially sections 5.1–5.4, 8, 9 and references.
   No PDF/image/benchmark archive downloaded. Paper license printed on p.98:
   **CC BY-NC-ND 4.0**; this does not establish a dataset/code redistribution license.

## Artifact-level findings (measured, not inferred from paper accuracy)

Pinned raw URLs use `https://raw.githubusercontent.com/r-dube/bec/` + commit + path.

| File | Exact bytes / rows | SHA256 |
|---|---|---|
| data/BEC-1-human.csv | 7,192 / 20 | f78630d795fbfb3967a4e6c88057184078b207b762ab8fa6646f8a63cabe61e3 |
| data/BEC-2-human.csv | 99,159 / 279 | ae818988b4fce7d25a8d02ac46825e4ca80f39b1b0d770017e82f4fd3463064c |
| data/bec_examples_split.csv | 1,912 / 6 | 93a2cfe2ebbbbedb458e278385b4a7b690343e1d4e35259c91666e24f0f73e41 |

CSV columns for BEC-1/2: `subject,body,Model,Q1,Q2,Q3,Q4,Human`.
BEC-1 Human: 20 positive; Model: 18 positive/2 neutral. BEC-2 Human: 276
positive/3 neutral; Model: 262 positive/17 neutral. Neither has a Human-negative
class. Six seed examples have label counts positive=4/neutral=1/negative=1.
Not a representative benign-versus-attack sample. Validator rubric is business,
authority, organisational action, urgency: sum 4→positive, 2/3→neutral, 0/1→negative.
These are **not** safe/unsafe payment or requested-destination truth labels.

All **20/20 BEC-1 subject/body pairs occur in BEC-2**; within-file exact subject/body
duplicates=0 in both. Do not concatenate them or use one as independent final test
of the other. Few-shot seed/generator family correlation remains beyond exact dedup.
Generator notebook configures DSPy/OpenAI gpt-3.5-turbo; article describes LLM-generated
20-email proof-of-concept and 279-email set, not observed fraud incidents. Human
credibility/rubric review does not supply ThreadGate field annotations. Seed examples
are derived from published examples per publisher notes; public visibility does not
establish permission for every upstream message. Enron folders are separate observed
email/authorship material, not extraction gold; not downloaded or treated as benign
control without explicit provenance/privacy/license assessment.

Repository LICENSE: GNU AGPL v3, 34,523 bytes, SHA256
`8486a10c4393cee1c25392769ddd3b2d6c242d6ec7928e1414efff7dfb2f07ef`.
Treat repository coverage/upstream-message rights and any incorporation obligations
as needing review; do not assume raw content can be relicensed as ThreadGate code.
No copied code/data under that license is added here.

The smallest inspected external sample illustrates wire-processing intent but does
not necessarily contain a new destination, prior destination, vendor master or
reference version. Subject/body alone cannot decide authorised identity or payment
safety. No field span labels, requested-versus-historical links, vendor IDs, complete
header-auth gold or trusted-reference snapshots exist in those CSV schemas.

## 2026 paper: related mechanism, not a ready extraction benchmark

Section 5.4 describes **300 seeded synthetic structured payee-change requests,
150 legitimate/150 BEC**, sampled from assumed feature distributions. Section 5.3
aggregates auth/display-name/country/time/semantic signals into LOW/MEDIUM/HIGH.
Its reported F1=.99/latency=.51ms are **authors' prototype figures**, not ThreadGate
results or actual LLM extraction latency. The paper itself warns this is mechanism
validation, not a live-firm measured detection rate. Section 5.2's illustrative
12,000-template corpus is distinct from the 300-case experiment; no inspected
artifact establishes access, labels, size or license for that claimed corpus.

The text says a service was released alongside the paper, but no retrievable
case-file/generator/repository URL was identified in the inspected sections or
references. Therefore exact data bytes/hash, seed, per-case labels, duplication,
field spans and reproducibility are **unverified**, not assumed absent everywhere.
The abridged scoring listing is not enough to reconstruct the original benchmark.
Contact authors for versioned generator/data, full schema and explicit rights before
using; do not manufacture a replacement and call it independent reproduction.

## Suitability / disposition

| Candidate | Classification/context | Field-level extraction | Gate/workflow | Decision |
|---|---|---|---|---|
| BEC-1 (smallest accessible, 7 KB) | External synthetic qualitative examples; almost no class diversity | No gold, quoted/active semantics or trusted identity | No reference/authority labels | Reject for scoring; retain metadata only |
| BEC-2 (99 KB) | Larger same-source rubric-labelled synthetic text; contains BEC-1 | Same gold gaps | Same reference gaps | Reject for scoring; no need to retain 279 messages |
| Springer DOI | Explains generation/credibility; same source as repository | No additional accessible extraction labels | Not control evaluation | Use as methodological citation, not extra sample count |
| ABH 2026 paper | Relevant payee-change mechanism; synthetic structured evaluation | No accessible verified field-level gold | Different score/bands, assumes structured inputs | Use as related work; data/code/license access unresolved |

**Smallest suitable current contribution is this metadata-only assessment.** None
justifies an adapter that maps positive→HOLD or missing field gold→negative.
No source was selected/filtered based on model success. External extraction sample
size=0; external gate sample size=0; no new independent accuracy evidence claimed.

## Reproduction and reconsideration

Retrieve only the three pinned CSVs above into memory, cap reads at 8 KB/100 KB/
2.5 KB, verify SHA256 before CSV parsing, count `Human`/`Model`, compare sets of
(subject,body). Pin notebook/license metadata too before reuse. Do not fetch an entire
repository or Enron archive. Measurements are source characterization, not model tests.

Reconsider only after permissible provenance, independently adjudicated spans/
active-request roles, complete field scope and separately governed reference context
are available. Freeze preprocessing/label mapping/scoring before provider runs;
separate classifications, extraction agreement and deterministic conservative policy.
Continue preserving existing synthetic v1 labels/results and denominators.
