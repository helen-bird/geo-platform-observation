# GEO Lab #07 · What makes a creator worth recommending?

**Helen Bird · GEO Learning Log · 13 November 2026**

*An observational study of AI recommendations, a comparison of four creator brands, and a practical guide to closing the gaps you can control.*

## What we found

- **Authority depends on the job the user is trying to do.** In 60 historical answers, Helen Bird was recommended in **10/20** answers seeking original, reproducible experiments, versus **3/40** seeking practical tutorials across two prompts. Artur Ferreira was recommended in **20/20** experiment answers. Aleyda Solis and Kevin Indig each appeared in **16/20** answers that explicitly asked for tutorial creators to recommend. The same person can be a strong match for one job and a weak match for another.
- **The comparison exposed a specific gap we could close.** GEO Lab already had original experiments, public evidence and scripts that reproduced published numbers. The missing asset was a path a solo builder could follow from a buyer question to a baseline, a recorded change and a follow-up. We built a [measurement guide](https://helen-bird.github.io/geo-platform-observation/learning-hub/measurement/), an [Excel worksheet](https://helen-bird.github.io/geo-platform-observation/learning-hub/measurement/ai-recommendation-measurement.xlsx) and a real worked example. Then we made [420 archived responses](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/) easier to inspect.
- **We verified the release. Recommendation lift is still unknown.** The guide opens, the Excel file downloads and opens, and both review reports lead to individual answers and their coding. No post-release AI sample or independent reader usability test was run. The historical counts are a reference, not a purpose-built immediate pre-release baseline.

> In this report, **brand authority** means the strength of the public evidence for relying on a named creator or product for a particular job. We look for clear ownership, useful work, evidence that can be checked, and independent corroboration when it exists. We do not assign a universal authority score or treat recommendation frequency as a measure of research quality.

<figure class="contrast"><figcaption>Helen Bird: recommendations by task</figcaption><div class="bar-row"><strong>Practical tutorials</strong><div class="track" aria-hidden="true"><span style="width:7.5%"></span></div><b>3/40</b></div><div class="bar-row"><strong>Reproducible experiments</strong><div class="track" aria-hidden="true"><span style="width:50%"></span></div><b>10/20</b></div><p>ChatGPT and Grok pooled for this display. The two tutorial prompts each contributed 20 answers; the evidence prompt contributed 20.</p></figure>

## 1. How we tested

We reused the creator side of [Interim Review Part 2](https://helen-bird.github.io/geo-platform-observation/reviews/interim-review/prompt-framing/). There were **three creator prompts × two consumer web interfaces × ten completed runs**. The other 60 answers asked for resources, and the earlier 300-answer review was historical context. Neither enters the Lab #07 denominator. The source collection took place on November 10–11, 2026; Lab #07 recoded and audited it on November 13. No new answers were bought or collected.

- **Discovery:** Which independent creators publish practical, data-backed GEO tutorials for independent builders? Explain why and cite sources when available.
- **Recommendation:** Which independent creators publishing practical, data-backed GEO tutorials would you recommend to independent builders? Explain why and cite sources when available.
- **Evidence:** Which independent creators publish original, reproducible GEO experiments useful to independent builders? Explain why and cite sources when available.

Discovery and Recommendation both ask about tutorials; the second explicitly asks for suggestions. Evidence changes the user's task to finding original, reproducible experiments. It is useful to compare these tasks, but the resulting difference is not a pure wording effect.

ChatGPT ran in fresh temporary web chats (GPT-5.6 Sol, Medium; captured label 5.6 Medium). Grok used fresh Expert web chats with X and conversation personalization disabled during collection. Native web search was explicitly enabled on all 60 submissions. Search activity was observable in **25/30 ChatGPT** and **30/30 Grok** captures. Lack of observed activity is unknown; it is not evidence that search was skipped. These are consumer web results, not API results.

**From answer to measurement.** Each answer was checked against its stored capture and block ID. We kept a row for every person in every answer, including negative outcomes. A name in a byline or a supporting paragraph counts as a **mention**. A person counts as **recommended** when the answer presents them as an option for the task. A recommended work, a correctly attributed work and a personal recommendation are distinct. We also kept answer citations, visible source-panel links and sources found later by the reviewer separate.

We used the earlier creator benchmark to select Aleyda, Kevin and Artur, then compared Helen against them and checked alternatives in the answers that omitted her. The three cases show different ways of creating value. They were chosen because they had already been recommended, so they do not represent all creators or provide a sample of unseen successes.

## 2. Who was recommended, and for what?

Each cell shows **person recommendations / person mentions**. Each of the two counts is out of ten answers per cell, or 60 in the total column. One answer can recommend several people.

|Creator|ChatGPT Discovery|ChatGPT Recommendation|ChatGPT Evidence|Grok Discovery|Grok Recommendation|Grok Evidence|All 60|
|---|---|---|---|---|---|---|---|
|Aleyda Solis|6 / 7|10 / 10|1 / 2|3 / 3|6 / 6|0 / 0|26 / 28|
|Kevin Indig|4 / 4|10 / 10|1 / 1|5 / 5|6 / 6|0 / 0|26 / 26|
|Artur Ferreira|7 / 7|9 / 9|10 / 10|2 / 2|2 / 2|10 / 10|40 / 40|
|Helen Bird|1 / 1|2 / 2|3 / 3|0 / 1|0 / 0|7 / 8|13 / 15|

**The answer to “who is ahead?” changes with the question.** On the explicit tutorial recommendation prompt, ChatGPT recommended Aleyda and Kevin in 10/10 answers each and Helen in 2/10; Grok recommended Aleyda and Kevin in 6/10 each and Helen in 0/10. On the evidence prompt, Helen reached 3/10 on ChatGPT and 7/10 on Grok, against Artur's 10/10 in both. Grok's tutorial discovery results point to other useful comparisons: Sam Shev was recommended 9/10 times, and Kevin Indig and Robin Pautigny 5/10 each. Inspect the people who answer your exact question well, rather than using the overall leader as the benchmark for every task.

**The answer is rarely a winner-takes-all list.** All ten evidence answers that recommended Helen also recommended Artur. Across all tasks, all 13 Helen recommendations co-occurred with Artur. This shows the answer had room for more than one creator. It gives no estimate of whether one creator affected the other's selection.

**Discovery and recommendation are different observations.** In three Grok tutorial answers, Helen's site appeared in the captured source panel and the answer did not recommend her. In the Grok evidence cell, the site appeared in 9/10 panels and she was recommended in 7/10. A panel entry shows what the interface exposed. It cannot tell us which page the system read or used. ChatGPT had no comparable captured panel; Grok had no identifiable final answer URLs in these 30 captures. Neither is a measured zero for the platform's actual citation or retrieval rate.

[Inspect a Grok tutorial answer with a boundary judgment](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/record.html?review=prompt-framing&id=IR2-GROK-WEB-DISCOVERY-CREATOR-B08-A01#answer) · [Inspect an evidence recommendation](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/record.html?review=prompt-framing&id=IR2-GROK-WEB-EVIDENCE-CREATOR-B01-A01#answer)

> With ten answers per cell, rates are rough. Under a simple binomial model, the descriptive 95% Wilson interval for 7/10 is about 40%–89%; for 0/10 it reaches about 28%. Repeated model responses can be correlated. These intervals do not establish significance, long-term stability or the expected return from an edit.

## 3. What reasons did the answers give?

We began with six categories: identity, experience, original evidence, sustained topic work, outside recognition and distribution. Reading a first answer from each cell suggested five more: actionable guidance, access, reproducibility, task fit and evidence judgment. We then applied one codebook to all 60 answers. The unit for the middle column is one recommended person in one answer. The right column deduplicates by answer. Categories overlap, and a single answer is not several independent observations.

|Reason given in the answer|Recommendation rows|Distinct answers|
|---|---|---|
|Original evidence|230/294|58/60|
|Fit for a user or task|216/294|60/60|
|Practical steps or tools|156/294|57/60|
|Free or easy to access|120/294|56/60|
|Evidence limits or disclosure|120/294|44/60|
|Conditions for checking or repeating|111/294|45/60|
|Sustained topical work|48/294|38/60|
|Role or identity|41/294|24/60|
|Specific experience|38/294|29/60|
|External recognition claim|20/294|14/60|
|Distribution or audience|11/294|10/60|

**“I can do it,” “I can check it” and “I know where it stops” are different benefits.** A checklist helps a reader act. Fixed prompts, inputs and code help a reader inspect or repeat a study. Failed runs, caveats and corrections help a reader decide how far to trust the conclusion. The reasons given for Helen support that last pair: all 13 recommendations referred to original work; 11 mentioned conditions for checking or repeating it, and 11 mentioned evidence judgment or disclosure. These are statements in the output. They are not a view into a platform's ranking mechanism.

**A claim and its source are checked separately.** A nearby answer URL is a lead. A panel is an inventory visible in the capture. A public page found during our audit can corroborate a claim today, but does not show that the historical model saw it. For instance, one ChatGPT answer linked Lab #04 near a statement about direct access and natural discovery; [Lab #02](https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/) is the clearer direct support. The same review found no confirmed license for a Grok claim suggesting MIT-style reuse. Accessible materials and permission to reuse them are separate.

## 4. What the comparison actually verified

We used the same checks on each creator: Who owns the work? What exactly can the reader do? Is the evidence original? Can the headline number be recalculated? Did a distinct party report, use or reproduce the work? Does the public source predate the historical answer? We checked a purposive set of consequential claims. “Supported” means the source supports the stated scope; it does not confer a general quality rating. “Partial” narrows a claim. “Unknown” preserves a missing fact.

|Creator|Supported|Partial|Contradicted|Unknown|Subjective|
|---|---|---|---|---|---|
|Aleyda Solis|12|2|2|0|1|
|Kevin Indig|13|5|0|0|1|
|Artur Ferreira|8|5|1|1|1|

These 52 claim groups cover the three focal benchmarks; the audit also examined three attribution or authorship leads involving other creators. A separate Helen audit split 13 recommendations into 27 claims: 21 supported, three partial, two subjective and one unknown. These were targeted checks, not accuracy estimates for all AI answers.

### Aleyda Solis: the next action is obvious

[Learning AI Search](https://learningaisearch.com/about/) connects a named author to a curated learning path. Her [AI search checklist and worksheet](https://www.aleydasolis.com/en/ai-search/ai-search-optimization-checklist/) turn the topic into ordered tasks and a reusable deliverable. The audited September edition had 12 steps; a Grok answer described ten. The mismatch matters when a reader tries to follow the instruction. Her [15-brand SaaS benchmark](https://www.aleydasolis.com/en/ai-search/saas-ai-search-optimization/) also gives original analysis, using Semrush and Similarweb data. Readers can inspect the method and aggregates; the complete supplier inputs were not found in the reviewed public materials.

**What to copy:** Choose one reader, one decision and one finished output. Turn scattered explanations into steps and add a blank template plus a real completed example. You can do this without a commercial dataset or an established newsletter.

### Kevin Indig: original data answers a decision question

Kevin and Amanda Johnson's [study of original data and AI citations](https://searchengineland.com/why-most-original-data-never-gets-cited-481676) analyzed 301 pages already cited across 316 questions in seven verticals. Eight original-research pages accounted for 90 citations; 75 of those citations came from one benchmark cluster. That concentration changes the interpretation. The sample supports a comparison within pages already cited; it cannot tell a founder what happens to the citation probability of any webpage after they publish original data. Growth Memo's archive, collaborations and external coverage give the work multiple routes to readers. A partner's article, an independent report and an independent replication are different evidence.

**What to copy:** Start with a specific decision, publish the sample and denominator, and show how much of the result comes from one case. A small transparent study may be enough. Seek commercial data only when it can answer a question the smaller sample cannot, and explain which inputs readers can access.

### Artur Ferreira: readers can follow the experiments and their revisions

[The GEO Log](https://thegeolab.net/log/) connects methods, experiments and revisions under a consistent byline. The [E026 archive](https://zenodo.org/api/records/22230285) made a result checkable: we recounted 136/750 citations from the posted records. [Paper B's preregistration](https://zenodo.org/api/records/22798718) predates the confirmation test; the [study package](https://zenodo.org/api/records/23122087) documents zero target retrievals in 40 formal runs, so it cannot estimate attribution after retrieval. The [E001 correction](https://zenodo.org/api/records/21539564) shows why a recognizable brand cannot replace checking the specific work: 18/30 versus 11/30 gives a 23.3-point descriptive gap and a two-sided two-proportion test near p=.07. The raw records are unavailable and older descriptions persisted in some materials during the audit.

**What to copy:** Freeze the question and measures before the first run. Assign record IDs, publish permitted inputs and negative results, and tie corrections to the specific edition. Keep the report, worksheet and source archive consistent when the interpretation changes.

### Where GEO Lab already had a credible case

The project already had consistent attribution, a connected research series, repeated unbranded tests, redacted answers, failed attempts and reproducible summaries. This explains why there was something useful to audit when answers recommended Helen for experiments. It does **not** explain why any specific model selected her. Part 1 was publicly committed before collection, but actual retrieval was not established. Part 2, Lab #06 and the new worksheet came later and cannot explain those historical recommendations. Third-party adoption, independent replication and comparative audience size remain unconfirmed.

## 5. From the gap to the operating decision

We used a table of 25 opportunities across 11 dimensions. It separates identity, experience, originality, continuity, outside recognition and distribution from actionable guidance, access, reproducibility, task fit and evidence judgment. For each opportunity we recorded the current proof, a comparable benchmark, the size of the gap, what the author controls, estimated effort, and an observable return. A small gap means an existing capability can be made easier to use; “80 to 90” is shorthand, not a measured score.

| Decision | What we observed | What a first action can earn | What it cannot promise |
|---|---|---|---|
| **Do first: a missing deliverable we control** | We had research and advice. Aleyda's worksheet and the [Sam Shev roadmap](https://www.samshev.com/blog/geo-90-day-roadmap) and [Robin Pautigny solo-founder guide](https://getrefine.ai/blog/geo-for-solo-founders-ai-visibility-playbook) gave readers a sequence they could use end to end. | A reader gets a single workflow and a filled example rather than assembling one from several studies. First-pass estimate: 2–3 days for the package, using existing materials. | No measured lift in recommendations or confirmed reader adoption. |
| **Do next: make existing evidence easier to use** | Both reviews already rebuilt offline, but a reader had to move across reports, appendices and large data files. | A direct path from a report to a selected answer and its coding, plus a fixed reproduction command and expected count. First-pass estimate: half a day to a day. | Easier verification does not turn the original study into an independently replicated experiment. |
| **Investigate before investing** | Source coverage differs by platform, current audience and independent recognition are unknown, and the site has no verified request-log evidence for this study. | Verify the page state, audit stored queries, or ask a willing reader to reproduce one result. Record the evidence and its limits. | Missing evidence does not establish a retrieval block or lack of reputation. |
| **Build over time where the work calls for it** | Larger datasets, controlled live-site interventions, sustained distribution and external validation have prerequisites we do not control. | A real product case or an independent rerun can answer a new question; legitimate collaborations can expand data or reach. | You cannot buy or claim independent validation by publishing your own work in more places. |

The full assessment also helps avoid spending on gaps that do not yet constrain the chosen task:

| Signal to check | GEO Lab compared with the benchmarks | How an operator should use the finding |
|---|---|---|
| Identity, experience and continuity | Authorship and a consistent GEO research series were already visible. Comparable career credentials were not established; the project has a shorter public history. | Keep bylines and links consistent. Add verifiable experience when it helps the user judge the work. |
| Original evidence and evidence judgment | Repeated answer tests and failure disclosures were already available. Industry data, live business interventions and request logs are different kinds of evidence. | Keep publishing bounded, checkable results. Add a dataset or instrumentation only when the next decision requires it. |
| Guidance, access and audience fit | Free reports answered research questions. The audited site lacked a complete beginner measurement workflow. | Turn the strongest existing evidence into a task-specific asset. Test that a reader can complete the job. |
| Reproduction | Offline arithmetic already worked; a clear path to individual answers and fixed versions was missing. External reruns and publicly timestamped protocols remain less developed. | Fix the path first. For a new study, prerecord the plan and invite an independent check. |
| Outside recognition and distribution | GitHub Pages, GitHub and an X publishing path existed. Relative reach and independent adoption were not verified. | Gather real examples of readers using or scrutinizing the work. Record who they are, how they relate to the work, and what they actually checked. |

The comparison justifies **why to build the asset now**: we could see the task people were asking about, the materials benchmark creators offered, and a specific missing deliverable. No evidence justified a numerical forecast for how many additional answers would recommend Helen. That would require a different study.

## 6. What we actually shipped

**First, we assembled the measurement workflow.** We linked the prompt-sensitivity lessons, technical discovery checks and content research into one guide. Each worksheet copy is for one fixed question, target and environment. Every attempt gets an ID. A retry shares a planned slot but gets a new attempt ID; only one complete answer can be selected. The workbook records the model, time zone, search evidence, answer, citation URLs, outcome codes and page changes. It computes Yes / (Yes + No), and shows unknowns and failures separately. A missing judgment never enters the denominator as a No.

**Then we filled it with a real baseline.** The Grok evidence cell has ten saved answers. Helen was mentioned in 8/10 and recommended in 7/10. Final target citation attribution is unknown for all ten, so the sheet leaves its rate empty. B01 is a recommendation; B07 is a background mention. The follow-up tabulation is blank because we did not collect those answers.

**Finally, we made the evidence travel with the claim.** The two reviews now link to a condition-by-condition index for 420 existing answers. A row opens the redacted original answer and its coding in one page, with the fixed GitHub source still visible. The report also shows where to find failed attempts. When live verification found that GitHub's large JSONL viewer did not reliably jump to the desired line, we added direct individual records on the website. No historical data or judgments were changed by that release.

| Verification | Result |
|---|---|
| [Guide](https://helen-bird.github.io/geo-platform-observation/learning-hub/measurement/) and [worksheet](https://helen-bird.github.io/geo-platform-observation/learning-hub/measurement/ai-recommendation-measurement.xlsx) | Opened from the public Learning Hub; downloaded and inspected both worksheet tabs and the example counts. Duplicate selected slots, failed retries and unknown citations were checked before release. |
| [Part 1 evidence](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/#part-1) and [Part 2 evidence](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/#part-2) | Opened from both reports. One live sample per review was checked for both answer and coding, and all 840 answer/coding destinations were matched to record IDs in the archived releases. |
| [Public release](https://github.com/helen-bird/geo-platform-observation/commit/5842a87b7f18bf45dd755a73fda0687d5634b101) and [direct-record fix](https://github.com/helen-bird/geo-platform-observation/commit/092941ac33125b30a1b6d88845a8813e3b56263e) | Released November 13, 2026. The two archived reviews also rebuilt offline: four files per version matched byte for byte, including data summaries, reports, appendices and data packages. |

## 7. How to apply this to your own brand

1. **Pick a job with a real user behind it.** Pull one question from a buyer conversation or support thread. Write it in the user's words without your brand. For example, a backup SaaS might measure “Which backup tools let a small GitHub team restore one deleted repository?” A question about generic backup is a separate condition.
2. **Record your baseline before changing pages.** Save the exact question, environment and plan. Use fresh sessions and keep platform results separate. Ten valid runs per setup can give an initial reading. Increase repetitions and use several windows when the decision needs more precision. Save full answers, visible queries or sources, and failed attempts. Score mentions, citations and recommendations separately.
3. **Audit actual alternatives.** Pick two or three repeatedly recommended options on that question. Locate the work each answer is pointing to, then check the page and owner independently. For backup software, an actionable gap might be a restore walkthrough that identifies supported plans, demonstrates a real restoration and states limitations. A source panel with your domain but no recommendation is a lead to inspect; it does not tell you why the model omitted you.
4. **Write one action with an acceptance test.** Use: *User job → observed gap → comparison evidence → what I control → smallest change → immediate check → later metric*. Example: “Publish a single-repository restore guide, link it from the product's backup page and verify that another person can finish a test restore using it. Then measure whether the unbranded question starts returning that page or the product more often.” Do not copy claims your product cannot support.
5. **Verify delivery, then watch outcomes.** Record the old and new URLs, page versions, release time and concurrent changes. Check the public URL and document what search exposure you can actually see. Later, repeat the fixed prompt and settings across multiple windows, with a contemporaneous unchanged comparison when feasible. Keep URL exposure, source-panel appearance, citation, recommendation, referral and conversion separate. If you change several assets together, a before/after change belongs to the bundle and may also reflect changes in the platform or web.

A useful diagnosis depends on which evidence is missing:

- **No suitable page exists:** make the smallest asset that completes the user task. Start with a working example and a way to check the outcome.
- **A suitable page exists but you see no search evidence:** check its public URL, technical eligibility and the queries you actually captured. Mark missing observations as unknown. A clean access check does not prove the engine retrieved it.
- **The page shows up, but the answer does not recommend you:** compare the question and the actual recommended works. Check whether your page supplies the same decision-critical facts, steps and evidence. Change the material only when you can name the gap; the source panel alone does not identify the cause.
- **The answer recommends the work but does not name you:** verify the ownership and byline on the underlying page. If attribution is weak, clarify it and track work recommendations and correct author attribution separately on the next batch.

> The next test for GEO Lab is practical: can an independent founder complete a valid baseline without help and explain the denominator? For AI outcomes, the next test is to establish prospective, repeated measurements on fixed tutorial and evidence questions, while preserving comparable untreated tasks. There was no matched immediate pre-release measurement for this launch. Our existing historical batch cannot isolate the effect of the guide or the evidence navigation.

## 8. Data, reproduction and limits

- [Fixed historical dataset](https://github.com/helen-bird/geo-platform-observation/tree/becc6a61a0ea6fdc5047cdd1a77ced3e2efa27dc/reviews/interim-review/prompt-framing/data): exact questions, redacted answers, original measurements and attempts. The original Part 2 used a slightly broader boundary for one Grok Discovery answer. Lab #07 treats that answer's positive supporting reference as a mention, not a recommendation. Including it would change Helen's total from 13 to 14 and tutorial result from 3/40 to 4/40. It does not change 10/20 for Evidence. Treating Grok Evidence B10 more strictly would reduce the latter to 9/20.
- [Lab #07 coding snapshot](creator-coding.json), [coding rules](coding-rules.md) and [recount script](recount.py): download both into the same directory and run `python3 recount.py`. This reproduces person counts and reason counts from the frozen review decisions; it does not independently recode the text. Every row contains an answer ID and a public record link. The [review evidence page](https://helen-bird.github.io/geo-platform-observation/learning-hub/review-evidence/#reproduce) separately explains how to rebuild the two earlier reports.
- The dataset covers three English GEO creator questions and one collection window. We used purposive cases and targeted claim audits, with one primary coder per question and review of edge cases. There is no independently measured coder agreement. Missing source fields, changing webpages, unavailable internal retrieval and changing model behavior constrain inference. External recognition, audience size and commercial outcomes were not measured comparably across people.

**Use the benchmark to find evidence you can build for a real user task. Use the follow-up to learn whether that change mattered.**
