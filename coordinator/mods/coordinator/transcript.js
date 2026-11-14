import { appHome, exec, home, shared, writeTextFile } from "herdr";

// The coordinator runs as pi; its sessions live in the agent's own session folder.
const DIR = `${home()}/.pi/agent-coordinator/sessions/--Users-shyamsivakumar-Code-coordinator--`;
// The pi terminal the panel talks to names its session after its tab.
export const SESSION_NAME = "Pi - Coordinator";
// A throwaway pi run in the same folder must not take the panel over.
const MIN_USERS = 5;
const TASK_ID = /\b[A-Z]{2,5}-\d{1,4}\b/g;
const DETAIL_MAX = 200;
const LINE_MAX = 400;
const OUTPUT_KEEP = 200;
const TEXT_MAX = 60000;
const DIFF_KEEP = 40;
const CODE_KEEP = 400;

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

const blocks = (content) => (Array.isArray(content) ? content : typeof content === "string" ? [{ type: "text", text: content }] : []);

const textOf = (content) => blocks(content).filter((b) => b.type === "text").map((b) => b.text).join("\n\n");

const mimeExt = (mime) => (mime === "image/jpeg" ? "jpg" : String(mime ?? "image/png").replace("image/", ""));

const imageRef = (b) => ({ key: keyOf(b.data), ext: mimeExt(b.mimeType), path: "", data: b.data });

const imagesOf = (content) => blocks(content).filter((b) => b.type === "image").map(imageRef);

const DETAIL_KEYS = ["command", "path", "file_path", "pattern", "query", "prompt", "url", "description", "code"];

function detailOf(args) {
  for (const key of DETAIL_KEYS) {
    const value = args?.[key];
    if (typeof value === "string" && value.trim()) return clip(value.split("\n")[0], DETAIL_MAX);
  }
  return "";
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

function diffOf(name, args) {
  if (name === "write") return { removed: [], added: [], hidden: 0, wrote: lineCount(args?.content ?? "") };
  if (name !== "edit") return null;
  const edits = Array.isArray(args?.edits) && args.edits.length ? args.edits : [{ oldText: args?.oldText, newText: args?.newText }];
  const removed = [];
  const added = [];
  for (const e of edits) {
    const d = trimmedDiff(String(e?.oldText ?? ""), String(e?.newText ?? ""));
    removed.push(...d.removed);
    added.push(...d.added);
  }
  const keep = (lines) => lines.slice(0, DIFF_KEEP).map((l) => clip(l, LINE_MAX));
  return { removed: keep(removed), added: keep(added), hidden: Math.max(0, removed.length - DIFF_KEEP) + Math.max(0, added.length - DIFF_KEEP) };
}

function toolItem(call, at) {
  const args = call.arguments ?? {};
  return {
    k: "tool",
    id: call.id,
    name: call.name.replace(/^mcp__/, "").replace(/__/g, "."),
    at,
    detail: detailOf(args),
    diff: diffOf(call.name, args),
    result: null,
  };
}

function resultOf(result) {
  const text = textOf(result.content);
  const body = text.slice(0, TEXT_MAX).replace(/\n+$/, "");
  return { error: Boolean(result.isError), total: lineCount(text.replace(/\n+$/, "")), lines: body ? body.split("\n").slice(0, OUTPUT_KEEP).map((l) => clip(l, LINE_MAX)) : [] };
}

function summary(tool) {
  const detail = detailOf(tool.arguments ?? {});
  return clip(`${tool.name}${detail ? ` ${detail}` : ""}`.trim(), 90);
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

const newParser = () => ({ turns: [], open: new Map(), tools: new Map(), pending: null, tokens: 0, model: "", errored: false });

const TEMPLATE_MARK = /\]<\][^\[\]]*\[>\[\w*/g;
const ERROR_MESSAGE = /"message"\s*:\s*"([^"]*)"/;
const ERROR_MAX = 140;

const stripMarks = (text) => text.replace(TEMPLATE_MARK, "");

function errorLine(m) {
  const raw = String(m.errorMessage ?? "").trim();
  const message = (ERROR_MESSAGE.exec(raw)?.[1] ?? raw).replace(/\s*\(\d{3}\)\s*$/, "").replace(/\.$/, "");
  return `${m.provider ?? "model"} error: ${clip(message || "unknown error", ERROR_MAX)}. The turn stopped.`;
}

function lastTurn(p, at) {
  if (p.turns.at(-1)?.role !== "coordinator") p.turns.push({ role: "coordinator", at, items: [] });
  const turn = p.turns.at(-1);
  turn.view = null;
  return turn;
}

