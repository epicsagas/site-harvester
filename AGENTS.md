# AGENTS.md — site-harvester

> Shared agent guide. Claude Code, Codex, agy, and hermes all load this file.

## Role

Authenticated website content harvester: recon an SPA's hidden JSON API, harvest the OAuth token via Playwright, then collect all content human-paced, resumable, cron-scheduled, into a committed `data/` layer. The authoritative workflow is `skills/site-harvester/SKILL.md`; host-discovery copies live under `.claude/skills/`, `.codex/skills/`, and `.hermes/skills/` and must mirror it.

## Host differences

- **All hosts** follow `skills/site-harvester/SKILL.md`. `commands/` is reserved
  for Claude Code slash commands but currently empty.

## Guardrails

- Authorized access only (user's own account). Output stays private; paid content never leaves localhost/private repos.
- During recon, check the site's terms for an automation/scraping ban; if banned, stop and surface it to the user.
- Personal, non-commercial use only. Collected content is never republished or publicly hosted.
- Community-site adapters: skip or mask other users' personal data (comments, profiles).
- Never remove or weaken the pacing defaults when adapting templates.
