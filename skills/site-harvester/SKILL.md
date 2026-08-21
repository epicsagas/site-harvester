---
name: site-harvester
description: >-
  Harvest content from authenticated websites into a local data vault. Use when
  the user wants to collect/scrape/archive all articles, posts, or documents
  from a site (including membership-gated content they subscribe to), keep
  collecting new items on a schedule, and structure the output as JSON + notes
  for later site generation. Triggers: "scrape site", "collect all articles",
  "archive membership content", "site collector", "수집", "아카이빙".
---

# site-harvester

Turn a login-walled content site into a local, resumable, scheduled data
pipeline. Battle-tested on React SPA membership sites at full-archive scale
(OAuth login, multi-day paced sweep, cron incremental).

## Principles

1. **API over browser.** SPAs get data from a JSON API. Find it, call it
   directly. Browsers are only for the one thing they're needed for: the OAuth
   login that mints your token.
2. **Human pacing.** Random 30–120s between item fetches, 1–2s between images.
   Spread big initial sweeps over days. Never hammer.
3. **Resumable by construction.** State file updated after every item; crash or
   Ctrl-C anywhere resumes cleanly. flock prevents overlapping runs.
4. **Raw JSON is the source of truth.** Store API responses verbatim
   (`data/articles/{id}.json`). Notes, sites, analytics are all derived —
   regenerable without refetching.
5. **Authorized access only.** The user must have legitimate access (their own
   subscription/account). Output stays local/private — paid content is
   copyrighted; no republication, no public repos, localhost-only sites.
   Personal, non-commercial use only; commercial reuse voids the
   personal-archival (private copy) defense.

## Intents → actions

| User intent | Action |
|-------------|--------|
| "Scrape/collect all content from X" | Full pipeline: recon → scaffold → login → sweep → schedule |
| "Login required" | Playwright persistent profile + token harvest (login.py) |
| "Keep collecting new stuff" | cron entry + window guard in collect.py |
| "Build a site from it later" | data/ layer (committed JSON); site reads it, never the network |

## Workflow

### Phase 1 — Recon (find the hidden API)

First, check the site's terms of service for an automation/scraping ban
(search the terms page for "bot", "scrape", "automated access"). If banned,
stop and surface it to the user before collecting anything — member accounts
are still bound by the terms.

```bash
# 1. Find the JS bundle
curl -s 'https://SITE/' | grep -oE '(static/js|/static)[^"]*\.js'

# 2. Download it, hunt for the API base and endpoints
curl -s 'https://SITE/static/js/main.HASH.js' -o /tmp/main.js
grep -oE '\bi="https?://[^"]*api[^"]*"' /tmp/main.js          # axios baseURL
grep -oE '(fetch|get|post)\(`?/[a-z][a-zA-Z0-9/${}._-]*' /tmp/main.js | sort -u

# 3. Find auth: token storage key + header shape
grep -oE 'localStorage\.setItem\("[^"]+"' /tmp/main.js        # token key
grep -oE 'Authorization=`[^`]*`' /tmp/main.js                 # header template
```

Verify endpoints with curl before writing any code:
- List endpoint unauthenticated → paginated? page size? total?
- Detail endpoint unauthenticated → is content field present or empty?
  Empty ⇒ token required per item.

If the bundle is unreadable, open the site in a browser instead and read the
Network tab: XHR requests to `api.*` or `/api/*` with JSON responses.

### Phase 2 — Scaffold

Copy `assets/templates/` from this skill into the target repo:

```
target-repo/
├── scraper/
│   ├── login.py      # generic; fill SITE config at top
│   ├── collect.py    # generic harness; fill SITE adapter (marked hooks)
│   └── .gitignore    # token.json, profile/, *.log, .lock
└── data/             # committed raw JSON (source of truth)
```

Fill the `SITE = {...}` block in each script (origin, api_base, endpoints,
token key, header). Set `tos_ok: True` in collect.py only after the Phase 1
terms check passes. Fill the parsing hooks in collect.py:
`iter_index_items`, `item_id`, `detail_content_html`, `detail_meta`,
`normalize_image_url`. Each is a lambda over the site's JSON shape — recon
output tells you the paths.

### Phase 3 — Login + token harvest

`login.py` opens a headed Chromium with a persistent profile at
`scraper/profile/`. The user completes OAuth manually (any provider). The
script polls localStorage for the token key and saves `scraper/token.json`.

Refresh strategy: most SPAs re-mint the token on page load using session
cookies. `login.py --refresh` loads the site headlessly in the same profile,
lets the app refresh, re-harvests. collect.py calls it automatically on any
401. If session cookies die too → manual `login.py` again.

### Phase 4 — Collect

```bash
python3 scraper/collect.py --limit 3 --no-commit   # smoke: 3 items, verify output
python3 scraper/collect.py                         # full sweep (background, nohup)
python3 scraper/collect.py --rebuild-notes         # regenerate derived notes from data/
```

Verify on the smoke run: notes render, images local, a known member-gated
item has non-empty body (proves auth works end to end).

### Phase 5 — Schedule

```bash
# twice-daily incremental; script self-disables after N days (window guard)
(crontab -l 2>/dev/null; echo "23 8,20 * * * cd REPO && python3 scraper/collect.py >> scraper/collect.log 2>&1") | crontab -
```

Auto-commit every ~50 items (Conventional Commits). Document the window end
date in the repo's PROGRESS; remove the cron line after.

### Phase 6 — Derived layers (optional)

- **Notes/KMS**: convert raw JSON → markdown notes with wikilinks
  (item ↔ series ↔ author). See worked example in the vault project.
- **Local site**: `data/` + `attachments/` is a self-contained static-site
  source. Body HTML is usually render-ready. Keep it localhost-only for paid
  content.

## Failure modes

| Symptom | Fix |
|---------|-----|
| Detail content empty despite 200 | Token not sent / wrong header shape — re-check Phase 1 auth grep |
| 401 mid-sweep | collect.py auto-refreshes once; if profile cookies died, rerun `login.py` |
| List API stops early | Some sites cap pages — look for offset/cursor params in recon |
| IP block / rate limit | Increase `--pace`, add jitter days, stop and reconsider |
| Site redesign | Endpoints moved → rerun Phase 1, update SITE dict; raw JSON history survives |
