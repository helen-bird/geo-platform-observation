# Multi-engine discoverability monitoring

GEO Lab keeps three independent evidence paths: Google indexed-version observations, Bing Webmaster discovery/crawl observations, and OpenAI search crawl eligibility. None establishes ChatGPT indexing or recommendations. No AI answer experiment is part of this monitoring work.

## Scope and private history

The original ten-page Google monitor and frozen baseline remain in place. Bing and OpenAI checks use every reviewed `indexing_desired: true` canonical in the existing public inventory: ten important report/navigation/appendix pages plus sixty individually addressable response archives. The two noindex OAuth support pages and verification/error files are excluded. A scope difference must not be interpreted as an engine-performance comparison.

All detailed records remain in the private `helen-bird/geo-index-monitor` repository, with Pages disabled. Google keeps its original root state files. Bing and OpenAI use `state/bing/` and `state/openai-search/`; each has an immutable first baseline, dated snapshots, CSV history, latest attempt and latest successful pointers. IndexNow uses a separate change ledger and receipts under `state/indexnow/`. The current Chinese operational report is `state/discoverability/report.zh-CN.md`, not a public research result. Each generated report and its safe summary have immutable timestamped copies under `state/discoverability/report-snapshots/`. Before replacing a pre-existing report, the runner also preserves its full text, including any manually appended progress notes not present in engine snapshots; these archival copies record preservation time and leave the original generation time unknown. Missing API authorization does not invalidate separately recorded official-UI Sitemap import evidence.

The existing workflow file remains `google-index-monitor.yml`, with its display name changed to **GEO Lab — Multi-Engine Discoverability Monitor**. It runs every Monday at **10:17 Asia/Shanghai** (`17 2 * * 1`) and supports manual dispatch. GitHub may delay scheduled starts. Google and the extension are separate steps; failure in one does not skip the other. The existing private-state persistence and independent watchdog remain active.

## Bing setup and limitations

Use the official Bing Webmaster Tools interface. Prefer **Import from Google Search Console**, select only the GEO URL-prefix property, and review Google's actual consent before granting Bing access. The official import can verify the selected branch and import its Sitemap. A new account or API-access agreement must be accepted by the owner.

For API automation, prefer a Bing OAuth client with the official `Webmaster.read` scope. The encrypted private Actions Secret is `BING_OAUTH_CREDENTIALS`, containing authorized-user fields `type`, `client_id`, `client_secret`, `refresh_token`, and `scopes`. Do not put these values in a repository, Issue, command argument or chat. The runtime refreshes against the official token endpoint, masks its ephemeral token, and restricts API calls to the fixed GEO property. Unexpected scope changes or refresh-token rotation require secure operator review.

The local [Bing authorization helper](../scripts/bing_webmaster_auth.py) accepts a private client JSON outside the public checkout, with file permissions 0600 and fields `client_id`, `client_secret`, and the exact registered `redirect_uri`. Its callback is restricted to `http://127.0.0.1:<registered-port>/oauth2callback`; it validates the callback Host and strong state before a single token exchange. Whether Bing accepts this loopback registration and returns state must be established by the actual owner-completed flow, not by synthetic tests. The helper fails closed rather than dropping those checks or assuming undocumented PKCE support.

Run from the public checkout, using private paths outside it:

```sh
python3 scripts/bing_webmaster_auth.py authorize --client-file /path/to/private/bing-client.json --url-file /path/to/private/bing-consent-url.txt --timeout 900
python3 scripts/bing_webmaster_auth.py check-monitor-credential
python3 scripts/bing_webmaster_auth.py configure-github-secret --repository helen-bird/geo-index-monitor
```

The first command writes the consent URL only to the private file; open it in the owner's browser and have the owner review the readonly grant. It never prints authorization codes or token values. A successful grant is stored under the separate native Keychain service `geo-lab-bing-webmaster`; Secret installation uses stdin and verifies the exact private repository has Pages disabled. Google credentials remain unchanged. Do not claim API readiness until an actual authorized query succeeds.

An API key is an alternative supported by Bing, but is account-wide and can cover all verified sites; it must not be represented as a readonly, site-only credential. Use it only after the owner explicitly approves this broader credential. Keep the value in native Keychain and the encrypted `BING_API_KEY` Secret of the private monitor repository; never place it in a repository variable, state, command argument or chat.

