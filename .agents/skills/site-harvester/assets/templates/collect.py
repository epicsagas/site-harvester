#!/usr/bin/env python3
"""Generic content collector harness: API sweep + token auth + human pacing.

Resumable (state file updated per item), flock-guarded, window-guarded.
Raw API JSON is the source of truth under data/; markdown notes are derived.

Usage:
  python3 collect.py [--limit N] [--pace MIN MAX] [--rebuild-notes]
                     [--rebuild-site] [--commit]
"""
import argparse
import fcntl
import json
import logging
import random
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# ===========================================================================
# SITE adapter — fill every hook from Phase 1 recon. This is the ONLY
# site-specific section; everything below the marker is generic harness.
# ===========================================================================
SITE = {
    "mode": "api",   # "api" = JSON API | "dom" = rendered pages | "rss" = feed index
    "origin": "https://example.com",
    "window_days": 14,
    "collection_name": "site",   # used in commits/notes
    "site_title": "",            # local-reader masthead (default: collection_name)
    "tos_ok": False,             # flip to True only after the Phase 1 terms check

    # ---- api mode ----
    "api_base": "https://example.com/api",
    # list endpoint (api) / list page URL (dom), paginated by ?page=N (1-based);
    # must stop at empty page
    "index_path": "/items?page={page}",
    # detail endpoint per item (api only)
    "detail_path": "/items/{id}",
    # auth header built from token; None if the site uses cookies instead
    "auth_header": "Bearer {token}",

    # ---- dom mode ----
    "dom_list_selector": ".item-card",           # one entry card on a list page
    "dom_content_selector": "article .content",  # main content on a detail page

    # ---- rss mode ----
    "feed_url": "https://example.com/feed.xml",
}

def iter_index_items(page_json) -> list:
    """Return the list of item entries from one index page response."""
    return page_json.get("items", [])

def item_id(entry) -> int | str:
    """Unique id of one index entry (api: JSON item; rss: feed entry)."""
    return entry["id"]

def item_summary(entry) -> dict:
    """Small dict stored in data/index.json (title, date, ...)."""
    return {"id": entry["id"], "title": entry.get("title", ""),
            "opened_at": entry.get("created_at")}

def detail_meta(detail_json) -> dict:
    """Extract display metadata from a detail response."""
    item = detail_json.get("item", detail_json)
    return {"id": item.get("id"), "title": item.get("title", ""),
            "published": (item.get("published_at") or "")[:10],
            "url": SITE["origin"] + "/" + str(item.get("id"))}

def detail_content_html(detail_json) -> str:
    """Body HTML from a detail response (empty string if gated/auth failed)."""
    return (detail_json.get("item", detail_json).get("content") or "")

def normalize_image_url(src: str) -> str | None:
    """Resolve an <img src> found in body HTML to an absolute URL (None = skip)."""
    src = (src or "").strip()
    if not src or src.startswith("data:"):
        return None
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return SITE["origin"] + src
    return src or None

# ---- dom mode hooks (fill only when mode="dom") ----------------------------

def dom_list_items(soup) -> list:
    """Entry cards from one rendered list page."""
    return soup.select(SITE["dom_list_selector"])

def dom_index_item(el) -> dict:
    """{"id", "url"} from one entry card; doubles as the index.json summary."""
    a = el.select_one("a") or el
    href = a.get("href", "")
    return {"id": href.rstrip("/").split("/")[-1], "url": SITE["origin"] + href}

def dom_detail_extract(soup, item: dict) -> dict:
    """Stored record from one rendered detail page. html empty = auth failed."""
    node = soup.select_one(SITE["dom_content_selector"])
    return {"url": item["url"],
            "meta": {"id": item["id"],
                     "title": (soup.h1.get_text(strip=True) if soup.h1 else ""),
                     "published": "", "url": item["url"]},
            "html": str(node) if node else ""}

# ---- rss mode hooks (fill only when mode="rss"; defaults fit most feeds) ---

def rss_entry_meta(entry) -> dict:
    """Display metadata from one feed entry (id slugified: feed ids are URLs)."""
    slug = re.sub(r"[^0-9a-zA-Z._-]+", "-", str(item_id(entry))).strip("-")
    tm = entry.get("published_parsed")
    return {"id": slug or str(item_id(entry)), "title": entry.get("title", ""),
            "published": time.strftime("%Y-%m-%d", tm) if tm else "",
            "url": entry.get("link", "")}

