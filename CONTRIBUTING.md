# Contributing to site-harvester

Thanks for your interest. This plugin is intentionally small — a methodology
skill plus two generic templates — so contribution guidelines are short too.

## What's welcome

- **Site adapter examples** — the highest-value contribution. If you ran the
  pipeline on a new site, a PR adding your filled-in `SITE` block (with the
  site's name and nothing else — no scraped content, no tokens) helps the
  next person enormously.
- **Converter improvements** — the HTML→Markdown walker handles a finite tag
  set; new tags encountered in the wild are legitimate issues/PRs.
- **Failure-mode entries** — new rows for the SKILL.md failure table, ideally
  with the symptom you actually hit.

## What's not welcome

- Anything that weakens the pacing defaults or adds anti-bot evasion, CAPTCHA
  solving, IP rotation, or paywall circumvention. These will be closed without
  discussion.
- Scraped content, credentials, or tokens in any form. Use synthetic samples in
  issues/PRs — especially other users' personal data (comments, profiles).

## Setup

```bash
git clone https://github.com/epicsagas/site-harvester
cd site-harvester
python3 -c "import ast; [ast.parse(open(f).read()) for f in ['skills/site-harvester/assets/templates/collect.py','skills/site-harvester/assets/templates/login.py']]"
```

`skills/site-harvester/SKILL.md` is the source of truth. Host-discovery
copies under `.claude/`, `.codex/`, `.hermes/` are symlinks — don't edit them.
After changes run `forge doctor` (from
[plugin-forge](https://github.com/epicsagas/plugin-forge)) to verify sync.

## Commits

Conventional Commits (`feat:`, `fix:`, `docs:`, …). Keep diffs small and
scoped; unrelated formatting churn gets asked to revert.
