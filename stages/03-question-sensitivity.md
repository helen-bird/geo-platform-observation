# Stage 3: Sensitivity to question design

[Back to the GEO Learning Log](../README.md) · **[Read the concise report](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/)** · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/technical-appendix.html) · [Selected answers](03-question-sensitivity/data/runs.json) · [All submissions](03-question-sensitivity/data/attempts.json) · [Download public data](03-question-sensitivity/public-data.zip)

This stage explores whether the same learning task produces different advice, cited domains and tool recommendations when repeated or reworded. The fixed scenario is a solo SaaS founder with no GEO budget. Collection took place on **November 2, 2026**: two intents, two wordings per intent, two collection interfaces and three repetitions produced **24 complete selected answers**. All **27 actual prompt submissions** remain represented, including three historical ChatGPT consumer-UI failures or partial captures.

> **The OpenAI API results cannot represent ChatGPT web/app performance.** The completed OpenAI arm used **OpenAI API + web search**, through the **Responses API**, after consumer-UI collection failed. It did not test the consumer ChatGPT Search interface. All API answers were collected after Grok, so interface, retrieval configuration and time are confounded. These observations cannot isolate a platform effect or establish GEO optimization effectiveness.

## Main findings after peer review

- **Repeated questions still produced different details.** Original strict recommendation sets varied across repeats. OpenAI API M1 proposed 0–3 rubrics in the first two answers and a −1/0–4 rubric in the third. These are generated suggestions, not validated measurement standards.
- **Matched answer-pair comparisons describe lower cross-wording overlap in the Grok sample.** Using the same Jaccard definition, M averaged **35.5% within wording versus 26.0% across wording**; V averaged **45.5% versus 27.0%**. Each comparison uses six within pairs and nine cross pairs drawn from six answers. The unrounded differences are −9.4359 and −18.5021 percentage points. These are post-hoc, dependent descriptive comparisons, not a causal wording effect.
- **Entity definitions change the headline overlap.** API M1/M2 pooled overlap is **0/7 under strict names** and **1/6 at the declared family level** when Google Analytics and explicitly named GA4 are grouped. Strict labels remain unchanged. Broad-category grouping can increase overlap mechanically; it is not stronger evidence of stability.

> The original pooled-union summaries (Grok M 7/27 and V 4/14) remain separately named appendix results. They are not directly comparable to a mean of repeat-pair Jaccards. API M has only five numeric within pairs and seven numeric cross pairs; API V has no numeric pairs because both recommendation sets are empty. N/A is not zero or perfect stability.

**Source granularity matters too:** API M1/M2 share all three normalized cited domains, but only **4 of 9 comparison URLs**. URL comparison removes declared tracking/session/signature parameters, retains encoded paths/fragments, and does not infer that two URLs identify the same article.

The expected alignment of M answers with workflows and V answers with checklists remains supplementary context. Source composition is also secondary because interfaces, time blocks and citation-map coverage differ. Three early Grok records do not meet the strict source-mapping condition.

[Itemized response to every review recommendation](03-question-sensitivity/data/review-response.md) · [Prompt Bank implications](03-question-sensitivity/data/prompt-bank.md)

## Three comparisons, three questions

| Comparison | Research question | Interpretation boundary |
| --- | --- | --- |
| Three repeats of exactly the same prompt | How much did an interface's observed answer, sources and recommendations vary? | Three pairwise overlaps reuse three answers; they are not independent trials or stable population estimates. |
| M1 versus M2; V1 versus V2 | How sensitive were results to different expressions of a similar intent? | Use the same answer-pair metric for within and cross groups; contextual and action cues also differ. The pairs reuse answers. |
| M group versus V group | Did “how to measure” and “how to validate a score” select different source categories and tool lists? | The task changes, so differences cannot be attributed wholly to phrasing. |

The original four prompts are preserved in [the protocol](03-question-sensitivity/data/protocol.json). They were submitted without added product identities, earlier answers, examples, output-format directions or steering follow-ups. Each formal API request was stateless; Grok used a fresh private conversation for each submission.