function feedAssistant(p, m, at) {
  const u = m.usage;
  if (u) p.tokens = (u.input ?? 0) + (u.cacheRead ?? 0) + (u.cacheWrite ?? 0);
  if (m.model) p.model = m.model;
  p.errored = m.stopReason === "error";
  const turn = lastTurn(p, at);
  for (const b of blocks(m.content)) {
    if (b.type === "toolCall") {
      const item = toolItem(b, at);
      turn.items.push(item);
      p.tools.set(b.id, item);
      p.open.set(b.id, { id: b.id, name: b.name, arguments: b.arguments ?? {}, at });
      p.pending = [...p.open.values()].at(-1);
    }
    const text = b.type === "text" ? stripMarks(b.text).trim() : "";
    if (text) {
      turn.items.push({ k: "text", text });
      turn.at = at;
    }
  }
  if (p.errored) turn.items.push({ k: "event", error: true, text: errorLine(m) });
}

function feedModel(p, rec, at) {
  p.model = rec.modelId;
  lastTurn(p, at).items.push({ k: "event", text: `Switched to ${rec.modelId} (${rec.provider})` });
}

const HC_FROM = /^<hc\s+from="([^"]*)"/;
const ANSWERS = /^Decisions:\n/;
const squash = (text) => text.replace(/\s+/g, " ").trim();

// A message the panel sent is the human's, even when it came through a session.
function composed(text, at) {
  const sent = shared("co.sent");
  if (!sent || at < sent.since) return ANSWERS.test(text);
  const wanted = squash(text);
  return sent.items.some((item) => squash(item.text) === wanted);
}

function feedUser(p, m, at) {
  const typed = pathImages(textOf(m.content));
  const raw = typed.rest.replace(/<\/?pasted_content[^>]*>/g, "").trim();
  const images = [...typed.images, ...imagesOf(m.content)];
  const hc = HC_FROM.exec(raw);
  const text = hc ? raw.replace(/<\/?hc\b[^>]*>/g, "").trim() : raw;
  if (!text && !images.length) return;
  if (text.startsWith("<")) return;
  p.open.clear();
  p.tools.clear();
  p.pending = null;
  p.errored = false;
  p.turns.push({
    role: hc && !composed(text, at) ? "session" : "you",
    from: hc?.[1] ?? "",
    at,
    items: [...(text ? [{ k: "text", text }] : []), ...(images.length ? [{ k: "images", images }] : [])],
  });
}

function feedResult(p, m) {
  p.errored = false;
  const item = p.tools.get(m.toolCallId);
  if (item) {
    item.result = resultOf(m);
    const images = imagesOf(m.content);
    if (images.length) item.images = images;
  }
  p.open.delete(m.toolCallId);
  p.tools.delete(m.toolCallId);
  p.pending = [...p.open.values()].at(-1) ?? null;
}

function feed(p, text) {
  for (const line of text.split("\n")) {
    if (!line) continue;
    let rec;
    try {
      rec = JSON.parse(line);
    } catch {
      continue;
    }
    const at = Date.parse(rec.timestamp) || rec.message?.timestamp || 0;
    if (rec.type === "model_change" && rec.modelId) feedModel(p, rec, at);
    if (rec.type !== "message" || !rec.message) continue;
    const m = rec.message;
    if (m.role === "assistant") feedAssistant(p, m, at);
    else if (m.role === "user") feedUser(p, m, at);
    else if (m.role === "toolResult") feedResult(p, m);
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

const MAIN_SESSIONS = `cd "${DIR}" && for f in $(ls -1t *.jsonl 2>/dev/null); do printf '%s\\t%s\\t%s\\n' "$f" "$(grep -m1 '"type":"session_info"' "$f" | grep -o '"name":"[^"]*"' | head -1)" "$(grep -c '"role":"user"' "$f")"; done || true`;

function sessions(rows) {
  return rows
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const [file, name, users] = line.split("\t");
      return { file: `${DIR}/${file}`, name: (name ?? "").replace(/^"name":"|"$/g, ""), users: Number(users) || 0 };
    })
    .filter((row) => row.file);
}

// The live session is the coordinator's own: it carries the coordinator's name
// and has enough turns to be a conversation, not a one-off pi run. The size
// filter alone is the fallback when no session carries that name.
function pickLive(rows) {
  return rows.find((r) => r.name === SESSION_NAME && r.users >= MIN_USERS)
    ?? rows.find((r) => r.users >= MIN_USERS)
    ?? null;
}

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
    model: live.parser.model,
    errored: live.parser.errored,
    lastReplyAt: turns.filter((t) => t.role === "coordinator").at(-1)?.at ?? 0,
  };
}

async function readNow() {
  if (!files.length || Date.now() - filesAt >= FILES_EVERY) {
    const r = await exec("sh", ["-c", MAIN_SESSIONS]);
    if (r.code !== 0) throw new Error(r.stderr.trim() || "cannot list coordinator sessions");
    const rows = sessions(r.stdout);
    const chosen = pickLive(rows);
    if (!chosen) throw new Error("no pi coordinator session");
    files = [chosen.file, ...rows.filter((row) => row.file !== chosen.file).map((row) => row.file)];
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
