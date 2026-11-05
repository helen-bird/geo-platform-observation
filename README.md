# GEO Learning Log

An ongoing record of experiments, resource reviews, and lessons from learning Generative Engine Optimization (GEO). Each stage preserves its questions, methods, evidence, and limitations for review and future revision.

**[Explore the GEO Learning Hub](https://helen-bird.github.io/geo-platform-observation/learning-hub/)** — start with a user question, then follow the report, public dataset and complete evidence appendix.

Maintained by **Helen Bird**. The hub was published on **November 3, 2026**; each entry records the original experiment, first-publication and last-revision dates.

## Stages

| Stage | Learning focus | Materials |
| --- | --- | --- |
| Stage 1 | Repeated queries to ChatGPT Search and Grok to explore the differences between Citation, Mention, and Recommendation | [Learning notes and data guide](stages/01-platform-observation.md) · [Concise report](https://helen-bird.github.io/geo-platform-observation/) · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/technical-appendix.html) |
| Stage 2 | Test whether an original public experiment post can be accessed by URL, found by an exact excerpt, or discovered through an unbranded question | [Learning notes and data guide](stages/02-post-discovery.md) · [Concise report](https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/) · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/technical-appendix.html) |
| Stage 3 | Explore repeated prompts and wording sensitivity in Grok Expert consumer sessions and OpenAI API web search; peer-review revision adds matched comparisons and normalization sensitivity | [Learning notes and data guide](stages/03-question-sensitivity.md) · [Concise report](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/) · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/technical-appendix.html) |
| Stage 4 | Test historically selected creator families using new answers; distinguish personal names from associated content brands and audit actual cited pages | [Learning notes and data guide](stages/04-creator-benchmark.md) · [Concise report](https://helen-bird.github.io/geo-platform-observation/stages/04-creator-benchmark/) · [Technical appendix](https://helen-bird.github.io/geo-platform-observation/stages/04-creator-benchmark/technical-appendix.html) |

New stages will be added as learning and experiments are completed. Each stage documents its findings, data, reproduction commands, and publication scope. Stage 1's report remains at the main website address; later stages have their own reports and data directories. File history preserves subsequent corrections.

> Stages 3 and 4 use the **Responses API with web search**, not the ChatGPT consumer website or app. Their OpenAI results cannot represent ChatGPT web/app performance. Each stage records its actual collection conditions and limits rather than treating different interfaces as equivalent.

## Revisions and evidence

[Report versions](report-versions.json) · [Changelog](CHANGELOG.md) · [Stage 1 / Stage 2 review decisions](reviews/2026-11-02-stages-01-02.md) · [Stage 4 review decisions](reviews/2026-11-03-stage04.md)

Each reader leads with bounded findings; a separate complete appendix preserves expanded original evidence. Later source audits and user-reported follow-ups are explicitly separate from the experiment-date outcomes. The November 7 B/C retest is an unconfirmed review proposal, with no results or automation.

The Learning Hub organizes existing material by user question; its effect on AI discovery, recommendation or conversions has not been measured. It is a candidate practice arising from the Stage 4 source audit, not an established GEO intervention result.

## Evidence access and technical maintenance

[Browse original answers](https://helen-bird.github.io/geo-platform-observation/evidence/) provides 60 individually addressable selected-response pages across the first four labs. Full expanded appendices, all historical attempts and original public datasets remain available. AI response text is preserved as generated output; Helen Bird curates the experiment record.

The November 4 technical maintenance adds consistent canonical/description/social metadata, truthful author/series markup and a [small canonical sitemap](https://helen-bird.github.io/geo-platform-observation/sitemap.xml). These bundled changes have no measured effect on AI discovery or recommendations. Actual search-engine indexing, real crawler visits and AI candidate-library inclusion are not established by static validation. Host robots and training preferences were not changed.

Build offline with `python3 scripts/build_site.py`. For presentation-only maintenance, use `--preserve-evidence`; it verifies that scientific data/results are unchanged and preserves existing evidence/download bytes. Run `python3 scripts/check_publication.py` to validate the public boundary and links. Local `audits/` evidence is ignored by Git and must not be included in a public release.

## Google indexing monitoring

The [canonical monitoring inventory](monitoring/google-index/urls.json) contains ten important editorial, navigation and full-appendix routes. Supplemental individual-answer archives remain crawlable but are not monitored individually in the initial configuration. The sitemap now includes the evidence index as well as the original nine report/hub routes.

[Monitoring architecture and operation](docs/google-index-monitoring.md) · [Owner OAuth setup](docs/google-oauth-setup.md). The scheduled workflow runs in a separate private repository, not in this Pages site. Detailed Search Console responses, historical snapshots, manual inspection evidence and credentials are not publication inputs. This public repository contains code, a workflow template and safe URL intent only.

URL Inspection queries Google's indexed-version state; it is not a live test and never requests indexing. Sitemap submission uses a separate one-time authorization and is not repeated by the weekly monitor. Ordinary-page indexing requests remain manual. Google index changes do not establish ChatGPT/Grok discovery or recommendation effects.

## Multi-engine monitoring

The private weekly monitor now separates Google indexing, Bing Webmaster discovery/crawl observations, and OpenAI search crawl eligibility. [Implementation and evidence boundaries](docs/multi-engine-discoverability.md) describe official authorization, the public IndexNow verification file, change-only notifications and UNKNOWN states. Search-engine indexing is not evidence of ChatGPT indexing or recommendations.
