# GEO Lab Interim Review, Part 1

**Historical replication and sample-size sensitivity** · Helen Bird · November 10, 2026

[Read the report](https://helen-bird.github.io/geo-platform-observation/reviews/interim-review/historical-replication/) · [Methods and evidence](https://helen-bird.github.io/geo-platform-observation/reviews/interim-review/historical-replication/technical-appendix.html) · [Download the public dataset](public-data.zip)

## What did we expect?

We expected several observations from GEO Lab #01–#04 to recur with more runs, including low overlap between recommendation lists and cases where an answer recommends a work without naming its author. We also expected rates based on three answers to be sensitive to which answers we kept.

## How did we test it?

We compared 60 historical answers with **300 new answers**. We reran ten original prompts fifteen times per environment using OpenAI Responses API with web search and Grok Expert with web search. Labs #01 and #04 share the new answers for their three identical prompts. For each condition, we enumerated all 455 three-answer subsets and all 3,003 ten-answer subsets from the new batch.

## What did we find?

- **Low recommendation overlap held up for the tutorial prompt.** All 105 matched comparisons using two answers per environment had overlap below 25%. Median overlap was 4.5%.
- **Access, discovery and author exposure stayed distinct.** Grok read the X post in 15/15 direct-link runs and found it in 0/15 natural-search runs. The OpenAI API identified the original in 11/15 exact-quote runs via the public archive. In the free-learning prompt, Grok recommended The GEO Lab in 15/15 answers and named Artur Ferreira in 0/15.
- **Three runs could substantially misstate a rate.** Grok recommended Artur or his work in 4/15 answers to the tutorial prompt. Three-answer subsets could show 0% or 100%. For two example rates, the fraction of subsets more than 20 percentage points from the full 15-run rate fell from 51.6% at three runs to 0.37% at ten.

> These are observations within the tested setups. The OpenAI arm uses the Responses API with web search. Historical ChatGPT consumer results belong to a different collection environment. The study does not establish the effect of a GEO intervention.

## Data and reproduction

| File | Contents |
| --- | --- |
| [conditions.json](data/conditions.json) | Original prompt text and 20 condition identifiers |
| [answers.jsonl](data/answers.jsonl) | All 300 selected answer bodies after redaction, with final links, observed search activity and source panels in separate fields |
| [attempts.jsonl](data/attempts.jsonl) | All 310 attempt records with 305 recorded submissions and five preparations that did not submit |
| [measurements.jsonl](data/measurements.jsonl) | Coded outcomes and normalized sets used by the public calculations. Unknown values remain null. |
| [claims.json](data/claims.json) | Decisions and evidence summaries for all twelve historical claims |
| [summary.json](data/summary.json) | Recomputed headline counts and subset statistics |

Run `python3 scripts/build_interim_review.py` from the repository root. The script works offline. Cite a GitHub commit permalink and the relevant answer ID for a fixed record.

> The export omits private conversation and share links, credentials, account details, local paths, opaque provider IDs, signed and tracking parameters, and original interface captures. Answer bodies and search evidence are redacted copies. Evidence unavailable from the provider remains unknown. The exclusion and failure records retain status and sequence without private diagnostics.
