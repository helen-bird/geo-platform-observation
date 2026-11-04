# Google indexing monitor: execution, storage and alerts

The public GEO Lab repository contains reviewed code, a canonical URL manifest and this workflow template. Detailed Search Console responses, referring URLs, histories and notification state belong in the separate **private** repository `helen-bird/geo-index-monitor`. It must not enable GitHub Pages. OAuth credentials belong in a GitHub Actions Secret, never in either repository's files.

## What the monitor does

`GEO Lab — Google Index Monitor` runs URL Inspection queries on the reviewed URL list. It records indexed-state results; this is not Google's live URL test and it does not request indexing. It also anonymously checks the public sitemap and uses the **readonly** Search Console Sitemaps GET method to inspect its reported state. It never submits the sitemap on a schedule and never calls Google's restricted Indexing API.

The workflow runs on Mondays at **10:17 Asia/Shanghai**, using UTC cron `17 2 * * 1`, and supports **Actions → GEO Lab — Google Index Monitor → Run workflow**. Scheduled jobs may start late; the schedule is not a punctual-delivery guarantee. The workflow must exist on the private repository's default branch.

## Installation boundary

Copy the allowlisted monitoring scripts and canonical manifest into the private repository, and copy `templates/google-index-monitor.yml` to `.github/workflows/google-index-monitor.yml` there. Also install `templates/google-index-monitor-watchdog.yml` as the private workflow of the same filename and include `scripts/index_monitor_watchdog.py`. Keep both templates inert in the public repository. Do not add the private `state/` directory to the public site.

The private repository needs `contents: write` for durable state commits and `issues: write` for the approved change notifications. There are no pull-request triggers and no execution of downloaded code. Only the canonical manifest is refreshed from this fixed public path:

`https://raw.githubusercontent.com/helen-bird/geo-platform-observation/main/monitoring/google-index/urls.json`

The runner rejects other storage repositories and checks GitHub's `private` flag before it accesses Google credentials or writes state. The manifest must stay inside the exact Search Console property, with unique HTTPS URLs and explicit monitoring flags.

## Authorization

Use the approved OAuth setup in [google-oauth-setup.md](google-oauth-setup.md). `GOOGLE_OAUTH_CREDENTIALS` in the private repository is an authorized-user credential with **exactly** `webmasters.readonly`. Its refresh token and client secret are never printed, passed in command-line arguments or committed. Access tokens are masked for Actions before use.

The sitemap submission helper is a separate, one-time write-scope operation. The scheduled workflow has no write-scope Google credential and no sitemap PUT call. No Search Console Owner grant is required by this implementation; the chosen Google identity still needs sufficient access to the existing property.

Missing or expired authorization is recorded as `AUTH_REQUIRED`; it does not create a false NOT_INDEXED result and does not count as a successful inspection run. Authorization, quota, transient server and response errors remain distinct in the private records. Failed runs retain their failure records and keep the last successful comparison snapshot.

## Durable history

`state/` contains immutable snapshots and the core's current status/history/summary files. After every run, including partial or authorization failures, the workflow commits only `state/` to the private repository's main branch. It rejects symlinks, unexpected state file types and credential-like values. Git history is the durable record; temporary workflow logs or expiring artifacts are not its only copy.

An empty `sitemap-submission.lock` created by the separate one-time submission helper is an ephemeral local lock, not history. It is excluded from staging; a nonempty or differently named unexpected file still fails validation. Keep that lock name in the private repository's `.gitignore` as well. Baseline XML sitemap evidence is allowed only when it parses as XML.

Important files include:

- `latest-index-status.json`: the latest actual attempt, including errors.
- `latest-successful-index-status.json`: only advanced by a complete successful query run.
- `index-history.csv` and `snapshots/`: the accumulated records and immutable run snapshots.
- `index-monitor-summary.md`: the current private readable summary.
- `inventory-used.json`: the exact manifest and source used by that run.
- `sitemap-status.json`: anonymous HTTP/XML observation plus the private readonly Google processing response, if available.
- `notification-ledger.json`: attempted, confirmed and uncertain alert delivery state.
- `authorization-status.json`: latest OAuth refresh result, updated on recovery as well as failure; property permissions remain a separate API check.
- `authorization-observations/`: immutable, credential-free authorization observations, including the prior failure when authorization recovers.

Index status and lifecycle descriptions come from actual API fields. Missing `lastCrawlTime` alone does not prove a URL was never crawled. A pending sitemap or absent download timestamp does not prove processing failed. Actual Google index improvements do not establish ChatGPT or Grok discovery or recommendation gains.

## Change-only private notifications

The runner creates a private GitHub Issue for recorded changes such as a first indexed page, deindexing, new blockers, lost authorization, repeated failures or a sitemap problem. It builds the Issue from controlled URL/status/time/source/action fields, not raw API response text or referring URLs.

Each event has a deterministic marker. Before a POST, the runner reconciles existing private Issues, including closed Issues, and writes delivery state. POST requests are never blindly retried. An uncertain POST is retained as uncertain until reconciliation or owner review; repeated unchanged incidents do not create another Issue. If reconciliation exceeds its bounded limit, delivery is blocked rather than risking a duplicate.

Normal unchanged runs save history without creating an Issue. Review a failed Actions run, its private summary and open monitoring Issues. If history persistence itself fails, Actions stays failed; fix repository permissions or the conflicting private branch rather than copying raw state into the public site.

The separate watchdog reads official Actions run history and can open a private Issue after two consecutive failures, even when checkout or state persistence failed. It has no Google credential and no state-write permission. It validates the exact private repository, trusted main branch and approved main workflow. A successful run resets the incident identity. To avoid duplicate delivery after an uncertain Issue POST without durable local state, only the earliest eligible second-failure callback may initiate that POST. Later callbacks reconcile existing Issues; absent or uncertain delivery requires owner review. GitHub/runner outages can also prevent notification, so a missing Issue is not proof that the workflow is healthy.

## Verification boundaries

Unit tests use fake HTTP responses and simulated notification delivery. A successful operational or missing-auth run is not a successful live URL Inspection run. Only a completed authorized run with real returned API data satisfies the live monitoring requirement. OAuth setup, a first successful inspection and a successful Google sitemap submission must each have their own dated evidence.

Official references: [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Google Sitemaps GET](https://developers.google.com/webmaster-tools/v1/sitemaps/get), and [Google URL Inspection](https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect). The checkout and setup-python actions are pinned to the official v4.2.2 and v5.6.0 commit SHAs rather than mutable tags.
