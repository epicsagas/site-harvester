**[English](README.md)** | [한국어](README.ko.md)

<img width="100%" src="assets/feature.png" alt="Site Harvester Features" />

<p align="center"><h1>site-harvester</h1></p>

<p align="center">
  <a href="https://github.com/epicsagas/site-harvester/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/epicsagas/site-harvester?style=for-the-badge&labelColor=0d1117&color=ffd700&logo=github&logoColor=white" /></a>
  <a href="https://github.com/epicsagas/site-harvester/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/epicsagas/site-harvester?style=for-the-badge&labelColor=0d1117&color=2ecc71&logo=github&logoColor=white" /></a>
  <a href="https://github.com/epicsagas/site-harvester/issues"><img alt="Issues" src="https://img.shields.io/github/issues/epicsagas/site-harvester?style=for-the-badge&labelColor=0d1117&color=ff6b6b&logo=github&logoColor=white" /></a>
  <a href="https://github.com/epicsagas/site-harvester/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/epicsagas/site-harvester?style=for-the-badge&labelColor=0d1117&color=58a6ff&logo=git&logoColor=white" /></a>
</p>

> Collect every article behind a login wall — politely, resumably, on schedule.

Many membership sites are SPAs (React and the like) backed by a JSON API. This plugin turns that into a local data pipeline: find the hidden API, harvest your own OAuth token once via a real browser login, then fetch everything through plain API calls — paced like a human reader, resumable after any crash, and scheduled to pick up new content while you sleep. Sites without an API work too: collect from an RSS feed (`rss` mode) or rendered pages via the login browser profile (`dom` mode).

Runs on Claude Code, Codex, Antigravity, and Hermes Agent. Built and battle-tested on large login-walled SPA sites — full-archive initial sweeps paced over days, OAuth login, scheduled incremental updates.

## Install

### Grok Build (xAI)

```bash
grok plugin install epicsagas/site-harvester --trust
```

Grok reads skills from `skills/` at the plugin root. No extra configuration needed.

```bash
# Claude Code
claude plugin marketplace add epicsagas/site-harvester
claude plugin install site-harvester@site-harvester

# Codex
codex plugin marketplace add epicsagas/site-harvester
codex plugin add site-harvester@site-harvester

# Antigravity
agy plugin install https://github.com/epicsagas/site-harvester

# Hermes Agent — the install scanner flags this plugin's AGENTS.md guide as a
# CRITICAL "persistence" finding (heuristic: any agent-config file reference),
# and dangerous verdicts cannot be --force'd. Temporarily disable install
# scanning, install, then re-enable:
hermes config set plugins.scan_on_install false
hermes plugins install https://github.com/epicsagas/site-harvester --enable
hermes config set plugins.scan_on_install true
hermes gateway restart
```

## Quick Start

Prerequisites: Python 3.10+, an agent host (Claude Code / Codex / Antigravity / Hermes Agent), and your own
account on the target site.

```
You: "Collect all articles from https://example.com — membership login
      required, I subscribe. Keep picking up new ones for two weeks."
```

That's it. The skill walks recon → scaffold → login → smoke test → scheduled
sweep. You log in once in the opened browser window; everything after that is
automatic.

## How It Works

| | Stage | What happens |
|--|-------|--------------|
| 🔍 | Recon | Check for an RSS feed, grep the site's JS bundle for its hidden API — endpoints, pagination, token storage — pick the mode |
| 🔑 | Token harvest | Headed browser login (you, once); the SPA's own token lands in a local profile |
| 📦 | Collect | Sweep at human pace — API calls, feed entries, or rendered pages; images downloaded |
| 🔁 | Resume | Per-item state file — crash, Ctrl-C, reboot: it picks up exactly where it stopped |
| ⏰ | Schedule | Cron picks up newly published items; a window guard self-disables the run |
| 🗄️ | Data layer | Raw API JSON is committed as the source of truth; notes and the local reader derive from it |

Site-specific code is confined to one `SITE` adapter block at the top of each template. Pick a mode — `api` (JSON endpoints), `rss` (feed as index), or `dom` (rendered pages via the login profile) — and fill that mode's small hook group from recon. Everything else (flock, 401 auto-refresh, HTML→Markdown, image handling, commits) is generic.