def rss_content_html(entry) -> str:
    """Body HTML from one feed entry (content:encoded / Atom content, else summary)."""
    for c in entry.get("content", []):
        if c.get("value"):
            return c["value"]
    return entry.get("summary") or entry.get("description") or ""

# ---- local-site hooks (optional; fill to emit the data/site/ reader layer) --

def norm_article(detail_json) -> dict | None:
    """One normalized article for the local reader (SKILL.md Phase 6b), or
    None to skip the site layer entirely. Required: id, title, body_html.
    Optional: date (ISO 8601), series_id, vol, is_free, tags [str],
    keywords [str], authors [{id, name}], likes. assets_dir is filled in by
    the harness. Body <img> tags are matched positionally, in document order,
    to the img-* files the harness downloads into assets_dir."""
    return None

def norm_series(detail_json) -> dict | None:
    """Series metadata, merged across its articles: {id, title, description?,
    reader_note?, episodes?: [{id, vol?, date?, title?}]}. Episodes the site
    lists but that are not collected yet may be included — `collected` flags
    are computed by the harness."""
    return None

def norm_authors(detail_json) -> list[dict]:
    """[{id, name, title?, bio?}] — merged across articles."""
    return []
# ============================== end SITE adapter ===========================

SCRAPER_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRAPER_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "articles"
NOTES_DIR = PROJECT_DIR / "notes"
ATTACH_DIR = PROJECT_DIR / "attachments"
SITE_DIR = DATA_DIR / "site"        # derived reader layer (gitignored, regenerable)
SITE_ARTICLES = SITE_DIR / "articles"
STATE_FILE = SCRAPER_DIR / "state.json"
INDEX_FILE = DATA_DIR / "index.json"
TOKEN_FILE = SCRAPER_DIR / "token.json"
PROFILE_DIR = SCRAPER_DIR / "profile"  # login.py's persistent browser profile
LOCK_FILE = SCRAPER_DIR / ".lock"

RENDERER = None     # DomRenderer instance, only when mode="dom"
PENDING: dict = {}  # id -> dom item dict | rss feed entry (set by dom/rss sweeps)

log = logging.getLogger("harvester")


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def sanitize_filename(s: str, cap: int = 80) -> str:
    s = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", s or "")
    return re.sub(r"\s+", " ", s).strip().strip(".")[:cap].rstrip()


USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Client:
    def __init__(self, token: str | None):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.token = token

    def get(self, path: str):
        headers = {}
        if self.token and SITE["auth_header"]:
            headers["Authorization"] = SITE["auth_header"].format(token=self.token)
        r = self.s.get(SITE["api_base"] + path, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()


class DomRenderer:
    """One headless Chromium for the whole run, sharing login.py's profile
    (session cookies carry auth; no token needed)."""

    def start(self):
        from playwright.sync_api import sync_playwright  # lazy: only mode="dom"
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=True, viewport={"width": 1280, "height": 900})
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def html(self, url: str) -> str:
        self._page.goto(url, timeout=60000, wait_until="networkidle")
        return self._page.content()

    def cookie_session(self) -> requests.Session:
        """Export profile cookies so image downloads pass the same auth."""
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        for c in self._ctx.cookies():
            s.cookies.set(c["name"], c["value"],
                          domain=c.get("domain", "").lstrip("."), path=c.get("path", "/"))
        return s

    def close(self):
        if getattr(self, "_ctx", None):
            self._ctx.close()
        if getattr(self, "_pw", None):
            self._pw.stop()


def refresh_token() -> bool:
    r = subprocess.run([sys.executable, str(SCRAPER_DIR / "login.py"), "--refresh"],
                       capture_output=True, text=True, timeout=180)
    return r.returncode == 0


def load_client(require_token: bool = True) -> Client:
    tok = load_json(TOKEN_FILE, {}).get("token")
    if not tok and require_token:
        log.error("no token — run: python3 scraper/login.py")
        sys.exit(1)
    return Client(tok)


# ---------------------------------------------------------------- index


def sweep_index(client: Client) -> list[dict]:
    mode = SITE.get("mode", "api")
    if mode == "dom":
        return sweep_index_dom()
    if mode == "rss":
        return sweep_index_rss()
    entries, page = [], 1
    while True:
        d = client.get(SITE["index_path"].format(page=page))
        items = iter_index_items(d)
        if not items:
            break
        for it in items:
            entries.append(item_summary(it))
        log.info("index page %d: %d items (total %d)", page, len(items), len(entries))
        page += 1
        time.sleep(random.uniform(1.0, 2.0))
    DATA_DIR.mkdir(exist_ok=True)
    save_json(INDEX_FILE, {"items": entries, "swept_at": datetime.now().isoformat()})
    return entries


