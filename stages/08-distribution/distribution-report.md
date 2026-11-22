# GEO Lab #08: How Do Indie Creators Get Their Work Discovered?

*A field study of community participation, free resource directories, and measurable distribution.*

I had a free guide and Excel Worksheet for measuring AI search visibility, plus a set of original studies. With no established distribution network, I shared findings on X, answered questions on Reddit, and pitched relevant directories. I wanted to see how far each effort got, from publishing to a click, a visit, a download, or a public listing.

The kit helps a builder choose a buyer question, collect repeated AI answers, and score mentions, citations, and recommendations. Its worked example uses ten saved answers. The research archive includes a replication and sample-size study based on 300 new answers. I pitched the kit to guides and templates sections and used original studies where the audience wanted research evidence. [Measurement Guide and Worksheet](../../learning-hub/measurement/) · [Replication study](../../reviews/interim-review/historical-replication/)

> **Scope.** Results are a snapshot as of November 22, 2026, Beijing time. The channels used different assets, audiences, dates, and measurement windows. The study supports decisions about what to test next. Long-term channel rankings and effects on AI recommendations remain unmeasured.

## Findings

### 1. X gave me a reason to run one more small test

**What the data shows.** Four X posts recorded 233 impressions and 30 engagements. Two posts each recorded two clicks on links to their research reports. Three Reddit replies addressed AI referrals, sample-size sensitivity, and evaluating AEO tools. They contained no resource links. I observed no views, votes, replies, substantive discussion, or requests for the resource in the November 22 Reddit check. [X posts and measurement notes](technical-appendix.html#community)

**What I can conclude.** X shows four link-click events, with no matching non-test X session identifiable in GA4. The two posts were published before the initial GA4 deployment, one by only two minutes. X reported cumulative clicks, so their timing and the number of people who clicked are unknown. The evidence supports another small test on X. It leaves Worksheet demand and Reddit's ability to generate referrals open.

**What you can do.** Write one post answering a narrow question your resource helps solve. For example, share what a ten-answer example can tell a solo founder about AI visibility, then link to the guide and Worksheet with a tag specific to that post. Read the platform's click count and site-side arrivals separately. On Reddit, answer the existing question on the page. Where a link would help answer it and the rules allow it, verify what actually appeared in the published reply. For replies without links, track follow-up questions and resource requests.

### 2. A free submission only earns a placement when the entry goes live

**What the data shows.** I screened 15 channels for audience fit, fees, rules, and reciprocal-link requirements. Seven reached submission or a free queue. Four GitHub PRs remained open and unmerged, one with an automated approval. SEOFOMO acknowledged delivery. The last verified PitchWall receipt showed review in progress, with an estimated wait over 30 days. Uneed confirmed a free queue slot for July 3, 2027. I had zero verified public listings at the cutoff. [Submission states and public PRs](technical-appendix.html#submissions)

**What I can conclude.** Getting into a free submission process was feasible. Public pickup remained pending. The first and last Reddit replies were about 17 minutes apart, and about 85 minutes elapsed between the first directory receipt and the last queue confirmation. These were elapsed intervals with preparation unmeasured and with waits or overlapping work possible. I can identify the work involved, including eligibility checks, screenshots, accounts, and scheduling. The study gives no reliable cost per placement or return per hour.

**What you can do.** Find a recent entry that matches your resource before filling out a form. A guide or template fits a relevant resource section. A reproducible study fits a collection that asks for original evidence. Prepare one reusable pack with a short description, audience, price, screenshot, direct link, and supporting evidence. Start with two or three closely matched free channels. Track submission date, last verified status, and public URL. Count a placement once you can open the public entry and follow its link to your resource.

### 3. QA traffic can make a download report look like reader interest

**What the data shows.** GA4 recorded 11 sessions, 7 active users, 16 views, and 7 Worksheet download clicks across the full observation window. The QA records explained all seven clicks. After exclusions, one unresolved session remained, with no view or download. A separate landing counter recorded 49 eligible requests to the Guide from November 17 to 22 outside explicitly marked QA. Of these, 47 had no source label and 2 carried a PitchWall label on submission day. [Traffic and QA breakdown](technical-appendix.html#traffic)

**What I can conclude.** The Guide endpoint received requests. We have zero confirmed non-test Worksheet clicks, and the source of the two PitchWall-tagged requests is unconfirmed. The requests may include previews, internal checks, or repeat opens. GA4 covers visits where people consented and analytics succeeded. Neither source establishes the total number of readers. A measured download click would record an action, with actual use of the Worksheet still to verify.

**What you can do.** Before publishing, run one marked QA visit. Verify that the link opens the intended page, the source is recorded, and one download click reports once. Send the production link without QA tags. Compare its platform clicks, attributed arrivals, GA4 sessions, and download events in separate columns. If clicks appear without a matching visit, review the actual redirect, campaign tag, consent, and event delivery. If verified visits appear with few downloads, collect more observations before deciding the resource or call to action needs changing.

## A small distribution test you can run in one week

1. **Pick one reader task and a single destination.** For this project, the task would be scoring an initial AI visibility baseline. The destination would be the Measurement Guide with its Worksheet. A Worksheet click is the first measurable resource action.
2. **Set up the link before launch.** Record the clean destination and one tag per actual placement. For example, use `utm_source=x`, `utm_medium=social`, `utm_campaign=measurement_kit_week1`, and `utm_content=baseline_workflow` for a single X post. Run a marked QA visit and confirm that one click produces one download event. Save the URL that appears in the published post and confirm it reaches the intended page.
3. **Keep the batch small.** Publish one X post with a finding readers can use on its own. Submit to up to two closely matched free directories if relevant, and log each receipt. Join a community discussion only when you have a specific answer to contribute. A community reply can be measured on its own even if it has no resource link.
4. **Check after seven days.** Save platform impressions, engagements and link clicks. Compare them with available tagged requests, consented sessions and resource clicks. Let the last GA4 dates finish processing before treating blanks as settled. For directories, record the status during the week and check the public entry after a decision or queue date. [GA4 data freshness](https://support.google.com/analytics/answer/11198161)
5. **Choose the next action based on the first gap.** With some exposure and no clicks, try a clearer post or a better-matched audience. With clicks and unresolved arrivals, check the measurement path before rewriting the resource. With repeated verified visits and no resource actions, inspect the page and download step. With a pending directory submission, set a follow-up date. Treat each change as a test for the next round.

Use one row per placement. A useful row contains the asset, publication or submission date, actual URL, platform clicks, attributable arrivals, consented sessions, resource clicks, public placement status, evidence link, and last checked date. Mark unavailable measures as unknown and measures that do not apply as N/A. Record zero when a metric was measured and none were observed.

## Methods and evidence

The [technical appendix](technical-appendix.html) provides the per-post results, directory status, traffic timeline, QA rules, and [public aggregate data](summary.csv). This release uses reviewed aggregate values and public references. Private analytics exports, account receipts, and personal details stay in the research archive.
