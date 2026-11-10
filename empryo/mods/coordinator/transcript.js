import { appHome, exec, home, shared, writeTextFile } from "herdr";

const DIR = `${home()}/.claude/projects/-Users-shyamsivakumar-Code-coordinator`;
const TASK_ID = /\b[A-Z]{2,5}-\d{1,4}\b/g;
const DETAIL_MAX = 200;
const LINE_MAX = 400;
const OUTPUT_KEEP = 200;
const TEXT_MAX = 60000;
const DIFF_KEEP = 40;
const CODE_KEEP = 400;
const EVENT_MAX = 200;

const IMAGE_SOURCE = /\[Image: source: ([^\]]+)\]/g;
const IMAGE_MARK = /\[Image #\d+\]/g;
const IMAGE_PATH = /(^|\s)((?:\/|~\/)[^\n]*?\.(?:png|jpe?g|gif|webp|heic))(?=\s|$)/gi;
const SAMPLES = 8;
const SAMPLE_LEN = 64;
const IMAGE_DIR = "data/coordinator/img";

function keyOf(text) {
  let h = 5381;
  const mix = (s) => {
    for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  };
  mix(String(text.length));
  const span = Math.max(0, text.length - SAMPLE_LEN);
  for (let n = 0; n < SAMPLES; n++) {
    const at = Math.floor((span * n) / (SAMPLES - 1));
    mix(text.slice(at, at + SAMPLE_LEN));
  }
  return `${h.toString(36)}${text.length.toString(36)}`;
}

const extOf = (path) => /\.([a-z0-9]{2,5})$/i.exec(path)?.[1].toLowerCase() ?? "png";

const fileImage = (path) => ({ key: keyOf(path), ext: extOf(path), path, data: null });

export function pathImages(text) {
  const paths = [...text.matchAll(IMAGE_PATH)].map((m) => (m[2].startsWith("~/") ? `${home()}${m[2].slice(1)}` : m[2]));
  return { images: paths.map(fileImage), rest: text.replace(IMAGE_PATH, "$1") };
}

export function imagePathSpans(text) {
  return [...text.matchAll(IMAGE_PATH)].map((m) => ({ start: m.index + m[1].length, end: m.index + m[0].length, path: m[2] }));
}

export function draftText(content) {
  let out = "";
  let at = 0;
  for (const { range, token } of [...content.tokens].sort((a, b) => a.range.start - b.range.start)) {
    out += content.text.slice(at, range.start) + token.text;
    at = range.end;
  }
  return out + content.text.slice(at);
}

const SHOT_TIME = /\bat (\d{1,2})\.(\d{2})\.\d{2}\s*([AP]M)/i;

export function chipLabel(path) {
  const shot = SHOT_TIME.exec(path);
  return shot ? `📷 Screenshot ${shot[1]}:${shot[2]} ${shot[3].toUpperCase()}` : `📷 ${path.slice(path.lastIndexOf("/") + 1)}`;
}

function resultImages(content) {
  if (!Array.isArray(content)) return [];
  return content
    .filter((b) => b.type === "image" && b.source?.type === "base64")
    .map((b) => ({ key: keyOf(b.source.data), ext: b.source.media_type === "image/jpeg" ? "jpg" : b.source.media_type.replace("image/", ""), path: "", data: b.source.data }));
}

export async function materialize(ref) {
  const dir = `${appHome()}/${IMAGE_DIR}`;
  const file = `${dir}/${ref.key}.${ref.ext}`;
  if ((await exec("test", ["-f", file])).code !== 0) {
    await exec("mkdir", ["-p", dir]);
    if (ref.path) {
      if ((await exec("cp", [ref.path, file])).code !== 0) return null;
    } else {
      const b64 = `${dir}/${ref.key}.b64`;
      await exec("rm", ["-f", b64]);
      await writeTextFile(b64, ref.data, null);
      const r = await exec("/usr/bin/base64", ["-D", "-i", b64, "-o", file]);
      await exec("rm", ["-f", b64]);
      if (r.code !== 0) throw new Error(r.stderr.trim() || "cannot decode image");
    }
  }
  ref.data = null;
  const dims = await exec("sips", ["-g", "pixelWidth", "-g", "pixelHeight", file]);
  const w = Number(/pixelWidth: (\d+)/.exec(dims.stdout)?.[1]);
  const h = Number(/pixelHeight: (\d+)/.exec(dims.stdout)?.[1]);
  if (!w || !h) throw new Error("cannot read image size");
  return { file, rel: `${IMAGE_DIR}/${ref.key}.${ref.ext}`, w, h };
}

const clip = (text, n) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

function textOf(content) {
  if (typeof content === "string") return content;
  return (content ?? []).filter((b) => b.type === "text").map((b) => b.text).join("\n\n");
}

function summary(tool) {
  const i = tool.input ?? {};
  const detail = i.description ?? i.command ?? i.file_path ?? i.pattern ?? i.prompt ?? i.query ?? "";
  return clip(`${tool.name} ${String(detail).split("\n")[0]}`.trim(), 90);
}

const lineCount = (text) => (text ? (text.match(/\n/g)?.length ?? 0) + 1 : 0);

function trimmedDiff(before, after) {
  const a = before.split("\n");
  const b = after.split("\n");
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a.at(-1 - tail) === b.at(-1 - tail)) tail++;
  return { removed: a.slice(head, a.length - tail), added: b.slice(head, b.length - tail) };
}