def sweep_index_dom() -> list[dict]:
    entries, page = [], 1
    while True:
        soup = BeautifulSoup(
            RENDERER.html(SITE["origin"] + SITE["index_path"].format(page=page)),
            "html.parser")
        els = dom_list_items(soup)
        if not els:
            break
        for el in els:
            item = dom_index_item(el)
            PENDING[item["id"]] = item
            entries.append(item)
        log.info("index page %d: %d items (total %d)", page, len(els), len(entries))
        page += 1
        time.sleep(random.uniform(1.0, 2.0))
    DATA_DIR.mkdir(exist_ok=True)
    save_json(INDEX_FILE, {"items": entries, "swept_at": datetime.now().isoformat()})
    return entries


def sweep_index_rss() -> list[dict]:
    try:
        import feedparser  # lazy: only mode="rss"
    except ImportError:
        log.error('mode="rss" needs feedparser — pip install feedparser')
        sys.exit(1)
    feed = feedparser.parse(SITE["feed_url"])
    if feed.bozo and not feed.entries:
        log.error("feed unreadable (%s) — check feed_url", feed.bozo_exception)
        sys.exit(1)
    entries = []
    for e in feed.entries:
        m = rss_entry_meta(e)
        PENDING[m["id"]] = e
        entries.append(m)  # rss_entry_meta output doubles as the index.json summary
    DATA_DIR.mkdir(exist_ok=True)
    save_json(INDEX_FILE, {"items": entries, "swept_at": datetime.now().isoformat()})
    log.info("feed: %d entries", len(entries))
    return entries


def fetch_detail(aid, client: Client) -> dict:
    """One item's stored record, fetched per mode."""
    mode = SITE.get("mode", "api")
    if mode == "rss":
        e = PENDING[aid]
        return {"meta": rss_entry_meta(e), "html": rss_content_html(e)}
    if mode == "dom":
        rec = dom_detail_extract(
            BeautifulSoup(RENDERER.html(PENDING[aid]["url"]), "html.parser"),
            PENDING[aid])
        if not rec["html"].strip():
            log.error("item %s: empty content — profile session likely dead; "
                      "rerun login.py", aid)
            sys.exit(1)
        return rec
    return client.get(SITE["detail_path"].format(id=aid))


# ---------------------------------------------------------------- images


