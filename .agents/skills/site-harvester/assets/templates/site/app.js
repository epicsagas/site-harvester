/* local archive reader — vanilla SPA, hash router */
"use strict";

const app = document.getElementById("app");
const sentinel = document.getElementById("sentinel");
const hideReadBox = document.getElementById("hideRead");

const state = {
  index: null,          // site_title + articles[] + series{} + authors{}
  listStart: 0,         // infinite scroll cursor
  renderedMonth: "",    // month separator tracker
  query: "",
  seriesFilter: "",
  read: new Set(),
  readKey: "reader.read",
  seriesMap: {},        // lazily filled per series page for prev/next nav
};
const CHUNK = 60;

const api = (p) => fetch("/api/" + p).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
});
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
const fmtDate = (iso) => (iso || "").slice(0, 10).replace(/-/g, ".");
const fmtMonth = (iso) => (iso || "").slice(0, 7);
const fmtMonthLong = (ym) =>
  new Date(ym + "-01").toLocaleDateString(undefined, { year: "numeric", month: "long" });
const saveRead = () => localStorage.setItem(state.readKey, JSON.stringify([...state.read]));

/* ---------- theme ---------- */

const themeBtn = document.getElementById("themeBtn");
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  themeBtn.textContent = t === "dark" ? "☀" : "☾";
}
applyTheme(localStorage.getItem("reader.theme") ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
themeBtn.addEventListener("click", () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("reader.theme", t);
  applyTheme(t);
});

/* ---------- in-body auto links ---------- */

/* wrap first occurrence of each term in a text node — skips existing anchors */
function linkify(container, terms) {
  const pending = terms.filter((t) => t.text && t.text.length >= 2);
  if (!pending.length) return;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) =>
      ["SCRIPT", "STYLE", "A"].includes(n.parentNode.nodeName)
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT,
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    for (let i = pending.length - 1; i >= 0; i--) {
      const term = pending[i];
      const at = node.data.indexOf(term.text);
      if (at < 0) continue;
      const after = node.splitText(at + term.text.length);
      const match = node.splitText(at);
      const a = document.createElement("a");
      a.className = "inlink";
      a.href = term.href;
      a.textContent = term.text;
      match.parentNode.replaceChild(a, match);
      node.parentNode.insertBefore(after, a.nextSibling);
      pending.splice(i, 1);
    }
    if (!pending.length) return;
  }
}

/* ---------- home (article feed) ---------- */

function filteredArticles() {
  if (!state.index) return [];
  const q = state.query.trim().toLowerCase();
  return state.index.articles
    .filter((a) => {
      if (state.seriesFilter && String(a.series_id) !== state.seriesFilter) return false;
      if (hideReadBox.checked && state.read.has(String(a.id))) return false;
      if (q && !(a.title || "").toLowerCase().includes(q)) return false;
      return true;
    })
    .sort((x, y) => (y.date || "").localeCompare(x.date || ""));
}

function renderHome() {
  const list = filteredArticles();
  state.listStart = 0;
  state.renderedMonth = "";
  const n = Object.keys(state.index.series || {}).length;
  app.innerHTML = `
    <section class="home-lede">
      <h1>${esc(state.index.site_title || "Archive")}</h1>
      <p>${state.index.articles.length} articles · ${n} series</p>
    </section>
    <div class="searchbar">
      <input id="q" type="search" placeholder="Search titles" value="${esc(state.query)}">
      <select id="seriesSel"><option value="">All series</option></select>
    </div>
    <div id="feed"></div>
    <p class="loading" id="feedStatus"></p>`;
  renderChunk(list);

  const q = app.querySelector("#q");
  q.addEventListener("input", () => {
    state.query = q.value;
    resetFeed();
  });
  const sel = app.querySelector("#seriesSel");
  const series = Object.entries(state.index.series || {}).sort((a, b) =>
    (a[1].title || "").localeCompare(b[1].title || ""));
  for (const [id, s] of series) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = s.title || id;
    sel.appendChild(o);
  }
  sel.value = state.seriesFilter;
  sel.addEventListener("change", () => {
    state.seriesFilter = sel.value;
    resetFeed();
  });
}

function resetFeed() {
  const list = filteredArticles();
  state.listStart = 0;
  state.renderedMonth = "";
  document.getElementById("feed").innerHTML = "";
  renderChunk(list);
}

function renderChunk(list) {
  const feed = document.getElementById("feed");
  const status = document.getElementById("feedStatus");
  const slice = list.slice(state.listStart, state.listStart + CHUNK);
  const frag = document.createDocumentFragment();
  for (const a of slice) {
    const m = fmtMonth(a.date);
    if (m && m !== state.renderedMonth) {
      state.renderedMonth = m;
      const sep = document.createElement("h2");
      sep.className = "month-sep";
      sep.textContent = fmtMonthLong(m);
      frag.appendChild(sep);
    }
    frag.appendChild(rowEl(a));
  }
  feed.appendChild(frag);
  state.listStart += slice.length;
  status.textContent = state.listStart >= list.length
    ? "— " + list.length + " shown —"
    : "";
}

