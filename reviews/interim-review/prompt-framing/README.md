# GEO Lab Interim Review, Part 2

**Question framing and creator visibility** · Helen Bird · November 11, 2026

[Read the report](https://helen-bird.github.io/geo-platform-observation/reviews/interim-review/prompt-framing/) · [Methods and evidence](https://helen-bird.github.io/geo-platform-observation/reviews/interim-review/prompt-framing/technical-appendix.html) · [Download the public dataset](public-data.zip) · [Part 1](../historical-replication/)

## What did we expect?

Asking for creators may increase personal-name exposure even when a resource appears under both prompts. Asking for original, reproducible experiments may also change which resources and people appear.

## How did we test it?

We collected **120 new answers** from ChatGPT web with GPT-5.6 Sol at Medium and Grok Expert. Each used native web search. We ran six prompts ten times per environment across ten blocks. The 300 Part 1 answers provide historical context.

The resource questions ask for practical, data-backed tutorials, explicitly request tutorial recommendations, or ask for original, reproducible experiments. The full prompts and corresponding creator questions appear in the [condition file](data/conditions.json).

## What did we find?

- **Every creator-prompt answer recommended at least one person.** The 60 resource-prompt answers recommended resources. Some named the authors in their explanations.
- **Resource-only framing changed author exposure.** Grok recommended The GEO Lab or its works in 6/10 discovery, 4/10 explicit recommendation, and 10/10 original-experiments resource answers. Artur Ferreira was named in 0/10, 0/10, and 4/10 respectively. In the original-experiments creator condition he was named in 10/10, while The GEO Lab also appeared in 10/10.
- **The evidence-oriented creator question surfaced Helen Bird.** Grok recommended her in 7/10 answers and ChatGPT in 3/10. Those answers exposed the GEO Learning Hub through their visible source panels or body links.

> These results describe the tested questions and the observed web sessions. The data cannot isolate a byline or a specific page as the cause of a recommendation.

## Data and reproduction

| File | Contents |
| --- | --- |
| [conditions.json](data/conditions.json) | Six prompts, environments, block seed and collection summary |
| [answers.jsonl](data/answers.jsonl) | 120 redacted answer bodies with visible links, search activity and a curated panel URL list |
| [attempts.jsonl](data/attempts.jsonl) | 120 attempt histories |
| [measurements.jsonl](data/measurements.jsonl) | Resource and person coding, evidence excerpts, and observable source sets |
| [entity-registry.json](data/entity-registry.json) | Aliases and first-party attribution checks |
| [summary.json](data/summary.json) | Recomputed condition and block comparisons |

Run `python3 scripts/build_prompt_framing.py` from the repository root. The build works offline. Cite a GitHub commit permalink and an answer ID for a fixed record.

The export removes private links and capture metadata, credentials, local paths, tracking parameters, panel previews and unrelated same-name search hits. One answer has a trailing word recovered from the same session's second capture. The public answer row marks this recovery.
