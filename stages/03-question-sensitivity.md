# Stage 3: Sensitivity to question design

[Back to the GEO Learning Log](../README.md) · **[Read the visual report](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/)** · [Selected answers](03-question-sensitivity/data/runs.json) · [All submissions](03-question-sensitivity/data/attempts.json) · [Download public data](03-question-sensitivity/public-data.zip)

This stage explores whether the same learning task produces different advice, cited domains and tool recommendations when repeated or reworded. The fixed scenario is a solo SaaS founder with no GEO budget. Collection took place on **November 2, 2026**: two intents, two wordings per intent, two collection interfaces and three repetitions produced **24 complete selected answers**. All **27 actual prompt submissions** remain represented, including three historical ChatGPT consumer-UI failures or partial captures.

> **The OpenAI API results cannot represent ChatGPT web/app performance.** The completed OpenAI arm used **OpenAI API + web search**, through the **Responses API**, after consumer-UI collection failed. It did not test the consumer ChatGPT Search interface. All API answers were collected after Grok, so interface, retrieval configuration and time are confounded. These observations cannot isolate a platform effect or establish GEO optimization effectiveness.

## Main findings

- **Repeating an identical question did not freeze the detailed advice.** Grok's mean pairwise overlap of recommended tool/service/feature/channel sets ranged from **27.5% to 60.0%** across the four prompts. OpenAI API M1 used a 0–3 scoring rubric in repetitions 1–2 and a different −1/0–4 rubric in repetition 3. Such generated rubrics are advice, not validated scoring standards.
- **Wording variants changed recommendations even when some source pools stayed similar.** Pooling three repetitions per variant, Grok M1/M2 shared **7 of 27** recommended entities (**25.9%**) and V1/V2 shared **4 of 14** (**28.6%**). OpenAI API M1/M2 shared **0 of 7** recommended entities while sharing all **3 normalized cited domains**. Its V variants recommended no new named tools: that empty-versus-empty overlap is **N/A**, not 0% or 100%.
- **Intent consistently aligned with the primary answer type in this sample.** Within each interface, all **6 M answers** primarily supplied measurement workflows and all **6 V answers** supplied score-audit checklists. Grok's M and V recommendation pools shared **11 of 30** entities (**36.7%**); OpenAI API had 7 M entities and no new V tool recommendations. This compares different tasks, not a pure wording effect.
- **The collected interfaces selected different source mixes.** All **12 OpenAI API answers** cited platform documentation; one also cited academic/methods research. Grok had editorial/industry sources in **7/12** answers, product pages in **4/12**, vendor research in **1/12**, and unresolved source types in **10/12**. Categories overlap and classifications remain provisional; these are not causal platform preferences.
- **Citation, Mention and Recommendation remained different observations.** In the coded new-entity rows, OpenAI API had **10 citation-plus-mention rows without recommendation**. Its supporting documentation citations did not automatically recommend those providers or tools.

> The wording contrasts also change contextual cues such as “no GEO budget” versus “bootstrapped,” and the request's emphasis. Differences describe sensitivity to the complete prompt variants. Sparse tool lists, model/source variation and only three repetitions limit stronger conclusions. External studies, tool capabilities, prices, numerical claims and generated scoring thresholds were collected as platform output, not independently fact-checked.

## Three comparisons, three questions

| Comparison | Research question | Interpretation boundary |
| --- | --- | --- |
| Three repeats of exactly the same prompt | How much did an interface's observed answer, sources and recommendations vary? | Three pairwise overlaps reuse three answers; they are not independent trials or stable population estimates. |
| M1 versus M2; V1 versus V2 | How sensitive were results to different expressions of a similar intent? | Compare wording differences with the repeat variation; contextual and action cues also differ. |
| M group versus V group | Did “how to measure” and “how to validate a score” select different source categories and tool lists? | The task changes, so differences cannot be attributed wholly to phrasing. |

The original four prompts are preserved in [the protocol](03-question-sensitivity/data/protocol.json). They were submitted without added product identities, earlier answers, examples, output-format directions or steering follow-ups. Each formal API request was stateless; Grok used a fresh private conversation for each submission.

> Recommendation-set overlap uses intersection divided by union. Identical-prompt cells contain three pairwise comparisons. Pooled wording/intent views combine the relevant recommendation sets and are labeled separately. Both sets empty gives **N/A**. Cited domains use documented normalized-domain mappings; exact URLs remain available separately. Source-category prevalence counts answers containing a category, so categories need not sum to 100%.

## Actual conditions and failure history

| Arm | Completed formal answers | Model and effort evidence | Search evidence |
| --- | --- | --- | --- |
| OpenAI API + web search | 12 | Requested and returned model string `gpt-5.6-sol`; requested and returned reasoning effort `medium` | Native web search required in requests; returned search calls, actions and citation annotations retained |
| Grok consumer interface | 12 | Expert mode; exact backend model version undisclosed; reasoning effort not independently selectable | Native retrieval activity observed; no separate force-search switch was available |

> **A fixed undated model string is not a pinned backend snapshot.** Matching requested/returned `gpt-5.6-sol` and `medium` records API metadata, not proof of an unchanged underlying model throughout collection. Grok's unchanged Expert label likewise does not identify or audit its backend version.

