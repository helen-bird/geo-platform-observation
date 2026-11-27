# GEO Lab #09 Supplement · Measurement Kit Optimization and Retest

I used one question from Lab #09 to compare resources ChatGPT already recommended, improve my free measurement guide and workbook, and run the same question again. Recommendations appeared in **16 of 30 answers (53.3%)**, compared with **0 of 30** before the changes. The first retest started three days and 53 minutes after v2.0 went live.

- [Read the public report](https://helen-bird.github.io/geo-platform-observation/stages/09-visibility-baseline/measurement-kit-retest/)
- [Methods and evidence](https://helen-bird.github.io/geo-platform-observation/stages/09-visibility-baseline/measurement-kit-retest/technical-appendix.html)
- [Download all 30 redacted answers and links](public-data.zip)
- [Exact question](data/prompts.json), [release and collection times](data/timing.json), [answer-level observations](data/observations.jsonl), and [attempts](data/attempts.jsonl)

## From benchmark to edit

I read the M2 baseline answers and counted recommended resources once per answer. I then tried publicly available guides, question builders and spreadsheets. Diego Navarro's tracker appeared in 12/30 answers, Apollo Digital and Digital6ix in 10/30 each, and Semantic Frame in 8/30. These resources suggested three improvements I could test in my own kit: help readers take a first measurement, let them compare a follow-up under the same conditions, and show them what to investigate when a resource is missing from the answer or sources.

I added a quick start, a worksheet preview and a downloadable prompt library. The rebuilt workbook tracks failed and eligible attempts, keeps source types separate, and compares a baseline with two follow-up rounds. The guide adds a diagnostic checklist, reproducible examples, a clearer author link and new links from relevant research pages. The sitemap lists the guide, and a follow-up deployment adjusted its search title and description.

## Release and retest

The [v2.0 release](https://github.com/helen-bird/geo-platform-observation/commit/c29189118f818cfdfc238c979ad2185665e02a32) deployed on November 24 at 20:04 Beijing time. On November 27 a fresh title-only ChatGPT search found v2.0. I then ran the unchanged, unbranded M2 question in 30 fresh unpersonalized ChatGPT web sessions with GPT-6 selected and automatic search. Medium recommended the kit in **9/15** answers and High in **7/15**. All 16 included a guide or workbook link in the answer body.

The combined changes preceded the increase. The study cannot isolate which edit helped or rule out changes in the search environment. The second time window remains pending. The original Lab #09 baseline stays [in its own record](../).

To rebuild the two public pages and check their input evidence, run `python3 scripts/build_measurement_kit_retest.py` from the repository root.