> Recommendation-set overlap uses intersection divided by union. Identical-prompt cells contain three pairwise comparisons. Pooled wording/intent views combine the relevant recommendation sets and are labeled separately. Both sets empty gives **N/A**. Cited domains use documented normalized-domain mappings; a separate URL lens uses the declared privacy/tracking-cleaned strings without article-identity inference. Source-category prevalence counts answers containing a category, so categories need not sum to 100%.

## Actual conditions and failure history

| Arm | Completed formal answers | Model and effort evidence | Search evidence |
| --- | --- | --- | --- |
| OpenAI API + web search | 12 | Requested and returned model string `gpt-5.6-sol`; requested and returned reasoning effort `medium` | Native web search required in requests; returned search calls, actions and citation annotations retained |
| Grok consumer interface | 12 | Expert mode; exact backend model version undisclosed; reasoning effort not independently selectable | Native retrieval activity observed; no separate force-search switch was available |

> **A fixed undated model string is not a pinned backend snapshot.** Matching requested/returned `gpt-5.6-sol` and `medium` records API metadata, not proof of an unchanged underlying model throughout collection. Grok's unchanged Expert label likewise does not identify or audit its backend version.

Grok's visible X-based and conversation-history personalization controls were disabled during testing and restored after collection. API requests contained the registered prompt without prior response IDs or conversation history. These controls reduce known context paths; they do not audit provider internals. Same-platform submissions were spaced by at least 90 seconds. All completed API submissions occurred later than the Grok batch.

Three historical ChatGPT consumer-UI submissions are excluded from the 24 formal answers: one technical failure and two incomplete body captures. The last recovered a substantial prefix but ended mid-sentence in both visible text and copied text. No missing remainder was treated as evidence of an absent tool, source or recommendation. It was not relabeled as an API answer. Recovery and copy attempts do not add prompt submissions.

## Supplementary C/M/R among coded named entities

The following counts are **coded named-entity × answer rows**, not numbers of products, general brand-mention rates or probabilities of recommendation. All rows already have M=true because the inventory selects substantively named entities:

| Recorded combination | OpenAI API + web search | Grok |
| --- | ---: | ---: |
| Citation + Mention + Recommendation | 0 | 7 |
| Citation + Mention, no Recommendation | 10 | 0 |
| Mention + Recommendation, no own-content Citation | 7 | 76 |
| Mention only | 13 | 43 |
| Total coded new-entity rows | 30 | 126 |

> **C:** content published or authored by the entity is cited. **M:** its name appears substantively. **R:** the answer actively suggests using, reading or following it for the task. C/M/R are assessed separately. The table covers coded tools, services, features and channels; it excludes supplied ChatGPT/Grok targets, generic methods and citation-only publishers. A missing own-content citation does not mean no supporting source. Tool roles and unresolved product aliases remain recorded, so an analytics product, a source channel and an API feature should not be treated as identical kinds of recommendation.

The assistant reviewed and coded the answers; there was no independent human double-coding. Source classifications remain provisional. A separate six-source assistant spot-check is recorded; it does not validate the full corpus or replace human coding review. It found partial sentence support for an arXiv citation and a commercial-origin qualification for an inaccessible Markets URL. Retrieval sources and hit badges are not automatically answer citations. API citation annotations and their matching Markdown URLs are two representations of the same citations, not additional independent sources.

## Data, sources and traceability

