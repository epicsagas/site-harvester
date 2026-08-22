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

1. **Cheapest source first.** JSON API → RSS feed → rendered DOM. Find the
   API and call it directly; fall back to the feed, then to dom mode. Browsers
   are only for what they're needed for: the OAuth login, and dom-mode pages.
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

Step 0 — check for an RSS/Atom feed before anything else:

```bash
curl -s 'https://SITE/' | grep -oE '<link[^>]+rel=.alternate.[^>]*>'
```

Pick the collection mode from what recon found:

| Recon finding | `SITE["mode"]` |
|---|---|
| JSON API found, token/Bearer auth | `api` |
| Feed with full `content:encoded` bodies | `rss` (no login needed) |
| Feed is summary-only or truncated to newest N | `api` or `dom` instead |
| No API, content rendered by JS / SSR pages | `dom` |
| Cookie-session site (no token in storage) | `dom` (login profile carries auth) |

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

Fill the `SITE = {...}` block in each script. Set `SITE["mode"]` from the
Phase 1 recon table. Set `tos_ok: True` in collect.py only after the Phase 1
terms check passes. Fill only the hook group for your mode:

| mode | SITE keys | hooks | extra dependency |
|------|-----------|-------|------------------|
| `api` | `api_base`, `index_path`, `detail_path`, `auth_header` | `iter_index_items`, `item_id`, `item_summary`, `detail_meta`, `detail_content_html`, `normalize_image_url` | — |
| `dom` | `index_path` (list URL), `dom_list_selector`, `dom_content_selector` | `dom_list_items`, `dom_index_item`, `dom_detail_extract`, `normalize_image_url` | `playwright install chromium` |
| `rss` | `feed_url` | `item_id`, `item_summary`, `rss_entry_meta`, `rss_content_html` | `pip install feedparser` |

Each hook is a small function over the site's data shape — recon output tells
you the paths/selectors. Unused hook groups stay as inert defaults.

### Phase 3 — Login + token harvest

`login.py` opens a headed Chromium with a persistent profile at
`scraper/profile/`. The user completes OAuth manually (any provider). The
script polls localStorage for the token key and saves `scraper/token.json`.

Refresh strategy: most SPAs re-mint the token on page load using session
cookies. `login.py --refresh` loads the site headlessly in the same profile,
lets the app refresh, re-harvests. collect.py calls it automatically on any
401. If session cookies die too → manual `login.py` again.

dom mode: run headed `login.py` once too — the profile's session cookies are
what carry auth (no token needed). "No token found" exiting 1 is expected on
cookie-session sites; the profile is what matters. Never run `login.py`
while a dom-mode collect is running — Chromium locks the profile directory
(flock only guards collect-vs-collect).

### Phase 4 — Collect

```bash
python3 scraper/collect.py --limit 3              # smoke: 3 items, verify output
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

**6a — Notes/KMS**: convert raw JSON → markdown notes with wikilinks
(item ↔ series ↔ author). See worked example in the vault project.

**6b — Local reader site**: serve the archive as a blog-like web app at
localhost. Zero per-site code: the collector emits a normalized
`data/site/` layer and the generic `site/` template reads only that.

1. Copy `assets/templates/site/` from this skill into the target repo root
   (`target-repo/site/`). Python stdlib + vanilla JS — nothing to install.
2. Fill the local-site hooks in `collect.py` (`norm_article`, `norm_series`,
   `norm_authors`) mapping the site's raw JSON to the normalized article
   shape documented on the hooks. Leave them unfilled to skip the site layer.
3. Emit the layer:

   ```bash
   python3 scraper/collect.py --rebuild-site   # regenerate from raw data/, no fetching
   ```

   The layer is also refreshed automatically at the end of every sweep.
   `data/site/` is gitignored — it is derived and regenerable.
4. Serve and verify in a browser:

   ```bash
   python3 site/serve.py                 # http://127.0.0.1:8765 (--port, --root)
   ```

Normalized shape (all fields optional except id/title; ids are strings):
articles `{id, title, date, body_html, series_id, vol, is_free, tags[],
keywords[], authors[{id,name}], likes, assets_dir}` — `assets_dir` is
repo-root-relative and auto-filled from `attachments/{id}/`; body `<img>`
tags are rewritten in document order onto its `img-*` files.
`index.json` holds `{site_title, articles[] (no bodies), series{id: {title,
description, reader_note, episodes[{id, vol, date, title, collected}]}},
authors{id: {name, title, bio, article_ids[]}}}`.

**Security invariant**: the reader binds 127.0.0.1 only. Paid content is
copyrighted — never expose it on a network interface, never make 0.0.0.0
the binding, never host the generated site publicly.

## Failure modes

| Symptom | Fix |
|---------|-----|
| Detail content empty despite 200 | Token not sent / wrong header shape — re-check Phase 1 auth grep |
| 401 mid-sweep | collect.py auto-refreshes once; if profile cookies died, rerun `login.py` |
| List API stops early | Some sites cap pages — look for offset/cursor params in recon |
| IP block / rate limit | Increase `--pace`, add jitter days, stop and reconsider |
| Site redesign | Endpoints moved → rerun Phase 1, update SITE dict; raw JSON history survives |
| dom: empty content on every item | Profile session died — rerun headed `login.py`, then collect again |
| rss: bodies empty or one-liners | Summary-only feed — switch mode to `api` or `dom` |
| rss: old items missing | Feed truncated to newest N — full archive needs `api`/`dom` |
| `feedparser` ImportError | `pip install feedparser` (only needed for mode `rss`) |
