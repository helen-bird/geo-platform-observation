# Google Search Console OAuth setup

These steps are needed only when no existing, authorized Search Console OAuth grant is available. Do not send a password, OAuth refresh token, downloaded client secret JSON or service-account private key through chat. Website ownership verification and API OAuth authorization are different operations.

## Minimal owner actions

1. In a Google Cloud project you control, enable **Google Search Console API**. Configure the OAuth consent screen for your own use, then create an OAuth client of type **Desktop app**. Do not enable the Google Indexing API for ordinary GEO reports.
2. Download the desktop-client JSON to a private local directory outside the public repository. Do not add it to Git. The script accepts an explicit `--client-file` path and does not print the file contents.
3. From the repository root, run the readonly authorization command below. Open the displayed official Google consent URL yourself. Complete Google sign-in and consent in your own browser. The temporary callback listens only on `127.0.0.1`; it validates state and uses PKCE. Do not paste the callback URL or its code into chat.

```sh
python3 scripts/google_search_console_auth.py authorize --mode monitor --client-file /path/to/private/desktop-client.json
```

The requested scope is exactly `https://www.googleapis.com/auth/webmasters.readonly`. The grant is stored in macOS Keychain service `geo-lab-search-console`, account `monitor-readonly`. This role queries indexed-state data; it does not execute Search Console's Live Test or request indexing. The helper does not require or grant a new Search Console Owner role: use the property permission the existing authorized account already has.

4. Once the private monitoring repository exists, explicitly install the readonly credential as an encrypted GitHub Actions repository Secret:

```sh
python3 scripts/google_search_console_auth.py configure-github-secret --repository OWNER/PRIVATE-MONITOR-REPOSITORY
```

The helper checks that the destination is private, validates the exact readonly scope, and supplies `GOOGLE_OAUTH_CREDENTIALS` through the `gh` process's stdin. Secret values never appear in shell arguments or console output. No token or raw Search Console response belongs in the public site repository.

## One-time Sitemap authorization

First save the immutable indexed-state baseline. The one-time write grant is separate from the readonly monitor grant:

```sh
python3 scripts/google_search_console_auth.py authorize --mode sitemap --client-file /path/to/private/desktop-client.json
python3 scripts/google_sitemap_submit.py --action submit --baseline /path/to/private/baseline-index-status.json --state-dir /path/to/private/monitor-state
```

This consent requests exactly `https://www.googleapis.com/auth/webmasters`. It is stored temporarily under Keychain account `sitemap-once`, never sent to Actions. After a confirmed successful submission the CLI removes that local one-time credential. It does **not** revoke the remote Google grant: Google's revocation can invalidate other tokens associated with the same project. If you choose to revoke it in Google later, consider the effect on your monitor and use a separately managed Cloud project when isolation is required.

The submission command requires a dated baseline for the exact property. It checks the deployed Sitemap and existing Google entry, then performs one explicitly authorized Sitemaps API `PUT` for this setup, even if the URL was registered earlier. Existing registration alone does not prove submission of the updated feed. Our successful private ledger prevents another submission. A private ledger prevents daily resubmission. Uncertain delivery is preserved and reconciled with a later `GET`; it is not blindly retried. An accepted submission is distinct from Google reading or processing the Sitemap.

Later processing status is readonly:

```sh
python3 scripts/google_sitemap_submit.py --action status --baseline /path/to/private/baseline-index-status.json --state-dir /path/to/private/monitor-state
```

If API authorization cannot be completed, select the verified URL-prefix property in Search Console, open **Sitemaps**, enter `sitemap.xml`, and submit once. Record the actual submission time and the interface result. For ordinary report pages, **URL inspection → Request indexing** remains a separate manual operation; neither this helper nor the URL Inspection API performs it.

## Long-term authorization limits

An external Google OAuth app left in **Testing** normally receives refresh tokens valid for seven days when requesting these scopes. That is unsuitable as an unattended weekly arrangement without further owner setup. Review the app's publishing status and Google's policies before treating monitoring as durable; a suitable Production configuration may avoid this particular testing limit, but refresh tokens can still expire or be revoked. The monitor must alert on authorization failure. Do not rotate accounts or create extra grants to bypass limits.

The local desktop flow opens no embedded browser and bypasses no CAPTCHA, login protection or consent. It uses a temporary loopback callback; Google's retired out-of-band code-copy flow is not used. Client secrets and tokens are handled only by the local program, native Keychain and the explicitly selected private repository Secret.

## Official references

- [Google desktop OAuth and PKCE](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Refresh-token expiration and Testing status](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Search Console Sitemaps submit](https://developers.google.com/webmaster-tools/v1/sitemaps/submit)
- [Search Console Sitemaps get](https://developers.google.com/webmaster-tools/v1/sitemaps/get)

Checked November 4, 2026. Setup and synthetic tests are not evidence of a successful live Google authorization or Sitemap submission; retain actual API receipts separately in private storage.
