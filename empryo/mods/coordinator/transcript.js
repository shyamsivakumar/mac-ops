import { exec, home } from "herdr";

const DIR = `${home()}/.claude/projects/-Users-shyamsivakumar-Code-coordinator`;
const TASK_ID = /\b[A-Z]{2,5}-\d{1,4}\b/g;
const READ_TOOLS = new Set(["Read", "Grep", "Glob", "WebFetch", "WebSearch"]);
const EDIT_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);

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

export function toolLine(tools) {
  const parts = [];
  if (tools.commands) parts.push(`ran ${tools.commands} command${tools.commands > 1 ? "s" : ""}`);
  if (tools.reads) parts.push(`read ${tools.reads} file${tools.reads > 1 ? "s" : ""}`);
  if (tools.edits) parts.push(`edited ${tools.edits} file${tools.edits > 1 ? "s" : ""}`);
  if (tools.other) parts.push(`${tools.other} other call${tools.other > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

const FILLER = /^(?:should I |should we |should |do I |do you want me to |I )/i;
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

const newParser = () => ({ turns: [], pending: null, tokens: 0 });

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
      if (turns.at(-1)?.role !== "coordinator") turns.push({ role: "coordinator", at, parts: [], tools: { commands: 0, reads: 0, edits: 0, other: 0 } });
      const turn = turns.at(-1);
      turn.view = null;
      for (const b of Array.isArray(content) ? content : []) {
        if (b.type === "tool_use") {
          p.pending = { ...b, at };
          if (b.name === "Bash") turn.tools.commands++;
          else if (READ_TOOLS.has(b.name)) turn.tools.reads++;
          else if (EDIT_TOOLS.has(b.name)) turn.tools.edits++;
          else turn.tools.other++;
        }
        if (b.type === "text" && b.text.trim()) {
          turn.parts.push(b.text.trim());
          turn.at = at;
        }
      }
    } else if (rec.type === "user" && !rec.isMeta) {
      if (Array.isArray(content) && content.some((b) => b.type === "tool_result")) {
        p.pending = null;
        continue;
      }
      const raw = textOf(content).replace(/<\/?pasted_content[^>]*>/g, "").trim();
      const text = raw.startsWith("<hc ") ? raw.replace(/<\/?hc\b[^>]*>/g, "").trim() : raw;
      if (text && !text.startsWith("<")) turns.push({ role: "you", at, parts: [text], tools: null });
    }
  }
}

const present = (t) => ({ role: t.role, at: t.at, text: t.parts.join("\n\n"), tools: t.tools ? toolLine(t.tools) : "", tasks: t.tools ? [...new Set(t.parts.join("\n").match(TASK_ID) ?? [])].slice(0, 6) : [] });

function join(older, first) {
  const last = older.at(-1);
  if (!last || first?.role !== "coordinator" || last.role !== "coordinator") return older;
  if (!first.parts.length) first.at = last.at;
  first.parts = last.parts.concat(first.parts);
  for (const k of Object.keys(first.tools)) first.tools[k] += last.tools[k];
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

let files = [];
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
  const turns = raw.slice(partial ? 1 : 0).filter((t) => t.parts.length).map((t) => (t.view ??= present(t)));
  const last = turns.at(-1);
  const { pending } = live.parser;
  return {
    turns,
    rev,
    unread: front().before > 0,
    hasOlder: files.some((f) => !loaded.has(f)),
    activity: pending ? summary(pending) : "",
    activityAt: pending?.at ?? 0,
    tokens: live.parser.tokens,
    lastReplyAt: turns.filter((t) => t.role === "coordinator").at(-1)?.at ?? 0,
    asks: last?.role === "coordinator" ? asksOf(last.text) : [],
  };
}

async function readNow() {
  const r = await exec("sh", ["-c", MAIN_SESSIONS]);
  if (r.code !== 0) throw new Error(r.stderr.trim() || "no coordinator transcript");
  files = r.stdout.split("\n").filter(Boolean);
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

let queue = Promise.resolve();

const serial = (fn) => (...args) => {
  const run = queue.then(() => fn(...args));
  queue = run.catch(() => {});
  return run;
};

export const readTranscript = serial(readNow);
export const loadOlder = serial(loadOlderNow);
