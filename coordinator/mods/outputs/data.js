const RG = "/opt/homebrew/bin/rg";
const TIMEOUT = 20000;
const RG_BATCH = 100;
const SIPS_BATCH = 100;
const MIN_IMAGE_BYTES = 4096;
const MIN_SCRATCH_IMAGE_BYTES = 20480;
const BASELINE_ROOTS = 3;
const T3_TTL_MS = 300000;
const T3_PAGES = 5;
const CAPS = { wiki: 60, artifacts: 60 };
const IMAGE_EXT = /\.(png|jpe?g|gif|svg)$/i;
const HTML_EXT = /\.html?$/i;
const TICKET = /(?<![a-z0-9])([a-z]{2,4})-(\d{1,5})(?![a-z0-9])/gi;
const SIDE_THREAD = /\b(review|critique|merge relay|fix gate|staging)\b/i;
const AGENT_TAG = /\s*\((?:[^()]*,\s*)?(?:Sol|Terra|Fable[^()]*|Claude Opus|Opus|Sonnet)\)$/i;
const SEED_PREFIXES = ["srw", "mo", "auh", "crn"];
export const OTHER = "Other";
const COORDINATOR = { key: "coordinator", label: "Coordinator", title: "" };
const WIKI = { key: "wiki", label: "Wiki", title: "" };

const FILES = String.raw`
find "$HOME"/Code/*/evidence "$HOME"/.t3/worktrees/*/*/evidence /private/tmp/claude-$(id -u)/*/*/scratchpad -maxdepth 4 \( -name node_modules -o -name .git \) -prune -o -type f -mtime -7 \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.gif' -o -iname '*.svg' -o -iname '*.html' -o -iname '*.pdf' \) -exec stat -f '%m %z %N' {} + 2>/dev/null
find /private/tmp -maxdepth 1 -type f -mtime -7 -iname '*.png' -exec stat -f '%m %z %N' {} + 2>/dev/null
`;

const TRANSCRIPTS = String.raw`
find "$HOME"/.claude/projects -maxdepth 2 -name '*.jsonl' -mtime -7 -print0 | xargs -0 stat -f '%m %N'
`;

const EXTRACT = String.raw`
const fs = require("fs");
const URL = /https:\/\/claude\.ai\/(?:artifact\/[A-Za-z0-9_-]{22}(?![A-Za-z0-9_-])|code\/artifact\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![0-9a-f-]))/g;
const PUBLISH = /(?:^|__)publish_files$|^Artifact$/;
for (const file of process.argv.slice(1)) {
  if (!fs.existsSync(file)) continue;
  const found = new Map(), calls = new Map();
  let cwd = "";
  const add = (url, info, ts) => {
    const rec = found.get(url) ?? { url, ts: 0 };
    found.set(url, rec);
    rec.ts = Math.max(rec.ts, ts);
    if (info.publish ? !rec.published : !rec.cwd) { rec.cwd = info.cwd; rec.published = Boolean(info.publish); }
    rec.title ||= info.title;
    rec.path ||= info.path;
  };
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (!line.includes("publish_files") && !line.includes('"Artifact"') && !line.includes("claude.ai/")) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (o.cwd) cwd = o.cwd;
    const ts = Date.parse(o.timestamp) / 1000 || 0;
    const parts = Array.isArray(o.message?.content) ? o.message.content : [];
    for (const p of parts) {
      if (p.type === "tool_use" && PUBLISH.test(p.name) && (p.name !== "Artifact" || !p.input.action || p.input.action === "publish")) {
        const files = Array.isArray(p.input.files) ? p.input.files : [];
        const html = files.find((f) => /\.html?$/i.test(f.path ?? "")) ?? files[0];
        const call = { publish: true, cwd, title: p.input.title, path: p.input.file_path ?? html?.path };
        calls.set(p.id, call);
        if (p.input.url) for (const url of p.input.url.match(URL) ?? []) add(url, call, ts);
      } else if (p.type === "tool_result" && calls.has(p.tool_use_id)) {
        const url = JSON.stringify(p.content).match(URL)?.[0];
        if (url) add(url, calls.get(p.tool_use_id), ts);
      } else if (o.type === "assistant" && p.type === "text") {
        for (const url of p.text.match(URL) ?? []) add(url, { cwd }, ts);
      }
    }
  }
  for (const rec of found.values()) {
    if (rec.path && /\.html?$/i.test(rec.path) && fs.existsSync(rec.path)) {
      const fd = fs.openSync(rec.path, "r"), buf = Buffer.alloc(20000);
      const n = fs.readSync(fd, buf, 0, buf.length, 0);
      fs.closeSync(fd);
      rec.html = buf.toString("utf8", 0, n).match(/<title[^>]*>([^<]{1,160})/i)?.[1].trim();
    }
  }
  console.log(JSON.stringify({ file, items: [...found.values()] }));
}
`;