## Why site-harvester?

| | site-harvester | Hand-rolled Playwright | ArchiveBox | wget/httrack |
|-|----------------|------------------------|------------|--------------|
| Login-gated content | ✅ own-session token | ✅ but fragile | ⚠️ limited | ❌ |
| Speed | ✅ plain API calls | ⚠️ full page loads | ⚠️ heavy | ✅ |
| Resume mid-sweep | ✅ per-item state | 🔧 build it yourself | ✅ | ⚠️ |
| Scheduled increments | ✅ built-in | 🔧 build it yourself | ✅ | ❌ |
| Structured JSON output | ✅ raw API responses | 🔧 parse DOM | ⚠️ | ❌ |
| Full-page snapshots | ❌ | ⚠️ | ✅ | ✅ |

If you need page screenshots or WARCs, use ArchiveBox. Sites with a full-content RSS feed collect with zero login (`rss` mode); sites with no API at all use `dom` mode on the login browser profile. For everything else, this is less code you own.

## FAQ

<details>
<summary>The token expired mid-sweep</summary>

The collector detects 401s and refreshes headlessly from the browser profile.
If the session cookie itself died, run `python3 scraper/login.py` once more.
</details>

<details>
<summary>Can I read the archive as a website?</summary>

Yes — fill the optional `norm_*` hooks in `collect.py`, run
`collect.py --rebuild-site`, then `python3 site/serve.py`. A dependency-free
reader (search, series, authors, tags, archive, dark theme) serves the
normalized `data/site/` layer at http://127.0.0.1:8765. Localhost only:
paid content stays copyrighted, so the reader is never exposed to a network.
</details>

<details>
<summary>The site redesigned</summary>

Rerun the recon phase, update the `SITE` dict. Already-collected raw JSON survives untouched — notes rebuild without refetching (`--rebuild-notes`).
</details>

<details>
<summary>collect.py exits with "tos_ok is False"</summary>

New sites start with the terms check unset. Complete the Phase 1 terms-of-service
check, then set `"tos_ok": True` in the `SITE` block. Offline note rebuilds
(`--rebuild-notes`) don't need it.
</details>

<details>
<summary>The run stopped with HTTP 403/429</summary>

The site blocked or rate-limited you — the collector stops immediately instead
of pushing through. Wait, raise `--pace`, or reconsider; do not rotate IPs.
</details>

<details>
<summary>Commits are skipped: "origin is a PUBLIC repo"</summary>

Harvested content must never land in a public repo — the collector verifies
visibility with `gh` before committing and refuses when public. Make the vault
repo private (`gh repo edit --visibility private`) or remove the remote.
</details>

<details>
<summary>--pace is rejected below 5 seconds</summary>

Human pacing is a design invariant; the floor is not configurable. For a quick
smoke test use `--limit 3`, which paces at 3–8s.
</details>

<details>
<summary>Is this allowed?</summary>

The plugin only accesses content your own paid account can access, at human speed, for personal archival. It contains no CAPTCHA solving, anti-bot evasion, IP rotation, or paywall bypass — by design, and the templates make weakening the pacing a deliberate, visible act. Check the site's terms and your local law before collecting (rules differ by country), keep use personal and non-commercial, and never republish collected content: paid content stays copyrighted, sites stay localhost-only.
</details>

## For Site Owners

Your content may be harvested by subscribers using tools like this one. We maintain a
separate guide for site operators — defense options, and why a "moat over blocking"
strategy often wins: **[docs/SITE-OWNERS-GUIDE.md](docs/SITE-OWNERS-GUIDE.md)**
(Korean: [docs/SITE-OWNERS-GUIDE.ko.md](docs/SITE-OWNERS-GUIDE.ko.md)).

## Disclaimer

This plugin is provided for personal archival of content you are legitimately subscribed to. Modifying the code, bypassing its built-in guardrails (terms check, pacing, block handling, private-repo enforcement), using it in violation of a site's terms or applicable law, or republishing/redistributing harvested content — all such use is at your own risk, and full responsibility lies with the user. The authors accept no liability for misuse.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New-site adapter examples are
especially welcome.

## License

[MIT](LICENSE)
