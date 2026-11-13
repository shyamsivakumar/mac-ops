// Coordinator guard + wake. Owned by the coordinator config (~/.pi/agent-coordinator).
// Deny-only: nobody watches the tab, so nothing here asks. A blocked call returns a
// reason; the coordinator routes the work to a T3 thread or parks it for Shyam.
// Changing this file needs Shyam's OK (the guard blocks the coordinator from editing it).
// @ts-nocheck
import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import { execFile } from "node:child_process";

const HOME = os.homedir();
const COORD = path.join(HOME, "Code/coordinator");
const SELF = path.join(HOME, ".pi/agent-coordinator");

// ---------- paths ----------
const WRITE_OK = [
  COORD + "/",
  path.join(SELF, "skills") + "/",
  path.join(HOME, ".coordinator/queue") + "/",
  "/tmp/",
  "/private/tmp/",
  "/var/folders/",
  "/private/var/folders/",
];
const SECRET_PATH = /(^|[\/\s'"=])(\.env(\.[\w-]+)?|auth\.json|\.netrc|\.npmrc|\.pypirc|id_[rd]sa\w*|[\w.-]*\.pem|credentials(\.json)?)(?=$|[\s'"\/;|&)])|\.ssh\/|\.aws\/|\.t3\/userdata\/settings\.json|\.config\/gh\/hosts\.yml/;

function abs(p: string, cwd: string) {
  if (!p) return p;
  if (p.startsWith("~")) p = HOME + p.slice(1);
  return path.resolve(cwd, p);
}

// ---------- bash rules ----------
const H = "(?:~|\\$HOME|\\$\\{HOME\\}|" + HOME.replace(/\//g, "\\/") + ")";
// Protected trees: every repo under ~/Code except coordinator, T3 worktrees, this guard.
const PROTECTED = new RegExp(
  H + "\\/(?:Code\\/(?!coordinator(?:\\/|\\b))[^\\s'\";|&)]+|\\.t3\\/worktrees|\\.pi\\/agent-coordinator\\/(?:extensions|settings\\.json|AGENTS\\.md|auth\\.json))",
);
const MUTATING = /(?:^|[^<0-9&])>>?(?!&)|\btee\b|\b(?:cp|mv|rm|rmdir|ln|touch|mkdir|install|rsync|truncate|patch|chmod|chown)\b|\bsed\s+(?:-\w*\s+)*-i|\bperl\s+-\w*i|\bgit\s+apply\b|\bwrite_text\b|open\([^)]*['"][wa]/;
const GIT_SUB = "\\bgit(?:\\s+(?:-C\\s+\\S+|-c\\s+\\S+|--[\\w-]+(?:=\\S+)?))*\\s+";

const DENY: Array<[RegExp, string]> = [
  [new RegExp(GIT_SUB + "(?:commit|push|merge|rebase|reset|revert|cherry-pick|am|clean|restore|switch|checkout|stash|tag|filter-branch|update-ref)\\b"), "git writes belong to T3 threads; send it to the task thread"],
  [new RegExp(GIT_SUB + "(?:branch\\s+-[dDmM]|worktree\\s+(?:remove|prune|move)|gc|prune)\\b"), "git deletions need Shyam's OK"],
  [/--no-verify|--admin\b|--force\b|\s-f\s+origin|\+refs\//, "no --no-verify, --admin or force flags"],
  [/\bgh\s+pr\s+(?:merge|close|ready|edit|review)\b/, "gates merge PRs themselves; the coordinator never does"],
  [/\bgh\s+(?:repo|release|secret|variable|workflow|ruleset)\s+(?:delete|create|edit|set|remove|archive|rename|run|enable|disable)\b/, "repo-level gh writes need Shyam"],
  [/\bgh\s+api\b(?=[^;&|]*(?:-X\s*(?:POST|PUT|PATCH|DELETE)|--method\s+(?:POST|PUT|PATCH|DELETE)|\s-[fF]\s|--(?:raw-)?field|--input))/i, "gh api is read-only here (use gh issue for ticket edits)"],
  [/(?:^|[;&|(`'"]\s*|\bnpx\s+|\bbunx\s+|\$\(\s*)(?:vercel|railway|wrangler|flyctl|fly|netlify|heroku|terraform|pulumi|alchemy)\b/, "deploys and infra go through T3 threads under an approval"],
  [/\brm\s+(?:-\w*[rR]|--recursive)|\bfind\b[^|;&]*\s-(?:delete|exec\s+rm)\b|\bsrm\b|\bshred\b|\bunlink\b|\brmdir\b|\bos\.(?:remove|unlink|rmdir)\b|\bshutil\.rmtree\b|\bfs\.(?:rm|unlink)/, "deletion needs Shyam's OK"],
  [/\btruncate\b|\bcp\s+\/dev\/null\b|:\s*>\s*\S/, "truncating files needs Shyam's OK"],
  [/\blaunchctl\s+(?:bootout|unload|remove|disable|kill)\b/, "stopping launchd jobs needs Shyam's OK"],
  [/\bemp-hub\b|\bemp\s+call\b/, "Empryo is gone; use coordq/t3mcp"],
  [/\bsecurity\s+(?:find|dump|export)-|\bprintenv\b|(?:^|[;&|]\s*)env\s*(?:$|[|;&])|\bset\s*\|/, "would print secrets"],
  [/\bsudo\b/, "no sudo"],
  [/\b(?:npm|pnpm|yarn|bun)\s+(?:i|install|add|publish)\b|\bpip3?\s+install\b|\bbrew\s+(?:install|uninstall|upgrade)\b/, "installs go through a T3 thread"],
];

// Plain rm only for files under temp dirs; anything else is a deletion and needs Shyam.
const TEMP = /^["']?(?:\/tmp\/|\/private\/tmp\/|\/var\/folders\/|\/private\/var\/folders\/|\$TMPDIR\/|\$\{TMPDIR\}\/)/;
function checkRm(cmd: string): string | undefined {
  for (const m of cmd.matchAll(/(?:^|[;&|(`]\s*|\bxargs\s+|\bsudo\s+)rm\s+([^;&|)`]*)/g)) {
    const args = m[1].trim().split(/\s+/).filter((a) => a && !a.startsWith("-"));
    if (!args.length || !args.every((a) => TEMP.test(a))) return "rm outside temp dirs is a deletion; it needs Shyam's OK (move it to $TMPDIR instead if it is scratch)";
  }
  if (/\bxargs\b[^|;&]*\brm\b/.test(cmd)) return "rm via xargs needs Shyam's OK";
  return undefined;
}
// Single > onto an existing coordinator doc wipes it; append with >> or use the edit tool.
function checkClobber(cmd: string): string | undefined {
  for (const m of cmd.matchAll(/(?:^|[^>0-9&])>\|?\s*["']?([^\s"';&|)]+)/g)) {
    let t = m[1];
    if (t.startsWith("/dev/") || TEMP.test(t)) continue;
    const a = abs(t, COORD);
    if (a.startsWith(COORD + "/") && fs.existsSync(a)) return `> would overwrite ${t}; use >> or the edit tool`;
  }
  return undefined;
}

function checkBash(cmd: string): string | undefined {
  for (const [re, why] of DENY) if (re.test(cmd)) return why;
  const rmWhy = checkRm(cmd);
  if (rmWhy) return rmWhy;
  const clob = checkClobber(cmd);
  if (clob) return clob;
  const literal = cmd.match(/^\s*cat\s+(?:>>?\s*(["']?)([^\s"'<>;|&]+)\1\s*<<(["'])([A-Za-z_][A-Za-z0-9_]*)\3|<<(["'])([A-Za-z_][A-Za-z0-9_]*)\5\s*>>?\s*(["']?)([^\s"'<>;|&]+)\7)\s*\n[\s\S]*?\n[A-Za-z_][A-Za-z0-9_]*\s*$/);
  let secretCmd = cmd;
  if (literal) {
    const target = literal[2] || literal[8];
    const delimiter = literal[4] || literal[6];
    const resolvedTarget = abs(target.replace(/^\$(?:TMPDIR|\{TMPDIR\})\//, (process.env.TMPDIR || "/tmp") + "/"), COORD);
    const lines = cmd.trimEnd().split("\n");
    const end = lines.findIndex((line, i) => i > 0 && line === delimiter);
    if (end === lines.length - 1 && (TEMP.test(resolvedTarget) || resolvedTarget.startsWith(COORD + "/"))) secretCmd = lines[0];
  }
  if (SECRET_PATH.test(secretCmd) && !/^\s*ls\b/.test(cmd)) return "touches a secret file (.env, auth.json, keys, T3 settings)";
  return undefined;
}

function checkWrite(p: string, cwd: string): string | undefined {
  const a = abs(p, cwd);
  if (SECRET_PATH.test(a)) return "secret file";
  if (WRITE_OK.some((d) => a.startsWith(d) || a + "/" === d)) return undefined;
  return `the coordinator writes only in ${COORD}, its own skills folder and temp dirs; send repo changes to a T3 thread`;
}

// ---------- backups ----------
// The coordinator folder has no git, so every edit/write of an existing file first
// copies it to ~/.pi/agent-coordinator/backups/<day>/<time>/<relative path>.
function backup(p: string, cwd: string) {
  const a = abs(p, cwd);
  try {
    if (!a.startsWith(COORD + "/") || !fs.statSync(a).isFile()) return;
    const now = new Date().toISOString();
    const dest = path.join(SELF, "backups", now.slice(0, 10), now.slice(11, 19).replace(/:/g, ""), path.relative(COORD, a));
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(a, dest);
  } catch { /* new file: nothing to back up */ }
}

// ---------- mirror ----------
// The phone relay (Claude "Pi - Coordinator") only shows the turns Shyam
// starts from the phone. Every coordinator reply is mirrored there as one
// "Mirror:" message, so the phone shows the whole session. Each assistant
// message that has text is its own mirror, sent in order through one queue
// so two sends never interleave. The mirror goes to exactly one terminal,
// the relay, and a relay that is down only costs the mirror, never the turn.
const MIRROR_TERMINAL = "pi-coord-phone";
const PHONE_MARKER = "From Shyam (phone):";
const TICK_MARKER = "Tick (";
// How much of Shyam's own message the phone shows above the reply, and
// how much of a custom message starts a run with no prompt of its own.
// Both are counts of characters, and both end in an ellipsis.
const MIRROR_QUOTE_MAX = 600;
const EVENT_QUOTE_MAX = 300;
const HC = process.env.COORD_HC_BIN || path.join(HOME, ".local/bin/hc");

function runHc(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(HC, args, { timeout: 15000, maxBuffer: 4 * 1024 * 1024 }, (err, stdout) => {
      if (err) reject(err);
      else resolve(stdout || "");
    });
  });
}

function assistantText(m: any): string {
  const c = m?.content;
  if (typeof c === "string") return c;
  if (!Array.isArray(c)) return "";
  return c
    .filter((x: any) => x && x.type === "text" && typeof x.text === "string")
    .map((x: any) => x.text)
    .join("\n");
}

const flat = (s: string) => (s || "").replace(/\s+/g, " ").trim();

// The text of a custom message that starts a run: a string, or the text
// blocks of an array content.
// A custom message that starts a run: a string, or a message whose
// content is a string or a list of blocks.
type CustomMessage = string | { content?: string | Array<{ type?: string; text?: string }> } | undefined;

function customText(message: CustomMessage): string {
  if (!message) return "";
  if (typeof message === "string") return message;
  const c = message.content;
  if (typeof c === "string") return c;
  if (!Array.isArray(c)) return "";
  return c
    .filter((x) => x && x.type === "text" && typeof x.text === "string")
    .map((x) => x.text as string)
    .join("\n");
}

// Shyam's own message as quoted lines: one "> " per line, the line breaks
// kept, so the phone can tell his words from the reply. A message longer
// than max is cut and ends with an ellipsis. The cut counts characters,
// not code units, so an emoji is never split in half.
function quoteText(text: string, max: number): string {
  const t = (text || "").replace(/\r\n?/g, "\n").trim();
  if (!t) return "";
  const chars = Array.from(t);
  const cut = chars.length > max ? chars.slice(0, max - 1).join("") + "…" : t;
  return cut
    .split("\n")
    .map((line) => (line.trim() ? "> " + line : ">"))
    .join("\n");
}

// The phone marker goes, so the quote holds Shyam's words and not the
// relay's wrapper.
function stripPhone(input: string): string {
  const s = input || "";
  const i = s.indexOf(PHONE_MARKER);
  if (i < 0) return s.trim();
  return (s.slice(0, i) + " " + s.slice(i + PHONE_MARKER.length)).trim();
}

// The kind of one mirror: "you" (typed here), "phone", "tick" or "event".
// A run with no prompt of its own is an event: its reply is still the
// coordinator talking, so it belongs on the phone.
export function mirrorLabel(input: string): string {
  const t = flat(input);
  if (!t) return "event";
  // A phone turn is labelled, not skipped: the relay forwards Shyam's
  // message but never sees the reply, so the phone needs the mirror.
  if (t.includes(PHONE_MARKER)) return "phone";
  if (t.startsWith(TICK_MARKER)) return "tick";
  return "you";
}

// The mirror text for one assistant message, or "" when it is not mirrored.
// The kind sits on its own first line, Shyam's own message is quoted under
// it, and the reply keeps its line breaks, bullets and table rows: the
// phone reads a paragraph otherwise.
export function mirrorText(input: string, reply: string, custom?: CustomMessage): string {
  // A carriage return would act as an Enter in the relay's terminal, so it
  // goes; the trailing blank lines go; every other line break stays.
  const body = (reply || "").replace(/\r\n?/g, "\n").replace(/\s+$/, "");
  if (!body.trim()) return "";
  const kind = mirrorLabel(input);
  // A tick that found nothing to do says so and stays off the phone.
  if (kind === "tick" && body.trim() === "NOOP") return "";
  // A tick has no message of Shyam's to quote, so it shows only its kind.
  let quote = "";
  if (kind === "you") quote = quoteText(input, MIRROR_QUOTE_MAX);
  else if (kind === "phone") quote = quoteText(stripPhone(input), MIRROR_QUOTE_MAX);
  else if (kind === "event") quote = quoteText(customText(custom), EVENT_QUOTE_MAX);
  const head = `Mirror: ${kind}`;
  return quote ? `${head}\n${quote}\n\n${body}` : `${head}\n\n${body}`;
}

// Sends one mirror message to the relay. A missing or dead relay is skipped.
export async function sendMirror(text: string): Promise<boolean> {
  if (!text) return false;
  try {
    const listed = JSON.parse(await runHc(["ls", "--json"]));
    const terms = (listed.terminals || []).filter(
      (t: any) => t?.name === MIRROR_TERMINAL && t?.state === "live",
    );
    if (!terms.length) return false;
    await runHc(["send", terms[0].address, text]);
    return true;
  } catch {
    return false;
  }
}

// One queue for every send, so two mirrors never interleave on the relay.
let mirrorQueue: Promise<unknown> = Promise.resolve();

function enqueueMirror(text: string): void {
  mirrorQueue = mirrorQueue.then(() => sendMirror(text)).catch(() => undefined);
}

// Waits for every queued mirror to finish. The probe uses it to read the
// sends after the events have been delivered.
export function flushMirrors(): Promise<unknown> {
  return mirrorQueue;
}

// ---------- wake ----------
const WAKE_MIN = Number(process.env.COORD_WAKE_MIN || 30);
const TICK_PROMPT = process.env.COORD_TICK_PROMPT ||
  "Tick (auto-wake). Run one tick per loop/tick.md. Keep it cheap: filter command output, act only on what changed, reply NOOP or ALERT lines only.";

export default function (pi: any) {
  let ctxRef: any;
  let lastActivity = Date.now();
  let wakeOn = process.env.COORD_WAKE !== "0";
  let timer: any;

  pi.on("tool_call", async (event: any, ctx: any) => {
    const cwd = ctx?.cwd || process.cwd();
    const name = event.toolName;
    const input = event.input || {};
    let why: string | undefined;
    if (name === "bash") why = checkBash(String(input.command || ""));
    else if (name === "write" || name === "edit") why = checkWrite(String(input.path || input.file_path || ""), cwd);
    else if (name === "read" && SECRET_PATH.test(abs(String(input.path || ""), cwd))) why = "secret file";
    if (why) return { block: true, reason: `Coordinator guard: ${why}. Do not work around it; route it or park it in loop/decisions.md.` };
    if (name === "write" || name === "edit") backup(String(input.path || input.file_path || ""), cwd);
  });

  const touch = (_e: any, ctx: any) => { lastActivity = Date.now(); if (ctx) ctxRef = ctx; };
  pi.on("session_start", touch);
  pi.on("agent_start", touch);
  pi.on("input", touch);

  // The newest user input, which names the mirror, and the prompt that
  // started the current run. The input event fires for every message Shyam
  // sends, including one that joins a run that is already going, so the
  // label of a reply is the input it answers.
  let latestInput = "";
  let runPrompt = "";
  // The custom message that started a run with no prompt of its own.
  let runCustom: CustomMessage = undefined;
  pi.on("input", (event: any) => {
    if (typeof event?.text === "string" && event.text.trim()) latestInput = event.text;
  });
  pi.on("before_agent_start", (event: any) => {
    if (event?.messageType === "user" && typeof event.prompt === "string" && event.prompt.trim()) {
      runPrompt = event.prompt;
      latestInput = event.prompt;
      runCustom = undefined;
      return;
    }
    // A run that no user message started (a custom message such as a
    // GitHub-bot note, a continuation) has no label of its own: the
    // previous run's input must not name it. The custom message is
    // quoted when it carries text.
    if (event?.messageType === "custom") {
      runPrompt = "";
      latestInput = "";
      runCustom = event.message as CustomMessage;
      return;
    }
    if (event?.messageType) {
      runPrompt = "";
      latestInput = "";
      runCustom = undefined;
    }
  });

  pi.on("message_end", (event: any, ctx: any) => {
    if (event?.message?.role !== "assistant") return;
    const text = assistantText(event.message);
    if (!text.trim()) return;
    // Only the interactive coordinator session mirrors. A headless tick run
    // (pi -p) is not a coordinator turn Shyam is watching.
    if (ctx?.mode && ctx.mode !== "tui") return;
    const mirror = mirrorText(latestInput || runPrompt, text, runCustom);
    if (!mirror) return;
    // Fire and forget: the turn never waits on the relay.
    enqueueMirror(mirror);
  });

  pi.on("agent_settled", async (event: any, ctx: any) => {
    touch(event, ctx);
  });

  function arm() {
    clearInterval(timer);
    timer = setInterval(() => {
      if (!wakeOn || !ctxRef) return;
      try {
        if (!ctxRef.isIdle() || ctxRef.hasPendingMessages()) return;
      } catch { return; }
      if (Date.now() - lastActivity < WAKE_MIN * 60_000) return;
      lastActivity = Date.now();
      pi.sendUserMessage(TICK_PROMPT);
    }, 60_000);
    timer.unref?.();
  }
  pi.on("session_start", () => { arm(); try { if (!pi.getSessionName?.()) pi.setSessionName("Pi - Coordinator"); } catch {} });
  pi.on("session_shutdown", () => clearInterval(timer));

  pi.registerCommand("tick", {
    description: "Run one coordinator tick now",
    handler: async () => { lastActivity = Date.now(); pi.sendUserMessage(TICK_PROMPT); },
  });
  pi.registerCommand("wake", {
    description: "Auto-wake: /wake on | off | status",
    handler: async (args: string, ctx: any) => {
      const a = (args || "").trim();
      if (a === "on") wakeOn = true;
      if (a === "off") wakeOn = false;
      ctx.ui.notify(`auto-wake ${wakeOn ? "on" : "off"}, every ${WAKE_MIN} min when idle`, "info");
    },
  });
}

export { checkBash, checkWrite };