function diffOf(name, input) {
  if (name === "Write") return { removed: [], added: [], hidden: 0, wrote: lineCount(input.content ?? "") };
  const edits = name === "MultiEdit" ? input.edits ?? [] : [input];
  const removed = [];
  const added = [];
  for (const e of edits) {
    const d = trimmedDiff(String(e.old_string ?? ""), String(e.new_string ?? ""));
    removed.push(...d.removed);
    added.push(...d.added);
  }
  const keep = (lines) => lines.slice(0, DIFF_KEEP).map((l) => clip(l, LINE_MAX));
  return { removed: keep(removed), added: keep(added), hidden: Math.max(0, removed.length - DIFF_KEEP) + Math.max(0, added.length - DIFF_KEEP) };
}

const DIFF_TOOLS = new Set(["Edit", "MultiEdit", "Write"]);

function toolItem(b, at) {
  const i = b.input ?? {};
  const detail = i.command ?? i.file_path ?? i.notebook_path ?? i.pattern ?? i.url ?? i.query ?? i.description ?? i.prompt ?? i.path ?? "";
  return { k: "tool", id: b.id, name: b.name.replace(/^mcp__/, "").replace(/__/g, "."), at, detail: clip(String(detail).split("\n")[0], DETAIL_MAX), diff: DIFF_TOOLS.has(b.name) ? diffOf(b.name, i) : null, result: null };
}

function resultOf(block) {
  const text = textOf(block.content);
  const body = text.slice(0, TEXT_MAX).replace(/\n+$/, "");
  return { error: Boolean(block.is_error), total: lineCount(text.replace(/\n+$/, "")), lines: body ? body.split("\n").slice(0, OUTPUT_KEEP).map((l) => clip(l, LINE_MAX)) : [] };
}

