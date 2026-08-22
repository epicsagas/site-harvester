# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org).

## [0.4.0] — 2026-08-22

### Added

- Local reader site (Phase 6b): generic, dependency-free (stdlib + vanilla
  JS) blog-like reader for every harvest. The collector emits a normalized
  `data/site/` layer (`index.json` + per-article JSON with `body_html`);
  the `site/` template (serve.py, index.html, app.js, style.css) contains
  zero per-site code and reads only that schema.
- Reader features: search + series filter + infinite scroll feed, article
  pages with prev/next within a series, series/author/tag/keyword pages,
  year/month archive, in-body auto-links, dark theme, read tracking
  (localStorage). `/api/tags` builds tag→ids and keyword→ids indexes in one
  cached scan.
- `collect.py` local-site hooks (`norm_article`, `norm_series`,
  `norm_authors`) — opt-in per site; unfilled hooks skip the layer with an
  INFO log. `--rebuild-site` regenerates `data/site/` from raw `data/`
  without refetching; the layer also refreshes at the end of every sweep.
- `serve.py --root/--port`: localhost-only binding (127.0.0.1, enforced by
  a CI guardrail), path-traversal-guarded `/media/`, positional body-image
  rewrite onto each article's `assets_dir` img-* files.
- `data/site/` added to the gitignore template (derived, regenerable);
  CI parses serve.py as a template and asserts the localhost binding.

## [0.3.0] — 2026-08-22

### Added

- `dom` collection mode: Playwright-rendered list/detail pages for SSR or
  API-less sites, reusing login.py's persistent profile (session cookies
  carry auth); profile cookies exported into the image-download session.
- `rss` collection mode: feed as index (`feedparser`, lazy import), bodies
  from inline `content:encoded`/summary; per-item pacing skipped (no
  per-item fetch).
- `SITE["mode"]` entry-level dispatch (`api` default; old adapters without
  the key keep working); dom/rss store a normalized `{"url","meta","html"}`
  record so notes/rebuild paths are unchanged.
- SKILL.md: cheapest-source ladder, RSS discovery step, mode-selection
  table, dom login notes, new failure-mode rows.

### Fixed

- SKILL.md smoke command referenced an undefined `--no-commit` flag.

## [0.2.0] — 2026-08-21

### Added

- Phase 1 terms-of-service check + `tos_ok` gate before any collection
- HTTP 403/429 hard stop, public-repo commit refusal, CI guardrail lint

### Fixed

- Markdown converter v2: block elements nested in `<p>`/`<div>` (figure, table,
  lists) no longer flatten into one line; literal `*` footnote markers escaped;
  sentence-glue spacing (`증가한다.반면` → `증가한다. 반면`); interview Q&A
  runs split into blocks. Validated on ~1,800 real notes (long-line defects
  181 → 9, glue 30 → 0).

## [0.1.0] — 2026-08-20

Initial release.

### Added

- SKILL: 6-phase methodology (recon → scaffold → login → collect → schedule →
  derived layers), with a Phase 1 terms-of-service check before any collection.
- Templates: generic `login.py` — Playwright persistent-profile token harvest
  (headed, manual OAuth) plus headless refresh.
- Templates: generic `collect.py` — SITE adapter hooks, human pacing
  (30–120s default, >= 5s floor, smoke pace only for `--limit <= 10`),
  per-item resume, flock, collection window, 401 auto-refresh, HTTP 403/429
  hard stop, image download, HTML→Markdown, optional conventional commits.
- Guardrails: `tos_ok` gate in collect.py, public-repo commit refusal
  (`gh repo view` visibility check), vault gitignore that keeps tokens and
  browser profiles out of git while committing `data/` as the source of truth.
- CI: template syntax check, frontmatter/README checks, guardrail lint
  (rejects proxy/rotation/CAPTCHA/stealth patterns in templates).
- Multi-host manifests: Claude Code, Codex, agy, hermes (symlinked skill
  discovery).
- Korean README translation.
