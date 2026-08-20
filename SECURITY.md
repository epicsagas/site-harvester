# Security Policy

## Reporting a vulnerability

Use [GitHub security advisories](https://github.com/epicsagas/site-harvester/security/advisories/new)
("Report a vulnerability"). Do not open a public issue for security problems.

## Scope

This project ships agent instructions and Python templates — it runs on your
machine, against sites you choose, with your credentials.

In-scope:

- Template code vulnerabilities (path traversal in filename sanitization,
  injection via crafted API responses, unsafe deserialization)
- Anything in this repo's manifests that a host might auto-execute

Out-of-scope:

- The sites you point it at, or their APIs
- Token handling *by the target site* (we store the token the site itself
  gives your browser, in a local gitignored file, and never transmit it
  anywhere except back to that site)

## Hardening notes for users

- `scraper/token.json` and `scraper/profile/` are gitignored by the templates —
  keep them that way. A committed token is a committed account.
- Collected paid content stays copyrighted. Keep the data repo private and
  derived sites localhost-only.