/* ---------- shared row ---------- */

function rowEl(a) {
  const s = (state.index.series || {})[a.series_id];
  const row = document.createElement("a");
  row.className = "article-row" + (state.read.has(String(a.id)) ? " is-read" : "");
  row.href = "#/article/" + a.id;
  row.innerHTML = `
    <img class="row-thumb" loading="lazy" src="/media/${a.id}/thumb" alt="" onerror="this.style.visibility='hidden'">
    <div>
      <div class="row-meta">
        <span class="vol">${s ? esc(s.title) : ""}${a.vol ? " · Ep. " + a.vol : ""}</span>
      </div>
      <h3 class="row-title">${esc(a.title)}</h3>
      <div class="row-series">${fmtDate(a.date)}${a.is_free ? " · free" : ""}</div>
    </div>`;
  return row;
}

/* ---------- article ---------- */

async function renderArticle(id) {
  app.innerHTML = '<p class="loading">Loading…</p>';
  try {
    const a = await api("article/" + id);
    document.title = (a.title || "") + " — " + (state.index.site_title || "Archive");
    const s = state.index.series[a.series_id];
    if (a.series_id && !state.seriesMap[a.series_id]) {
      try {
        const full = await api("series/" + a.series_id);
        state.seriesMap[a.series_id] = sortedEpisodes(full.episodes);
      } catch (_) { state.seriesMap[a.series_id] = []; }
    }
    const eps = state.seriesMap[a.series_id];
    let prev = null, next = null;
    if (eps) {
      const i = eps.findIndex((e) => String(e.id) === String(id));
      if (i > 0) prev = eps[i - 1];
      if (i >= 0 && i < eps.length - 1) next = eps[i + 1];
    }
    const isRead = state.read.has(String(a.id));
    app.innerHTML = `
      <article>
        <header class="article-head">
          <div class="article-kicker">
            ${s ? `<a href="#/series/${a.series_id}">${esc(s.title)}</a>${a.vol ? " · Ep. " + a.vol : ""}` : ""}
          </div>
          <h1 class="article-title">${esc(a.title)}</h1>
          <div class="article-meta">
            <span>${fmtDate(a.date)}</span>
            ${a.likes ? "<span>♥ " + a.likes + "</span>" : ""}
            ${(a.authors || []).map((au) =>
              au.id ? `<a href="#/author/${au.id}">${esc(au.name)}</a>` : `<span>${esc(au.name)}</span>`).join("")}
            ${(a.tags || []).map((t) => `<a class="tag" href="#/tags/tag/${encodeURIComponent(t)}">${esc(t)}</a>`).join("")}
            <button class="btn-read${isRead ? " on" : ""}" id="readBtn">${isRead ? "Read ✓" : "Mark read"}</button>
          </div>
        </header>
        <div class="article-body">${a.body_html}</div>
        <nav class="article-nav">
          ${prev ? `<a href="#/article/${prev.id}"><span class="dir">← Previous</span>${esc(prev.title)}</a>` : "<span></span>"}
          ${next ? `<a href="#/article/${next.id}" style="text-align:right"><span class="dir">Next →</span>${esc(next.title)}</a>` : "<span></span>"}
        </nav>
      </article>`;
    const btn = document.getElementById("readBtn");
    // in-body links: series title, authors, tags, keywords
    linkify(document.querySelector(".article-body"), [
      ...(s && s.title ? [{ text: s.title, href: "#/series/" + a.series_id }] : []),
      ...(a.authors || []).filter((au) => au.id).map((au) => ({ text: au.name, href: "#/author/" + au.id })),
      ...(a.tags || []).map((t) => ({ text: t, href: "#/tags/tag/" + encodeURIComponent(t) })),
      ...(a.keywords || []).map((k) => ({ text: k, href: "#/tags/keyword/" + encodeURIComponent(k) })),
    ]);
    btn.addEventListener("click", () => {
      const k = String(a.id);
      state.read.has(k) ? state.read.delete(k) : state.read.add(k);
      saveRead();
      btn.classList.toggle("on");
      btn.textContent = state.read.has(k) ? "Read ✓" : "Mark read";
    });
  } catch (e) {
    app.innerHTML = '<p class="loading">Article not found (' + esc(e.message) + ")</p>";
  }
}

/* ---------- series ---------- */

const sortedEpisodes = (eps) => (eps || []).slice()
  .sort((a, b) => (a.vol || 0) - (b.vol || 0) || (a.date || "").localeCompare(b.date || ""));

