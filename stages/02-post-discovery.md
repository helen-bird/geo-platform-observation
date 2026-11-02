# Stage 2: Accessing and discovering a public experiment post

[Back to the GEO Learning Log](../README.md) · **[Read the visual report](https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/)** · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/technical-appendix.html) · [Selected answers](02-post-discovery/data/runs.json) · [All submissions](02-post-discovery/data/attempts.json) · [Download public data](02-post-discovery/public-data.zip)

This stage tests three routes to the same [public GEO Lab #01 post by HelenBird](https://x.com/bird_helen67403/status/2116080254523445676): a supplied URL, an exact excerpt, and an unbranded research request. ChatGPT Search and Grok each received one question per condition in a fresh conversation. Collection took place on **October 31, 2026**. The six planned cells ultimately required ten submissions to obtain six complete selected answer bodies.

## Main findings

- **Access by a supplied URL did not establish discovery.** Grok extracted body-specific findings when given the link. ChatGPT explicitly said it could not access the post. Neither platform returned the target post in the exact-excerpt or natural-discovery condition.
- **The exact excerpt matched the post character for character.** It was an 86-character continuous passage from the latter part of a sentence, with matching case, spaces, numbers, and punctuation. Grok's recorded activity also included shorter phrases and variants without punctuation. The unsuccessful B answers cannot be attributed to an observed transcription error. Grok retrieval activity was recorded; ChatGPT B's actual search queries were not independently captured.
- **The missing ChatGPT C body was recovered through a qualified manual replacement.** Four earlier technical failures or incomplete captures remain in the submission history. They were not silently replaced, treated as complete, or scored as failures to discover the target.

> These are small, exploratory observations, not platform-wide performance estimates. They do not establish whether the post is indexed, identify the cause of a search failure, rank the author's GEO performance, or demonstrate that a GEO intervention works. The platforms' claims about external experiments, sample sizes, and effectiveness were collected as answers and were **not independently fact-checked**.

## Conditions and observed outcomes

| Condition | Information supplied | ChatGPT Search | Grok |
| --- | --- | --- | --- |
| A — Direct URL | Original X post URL | Did not demonstrate content access; explicitly reported inability to access the body | Met the content-access criterion; summary wording has a separate qualification |
| B — Exact Search | Exact excerpt, without URL or author | Did not find and verify the original post | Did not find and verify the original post |
| C — Natural Search | A research need, without target identity, URL, or excerpt | Returned other experiments; did not discover the target post | Returned other experiments; did not discover the target post |

> Each cell has one selected complete answer. These are observed outcomes, not stable success/failure rates. The later manual ChatGPT C has qualified control evidence.

The supplied excerpt was:

> the two platforms shared only 2 of 20 unique recommended entities — about 10% overlap.

> The prompt called this an “exact sentence,” but it is the latter clause of a longer sentence. The quoted passage itself occurs continuously and unchanged in the captured post. A no-result answer does not prove that the post is absent or unindexed. ChatGPT's statements about HTTP 403 responses are answer claims, not independently captured HTTP measurements.

Grok A correctly extracted the reported two-of-twenty overlap and other body-specific details. Its description of variability added “on the same platforms,” which the original post does not explicitly state. The content-access pass is therefore distinct from a claim that every part of the summary was fully supported.

## Models, search, and collection differences

- **ChatGPT:** the selected interface setting was GPT-5.6 Sol with Medium reasoning and native web search. The original automated attempts used non-personalized temporary conversations. Backend model routing was not independently audited. Actual search activity was observed where recorded; B has the selected search control and answer self-report, without an independently captured activity panel.
- **Grok:** private conversations used Expert mode, with both available personalization switches disabled for testing. The exact backend model version was not disclosed. Native web/X retrieval was observed; the interface did not expose a separate force-search toggle.
- **Manual ChatGPT C replacement:** the user confirmed GPT-5.6 Sol / Medium and an approximate submission time. The original single-question conversation, complete native answer, exact question, eleven returned URLs, and search activity were corroborated. Pre-submission temporary-chat and personalization settings were not independently captured. Native source timestamps are retained separately from the approximate user-reported submission time.

> Six complete answer bodies do not mean that every submission has identical control evidence. Earlier C captures consist of an initial technical failure, two truncated prefixes, and a later search run with no recoverable answer body. Saving an existing generated conversation for recovery was not another submission. Partial text cannot establish whether the missing remainder found the target.

## Data, sources, and traceability

| File | Contents |
| --- | --- |
| [index.html](02-post-discovery/index.html) | Concise reader with findings and six-cell comparison; complete answers and attempts remain in the [technical appendix](02-post-discovery/technical-appendix.html) |
| [data/protocol.json](02-post-discovery/data/protocol.json) | Original prompts, criteria, controls, and methodological qualifications |
| [data/runs.json](02-post-discovery/data/runs.json) | Six selected plan cells, linked to their chosen actual submissions |
| [data/attempts.json](02-post-discovery/data/attempts.json) | All ten actual submissions, including the four earlier unsuccessful C captures |
| [data/records/](02-post-discovery/data/records/) | Individual redacted submission records, including available partial text and recovery summaries |
| [data/target-post.json](02-post-discovery/data/target-post.json) | Public target identity, URL, and captured post content without account-interface material |
| [data/publication-notes.json](02-post-discovery/data/publication-notes.json) | Public-edition scope, omissions, and evidence boundaries |
| [public-data.zip](02-post-discovery/public-data.zip) | Downloadable copy of the Stage 2 public data |
| [scripts/build_stage2_report.py](../scripts/build_stage2_report.py) | Report generation from the versioned public records |

> **Citation, Mention, and Recommendation are separate judgments.** A source URL can support an exclusion rather than a recommendation. Grok's whole-page links captured while a source panel was open are not a verified result set or a list of answer citations; platform hit badges are not unique citation counts. The report preserves these evidence categories separately rather than treating them as comparable source totals.

Use GitHub's **Copy permalink** on a file page to cite a fixed revision. For a platform answer, cite its experiment ID and selected attempt ID alongside the relevant public record. The public data supports review of what the platforms returned; it is not an independently audited database of the external studies they describe.

## Publication scope

**Published answers and capture summaries are redacted public copies. Complete private originals remain local.** This edition preserves the questions, observed outcomes, source attribution, model/search evidence, manual-replacement qualifications, and all ten submission records.

Private conversation and share URLs, private message identifiers, local paths, original screenshots, captured DOM/HTML, native tool dumps, account-interface details, and internal automation identifiers are excluded. Public source URLs have tracking parameters removed. The target post URL, its public author, and the approved HelenBird/helen-bird identity remain because they are necessary to reproduce and interpret this experiment. Earlier local-only collection restrictions remain historical; public release of a redacted edition was authorized on November 1, 2026.

## Reproduce and read locally

Run from the repository root using the Python 3 standard library:

```sh
python3 scripts/build_stage2_report.py
python3 scripts/check_publication.py
python3 -m http.server 8000
```

Open the [local Stage 2 report](http://localhost:8000/stages/02-post-discovery/). Rebuilding does not submit new questions or access either AI account.

## Post-publication checks and revisions

On November 2, the user reported that X native search returned the original post for `from:bird_helen67403 "2 of 20"` and `from:bird_helen67403 "GEO Lab"`, with Latest and All users selected. The actual search date and a screenshot were not supplied. An independent browser attempt on November 2 showed only a loading placeholder, so independent confirmation remains unresolved; it is not a negative search result.

> This user-reported, author-scoped native-search observation is separate from the October 31 experiment and does not alter any A/B/C outcome. It does not establish availability on the experiment date or explain the AI result. Details are in [post-publication-checks.json](02-post-discovery/data/post-publication-checks.json).

The review proposed a November 7 B/C follow-up. This date is **unconfirmed**; there are no new results and no automation. If conducted, later runs will have their own dates, conditions and records. The Artur Ferreira citation/exclusion example remains a supporting observation in the appendix. See [review decisions](../reviews/2026-11-02-stages-01-02.md), [version metadata](../report-versions.json) and [revision history](../CHANGELOG.md).