const FENCE = /^\s*```/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
function cellsOf(line) {
  const s = line.trim();
  const cells = [];
  let cell = "";
  let ticked = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === "\\" && s[i + 1] === "|") {
      cell += "|";
      i++;
    } else if (ch === "`") {
      ticked = !ticked;
      cell += ch;
    } else if (ch === "|" && !ticked) {
      cells.push(cell.trim());
      cell = "";
    } else cell += ch;
  }
  cells.push(cell.trim());
  if (s.startsWith("|")) cells.shift();
  if (s.endsWith("|") && !s.endsWith("\\|") && cells.at(-1) === "") cells.pop();
  return cells;
}
const plain = (cell) => cell.replace(/\*\*|__/g, "").replace(/`/g, "");

function tableOf(rows) {
  const cols = Math.max(...rows.map((r) => r.length));
  const grid = rows.map((r) => Array.from({ length: cols }, (_x, c) => ({ text: plain(r[c] ?? ""), mono: /^`[^`]+`$/.test(r[c] ?? "") })));
  const longest = (c, measure) => Math.max(...grid.map((r) => measure(r[c].text)));
  return {
    t: "table",
    head: grid[0],
    rows: grid.slice(1),
    ideal: Array.from({ length: cols }, (_x, c) => longest(c, (s) => s.length)),
    min: Array.from({ length: cols }, (_x, c) => longest(c, (s) => Math.max(0, ...s.split(/\s+/).map((w) => w.length)))),
  };
}

export function blocksOf(text) {
  const lines = text.split("\n");
  const out = [];
  let md = [];
  const flush = () => {
    const joined = md.join("\n").trim();
    if (joined) out.push({ t: "md", text: joined });
    md = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (FENCE.test(line)) {
      flush();
      const body = [];
      for (i++; i < lines.length && !FENCE.test(lines[i]); i++) body.push(lines[i]);
      out.push({ t: "code", lines: body.slice(0, CODE_KEEP).map((l) => clip(l, LINE_MAX)), more: Math.max(0, body.length - CODE_KEEP) });
    } else if (TABLE_ROW.test(line) && TABLE_RULE.test(lines[i + 1] ?? "")) {
      flush();
      const rows = [cellsOf(line)];
      for (i += 2; i < lines.length && TABLE_ROW.test(lines[i]); i++) rows.push(cellsOf(lines[i]));
      i--;
      out.push(tableOf(rows));
    } else md.push(line);
  }
  flush();
  return out;
}

const FILLER = /^(?:should I |should we |should |do I |do you want me to |I )/i;
const ANSWERS = /^\d+\. /;
const squash = (text) => text.replace(/\s+/g, " ").trim();

function composed(text, at) {
  const sent = shared("co.sent");
  if (!sent || at < sent.since) return ANSWERS.test(text);
  const wanted = squash(text);
  return sent.items.some((item) => squash(item.text) === wanted);
}
const MARKER = /\(?\s*\bRecommended:\s*(.*?)\)?\s*$/i;

const cleanOption = (p) => p.replace(FILLER, "").replace(/[?.\s]+$/, "").trim();

function optionsOf(question) {
  const body = question.replace(/^[^:]*:\s*/, "");
  const parts = body.split(/,\s*or\s+|\s+or\s+/i).map(cleanOption);
  if (parts.length < 2 || parts.length > 4) return [];
  if (parts.some((p) => p.length < 3 || p.length > 80)) return [];
  return parts.map((p) => p[0].toUpperCase() + p.slice(1));
}

function recommendationOf(raw, options) {
  const answer = raw.trim();
  if (!answer) return null;
  const key = cleanOption(answer).toLowerCase();
  const keys = options.map((o) => o.toLowerCase());
  const at = keys.includes(key) ? keys.indexOf(key) : keys.findIndex((o) => o.includes(key) || key.includes(o));
  if (at >= 0) return { answer, reason: "", kind: "option", text: options[at] };
  const yesNo = /^(yes|no)\b/i.exec(answer);
  if (yesNo) {
    const kind = yesNo[1].toLowerCase();
    return { answer: kind, reason: answer.includes(",") ? answer.slice(answer.indexOf(",") + 1).trim() : "", kind, text: kind };
  }
  return { answer, reason: "", kind: "text", text: answer };
}