async function renderSeriesList() {
  app.innerHTML = `
    <a class="backlink" href="#/">← Home</a>
    <section class="page-lede"><h1>Series</h1></section>
    <div id="seriesList"><p class="loading">Loading…</p></div>`;
  const box = document.getElementById("seriesList");
  const arts = state.index.articles;
  const counts = {};
  for (const a of arts) counts[a.series_id] = (counts[a.series_id] || 0) + 1;
  box.innerHTML = Object.entries(state.index.series || {})
    .sort((a, b) => counts[b[0]] - counts[a[0]] || String(a[1].title || "").localeCompare(String(b[1].title || "")))
    .map(([id, s]) => `
      <a class="series-card" href="#/series/${id}">
        <h2 class="sc-title">${esc(s.title || id)}</h2>
        <div class="sc-meta">${counts[id] || 0} collected</div>
      </a>`).join("");
}

async function renderSeries(id) {
  app.innerHTML = '<p class="loading">Loading…</p>';
  try {
    const s = await api("series/" + id);
    document.title = (s.title || "Series") + " — " + (state.index.site_title || "Archive");
    const eps = sortedEpisodes(s.episodes);
    state.seriesMap[id] = eps;
    app.innerHTML = `
      <a class="backlink" href="#/series">← All series</a>
      <section class="page-lede">
        <div class="lede-meta">${eps.length} episodes</div>
        <h1>${esc(s.title || id)}</h1>
        ${s.reader_note ? `<p><strong>For readers of</strong>\n${esc(s.reader_note)}</p>` : ""}
        ${s.description ? `<p>${esc(s.description)}</p>` : ""}
      </section>
      <div id="eps">${eps.map((e) => {
        const row = rowEl({ id: e.id, title: e.title, date: e.date, vol: e.vol, series_id: id });
        const meta = row.querySelector(".row-series");
        meta.innerHTML = fmtDate(e.date) + (e.collected ? "" : " · not collected");
        return row.outerHTML;
      }).join("")}</div>`;
  } catch (e) {
    app.innerHTML = '<p class="loading">Series not found (' + esc(e.message) + ")</p>";
  }
}

/* ---------- authors ---------- */

async function renderAuthorList() {
  app.innerHTML = `
    <a class="backlink" href="#/">← Home</a>
    <section class="page-lede"><h1>Authors</h1></section>
    <div id="authorList"><p class="loading">Loading…</p></div>`;
  const list = await api("authors");
  document.getElementById("authorList").innerHTML = list
    .sort((a, b) => (b.n || 0) - (a.n || 0))
    .map((au) => `
      <a class="author-card" href="#/author/${au.id}">
        <span class="ac-name">${esc(au.name)}</span>
        <span class="ac-title">${esc(au.title || "")}</span>
        <span class="ac-n">${au.n}</span>
      </a>`).join("");
}

async function renderAuthor(id) {
  app.innerHTML = '<p class="loading">Loading…</p>';
  try {
    const au = await api("author/" + id);
    document.title = (au.name || "Author") + " — " + (state.index.site_title || "Archive");
    const byId = {};
    for (const a of state.index.articles) byId[a.id] = a;
    const arts = (au.article_ids || [])
      .map((aid) => byId[aid])
      .filter(Boolean)
      .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    app.innerHTML = `
      <a class="backlink" href="#/authors">← All authors</a>
      <section class="page-lede">
        <div class="lede-meta">${arts.length} articles</div>
        <h1>${esc(au.name)}${au.title ? " — " + esc(au.title) : ""}</h1>
        ${au.bio ? `<p>${esc(au.bio)}</p>` : ""}
      </section>
      <div>${arts.map((a) => rowEl(a).outerHTML).join("")
        || '<p class="loading">No collected articles</p>'}</div>`;
  } catch (e) {
    app.innerHTML = '<p class="loading">Author not found (' + esc(e.message) + ")</p>";
  }
}

/* ---------- tags / keywords ---------- */

async function renderTagList() {
  app.innerHTML = `
    <a class="backlink" href="#/">← Home</a>
    <section class="page-lede"><h1>Tags · Keywords</h1></section>
    <p class="loading">Loading…</p>`;
  const t = await api("tags");
  const section = (title, map) => `
    <section class="kw-section">
      <h2>${title}</h2>
      <div class="tag-cloud">
        ${Object.entries(map)
          .sort((a, b) => b[1].length - a[1].length)
          .slice(0, 200)
          .map(([name, ids]) => `
            <a class="tag-chip${ids.length >= 20 ? " hot" : ""}" href="#/tags/${title === "Tags" ? "tag" : "keyword"}/${encodeURIComponent(name)}">
              ${esc(name)}<span class="n">${ids.length}</span>
            </a>`).join("")}
      </div>
    </section>`;
  app.querySelector(".loading").outerHTML = section("Tags", t.tags) + section("Keywords", t.keywords);
}

