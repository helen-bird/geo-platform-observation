# Website analytics

Website analytics and repository traffic are separate. The editorial website uses a Google Analytics 4 web data stream for page views and file-link clicks. GitHub's repository Traffic view covers a separate rolling 14-day window.

## Setup

Use the existing web stream for `https://helen-bird.github.io/geo-platform-observation/`. Keep Google signals and advertising personalization off. In Enhanced Measurement, keep page loads and file downloads enabled; leave history-only page changes, scrolls, outbound clicks, site search, forms and videos off. Use GA4's built-in `file_download`, which includes `.xlsx`, and do not add a second download listener. Write only the stream's public ID to `assets/analytics-config.json` as `{"measurement_id":"G-..."}`. Rebuild with `python3 scripts/build_site.py --preserve-evidence` and run `python3 scripts/check_publication.py` before deploying.

The tag is limited to editorial report pages, the Learning Hub and the measurement guide. It loads Google Analytics only after the visitor opts in and respects browser Global Privacy Control and Do Not Track settings. The site explains this on the [analytics privacy page](../privacy.html). It supplies only the page path, recognized campaign parameters and the referring origin to GA4's page-view configuration. Do not put a person's name, account ID or email address in an attribution tag.

Queue consent and the shared settings before the tag's initialization event, then apply those same settings to the stream configuration. This also covers a connected Google tag that initializes before processing the stream-specific configuration. Verify the actual outgoing URL and campaign fields; the presence of a script element or a configuration command alone is not proof that the settings reached an event.

## Links and reporting

For the Lab #07 post, set source to `x`, medium to `social`, campaign to `geo-lab-07`, and content to `original` using the corresponding UTM parameters. Use `reply` or `quote` for the corresponding placement. Preserve the canonical URL. Untagged traffic from `t.co` or `x.com` may still be observable as referral traffic if the browser preserves the source; it cannot reliably be assigned to a post. ChatGPT Search links may carry `utm_source=chatgpt.com`; the referring origin can also provide a signal. Report visits without either signal as direct or unknown.

For GEO Lab #08 distribution, the measurement guide accepts the registered Reddit comment links under `geo_lab_08_distribution`. Use a distinct `utm_content` for each link placement, and register new values in the loader before sharing. Use fixed, lowercase labels without personal data; pick a source, medium, campaign and unique placement ID. Existing X and ChatGPT link handling is unchanged. In GA4, use Session manual ad content for a placement breakdown, and include only the exact production campaign.

For verification, append `geo_test=1`. Registered distribution links use the separate `geo_lab_08_distribution_qa` campaign, retain their placement ID, enable debug mode and use separate cookies for each QA placement. Other QA URLs keep the `geo-qa` source. Allow analytics when prompted. Check event delivery in DebugView and final session attribution in processed reports; the two checks measure different things. `file_download` measures a link click, irrespective of whether the file finishes downloading or is used. Source labels describe observable traffic, not visitor identity or confirmed AI recommendations.