| File | Contents |
| --- | --- |
| [index.html](03-question-sensitivity/index.html) | Concise seven-section reader with three bounded findings and two core figures |
| [technical-appendix.html](03-question-sensitivity/technical-appendix.html) | Complete answer copies, coding, failures, source composition, C/M/R and all sensitivity tables; sections remain expanded |
| [findings.json](03-question-sensitivity/findings.json) | Aggregates recalculated from the public records |
| [data/protocol.json](03-question-sensitivity/data/protocol.json) | Exact prompts, design, conditions, amendments and limits |
| [data/runs.json](03-question-sensitivity/data/runs.json) | The 24 selected formal positions and their actual selected attempt IDs |
| [data/attempts.json](03-question-sensitivity/data/attempts.json) | All 27 actual prompt submissions, including historical UI failures |
| [data/records/](03-question-sensitivity/data/records/) | Individual redacted answer/attempt records |
| [data/coding/](03-question-sensitivity/data/coding/) | Entity evidence, C/M/R judgments, answer types and provisional source categories |
| [data/requests/](03-question-sensitivity/data/requests/) · [data/responses/](03-question-sensitivity/data/responses/) | Redacted API request/response copies, excluding headers, private provider identifiers and reasoning traces |
| [data/analysis-plan.md](03-question-sensitivity/data/analysis-plan.md) | Analysis definitions and historical amendments |
| [data/setup-history.json](03-question-sensitivity/data/setup-history.json) · [data/settings-summary.json](03-question-sensitivity/data/settings-summary.json) | Public setup/control summaries; no credential setup details or original account preference values |
| [data/entity-normalization.json](03-question-sensitivity/data/entity-normalization.json) | Explicit strict-name/family/category mapping; no original coding silently merged |
| [data/human-review.json](03-question-sensitivity/data/human-review.json) · [review packet](03-question-sensitivity/data/human-review.md) | Eight targeted decisions pending genuine independent human review; zero completed cases |
| [data/source-audit.json](03-question-sensitivity/data/source-audit.json) | Limited source-access and selected-claim-support audit, separate from original coding |
| [data/review-response.md](03-question-sensitivity/data/review-response.md) · [data/prompt-bank.md](03-question-sensitivity/data/prompt-bank.md) | Full recommendation assessment and practical question-bank implications |
| [data/publication-notes.json](03-question-sensitivity/data/publication-notes.json) | Explicit public-edition scope and exclusions |
| [public-data.zip](03-question-sensitivity/public-data.zip) | Downloadable public dataset |
| [scripts/build_stage3_report.py](../scripts/build_stage3_report.py) · [analysis_extensions.py](../scripts/analysis_extensions.py) | Offline report generation and deterministic post-hoc comparisons |

Use GitHub's **Copy permalink** to cite a fixed file revision. When citing an answer, include its original position ID and selected actual attempt ID. The `S3-CHATGPT-*` position IDs preserve the registered design; their completed formal answers have `S3-OPENAIAPI-*` attempt IDs and explicit API interface metadata. The old identifier is not evidence of consumer ChatGPT Search collection.

## Publication scope

**This November 2, 2026 edition contains redacted public copies. Complete private originals remain local.** The questions, answer meaning, source attribution, C/M/R judgments, counts and condition changes are preserved, apart from documented privacy edits and tracking removal.

Private conversation/share URLs, personal account details, email controls, provider request/response identifiers, local paths, original screenshots, captured UI/DOM archives, credentials, credential-setup details and reasoning traces are excluded. Public source URLs retain article identifiers while tracking parameters are removed. Publication does not turn platform claims into independently verified findings. The original strict labels and data are unchanged; the peer-review calculations are explicitly post-hoc and the eight-case human packet remains uncompleted.

> This exploratory experiment measures sensitivity of observed outputs to question design under recorded conditions. It cannot prove that a GEO tactic works, grade a product's GEO performance, estimate visibility among real buyers, validate a vendor's score, or establish that either interface is inherently better. The API arm cannot stand in for ChatGPT web/app performance; the two interfaces were also collected in different time blocks.

## Reproduce and read locally

The reader/appendix split reduces initial reading load while preserving the earlier default-expanded requirement. Existing published technical fragments forward to their matching appendix anchors. The original public release remains in Git history.

Run from the repository root with the Python 3 standard library:

```sh
python3 scripts/build_stage3_report.py
python3 scripts/check_stage3_publication.py
python3 -m http.server 8000
```

Open the [local Stage 3 report](http://localhost:8000/stages/03-question-sensitivity/). These commands rebuild and check the public report offline. They do not call either platform, require an API key or incur new API charges. Repeating the original collection is a separate activity with its own interface, budget and condition requirements.
