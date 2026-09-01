#!/usr/bin/env python3
"""Generic OAuth login + token harvest for SPA sites.

Fills scraper/token.json with the Bearer token the SPA stores client-side.
Requires: pip install playwright && playwright install chromium

Usage:
  python3 login.py            # headed — user completes OAuth manually
  python3 login.py --refresh  # headless — reload site so the app re-mints the
                              # token from the session cookie in the profile
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# ---- SITE config (fill from Phase 1 recon) -------------------------------
SITE = {
    "origin": "https://example.com",
    "login_path": "/login",          # where the user logs in
    "token_ls_key": "authToken",     # localStorage key the SPA reads on every request
}
# ---------------------------------------------------------------------------

SCRAPER_DIR = Path(__file__).resolve().parent
PROFILE_DIR = SCRAPER_DIR / "profile"   # persistent: keeps OAuth session cookies
TOKEN_FILE = SCRAPER_DIR / "token.json"


def harvest_token(page, timeout_s: int) -> str | None:
    js = (
        "() => localStorage.getItem(KEY) || sessionStorage.getItem(KEY)"
    ).replace("KEY", json.dumps(SITE["token_ls_key"]))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        tok = page.evaluate(js)
        if tok:
            return tok
        page.wait_for_timeout(1000)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    PROFILE_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=args.refresh,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SITE["origin"] + (SITE["login_path"] if not args.refresh else ""))
        if args.refresh:
            page.wait_for_timeout(5000)  # let the app call its token-refresh endpoint
            tok = harvest_token(page, timeout_s=15)
        else:
            print("Browser open. Complete login...")
            tok = harvest_token(page, timeout_s=args.timeout)
        ctx.close()

    if not tok:
        print("No token found. Login incomplete or session expired.")
        return 1
    TOKEN_FILE.write_text(json.dumps({"token": tok}, ensure_ascii=False, indent=2))
    print(f"Token saved to {TOKEN_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
