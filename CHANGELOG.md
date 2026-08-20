# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org).

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