def download_images(urls: list[str], dest_dir: Path, session: requests.Session,
                    prefix: str = "img") -> dict[str, str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping, n = {}, 0
    for url in urls:
        if url in mapping:
            continue
        ext = Path(url.split("?")[0]).suffix.lower() or ".jpg"
        n += 1
        fpath = dest_dir / f"{prefix}-{n:03d}{ext or '.jpg'}"
        if not fpath.exists():
            for attempt in range(3):
                try:
                    r = session.get(url, timeout=60)
                    r.raise_for_status()
                    fpath.write_bytes(r.content)
                    break
                except requests.RequestException as e:
                    if attempt == 2:
                        log.warning("image failed %s: %s", url, e)
                        fpath = None
                        break
                    time.sleep(3 * (attempt + 1))
            time.sleep(random.uniform(1.0, 2.0))
        if fpath:
            mapping[url] = str(fpath.relative_to(PROJECT_DIR))
    return mapping


# ---------------------------------------------------------------- html -> md


BLOCK_TAGS = {
    "p", "div", "figure", "figcaption", "table", "ul", "ol", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "section", "article", "aside",
    "small", "pre",
}


def html_to_md(html: str, img_map: dict[str, str]) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup.find_all(["script", "style"]):
        t.decompose()

    def inline(node) -> str:
        if isinstance(node, NavigableString):
            return str(node).replace("*", "\\*")
        if not isinstance(node, Tag):
            return ""
        name = node.name
        if name in ("b", "strong"):
            inner = "".join(inline(c) for c in node.children).strip()
            return f"**{inner}**" if inner else ""
        if name in ("i", "em"):
            inner = "".join(inline(c) for c in node.children).strip()
            return f"*{inner}*" if inner else ""
        if name == "br":
            return "  \n"
        if name == "a":
            inner = "".join(inline(c) for c in node.children).strip()
            href = node.get("href") or ""
            return f"[{inner}]({href})" if inner and href else inner
        if name == "img":
            src = normalize_image_url(node.get("src") or node.get("data-src"))
            if not src:
                return ""
            local = img_map.get(src)
            return f"\n\n![[{local}]]\n\n" if local else ""
        return "".join(inline(c) for c in node.children)

    def para_flush(buf: list, out: list) -> None:
        txt = "".join(buf)
        txt = re.sub(r"[ \t]+\n", "\n", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
        if txt:
            out.append(txt + "\n\n")

    def block(node, out: list) -> None:
        if not isinstance(node, Tag):
            txt = str(node).strip()
            if txt:
                out.append(txt)
            return
        name = node.name
        if name == "figure":
            for c in node.children:
                if isinstance(c, Tag) and c.name == "figcaption":
                    continue
                block(c, out)
            cap = node.find("figcaption")
            if cap:
                captxt = "".join(inline(c) for c in cap.children).strip()
                if captxt:
                    out.append(f"*{captxt}*\n\n")
            return
        if name == "figcaption":
            captxt = "".join(inline(c) for c in node.children).strip()
            if captxt:
                out.append(f"*{captxt}*\n\n")
            return
        if name == "small":
            txt = "".join(inline(c) for c in node.children).strip()
            if txt:
                out.append(f"*{txt}*\n\n")
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1]) + 1  # article title is h1 already
            txt = "".join(inline(c) for c in node.children).strip()
            if txt:
                out.append(f"{'#' * min(level, 6)} {txt}\n\n")
            return
        if name == "blockquote":
            inner = []
            for c in node.children:
                block(c, inner)
            quote = "".join(inner).strip().replace("\n\n", "\n>\n")
            if quote:
                out.append("> " + quote + "\n\n")
            return
        if name in ("ul", "ol"):
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                txt = "".join(inline(c) for c in li.children).strip()
                bullet = "-" if name == "ul" else f"{i}."
                if txt:
                    out.append(f"{bullet} {txt}\n")
            out.append("\n")
            return
        if name == "hr":
            out.append("---\n\n")
            return
        if name == "br":
            out.append("\n\n")
            return
        if name == "table":
            rows = node.find_all("tr")
            for ri, tr in enumerate(rows):
                cells = [
                    "".join(inline(c) for c in (td or NavigableString("")).children).strip()
                    for td in tr.find_all(["td", "th"])
                ]
                out.append("| " + " | ".join(cells) + " |\n")
                if ri == 0:
                    out.append("|" + "---|" * len(cells) + "\n")
            out.append("\n")
            return
        # inline-ish containers (p, div, span, em, strong, a, code, unknown):
        # block children nested inside (messy CMS HTML) flush the inline run
        # and recurse as blocks instead of flattening everything to one line.
        buf: list[str] = []
        for c in node.children:
            if isinstance(c, Tag) and c.name in BLOCK_TAGS:
                para_flush(buf, out)
                buf = []
                block(c, out)
            else:
                buf.append(inline(c))
        para_flush(buf, out)
        return

    out: list[str] = []
    for c in soup.children:
        block(c, out)
    md = "".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    # flattened CMS HTML glues sentences: "증가한다.반면" → "증가한다. 반면"
    md = re.sub(r"([.!?])([가-힣])", r"\1 \2", md)
    # interview Q&A runs glued in one paragraph: "…그렇다Q. 왜" → split
    md = re.sub(r'([가-힣!?"\'\)])\s*(Q\.|A\.) ', r"\1\n\n\2 ", md)
    return md.strip()


# ---------------------------------------------------------------- notes


def build_note(detail: dict, session: requests.Session | None = None) -> None:
    if SITE.get("mode", "api") == "api":
        meta, html = detail_meta(detail), detail_content_html(detail)
    else:  # dom/rss store an already-normalized record
        meta, html = detail["meta"], detail["html"]
    # rss ids are often full URLs — one sanitized on-disk name everywhere
    aid = sanitize_filename(str(meta["id"]))

    urls, seen = [], set()
    for m in re.finditer(r'<img[^>]+(?:data-)?src="([^"]+)"', html):
        u = normalize_image_url(m.group(1))
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    img_map = download_images(urls, ATTACH_DIR / aid, session or requests.Session())

    body = html_to_md(html, img_map)
    fm = ["---", f"id: {aid}", f"title: {json.dumps(meta.get('title') or '', ensure_ascii=False)}",
          f"published: {meta.get('published') or ''}", f"url: {meta.get('url') or ''}", "---", "",
          f"# {meta.get('title') or aid}", ""]
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (NOTES_DIR / f"{aid} - {sanitize_filename(meta.get('title') or str(aid))}.md").write_text(
        "\n".join(fm) + (body or "(no content)") + "\n", encoding="utf-8")