export function ticketOf(text, prefixes) {
  for (const m of text.matchAll(TICKET)) {
    if (!prefixes || prefixes.has(m[1].toLowerCase())) return `${m[1].toUpperCase()}-${m[2]}`;
  }
  return null;
}

const worktreeName = (path) => path.match(/\/\.t3\/worktrees\/[^/]+\/([^/]+)/)?.[1];

function placeTicket(texts, prefixes, cwd) {
  const wt = cwd && worktreeName(cwd);
  return (wt && ticketOf(wt)) ?? texts.map((text) => text && ticketOf(text, prefixes)).find(Boolean) ?? null;
}

const humanize = (name) => name.replace(/\.[a-z0-9]+$/i, "").replace(/[-_]+/g, " ");
const basename = (path) => path.slice(path.lastIndexOf("/") + 1);

function nameFromPath(path) {
  const [file, dir] = path.split("/").reverse();
  return humanize(/^index\.html?$/i.test(file) ? dir : file);
}

function projectOf(path, home) {
  const wt = path.match(/\/\.t3\/worktrees\/([^/]+)/);
  if (wt) return wt[1];
  const code = path.match(/\/Code\/([^/]+)/);
  if (code) return code[1];
  return path.startsWith(`${home}/`) ? path.slice(home.length + 1).split("/")[0] : "tmp";
}

function fileRow(line, home) {
  const [t, size, ...rest] = line.split(" "), path = rest.join(" "), name = basename(path);
  return {
    kind: IMAGE_EXT.test(name) ? "image" : "page",
    name, file: name, path, target: path, t: Number(t), size: Number(size),
    scratch: path.includes("/scratchpad/"),
    src: path.includes("/scratchpad/") ? "scratch" : projectOf(path, home),
  };
}

function keepFile(r) {
  if (r.kind === "image" && r.size < MIN_IMAGE_BYTES) return false;
  if (!r.scratch) return true;
  return r.kind === "page" ? HTML_EXT.test(r.name) : r.size >= MIN_SCRATCH_IMAGE_BYTES;
}

const rootOf = (path) => path.includes("/evidence/") ? path.split("/evidence/")[0] : path.slice(0, path.lastIndexOf("/"));

function dropBaseline(rows) {
  const roots = new Map();
  for (const r of rows) {
    const key = `${r.name}|${r.size}`, root = rootOf(r.path);
    if (!roots.has(key)) roots.set(key, new Set());
    roots.get(key).add(root);
  }
  return rows.filter((r) => roots.get(`${r.name}|${r.size}`).size < BASELINE_ROOTS);
}

function wikiRows(out, host) {
  const seen = new Set(), rows = [];
  let t = 0, subject = "";
  for (const line of out.split("\n")) {
    if (line.startsWith("@")) {
      const space = line.indexOf(" ");
      t = Number(line.slice(1, space)); subject = line.slice(space + 1);
      continue;
    }
    if (!line.startsWith("source/docs/") || !line.endsWith(".md") || seen.has(line)) continue;
    seen.add(line);
    const parts = line.split("/"), file = parts.pop();
    rows.push({ kind: "wiki", name: humanize(file), file, src: parts[2] ?? "docs", subject, t, target: `${host.home()}/Code/llmwiki/${line}` });
  }
  return rows;
}

