# ChatGPT web visibility baseline

This one-time study records 180 answers collected on November 23–24, 2026 (Beijing time) using six fixed prompts and 15 repeats each at Medium and High. Two failed attempts remain in the manifest. The 12-answer pilot is outside the study sample.

- [Read the report](https://helen-bird.github.io/geo-platform-observation/reviews/visibility-baseline/)
- [Methods and source evidence](https://helen-bird.github.io/geo-platform-observation/reviews/visibility-baseline/technical-appendix.html)
- [Exact prompts](data/prompts.json), [observation codes](data/observations.jsonl), and [attempts](data/attempts.jsonl)
- [Redacted data download](public-data.zip), including answer text, observed primary links, and excerpts behind alternative-resource codes

Public IDs identify positions in the frozen plan. The `F` suffix identifies a failed capture. The `R` suffix identifies the valid replacement for that position. The search field records whether search was explicitly observed. Panel coverage separates complete panels, earlier partial evidence and a completed answer with no panel displayed. Target hits in the “More” list stay separate from Citation.

The public record uses a selected field set and strips tracking arguments, embedded interface image links and unpublished metadata. Private session and account details, full browser evidence and failed answer bodies stay with the original working data.

From the repository root, run `python3 scripts/build_visibility_baseline.py` to validate the public evidence and rebuild both HTML pages.