def rebuild_notes() -> None:
    n = 0
    for f in sorted(RAW_DIR.glob("*.json")):
        build_note(json.loads(f.read_text(encoding="utf-8")))
        n += 1
    log.info("rebuild done: %d notes", n)


# ---------------------------------------------------------------- site layer


def _merge_series(store: dict, sid: str, s: dict | None, art: dict) -> None:
    """Merge hook-provided series info + the article itself as an episode."""
    cur = store.setdefault(sid, {"episodes": {}})
    if s:
        for k in ("title", "description", "reader_note"):
            if s.get(k):
                cur[k] = s[k]
        for e in s.get("episodes") or []:
            if not e or e.get("id") is None:
                continue
            ep = cur["episodes"].setdefault(str(e["id"]), {"id": str(e["id"])})
            for k in ("vol", "date", "title"):
                if e.get(k) is not None:
                    ep[k] = e[k]
    ep = cur["episodes"].setdefault(art["id"], {"id": art["id"]})
    for k in ("vol", "date", "title"):
        if art.get(k) is not None:
            ep[k] = art[k]


def rebuild_site() -> int:
    """Regenerate data/site/ (index.json + normalized articles) from raw
    data/, no refetching. Opt-in: a no-op with one INFO line until
    norm_article is filled."""
    raws = sorted(RAW_DIR.glob("*.json"))
    if not raws or norm_article(json.loads(raws[0].read_text(encoding="utf-8"))) is None:
        log.info("norm_article not filled — local-site layer skipped "
                 "(opt-in, see SKILL.md Phase 6b)")
        return 0
    arts, series, authors = [], {}, {}
    for f in raws:
        detail = json.loads(f.read_text(encoding="utf-8"))
        art = norm_article(detail)
        if art is None:
            continue
        art["id"] = str(art["id"])   # site layer ids are strings everywhere
        if art.get("series_id") is not None:
            art["series_id"] = str(art["series_id"])
        for au in art.get("authors") or []:
            if au.get("id") is not None:
                au["id"] = str(au["id"])
        adir = ATTACH_DIR / sanitize_filename(art["id"])
        if not art.get("assets_dir") and adir.is_dir():
            art["assets_dir"] = str(adir.relative_to(PROJECT_DIR))
        SITE_ARTICLES.mkdir(parents=True, exist_ok=True)
        save_json(SITE_ARTICLES / f"{sanitize_filename(art['id'])}.json", art)
        if art.get("series_id") is not None:
            _merge_series(series, art["series_id"], norm_series(detail), art)
        for au in norm_authors(detail) or []:
            if not au or au.get("id") is None:
                continue
            a = authors.setdefault(str(au["id"]), {"name": au.get("name")})
            for k in ("name", "title", "bio"):
                if au.get(k):
                    a[k] = au[k]
            if art["id"] not in a.setdefault("article_ids", []):
                a["article_ids"].append(art["id"])
        arts.append({k: v for k, v in art.items() if k != "body_html"})
    collected = {a["id"] for a in arts}
    for s in series.values():
        for e in s["episodes"].values():
            e["collected"] = e["id"] in collected
        s["episodes"] = sorted(s["episodes"].values(),
                               key=lambda e: (e.get("vol") or 0, e.get("date") or ""))
    save_json(SITE_DIR / "index.json", {
        "site_title": SITE.get("site_title") or SITE["collection_name"],
        "articles": arts, "series": series, "authors": authors})
    log.info("site layer rebuilt: %d articles, %d series, %d authors",
             len(arts), len(series), len(authors))
    return len(arts)


def git_commit(count: int) -> None:
    # guard: never commit harvested content to a public repo
    remote = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                            cwd=PROJECT_DIR, capture_output=True, text=True)
    if remote.stdout.strip():
        vis = subprocess.run(["gh", "repo", "view", "--json", "isPrivate", "-q", ".isPrivate"],
                             cwd=PROJECT_DIR, capture_output=True, text=True)
        if vis.returncode == 0 and vis.stdout.strip() == "false":
            log.error("origin is a PUBLIC repo — refusing to commit harvested content")
            sys.exit(1)
        if vis.returncode != 0:
            log.warning("could not verify repo visibility — keep the vault repo private")
    subprocess.run(["git", "add", "."], cwd=PROJECT_DIR, capture_output=True)
    st = subprocess.run(["git", "diff", "--cached", "--stat"], cwd=PROJECT_DIR,
                        capture_output=True, text=True)
    if not st.stdout.strip():
        return
    msg = f"feat({SITE['collection_name']}): collect {count} item(s)"
    subprocess.run(["git", "commit", "-m", msg], cwd=PROJECT_DIR,
                   capture_output=True, text=True, timeout=300)
    log.info("committed: %s", msg)


