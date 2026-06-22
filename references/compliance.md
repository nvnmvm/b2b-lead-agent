# Compliance

Process only public webpages and public business contacts. Do not bypass captchas, logins, paywalls, access restrictions, or rate limits. No proxy pools, forged fingerprints, LinkedIn scraping, Sales Navigator scraping, private profile scraping, SMTP probing, or auto connection requests.

Apollo-like behavior must stay source-compliant: discover companies through public search results, official company sites, public directories, or user-provided/imported lists; then enrich only from public business pages. LinkedIn may be used only as a public search-result clue or user-provided URL/list. Do not automate logged-in LinkedIn browsing, hidden profile collection, connection requests, or message sending.

On captcha/login/paywall/429/repeated access error: stop that source, record the error, continue unrelated companies.

Default email mode is `draft_only`; keep send adapters separate from search/scan/score/draft.
