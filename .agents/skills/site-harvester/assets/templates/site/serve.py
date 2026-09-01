#!/usr/bin/env python3
"""localhost-only reader for the harvested archive. stdlib only, no build step.

Serves the normalized data/site/ layer emitted by collect.py's norm_* hooks
(see SKILL.md Phase 6b). Binds 127.0.0.1 ONLY — harvested content is often
paid/copyrighted; never make 0.0.0.0 the default.

Body images: <img> tags are rewritten in document order to /media/{id}/{file}
over the img-* files in the article's assets_dir (collect.py downloads them
in document order as img-001, img-002, ...).

usage: python3 site/serve.py [--root DIR] [--port N]
  --root  base dir holding data/site/ and the assets_dir paths referenced in
          it (default: the directory above this site/ folder)
"""
import argparse
import json
import re
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent                   # overridable via --root
DATA = ROOT / "data" / "site"

IMG_RE = re.compile(r'(<img[^>]*?src=")[^"]+(")', re.I)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SITE), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # -- helpers ---------------------------------------------------------
    _tag_cache = None
    _assets_map = None

    @classmethod
    def _tag_index(cls):
        """{tags: {name: [article ids]}, keywords: {...}} — one full scan, cached."""
        if cls._tag_cache is not None:
            return cls._tag_cache
        tags, kws = {}, {}
        for p in (DATA / "articles").glob("*.json"):
            try:
                a = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            aid = a.get("id")
            if aid is None:
                continue
            for t in a.get("tags") or []:
                tags.setdefault(t, []).append(aid)
            for k in a.get("keywords") or []:
                kws.setdefault(k, []).append(aid)
        cls._tag_cache = {"tags": tags, "keywords": kws}
        return cls._tag_cache

    @classmethod
    def _index(cls):
        try:
            return json.loads((DATA / "index.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    @classmethod
    def _assets_dir(cls, aid) -> str | None:
        """assets_dir of one article id, from a cached id -> assets_dir map."""
        if cls._assets_map is None:
            cls._assets_map = {str(a.get("id")): a.get("assets_dir")
                               for a in cls._index().get("articles", [])}
        return cls._assets_map.get(str(aid))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype):
        if not path.is_file():
            return self.send_error(404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _rewrite_imgs(self, aid, assets_dir: str | None, html: str) -> str:
        """map body <img> (document order) to assets_dir img-* files"""
        files = sorted(p for p in (ROOT / (assets_dir or "")).glob("img-*")
                       if p.is_file())
        it = iter(files)

        def sub(m):
            f = next(it, None)
            if f is None:
                return m.group(0)  # ponytail: extra imgs keep remote src
            return "%s/media/%s/%s%s" % (m.group(1), aid, f.name, m.group(2))

        return IMG_RE.sub(sub, html)

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        parts = [p for p in path.split("/") if p]

        if path == "/":
            return self._file(SITE / "index.html", "text/html; charset=utf-8")
        if parts and parts[0] == "api":
            return self._api(parts[1:])
        if parts and parts[0] == "media" and len(parts) >= 3:
            return self._media(parts)
        return super().do_GET()

    def _media(self, parts):
        adir_s = self._assets_dir(parts[1])
        if not adir_s:
            return self.send_error(404)
        adir = ROOT / adir_s
        name = parts[2]
        if name == "thumb":  # row thumbnails: cover if the adapter kept one
            files = (sorted(p for p in adir.glob("cover-*") if p.is_file())
                     or sorted(p for p in adir.glob("img-*") if p.is_file()))
            return self._file(files[0], self.guess_type(files[0].name)) if files \
                else self.send_error(404)
        f = (adir / name).resolve()
        if not f.is_relative_to(adir.resolve()):  # path traversal guard
            return self.send_error(403)
        return self._file(f, self.guess_type(f.name))

    def _api(self, parts):
        try:
            if parts == ["index"]:
                return self._json(self._index())
            if parts == ["tags"]:
                return self._json(self._tag_index())
            if parts[0] == "article":
                art = json.loads(
                    (DATA / "articles" / ("%s.json" % parts[1])).read_text(encoding="utf-8"))
                art["body_html"] = self._rewrite_imgs(
                    parts[1], art.get("assets_dir"), art.get("body_html") or "")
                return self._json(art)
            if parts[0] == "series":
                obj = self._index().get("series", {}).get(parts[1])
                if obj is None:
                    return self.send_error(404)
                return self._json(obj)
            if parts == ["authors"]:
                out = [{"id": i, "name": a.get("name"), "title": a.get("title"),
                        "n": len(a.get("article_ids") or [])}
                       for i, a in self._index().get("authors", {}).items()]
                return self._json(out)
            if parts[0] == "author":
                obj = self._index().get("authors", {}).get(parts[1])
                if obj is None:
                    return self.send_error(404)
                return self._json(obj)
            return self.send_error(404)
        except FileNotFoundError:
            return self.send_error(404)
        except Exception as e:  # malformed id etc.
            return self._json({"error": str(e)}, 500)


def main():
    global ROOT, DATA
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="base dir holding data/site/ and assets (default: %(default)s)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    ROOT, DATA = args.root.resolve(), args.root.resolve() / "data" / "site"
    Handler._assets_map = None  # drop any cache built against the old root
    httpd = HTTPServer(("127.0.0.1", args.port), Handler)
    print("local reader on http://127.0.0.1:%d (ctrl-c to stop)" % args.port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