async function rg(host, args) {
  const r = await host.exec(RG, ["--no-messages", ...args], { timeout: TIMEOUT })
    .catch((e) => { throw new Error(`rg is missing or failed to start at ${RG}: ${e}`); });
  if (r.code > 1 && r.stderr.trim()) throw new Error(`rg failed (${r.code}): ${r.stderr.trim()}`);
  return r;
}

async function scanTranscripts(host, cache) {
  const listing = await host.exec("sh", ["-c", TRANSCRIPTS], { timeout: TIMEOUT });
  if (listing.code !== 0) throw new Error(`transcript listing failed: ${listing.stderr.trim()}`);
  const current = new Map();
  for (const line of listing.stdout.split("\n").filter(Boolean)) {
    const space = line.indexOf(" ");
    current.set(line.slice(space + 1), Number(line.slice(0, space)));
  }
  for (const file of cache.transcripts.keys()) if (!current.has(file)) cache.transcripts.delete(file);
  const changed = [...current].filter(([file, t]) => cache.transcripts.get(file)?.t !== t).map(([file]) => file);
  for (let i = 0; i < changed.length; i += RG_BATCH) {
    const batch = changed.slice(i, i + RG_BATCH);
    const hits = await rg(host, ["-l", "https://claude\\.ai/(code/)?artifact/[A-Za-z0-9_-]{22}", ...batch]);
    const withUrls = hits.stdout.split("\n").filter(Boolean);
    const extracted = new Map();
    if (withUrls.length) {
      const r = await host.exec("node", ["-e", EXTRACT, ...withUrls], { timeout: TIMEOUT });
      if (r.code !== 0) throw new Error(`artifact extraction failed (${r.code}): ${r.stderr.trim().slice(0, 300)}`);
      for (const line of r.stdout.split("\n").filter(Boolean)) {
        const { file, items } = JSON.parse(line);
        extracted.set(file, items);
      }
    }
    const titles = await sessionTitles(host, batch);
    for (const file of batch) cache.transcripts.set(file, { t: current.get(file), items: extracted.get(file) ?? [], title: titles.get(file) ?? null });
  }
}

async function sessionTitles(host, files) {
  const r = await rg(host, ["-o", "-H", "--no-line-number", '"(customTitle|aiTitle)":"(?:[^"\\\\]|\\\\.)*"', ...files]);
  const best = new Map();
  for (const line of r.stdout.split("\n")) {
    const m = line.match(/^(.*?):"(customTitle|aiTitle)":"((?:[^"\\]|\\.)*)"$/);
    if (!m) continue;
    let title;
    try { title = JSON.parse(`"${m[3]}"`); } catch { continue; }
    const entry = best.get(m[1]) ?? {};
    entry[m[2]] = title;
    best.set(m[1], entry);
  }
  return new Map([...best].map(([file, e]) => [file, e.customTitle || e.aiTitle || null]));
}

const sessionOf = (file) => basename(file).replace(/\.jsonl$/, "");

function artifactRows(cache, now, host) {
  const byUrl = new Map();
  for (const [file, { items }] of cache.transcripts) {
    for (const rec of items) {
      const have = byUrl.get(rec.url) ?? { url: rec.url, ts: 0 };
      byUrl.set(rec.url, have);
      have.ts = Math.max(have.ts, rec.ts);
      have.html ||= rec.html;
      have.title ||= rec.title;
      have.path ||= rec.path;
      have.cwd ||= rec.cwd;
      have.session ||= sessionOf(file);
    }
  }
  const cutoff = now - 7 * 86400;
  return [...byUrl.values()].filter((a) => a.ts >= cutoff).map((a) => {
    const id = a.url.slice(a.url.lastIndexOf("/") + 1);
    const title = a.html || a.title || (a.path && nameFromPath(a.path));
    return { kind: "artifact", name: title ?? id, titled: Boolean(title), id, src: a.cwd ? projectOf(a.cwd, host.home()) : "", t: a.ts, target: a.url, cwd: a.cwd, path: a.path, session: a.session };
  });
}