export function asksOf(text) {
  const out = [];
  let fenced = false;
  for (const raw of text.split("\n")) {
    if (raw.startsWith("```")) fenced = !fenced;
    const cleaned = raw.replace(/^\s*(?:[-*]|\d+[.)])\s+/, "").replace(/\*\*|`/g, "").trim();
    if (fenced || !cleaned || cleaned.startsWith("|")) continue;
    const marker = MARKER.exec(cleaned);
    const line = marker ? cleaned.slice(0, marker.index).trim() : cleaned;
    const first = out.length;
    for (const s of line.match(/[^.!?]+[.!?]?/g) ?? []) {
      const q = s.trim();
      if (q.endsWith("?") && q.length > 8) out.push({ text: q, options: optionsOf(q), recommended: null });
    }
    if (marker && out.length > first) {
      const last = out.at(-1);
      last.recommended = recommendationOf(marker[1], last.options);
    }
  }
  return out.slice(0, 5);
}

const newParser = () => ({ turns: [], open: new Map(), tools: new Map(), pending: null, tokens: 0 });

const NOTE_SUMMARY = /<summary>([\s\S]*?)<\/summary>/;

function lastTurn(p, at) {
  if (p.turns.at(-1)?.role !== "coordinator") p.turns.push({ role: "coordinator", at, items: [] });
  const turn = p.turns.at(-1);
  turn.view = null;
  return turn;
}

function feed(p, text) {
  const { turns } = p;
  for (const line of text.split("\n")) {
    if (!line) continue;
    let rec;
    try {
      rec = JSON.parse(line);
    } catch {
      continue;
    }
    if (rec.isSidechain || !rec.message) continue;
    const at = Date.parse(rec.timestamp);
    const content = rec.message.content;
    if (rec.type === "assistant") {
      const u = rec.message.usage;
      if (u) p.tokens = (u.input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0);
      const turn = lastTurn(p, at);
      for (const b of Array.isArray(content) ? content : []) {
        if (b.type === "tool_use") {
          const item = toolItem(b, at);
          turn.items.push(item);
          p.tools.set(b.id, item);
          p.open.set(b.id, { ...b, at });
          p.pending = [...p.open.values()].at(-1);
        }
        if (b.type === "text" && b.text.trim()) {
          turn.items.push({ k: "text", text: b.text.trim() });
          turn.at = at;
        }
      }
    } else if (rec.type === "user" && rec.isMeta) {
      const last = turns.at(-1);
      const attached = [...textOf(content).matchAll(IMAGE_SOURCE)].map((m) => fileImage(m[1].trim()));
      if (attached.length && last && last.role !== "coordinator") {
        const strip = last.items.find((i) => i.k === "images");
        if (strip) strip.images.push(...attached);
        else last.items.push({ k: "images", images: attached });
        last.view = null;
      }
    } else if (rec.type === "user" && !rec.isMeta) {
      if (Array.isArray(content) && content.some((b) => b.type === "tool_result")) {
        for (const b of content) {
          if (b.type !== "tool_result") continue;
          const item = p.tools.get(b.tool_use_id);
          if (item) {
            item.result = resultOf(b);
            const images = resultImages(b.content);
            if (images.length) item.images = images;
          }
          p.open.delete(b.tool_use_id);
          p.tools.delete(b.tool_use_id);
        }
        p.pending = [...p.open.values()].at(-1) ?? null;
        continue;
      }
      const typed = pathImages(textOf(content));
      const whole = typed.rest;
      const images = [...whole.matchAll(IMAGE_SOURCE)].map((m) => fileImage(m[1].trim()));
      for (const ref of typed.images) if (!images.some((i) => i.path === ref.path)) images.push(ref);
      const raw = whole.replace(IMAGE_SOURCE, "").replace(IMAGE_MARK, "").replace(/<\/?pasted_content[^>]*>/g, "").trim();
      const hc = /^<hc\s+from="([^"]*)"/.exec(raw);
      const text = hc ? raw.replace(/<\/?hc\b[^>]*>/g, "").trim() : raw;
      const note = raw.startsWith("<task-notification") ? NOTE_SUMMARY.exec(raw)?.[1].trim() : null;
      if (note) lastTurn(p, at).items.push({ k: "event", text: clip(note.replace(/\s+/g, " "), EVENT_MAX) });
      else if ((text || images.length) && !text.startsWith("<")) {
        p.open.clear();
        p.tools.clear();
        p.pending = null;
        turns.push({ role: hc && !composed(text, at) ? "session" : "you", from: hc?.[1] ?? "", at, items: [...(text ? [{ k: "text", text }] : []), ...(images.length ? [{ k: "images", images }] : [])] });
      }
    }
  }
}

function present(t) {
  const texts = t.items.filter((i) => i.k === "text").map((i) => i.text);
  return {
    role: t.role,
    from: t.from ?? "",
    at: t.at,
    text: texts.join("\n\n"),
    items: t.items.map((i) => (i.k === "text" ? { k: "text", blocks: blocksOf(i.text) } : i)),
    tasks: t.role === "coordinator" ? [...new Set(texts.join("\n").match(TASK_ID) ?? [])].slice(0, 6) : [],
  };
}

function join(older, first) {
  const last = older.at(-1);
  if (!last || first?.role !== "coordinator" || last.role !== "coordinator") return older;
  if (!first.items.length) first.at = last.at;
  first.items = last.items.concat(first.items);
  first.view = null;
  return older.slice(0, -1);
}

const CHUNK = 2 * 1024 * 1024;
const BLOCK = 1024 * 1024;
const WINDOW = 'open F, "<", $ARGV[0] or die "$!"; my $e = $ARGV[1] < 0 ? -s F : $ARGV[1]; my $s = $e - $ARGV[2]; $s = 0 if $s < 0; seek F, $s > 0 ? $s - 1 : 0, 0; read F, my $d, $e - $s + ($s > 0 ? 1 : 0); if ($s > 0) { my $i = index($d, "\n"); if ($i < 0) { $d = ""; } else { $d = substr($d, $i + 1); $s += $i; } } my $j = rindex($d, "\n"); $d = $j < 0 ? "" : substr($d, 0, $j + 1); print "$s\n", $s + length($d), "\n", $d;';
const SLICE = 'open F, "<", $ARGV[0] or die "$!"; seek F, $ARGV[1], 0; read F, my $d, $ARGV[2]; $d .= <F> if $d !~ /\n/ && !eof(F); my $i = rindex($d, "\n"); $d = $i < 0 ? "" : substr($d, 0, $i + 1); print length($d), "\n", $d;';

async function chunk(file, offset) {
  const r = await exec("perl", ["-e", SLICE, file, String(offset), String(CHUNK)]);
  if (r.code !== 0) throw new Error(r.stderr.trim() || "cannot read coordinator transcript");
  const at = r.stdout.indexOf("\n");
  return { bytes: Number(r.stdout.slice(0, at)), text: r.stdout.slice(at + 1) };
}

async function slice(file, offset) {
  let bytes = 0;
  let text = "";
  for (let next = await chunk(file, offset); next.bytes; next = await chunk(file, offset + bytes)) {
    bytes += next.bytes;
    text += next.text;
  }
  return { bytes, text };
}

async function window(file, end) {
  for (let len = BLOCK; ; len *= 2) {
    const r = await exec("perl", ["-e", WINDOW, file, String(end), String(len)]);
    if (r.code !== 0) throw new Error(r.stderr.trim() || "cannot read coordinator transcript");
    const a = r.stdout.indexOf("\n");
    const b = r.stdout.indexOf("\n", a + 1);
    const start = Number(r.stdout.slice(0, a));
    if (b + 1 < r.stdout.length || start === 0) return { start, end: Number(r.stdout.slice(a + 1, b)), text: r.stdout.slice(b + 1) };
  }
}

const MAIN_SESSIONS = `cd "${DIR}" && for f in $(ls -t *.jsonl); do if [ "$(grep -c '"type":"user"' "$f")" -ge 5 ]; then echo "${DIR}/$f"; fi; done`;

const FILES_EVERY = 30000;
let files = [];
let filesAt = 0;
let live = null;
let rev = 0;
const hist = { file: null, before: 0, lead: [] };
const loaded = new Set();

const front = () => (hist.file ? hist : live);

async function readBefore(target) {
  const w = await window(target.file, target.before);
  const p = newParser();
  feed(p, w.text);
  const first = target.before < 0 ? null : (target.lead[0] ?? (target === live ? live.parser.turns[0] : null));
  target.lead = join(p.turns, first).concat(target.lead);
  target.before = w.start;
  rev++;
}

function snapshot() {
  const raw = hist.lead.concat(live.lead, live.parser.turns);
  const partial = front().before > 0 && raw[0]?.role === "coordinator";
  const turns = raw.slice(partial ? 1 : 0).filter((t) => t.items.length).map((t) => (t.view ??= present(t)));
  const last = turns.at(-1);
  const { pending } = live.parser;
  return {
    turns,
    rev,
    unread: front().before > 0,
    hasOlder: files.some((f) => !loaded.has(f)),
    pendingId: pending?.id ?? "",
    activity: pending ? summary(pending) : "",
    activityAt: pending?.at ?? 0,
    tokens: live.parser.tokens,
    lastReplyAt: turns.filter((t) => t.role === "coordinator").at(-1)?.at ?? 0,
    asks: last?.role === "coordinator" ? asksOf(last.text) : [],
  };
}

async function readNow() {
  if (!files.length || Date.now() - filesAt >= FILES_EVERY) {
    const r = await exec("sh", ["-c", MAIN_SESSIONS]);
    if (r.code !== 0) throw new Error(r.stderr.trim() || "no coordinator transcript");
    files = r.stdout.split("\n").filter(Boolean);
    filesAt = Date.now();
  }
  if (live?.file !== files[0]) {
    if (live) {
      while (live.before > 0) await readBefore(live);
      hist.file ??= live.file;
      hist.lead = hist.lead.concat(live.lead, live.parser.turns);
    }
    live = { file: files[0], offset: 0, before: -1, lead: [], parser: newParser() };
    loaded.add(files[0]);
    const w = await window(live.file, -1);
    feed(live.parser, w.text);
    live.offset = w.end;
    live.before = w.start;
    rev++;
  }
  const { bytes, text } = await slice(live.file, live.offset);
  if (bytes) {
    live.offset += bytes;
    feed(live.parser, text);
    rev++;
  }
  return snapshot();
}

const visible = () => snapshot().turns.length;

async function loadOlderNow(want) {
  if (front().before === 0) {
    const file = files.find((f) => !loaded.has(f));
    loaded.add(file);
    hist.file = file;
    hist.before = -1;
  }
  const target = front();
  const had = visible();
  do await readBefore(target);
  while (target.before > 0 && visible() - had < want);
  return snapshot();
}

const READ_LIMIT = 45000;

const within = (cx, work) => new Promise((resolve, reject) => {
  let limit;
  work.then(resolve, reject).finally(() => limit?.cancel());
  limit = cx.timer.after(READ_LIMIT, () => reject(new Error("reading the Coordinator transcript timed out")));
});

let running = null;

const serial = (fn) => async (cx, ...args) => {
  while (running) {
    if (Date.now() - running.since >= READ_LIMIT) throw new Error("previous transcript read still running");
    await running.settled;
  }
  const work = fn(...args);
  const mine = { since: Date.now() };
  const clear = () => {
    if (running === mine) running = null;
  };
  mine.settled = work.then(clear, clear);
  running = mine;
  return within(cx, work);
};

export const readTranscript = serial(readNow);
export const loadOlder = serial(loadOlderNow);
