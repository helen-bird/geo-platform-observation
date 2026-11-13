# Website analytics

Website analytics and repository traffic are separate. The editorial website can use a Google Analytics 4 web data stream for basic page views. GitHub's repository Traffic view covers a separate rolling 14-day window.

## Setup

Create the web stream for `https://helen-bird.github.io/geo-platform-observation/`. Keep optional enhanced measurement, Google signals and advertising personalization off. Write the stream's public ID to `assets/analytics-config.json` as `{"measurement_id":"G-..."}`. Do not add an account credential or API secret. Rebuild with `python3 scripts/build_site.py --preserve-evidence` and run `python3 scripts/check_publication.py` before deploying.

The tag is limited to editorial report pages, the Learning Hub and the measurement guide. It loads Google Analytics only after the visitor opts in and respects browser Global Privacy Control and Do Not Track settings. The site explains this on the [analytics privacy page](../privacy.html). It supplies only the page path, recognized campaign parameters and the referring origin to GA4's page-view configuration. Do not put a person's name, account ID or email address in an attribution tag.

## Links and reporting

For the Lab #07 post, set source to `x`, medium to `social`, campaign to `geo-lab-07`, and content to `original` using the corresponding UTM parameters. Use `reply` or `quote` for the corresponding placement. Preserve the canonical URL. Untagged traffic from `t.co` or `x.com` may still be observable as referral traffic if the browser preserves the source; it cannot reliably be assigned to a post. ChatGPT Search links may carry `utm_source=chatgpt.com`; the referring origin can also provide a signal. Report visits without either signal as direct or unknown.

For acceptance, append `geo_test=1` to a tagged URL. The tag reports a separate `geo-qa` source so that test visits are distinguishable. Allow analytics when prompted, then verify the hit in Analytics Realtime or DebugView. A browser that blocks Analytics does not represent a failed deployment. Source labels describe observable traffic, not visitor identity or confirmed AI recommendations.
