# Stage 1: Observing ChatGPT Search and Grok

[Back to the GEO Learning Log](../README.md) · **[Read the visual report](https://helen-bird.github.io/geo-platform-observation/)** · [Main answer data](../data/runs.json) · [Historical attempts](../data/attempts.json) · [Aggregate results](../findings.json) · [Download public data](../public-data.zip)

This stage uses repeated queries to explore which entities AI answers recommend, which sources they cite, and how answers vary. ChatGPT Search and Grok received the same 3 English questions, with 2 repetitions per question on each platform. Testing took place on **2026-10-29 to 2026-10-30**.

## Main findings

- **The creator question produced the largest difference between platforms' recommendation sets**: after combining each platform's two answers, 2 / 20 distinct recommended entities were shared, an overlap of 10.0%.
- **In this sample, ChatGPT recommendations more often cited content published or authored by the recommended entity**: 47 / 48 (97.9%) for ChatGPT, compared with 39 / 76 (51.3%) for Grok.
- **Neither platform had higher repeat overlap on every question.** Grok's two answers were more similar on the empirical research question; the other two questions showed smaller differences.
- **Citation, Mention, and Recommendation can occur separately.** Content can be cited without the entity being named or recommended, and an entity can be recommended without its own content being cited.

> This is a small exploratory learning exercise. The assistant read and coded each answer; there was no independent human double-coding. Each question had only two repetitions per platform, testing spanned multiple days, reasoning effort varied, and account context appeared in the responses and retrieval evidence. There was no pre-optimization baseline, intervention, or control group. **These observations cannot establish whether a GEO tactic works, assess a brand's GEO performance, or demonstrate an inherent advantage of either platform.** External studies and effectiveness claims in the platform answers were not independently verified in this stage.

## Data, sources, and traceability

| File | Contents |
| --- | --- |
| [index.html](../index.html#stage-1) | Stage 1 report with a sidebar, findings, charts, and individual public answers |
| [data/protocol.json](../data/protocol.json) | The three original English questions, study design, and coding definitions |
| [data/runs.json](../data/runs.json) | 12 complete main answers and 142 entity × answer observations |
| [data/attempts.json](../data/attempts.json) | 10 historical submissions excluded from the main statistics, with failure and recovery status preserved |
| [data/capture-history.json](../data/capture-history.json) | 37 captures and diagnostic corrections; capture count is not query count |
| [data/records/](../data/records/) | Separate redacted records of 22 actual submissions, corresponding to the main and historical records |
| [data/captures/](../data/captures/) | A public summary of each capture |
| [findings.json](../findings.json) | Aggregates and C/M/R distributions calculated from the public observation data |
| [scripts/](../scripts/) | Code for calculations, page generation, and public-file checks |

> **C — Citation:** content published or authored by the entity is cited. **M — Mention:** the answer explicitly names the entity. **R — Recommendation:** the answer actively suggests using, reading, or following the entity. These are assessed separately and do not form a strict funnel. The statistics cover only the coded entities that were primarily recommended or substantively discussed, not every source publisher. Grok's “C only = 0” does not establish that it never cites content without naming its source entity.

Each observation retains an `evidence` excerpt, C/M/R judgments, and `source_urls`. Every source includes its URL and domain. The HTML links to public records using repository-relative paths, while external research links retain their article or paper identifiers. GitHub's file history tracks later corrections; use **Copy permalink** on a file page when citing a fixed version.

## Publication scope

**The published “raw answers” are redacted copies for review; unmodified private capture files are retained locally.** The original English questions, studied entities, citation attribution, and statistics remain unchanged. Personal context unrelated to the experiment has been omitted, with editorial markers retained. Tracking parameters have been removed from public URLs.

Documentation and annotations are in English. Verbatim platform answers and captured UI strings retain their original wording; non-English UI tokens are stored and displayed with Unicode escapes. Where available, `title_en` provides an English display translation alongside the original source-panel title.

Private conversation and share links, local file paths, account details, original screenshots, full captured HTML, and internal diagnostic archives are excluded from this repository. The complete original archives remain local. The public version retains 12 main answers, 22 actual submissions, 10 historical attempts, and 37 capture summaries. [Full publication notes](../data/publication-notes.json)

## Reproduce and read locally

Run these commands from the repository root. Only the Python 3 standard library is required; no account or API access is needed:

```sh
python3 scripts/rebuild.py
python3 scripts/check_publication.py
python3 -m http.server 8000
```

Open the [local report](http://localhost:8000/) to read the full results. The GitHub repository provides these stage notes, JSON data, and code; GitHub Pages serves the same [index.html](../index.html) with its layout and charts.
