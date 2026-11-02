# What this experiment changes about a GEO prompt bank

This lesson concerns measurement design, not a proven GEO optimization tactic. The practical output is a versioned question bank that separates intent, wording, execution conditions and coding decisions.

## Separate intent from wording

Keep measurement-workflow questions and score-validation questions in separate intent groups. Within each group, retain independently identified wording variants. Do not pool a changed task into an apparent wording effect.

The four original prompts remain unchanged. Their context cues are not perfectly equivalent: M1 emphasizes reliable measurement and no GEO budget; M2 explicitly asks for a free, repeatable workflow; V1 explicitly says no GEO budget; V2 says bootstrapped. Record these differences rather than assuming synonymous treatment.

## Freeze a baseline before comparing results

Store the exact prompt text, intent ID, variant ID, buyer context, budget cue, purpose and prompt-bank version. A change to any of these creates a new version. Keep branded knowledge diagnostics separate from unbranded discovery questions.

For every run record the actual execution environment, requested and returned model labels, reasoning configuration, search enablement and observed search, date/time, locale if known, and session/context controls. An API result is not a consumer-interface result. A fixed model alias does not prove a fixed backend snapshot.

## Repeat, and compare like with like

Collect independent fresh runs under fixed recorded conditions. Three repeats were this exploratory experiment's design, not an established universal minimum for trustworthy measurement. Choose future sample sizes in light of the decision, variance and available budget.

When comparing wording variants, show both within-variant pairs and cross-variant pairs using the same set metric. Here six within-wording pairs and nine cross-wording pairs reuse six answers; they are not fifteen independent trials. Keep both-empty Jaccard comparisons N/A and display eligible counts.

## Publish entity definitions with the score

Keep strict entity names as the baseline. Report a separate, explicitly mapped family sensitivity view and distinguish specialized GEO offerings, general measurement tools, channels, and other AI features. Do not silently infer a version from an unspecified name or treat two products from one vendor as identical.

Citation, substantive mention and active recommendation require separate decisions. C/M/R among already coded named entities is not a population brand-mention rate. Count source URLs and source domains separately, with a declared tracking/privacy cleanup policy. Sharing a domain does not establish sharing an article, and sharing a URL does not independently verify its contents.

## Keep evidence and review status visible

Archive the original response and all failures. Missing or truncated responses do not establish non-recommendation. Preserve source links, actual search evidence and the reason for each coding judgment. Mark source-map coverage limits.

For future substantive decisions, independently check ambiguous entity matches and C/M/R labels with a human reviewer. This revision supplies an eight-case targeted packet, still pending human completion; its purpose is to inspect difficult decisions, not estimate an error rate for all answers. A six-source assistant spot-check is likewise not a full fact-check of the corpus.

## A minimal record schema

```json
{
  "prompt_bank_version": "example-version",
  "intent_id": "measurement_or_validation",
  "variant_id": "stable_variant_id",
  "exact_prompt": "Preserve the exact text",
  "buyer_context_and_budget_cues": [],
  "branded_or_unbranded": "explicitly_label_this",
  "execution_environment": "consumer_interface_or_API",
  "model_and_search_evidence": "recorded_per_run",
  "normalization_version": "explicit_mapping_version",
  "repetition_id": "independent_run_id",
  "body_and_source_map_completeness": "separate_fields",
  "human_review_status": "pending_or_documented"
}
```

> This schema is a proposed workflow informed by the observed sensitivities. The experiment did not test whether using it improves GEO visibility, validates a commercial score, or predicts real buyer exposure.