# ---------------------------------------------------------------- main


def main() -> int:
    global RENDERER
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pace", type=float, nargs=2, default=(30, 120), metavar=("MIN", "MAX"))
    ap.add_argument("--rebuild-notes", action="store_true")
    ap.add_argument("--rebuild-site", action="store_true",
                    help="regenerate the data/site/ reader layer from raw data/ (no fetching)")
    ap.add_argument("--commit", action="store_true", help="git commit progress (every 50 items + end)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(SCRAPER_DIR / "collect.log", encoding="utf-8"),
                                  logging.StreamHandler()])

    if not SITE.get("tos_ok") and not (args.rebuild_notes or args.rebuild_site):
        log.error("tos_ok is False — run the Phase 1 terms-of-service check first (see SKILL.md)")
        return 1
    if args.pace[0] < 5:
        ap.error("--pace MIN must be >= 5 seconds (human pacing is a design invariant)")

    LOCK_FILE.touch(exist_ok=True)
    with open(LOCK_FILE) as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log.error("another collect.py is running — exiting")
            return 0

    if args.rebuild_notes or args.rebuild_site:
        if args.rebuild_notes:
            rebuild_notes()
        if args.rebuild_site:
            rebuild_site()
        return 0

    state = load_json(STATE_FILE, {"window_start": None, "collected": {}})
    if state.get("window_start") is None:
        state["window_start"] = date.today().isoformat()
        save_json(STATE_FILE, state)
    if date.today() > date.fromisoformat(state["window_start"]) + timedelta(days=SITE["window_days"]):
        log.info("collection window over — nothing to do")
        return 0

    mode = SITE.get("mode", "api")
    client = load_client(require_token=(mode == "api" and bool(SITE["auth_header"])))
    img_session = None
    if mode == "dom":
        try:
            RENDERER = DomRenderer()
            RENDERER.start()
        except ImportError:
            log.error('mode="dom" needs playwright — pip install playwright && '
                      "playwright install chromium")
            return 1
        img_session = RENDERER.cookie_session()

    try:
        entries = sweep_index(client)
        collected = state["collected"]
        pending = sorted((e["id"] for e in entries if str(e["id"]) not in collected),
                         key=str)  # oldest/lowest id first
        if args.limit:
            pending = pending[: args.limit]
        log.info("pending: %d", len(pending))

        done = 0
        for i, aid in enumerate(pending):
            for attempt in range(2):
                try:
                    detail = fetch_detail(aid, client)
                    RAW_DIR.mkdir(parents=True, exist_ok=True)
                    # rss ids are often full URLs — sanitize for the filename
                    (RAW_DIR / f"{sanitize_filename(str(aid))}.json").write_text(
                        json.dumps(detail, ensure_ascii=False), encoding="utf-8")
                    build_note(detail, img_session)
                    collected[str(aid)] = datetime.now().isoformat(timespec="seconds")
                    save_json(STATE_FILE, state)
                    done += 1
                    break
                except requests.RequestException as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status == 401 and attempt == 0 and mode == "api" and refresh_token():
                        client = load_client(require_token=bool(SITE["auth_header"]))
                        continue
                    if status in (403, 429):
                        log.error("blocked or rate-limited (HTTP %s) — stopping; see SKILL.md failure modes", status)
                        return 1
                    log.error("item %s failed: %s", aid, e)
                    time.sleep(10)
                except Exception as e:  # dom: render/extract failure on one item
                    if mode != "dom":
                        raise
                    log.error("item %s failed: %s", aid, e)
                    time.sleep(10)
            if i < len(pending) - 1 and mode != "rss":
                smoke = bool(args.limit) and args.limit <= 10
                time.sleep(random.uniform(3, 8) if smoke else random.uniform(*args.pace))
            if done and done % 50 == 0 and args.commit:
                git_commit(done)

        if done and args.commit:
            git_commit(done)
    finally:
        if RENDERER:
            RENDERER.close()
    rebuild_site()  # refresh the reader layer even on no-new-item runs
    log.info("run complete: %d new items", done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