Grok's visible X-based and conversation-history personalization controls were disabled during testing and restored after collection. API requests contained the registered prompt without prior response IDs or conversation history. These controls reduce known context paths; they do not audit provider internals. Same-platform submissions were spaced by at least 90 seconds. All completed API submissions occurred later than the Grok batch.

Three historical ChatGPT consumer-UI submissions are excluded from the 24 formal answers: one technical failure and two incomplete body captures. The last recovered a substantial prefix but ended mid-sentence in both visible text and copied text. No missing remainder was treated as evidence of an absent tool, source or recommendation. It was not relabeled as an API answer. Recovery and copy attempts do not add prompt submissions.

## C/M/R scope

The following counts are **entity × answer rows**, not numbers of products or probabilities of recommendation:

| Recorded combination | OpenAI API + web search | Grok |
| --- | ---: | ---: |
| Citation + Mention + Recommendation | 0 | 7 |
| Citation + Mention, no Recommendation | 10 | 0 |
| Mention + Recommendation, no own-content Citation | 7 | 76 |
| Mention only | 13 | 43 |
| Total coded new-entity rows | 30 | 126 |

> **C:** content published or authored by the entity is cited. **M:** its name appears substantively. **R:** the answer actively suggests using, reading or following it for the task. C/M/R are assessed separately. The table covers coded tools, services, features and channels; it excludes supplied ChatGPT/Grok targets, generic methods and citation-only publishers. A missing own-content citation does not mean no supporting source. Tool roles and unresolved product aliases remain recorded, so an analytics product, a source channel and an API feature should not be treated as identical kinds of recommendation.

The assistant reviewed and coded the answers; there was no independent human double-coding. Source classifications rely on the available titles, URLs and answer roles and remain provisional where the underlying page was not examined. Retrieval sources and hit badges are not automatically answer citations. API citation annotations and their matching Markdown URLs are two representations of the same citations, not additional independent sources.

## Data, sources and traceability

| File | Contents |
| --- | --- |
| [index.html](03-question-sensitivity/index.html) | Findings, comparisons, full public answer copies, conditions and attempt history |
| [findings.json](03-question-sensitivity/findings.json) | Aggregates recalculated from the public records |
| [data/protocol.json](03-question-sensitivity/data/protocol.json) | Exact prompts, design, conditions, amendments and limits |
| [data/runs.json](03-question-sensitivity/data/runs.json) | The 24 selected formal positions and their actual selected attempt IDs |
| [data/attempts.json](03-question-sensitivity/data/attempts.json) | All 27 actual prompt submissions, including historical UI failures |
| [data/records/](03-question-sensitivity/data/records/) | Individual redacted answer/attempt records |
| [data/coding/](03-question-sensitivity/data/coding/) | Entity evidence, C/M/R judgments, answer types and provisional source categories |
| [data/requests/](03-question-sensitivity/data/requests/) · [data/responses/](03-question-sensitivity/data/responses/) | Redacted API request/response copies, excluding headers, private provider identifiers and reasoning traces |
| [data/analysis-plan.md](03-question-sensitivity/data/analysis-plan.md) | Analysis definitions and historical amendments |
| [data/setup-history.json](03-question-sensitivity/data/setup-history.json) · [data/settings-summary.json](03-question-sensitivity/data/settings-summary.json) | Public setup/control summaries; no credential setup details or original account preference values |
| [data/publication-notes.json](03-question-sensitivity/data/publication-notes.json) | Explicit public-edition scope and exclusions |
| [public-data.zip](03-question-sensitivity/public-data.zip) | Downloadable public dataset |
| [scripts/build_stage3_report.py](../scripts/build_stage3_report.py) | Offline aggregation and report generation |

Use GitHub's **Copy permalink** to cite a fixed file revision. When citing an answer, include its original position ID and selected actual attempt ID. The `S3-CHATGPT-*` position IDs preserve the registered design; their completed formal answers have `S3-OPENAIAPI-*` attempt IDs and explicit API interface metadata. The old identifier is not evidence of consumer ChatGPT Search collection.

## Publication scope

**This November 2, 2026 edition contains redacted public copies. Complete private originals remain local.** The questions, answer meaning, source attribution, C/M/R judgments, counts and condition changes are preserved, apart from documented privacy edits and tracking removal.

Private conversation/share URLs, personal account details, email controls, provider request/response identifiers, local paths, original screenshots, captured UI/DOM archives, credentials, credential-setup details and reasoning traces are excluded. Public source URLs retain article identifiers while tracking parameters are removed. Publication does not turn platform claims into independently verified findings.

> This exploratory experiment measures sensitivity of observed outputs to question design under recorded conditions. It cannot prove that a GEO tactic works, grade a product's GEO performance, estimate visibility among real buyers, validate a vendor's score, or establish that either interface is inherently better. The API arm cannot stand in for ChatGPT web/app performance; the two interfaces were also collected in different time blocks.

## Reproduce and read locally

Run from the repository root with the Python 3 standard library:

```sh
python3 scripts/build_stage3_report.py
python3 scripts/check_stage3_publication.py
python3 -m http.server 8000
```

Open the [local Stage 3 report](http://localhost:8000/stages/03-question-sensitivity/). These commands rebuild and check the public report offline. They do not call either platform, require an API key or incur new API charges. Repeating the original collection is a separate activity with its own interface, budget and condition requirements.