Authentication selection is explicit: the default `BING_AUTH_METHOD=oauth` uses only `BING_OAUTH_CREDENTIALS`. For an approved API key, set the private repository variable `BING_AUTH_METHOD` to `api_key` and install the `BING_API_KEY` Secret. The workflow does not infer a mode from available secrets or fall back between methods. A missing, invalid or rejected selected credential remains an authorization failure. The program always creates `BingClient(..., allow_write=False)`, permits only `GetUserSites`, `GetUrlInfo` and `GetFeeds`, fixes all site-specific requests to the GEO property, and removes other sites from stored `GetUserSites` responses. This is a program restriction, not a reduced capability of the API key itself. Google credentials and IndexNow's public verification key are unrelated and unchanged.

Actual registration attempts on November 6, 2026 rejected both `http://127.0.0.1:57787/oauth2callback` and `http://localhost:57787/oauth2callback`. Clearing a field error on edit was not registration success; no OAuth client or credential was obtained. The local helper remains a guarded, unverified alternative until a legitimate provider-supported callback is configured. Do not bypass Bing's redirect validation.

The official JSON REST methods used are `GetUserSites`, `GetUrlInfo`, and `GetFeeds`. The documented `GetUrlInfo` fields do not include an unambiguous index-membership verdict. `IsPage`, HTTP 200, document size and crawl times are not treated as proof of indexing. Thus even successful API observations retain `index_status: UNKNOWN`, alongside actual discovery/crawl fields. If membership is needed, record the official Bing **URL Inspection → Index** observation separately; the Live URL test is a different operation.

Requests are serial, with a default five-second pause between actual Bing API requests; an explicit client interval may only increase within 5–60 seconds. Official provider codes `ThrottleUser` (4) and `ThrottleHost` (5) are quota failures even when returned with HTTP 400 or 200. HTTP 429 also stops the batch immediately. Codes 3 (invalid API key), 6 (blocked user), 13 (not allowed) and 14 (not authorized), or HTTP 401/403, stop further requests as authentication/permission failures. The first blocking response is retained after credential sanitization. All remaining planned URL slots stay present with `NOT_QUERIED_QUOTA_BLOCKED` or `NOT_QUERIED_AUTH_BLOCKED`, zero attempts and unknown index membership; no later URL or feed request reaches Bing after the block. Any supplied `Retry-After` is recorded; its absence does not establish a cooldown or recovery time. There is no immediate retry of quota/provider faults, credential/environment switch, or claim of a complete run. UnknownError (2) stays an ordinary failed request, without a generic immediate retry. Existing bounded network/5xx retries remain serial and paced. A 5xx `Retry-After` greater than the bounded 30-second local wait, or an unsupported date-format wait, is preserved without truncation or guessed expiry; that response ends the batch, and subsequent slots use `NOT_QUERIED_RETRY_DEFERRED` so another URL cannot send an early request to the same host.

The same canonical Sitemap URL is used by both engines. Google's successful one-time submission is never repeated by this extension. Bing's `GetFeeds` records registration, processing and last crawl separately. `submit_sitemap_once` checks whether the exact feed was already imported; only a missing feed plus a separately approved manage grant can cause one `SubmitFeed` POST. A persisted accepted or uncertain attempt prevents blind repetition. Missing authorization remains `AUTH_REQUIRED`, with index membership UNKNOWN.

Each newly collected Bing snapshot records its actual `execution_environment`: the scheduled runner uses `github_actions`; a local invocation of the orchestrator uses `local_process`. An explicitly documented owner-Mac one-off collection can use `owner_macOS_oneoff`. Reports use the field from the source snapshot, never the environment that later renders the report; older snapshots without the field remain `UNKNOWN`. A complete local one-off baseline does not establish weekly GitHub Actions success, and any partial GitHub run remains a separate immutable record rather than being reclassified from local results.

## IndexNow under GitHub Pages

The ownership file is in the existing project directory, with its exact location recorded in [the public configuration](../monitoring/discoverability/indexnow.json). The file contains a public IndexNow verification token. This token is intentionally public and is entirely separate from private Bing OAuth or API credentials.

Every notification specifies `host: helen-bird.github.io` and explicit `keyLocation` under `/geo-platform-observation/`. That location limits the accepted URL prefix to this project subtree. No host-root file, new domain, third-party indexing service or false schema is used.