async function t3Titles(host, cache) {
  if (cache.t3 && Date.now() - cache.t3.at < T3_TTL_MS) return cache.t3;
  const threads = [];
  let cursor = null;
  for (let page = 0; page < T3_PAGES; page++) {
    const args = { allProjects: true, includeSubagents: false, limit: 100, ...(cursor === null ? {} : { cursor }) };
    const r = await host.exec(`${host.home()}/.local/bin/t3mcp`, ["call", "t3_thread_list", JSON.stringify(args)], { timeout: TIMEOUT });
    if (r.code !== 0) throw new Error(`t3mcp failed (${r.code}): ${(r.stderr || r.stdout).trim().slice(0, 200)}`);
    const body = JSON.parse(r.stdout);
    threads.push(...body.threads);
    cursor = body.nextCursor;
    if (cursor === null || cursor === undefined) break;
  }
  const titles = new Map(), mainRank = new Map(), prefixes = new Set(SEED_PREFIXES);
  for (const th of threads.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))) {
    const m = th.title.match(/^\s*([a-z]{2,4})-(\d{1,5})\b/i);
    if (!m) continue;
    const id = `${m[1].toUpperCase()}-${m[2]}`, main = !SIDE_THREAD.test(th.title);
    prefixes.add(m[1].toLowerCase());
    if (mainRank.get(id) || (!main && titles.has(id))) continue;
    const dot = th.title.indexOf("·");
    const text = dot >= 0 ? th.title.slice(dot + 1) : th.title.slice(m[0].length);
    titles.set(id, main ? text.replace(AGENT_TAG, "").trim() : "");
    mainRank.set(id, main);
  }
  return { at: Date.now(), titles, prefixes };
}

async function fileTitles(host, cache, pages) {
  const need = pages.filter((p) => HTML_EXT.test(p.name) && cache.pageTitles.get(p.path)?.t !== p.t);
  if (need.length) {
    const r = await rg(host, ["-o", "-H", "--no-line-number", "-i", "-m1", "<title[^>]*>[^<]{1,160}", ...need.map((p) => p.path)]);
    const found = new Map();
    for (const line of r.stdout.split("\n")) {
      const at = line.indexOf(":<");
      if (at > 0) found.set(line.slice(0, at), line.slice(at + 1).replace(/^<title[^>]*>/i, "").trim());
    }
    for (const p of need) cache.pageTitles.set(p.path, { t: p.t, title: found.get(p.path) ?? null });
  }
  for (const p of pages) p.title = cache.pageTitles.get(p.path)?.title ?? null;
}

async function imageSizes(host, cache, images) {
  const need = images.filter((i) => cache.dims.get(i.path)?.t !== i.t);
  for (let i = 0; i < need.length; i += SIPS_BATCH) {
    const batch = need.slice(i, i + SIPS_BATCH);
    const r = await host.exec("sips", ["-g", "pixelWidth", "-g", "pixelHeight", ...batch.map((b) => b.path)], { timeout: TIMEOUT });
    const dims = new Map();
    let path = null;
    for (const line of r.stdout.split("\n")) {
      if (line.startsWith("/")) { path = line.trim(); dims.set(path, {}); }
      else if (path && line.includes("pixelWidth:")) dims.get(path).w = Number(line.split(":")[1]);
      else if (path && line.includes("pixelHeight:")) dims.get(path).h = Number(line.split(":")[1]);
    }
    for (const b of batch) cache.dims.set(b.path, { t: b.t, w: dims.get(b.path)?.w, h: dims.get(b.path)?.h });
  }
  for (const i of images) { const d = cache.dims.get(i.path); i.w = d.w; i.h = d.h; }
}

export function newCache() {
  return { transcripts: new Map(), dims: new Map(), pageTitles: new Map(), t3: null };
}

