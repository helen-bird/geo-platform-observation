# Independent human spot-check packet

**Status: not completed.** This packet prepares eight targeted decisions; no AI review is counted as independent human validation.

The cases are purposive and cannot estimate the accuracy of all 24 coded answers. Read the full linked transcript, record your decision and rationale, then compare with existing assistant coding if needed. Existing public coding remains accessible, so blinding is not guaranteed.

C = the entity’s own content is cited; M = a substantive explicit mention; R = actively suggested for the task. A source title alone is not a tool recommendation. Unspecified product versions remain unspecified.

## H01 · S3-OPENAIAPI-M2-R2

A suggestion to include X-centric prompts: does this actively recommend using a channel for the task, or merely describe source coverage?

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M2-R2.json)

> For Grok, include a few X-centric prompts because its search capabilities can use both real-time web and X information.

Human decision: **pending**. Rationale: **pending**.

## H02 · S3-OPENAIAPI-M2-R2

The answer does not specify GA4. Review the strict name, conditional recommendation and whether any citation is the tool’s own content.

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M2-R2.json)

> making them identifiable in tools such as Google Analytics.

Human decision: **pending**. Rationale: **pending**.

## H03 · S3-OPENAIAPI-M1-R1

Is sourcing buyer wording from Search Console an active measurement-support recommendation? Keep supporting tools distinct from specialized GEO products.

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M1-R1.json)

> Search Console queries

Human decision: **pending**. Rationale: **pending**.

## H04 · S3-OPENAIAPI-M1-R3

Review the explicitly named analytics option and distinguish recommendation from own-content citation.

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M1-R3.json)

> In GA4, Plausible, PostHog, or server logs, create a segment for:

Human decision: **pending**. Rationale: **pending**.

## H05 · S3-OPENAIAPI-M2-R1

Review whether a recurring cited-source pattern is an active tool/channel recommendation.

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M2-R1.json)

> Reddit or community discussions

Human decision: **pending**. Rationale: **pending**.

## H06 · S3-GROK-V2-R1

Review a corroborating developer/community signal: active suggestion, contextual mention, or neither?

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-GROK-V2-R1.json)

> Community and third-party presence (Reddit, review sites, GitHub, directories, X engagement)—these heavily influence what the models say.

Human decision: **pending**. Rationale: **pending**.

## H07 · S3-GROK-V1-R2

Review the unspecified product label without inferring an AEO/AI Search product identity. Family grouping is a separate sensitivity lens.

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-GROK-V1-R2.json)

> Free one-off checkers (Ahrefs, Semrush limited free checks, HubSpot grader, and others) can give a directional snapshot. Treat them as low-trust starting points and always verify the important prompts yourself. They are useful for spotting gaps, not for precise scores.

Human decision: **pending**. Rationale: **pending**.

## H08 · S3-OPENAIAPI-M2-R2

Does the returned Recommendation visibility formula measure mention rate, recommendation rate, or an ambiguous combination? Is the answer internally consistent elsewhere?

[Full redacted answer](https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/data/records/S3-OPENAIAPI-M2-R2.json)

> ### Recommendation visibility
>
> ```text
> Answers mentioning you ÷ total tested answers
> ```

Human decision: **pending**. Rationale: **pending**.

## Recording a completed review

Enter genuine human judgments in `human-review.json`, with review date and the reviewer’s approved public identifier if any. Do not mark completion merely because another assistant reread the evidence. Corrected coding, if required, must be a separately documented revision preserving the original labels.