Initialization establishes current deployed content hashes and sends no old URLs. Subsequent actual additions and meaningful content changes require a deployed, canonical, indexable HTTP-200 page. A removal from the monitoring inventory is insufficient for deletion: the old URL must actually return 404 or 410. Pure stylesheet/class changes are excluded by semantic hashes; actual response hashes are retained as evidence. No report content is changed merely to exercise the endpoint.

Before any IndexNow POST, the private change ledger is committed and pushed. If that durable write fails, no POST occurs. A single POST follows; HTTP 200 means received and 202 means ownership validation pending. Network/5xx uncertainty remains in the ledger and is not automatically retried. A successful receipt does not prove crawl or indexing. Unresolved deliveries remain visible even on subsequent unchanged runs.

## OpenAI eligibility evidence

Effective robots policy comes from `https://helen-bird.github.io/robots.txt`, not the project-path `robots.txt`. The monitor checks the host-root response, applicable `OAI-SearchBot` rules, page robots/noindex directives, response headers and public HTTP access. Root robots 4xx means unavailable under RFC 9309; unreachable/5xx remains UNKNOWN with a conservative disallow assumption.

The second request declares the official OAI-SearchBot user-agent and is explicitly a simulation from our runner. It is not a real OpenAI crawler and cannot prove IP-based access. Genuine visits require trusted server/CDN logs and source-IP checks against OpenAI's published ranges. GitHub Pages does not provide such logs to this workflow; real crawl time and OpenAI index status remain UNKNOWN. `GPTBot` and `ChatGPT-User` are separate agents.

## Official references

- [Bing GSC import and verification](https://www.bing.com/webmasters/help/add-and-verify-site-12184f8b)
- [Bing OAuth](https://learn.microsoft.com/en-us/bingwebmaster/oauth2)
- [Bing API reference](https://learn.microsoft.com/en-us/bingwebmaster/)
- [Bing URL Inspection](https://www.bing.com/webmasters/help/URL-Inspection-55a30305)
- [IndexNow protocol](https://www.indexnow.org/documentation) and [FAQ](https://www.indexnow.org/faq)
- [OpenAI crawler documentation](https://developers.openai.com/api/docs/bots) and [published SearchBot IP ranges](https://openai.com/searchbot.json)
- [RFC 9309 robots policy](https://www.rfc-editor.org/rfc/rfc9309.html)

## Delayed Bing-only recheck and completion notice

The private `bing-index-recheck.yml` workflow is manual-only: it has no additional recurring schedule. It runs the same reviewed canonical inventory through `--bing-only --bing-request-interval 10`, with ten-second serial spacing and the existing first-throttle stop. It records all planned positions, preserves failures and unqueried UNKNOWN slots, and persists state even if the batch fails. Only Bing is queried; the report explicitly carries forward prior Google, OpenAI and IndexNow observations with their original timestamps. It does not submit URLs, repeat Sitemaps, rotate credentials or change the existing weekly workflow's five-second default.

A separate `bing-index-completion.yml` callback considers only officially completed, successful private main/recheck workflow runs. It checks the official workflow and run metadata and binds a committed immutable full Bing snapshot to that run ID and attempt. Every current planned URL must have a successful actual query, and site access and the Sitemap read must succeed. A stable `BING_FIRST_COMPLETE_BATCH` notification then uses the existing private Issue reconciliation ledger, mentions the approved owner `@helen-bird`, and is not repeated on later successes or failure/recovery cycles. The callback does not hold Bing credentials or query any search engine. Its notice means the complete query batch passed; it does not establish indexing or ChatGPT discoverability. If GitHub delivery is uncertain, normal reconciliation applies rather than blind repeated sends.

## IndexNow-only real-change acceptance

The private manual-only `indexnow-change-notify.yml` workflow runs `--indexnow-only`. It loads the current reviewed public manifest, verifies deployed canonical/indexable HTML, compares actual content with the private ledger, and commits and pushes intent before one IndexNow POST. It holds no Bing or Google credentials, does not run OpenAI eligibility probes, and carries forward other engines' observations with their original dates. No actual change means no POST. HTTP 202 remains key validation pending; neither 200 nor 202 establishes crawl or index membership. Failed or uncertain deliveries remain visible and are not replayed automatically.

The ledger freezes initial-baseline manifest membership separately from later seen URLs. A genuinely new URL whose first deployment verification failed is still eligible as ADDED once its real page is available. Legacy initial membership is retained conservatively, so old failed baseline observations do not become retroactive new-content notifications.