export async function collect(host, cache) {
  const timings = {}, warnings = [];
  const timed = async (name, promise) => {
    const start = Date.now();
    const value = await promise;
    timings[name] = Date.now() - start;
    return value;
  };
  const [files, wiki, , t3] = await Promise.all([
    timed("files", host.exec("sh", ["-c", FILES], { timeout: TIMEOUT })),
    timed("wiki", host.exec("git", ["-C", `${host.home()}/Code/llmwiki`, "log", "--since=7.days", "--diff-filter=AM", "--name-only", "--pretty=format:@%ct %s"], { timeout: TIMEOUT })),
    timed("transcripts", scanTranscripts(host, cache)),
    timed("t3", t3Titles(host, cache).catch((e) => {
      warnings.push(`Group titles unavailable: ${e.message ?? e}`);
      return cache.t3 ?? { at: 0, titles: new Map(), prefixes: new Set(SEED_PREFIXES) };
    })),
  ]);
  if (files.code !== 0) throw new Error(`file search failed (${files.code}): ${files.stderr.trim()}`);
  if (wiki.code !== 0) throw new Error(`git log failed (${wiki.code}): ${wiki.stderr.trim()}`);
  cache.t3 = t3;

  const home = host.home(), now = Date.now() / 1000;
  const prefixes = new Set(t3.prefixes);
  const rows = dropBaseline(files.stdout.split("\n").filter(Boolean).map((l) => fileRow(l, home))).filter(keepFile);
  for (const r of rows) {
    const wt = worktreeName(r.path), m = wt && [...wt.matchAll(TICKET)][0];
    if (m) prefixes.add(m[1].toLowerCase());
  }
  const sessions = new Map([...cache.transcripts].map(([file, e]) => [sessionOf(file), e.title]));
  const sessionBucket = (id) => ({ key: `session:${id}`, label: "Session", title: sessions.get(id) || id.slice(0, 8) });
  const place = (item, texts, cwd, session, fallback) => {
    item.ticket = placeTicket(texts, prefixes, cwd) ?? (session && sessions.get(session) ? ticketOf(sessions.get(session), prefixes) : null);
    item.bucket = item.ticket ? null : fallback ?? (session ? sessionBucket(session) : null);
  };

  for (const r of rows) {
    const session = r.path.match(/\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\/scratchpad\//)?.[1];
    place(r, [r.path], r.path, session, r.path.includes("/Code/coordinator/") && !session ? COORDINATOR : null);
  }
  const newestPerName = new Map();
  for (const r of rows) {
    const key = `${r.ticket ?? r.bucket?.key ?? rootOf(r.path)}|${r.kind}|${r.name}`;
    if (!newestPerName.has(key) || r.t > newestPerName.get(key).t) newestPerName.set(key, r);
  }
  const files_ = [...newestPerName.values()];

  const wikis = wikiRows(wiki.stdout, host).sort((a, b) => b.t - a.t).slice(0, CAPS.wiki);
  for (const w of wikis) place(w, [w.file, w.subject], null, null, WIKI);
  const artifacts = artifactRows(cache, now, host).sort((a, b) => b.t - a.t).slice(0, CAPS.artifacts);
  for (const a of artifacts) place(a, [a.path, a.name], a.cwd, a.session, null);

  const images = files_.filter((r) => r.kind === "image");
  const pages = files_.filter((r) => r.kind === "page");
  await Promise.all([
    timed("sizes", imageSizes(host, cache, images)),
    timed("titles", fileTitles(host, cache, pages)),
  ]);
  for (const p of pages) if (p.title) p.name = p.title;
  for (const [cached, known] of [[cache.dims, images], [cache.pageTitles, pages]]) {
    const live = new Set(known.map((i) => i.path));
    for (const path of cached.keys()) if (!live.has(path)) cached.delete(path);
  }

  const items = [...files_, ...wikis, ...artifacts].sort((a, b) => b.t - a.t);
  return { items, titles: t3.titles, warnings, timings };
}

export function groupItems(items, titles) {
  const by = new Map();
  for (const it of items) {
    const group = it.ticket ? { key: it.ticket, label: it.ticket, title: titles.get(it.ticket) ?? "" } : it.bucket ?? { key: OTHER, label: OTHER, title: "" };
    if (!by.has(group.key)) by.set(group.key, { ...group, items: [] });
    by.get(group.key).items.push(it);
  }
  return [...by.values()].map((g) => ({ ...g, t: g.items[0].t }))
    .sort((a, b) => (a.key === OTHER) - (b.key === OTHER) || b.t - a.t);
}