async function renderTag(kind, name) {
  app.innerHTML = '<p class="loading">Loading…</p>';
  const t = await api("tags");
  const map = kind === "tag" ? t.tags : t.keywords;
  const ids = new Set(map[name] || []);
  document.title = name + " — " + (state.index.site_title || "Archive");
  const byId = {};
  for (const a of state.index.articles) byId[a.id] = a;
  const arts = [...ids].map((i) => byId[i]).filter(Boolean)
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  app.innerHTML = `
    <a class="backlink" href="#/tags">← All tags</a>
    <section class="page-lede">
      <div class="lede-meta">${kind === "tag" ? "Tag" : "Keyword"} · ${arts.length} articles</div>
      <h1>${esc(name)}</h1>
    </section>
    <div>${arts.map((a) => rowEl(a).outerHTML).join("")}</div>`;
}

/* ---------- archive ---------- */

function monthCounts() {
  const counts = {};
  for (const a of state.index.articles) {
    const m = fmtMonth(a.date);
    if (m) counts[m] = (counts[m] || 0) + 1;
  }
  return counts;
}

function renderArchive() {
  const counts = monthCounts();
  const months = Object.keys(counts).sort().reverse();
  const years = [...new Set(months.map((m) => m.slice(0, 4)))];
  const now = new Date().toISOString().slice(0, 7);
  app.innerHTML = `
    <a class="backlink" href="#/">← Home</a>
    <section class="page-lede"><h1>Archive</h1></section>
    ${years.map((y) => `
      <section class="archive-year">
        <h2>${y}</h2>
        <div class="archive-months">
          ${months.filter((m) => m.startsWith(y)).map((m) => `
            <a class="archive-month${m === now ? " now" : ""}" href="#/archive/${m}">
              <span>${fmtMonthLong(m)}</span><span class="n">${counts[m]}</span>
            </a>`).join("")}
        </div>
      </section>`).join("")}`;
}

function renderArchiveMonth(ym) {
  const arts = state.index.articles
    .filter((a) => fmtMonth(a.date) === ym)
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  document.title = fmtMonthLong(ym) + " — " + (state.index.site_title || "Archive");
  app.innerHTML = `
    <a class="backlink" href="#/archive">← Archive</a>
    <section class="page-lede">
      <div class="lede-meta">${arts.length} articles</div>
      <h1>${fmtMonthLong(ym)}</h1>
    </section>
    <div>${arts.map((a) => rowEl(a).outerHTML).join("")}</div>`;
}

/* ---------- router ---------- */

async function loadIndex() {
  state.index = await api("index");
  // read marks are scoped per site so two archives on the same port don't mix
  state.readKey = "reader.read:" + (state.index.site_title || "site");
  state.read = new Set(JSON.parse(localStorage.getItem(state.readKey) || "[]"));
  document.getElementById("wordmark").textContent = state.index.site_title || "Archive";
  document.title = state.index.site_title || "Local reader";
}

async function route() {
  const h = location.hash.replace(/^#/, "");
  const p = h.split("/").filter(Boolean);
  window.scrollTo(0, 0);
  if (!state.index) {
    app.innerHTML = '<p class="loading">Loading…</p>';
    try { await loadIndex(); } catch (e) {
      app.innerHTML = '<p class="loading">Index load failed — is serve.py running against a data/site/ layer? (' + esc(e.message) + ")</p>";
      return;
    }
  }
  if (!p.length) return renderHome();
  if (p[0] === "article") return renderArticle(p[1]);
  if (p[0] === "series") return p[1] ? renderSeries(p[1]) : renderSeriesList();
  if (p[0] === "authors") return renderAuthorList();
  if (p[0] === "author") return renderAuthor(p[1]);
  if (p[0] === "tags")
    return (p[1] === "tag" || p[1] === "keyword")
      ? renderTag(p[1], decodeURIComponent(p.slice(2).join("/")))
      : renderTagList();
  if (p[0] === "archive") return p[1] ? renderArchiveMonth(p[1]) : renderArchive();
  renderHome();
}

hideReadBox.addEventListener("change", () => {
  if (!location.hash.replace(/^#/, "").split("/").filter(Boolean).length) resetFeed();
});
new IntersectionObserver((entries) => {
  if (entries[0].isIntersecting && state.index && !location.hash.replace(/^#/, "").split("/").filter(Boolean).length) {
    const list = filteredArticles();
    if (state.listStart && state.listStart < list.length) renderChunk(list);
  }
}, { rootMargin: "400px" }).observe(sentinel);
window.addEventListener("hashchange", route);
route();
