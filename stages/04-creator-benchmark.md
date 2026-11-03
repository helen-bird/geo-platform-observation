# Stage 4: Which creators get recommended?

**Helen Bird** · Experiment: **November 3, 2026** · First public edition and last revision: **November 3, 2026**

[Learning Hub](https://helen-bird.github.io/geo-platform-observation/learning-hub/) · [Concise report](https://helen-bird.github.io/geo-platform-observation/stages/04-creator-benchmark/) · [Complete technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/04-creator-benchmark/technical-appendix.html) · [Public data](04-creator-benchmark/public-data.zip)

This stage separates **historical selection**, **new-answer validation** and **source auditing**. Stage 1 observations selected Aleyda Solis, Kevin Indig and Artur Ferreira / The GEO Lab. The new sample repeats Stage 1's three exact questions three times in two collection environments, producing **18 complete selected answers**. Eight own/bylined pages actually linked in these answers were then audited.

> **OpenAI Responses API + native web search is not consumer ChatGPT Search.** The API arm used requested/returned `gpt-5.6-sol` and `medium`; Grok used Expert consumer sessions with an undisclosed backend model. All 18 answers have observed search evidence. Three of nine API answers reached the fixed eight-tool-call cap, so retrieval configuration and budgets qualify every cross-environment comparison.

## Main observations

- **User intent mattered.** In Q1, Grok recommended Aleyda's resources and The GEO Lab in 3/3 answers each; the API recommended Aleyda in 1/3. In Q3, Kevin was recommended in 3/3 API answers; Artur / The GEO Lab in 2/3 Grok answers. None of the three candidate families received C, M or R in any Q2 answer.
- **Content-brand visibility and personal-name visibility differed.** Grok recommended Artur or his verified associated assets in 5/9 pooled answers but explicitly named Artur in 2/9. The API recommended The GEO Lab once without his name. These pooled counts combine different questions and are not general recommendation probabilities.
- **Recommendation did not guarantee an own-content hyperlink.** Among 54 candidate-by-answer observations, 14 had M and R, while 10 had strict linked own/bylined C. Two other recommendations used third-party coverage; two displayed a plain-text address. Those addresses are preserved and assessed separately.
- **Source quality still required inspection.** The cited Field Manual has a correction note but retains a method/results denominator conflict and significance wording alongside `p=.07`. The audit preserves both the note and unresolved inconsistency, without treating an AI endorsement as verification.

> **C** means an observable answer-body hyperlink to verified own/bylined content. **M** and **R** can include a verified associated asset, but personal-name mention and personal recommendation are separately recorded. Third-party coverage, retrieval-only sources and plain-text addresses remain distinct. Coding is assistant observational judgment, not independent human double coding.

## Practices suggested by the audit

Aleyda's curated learning routes, Kevin's methods-led research and searchable transcripts, and Artur's interconnected guides and experiment templates suggest feasible content practices. Clear author identity, a user-question index, transparent methods and reusable worksheets are candidates for later testing. The Learning Hub is the first content-organization application; no resulting visibility effect has been measured.

Existing reputations, audiences, data partnerships and professional experience are background advantages. There is no matched un-recommended creator group, content intervention, long-term stability measurement or conversion study here. The title describes observed recommendations, not a direct test of indexing or general searchability.

## Evidence and reproduction

| Material | Contents |
| --- | --- |
| [Reader](04-creator-benchmark/index.html) | Findings, per-question n=3 comparisons, person-versus-asset views, source audit and untested hypotheses |
| [Technical appendix](04-creator-benchmark/technical-appendix.html) | All 18 original selected answers, body URLs/domains, search activity, coding and preserved local recovery history |
| [Selected answers](04-creator-benchmark/data/runs.json) | Eighteen formal positions and their selected attempt records |
| [All submissions](04-creator-benchmark/data/attempts.json) | Eighteen actual submissions; recovery of an existing capture does not add a submission |
| [Coding](04-creator-benchmark/data/coding.json) | Fifty-four candidate-by-answer judgments with evidence and source roles |
| [Protocol](04-creator-benchmark/data/protocol.json) | Exact prompts, selection rules, actual conditions and limits |
| [Source audit](04-creator-benchmark/data/audit/source-audit.json) | Eight actual cited own/bylined pages; attributed context and distribution checks kept separate |
| [Review response](04-creator-benchmark/data/review-response.md) | Itemized assessment of the supplied peer-review recommendations |
| [Publication notes](04-creator-benchmark/data/publication-notes.json) | Public-copy transformations and privacy exclusions |
| [Downloadable public data](04-creator-benchmark/public-data.zip) | Public records and reproducible findings |
| [Public builder](../scripts/build_stage4_report.py) | Offline public report generation; no model requests or credentials |

```sh
python3 scripts/build_stage4_report.py
python3 scripts/check_stage4_publication.py
python3 scripts/build_learning_hub.py
python3 scripts/check_publication.py
```

The reports, dataset and checks work from the public repository without private captures or paid model access. Use GitHub's Copy permalink to cite a fixed revision and include the relevant `S4-*` observation or attempt ID.

## Publication boundary

This public edition preserves prompts, answer meaning, experimental metadata, judgments and methodological qualifications. Private account evidence, conversations/share links, provider identifiers, local paths, credentials and setup details, native screenshots/DOM and reasoning-trace items are excluded. Tracking/session/signature parameters are removed from actual URLs, with necessary semantic parameters retained. Complete private originals remain unchanged locally.

[Report versions](../report-versions.json) · [Revision history](../CHANGELOG.md) · [Stage 4 publication and review decisions](../reviews/2026-11-03-stage04.md)
