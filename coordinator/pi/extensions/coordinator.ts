// Coordinator guard + wake. Owned by the coordinator config (~/.pi/agent-coordinator).
// Deny-only: nobody watches the tab, so nothing here asks. A blocked call returns a
// reason; the coordinator routes the work to a T3 thread or parks it for Shyam.
// Changing this file needs Shyam's OK (the guard blocks the coordinator from editing it).
// @ts-nocheck
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

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

const FORCE_FLAGS = /--no-verify|--admin\b|--force\b|\s-f\s+origin|\+refs\//;
const FORCE_REASON = "no --no-verify, --admin or force flags";

const DENY: Array<[RegExp, string]> = [
  [new RegExp(GIT_SUB + "(?:commit|push|merge|rebase|reset|revert|cherry-pick|am|clean|restore|switch|checkout|stash|tag|filter-branch|update-ref)\\b"), "git writes belong to T3 threads; send it to the task thread"],
  [new RegExp(GIT_SUB + "(?:branch\\s+-[dDmM]|worktree\\s+(?:remove|prune|move)|gc|prune)\\b"), "git deletions need Shyam's OK"],
  [FORCE_FLAGS, FORCE_REASON],
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

type ShellToken = { value: string; op?: boolean };

function shellSegments(input: string): ShellToken[][] {
  const segments: ShellToken[][] = [];
  let tokens: ShellToken[] = [], word = "", active = false;
  let i = 0, quote = "";
  const heredocs: Array<{ end: string; literal: boolean; tabs: boolean }> = [];
  const flush = () => { if (active) tokens.push({ value: word }); word = ""; active = false; };
  const end = () => { flush(); if (tokens.length) segments.push(tokens); tokens = []; };
  function substitution(backtick: boolean) {
    i += backtick ? 1 : 2;
    const start = i;
    let depth = 1, q = "";
    for (; i < input.length; i++) {
      const c = input[i];
      if (c === "\\") { i++; continue; }
      if (backtick && c === "`") break;
      if (c === "'" && q !== '"') { q = q ? "" : "'"; continue; }
      if (c === '"' && q !== "'") { q = q ? "" : '"'; continue; }
      if (!backtick && q !== "'") {
        if (c === "(") depth++;
        if (c === ")") { depth--; if (depth === 0) break; }
      }
    }
    segments.push(...shellSegments(input.slice(start, i)));
    i++;
  }
  while (i < input.length) {
    const c = input[i];
    if (c === "\\" && quote !== "'") { active = true; word += input[i + 1] || ""; i += 2; continue; }
    if (quote !== "'" && (input.startsWith("$(", i) || c === "`")) { active = true; substitution(c === "`"); continue; }
    if (c === "'" || c === '"') {
      if (!quote) { quote = c; active = true; i++; continue; }
      if (quote === c) { quote = ""; i++; continue; }
    }
    if (quote) { word += c; i++; continue; }
    if (c === "#" && !active) { while (i < input.length && input[i] !== "\n") i++; continue; }
    if (input.startsWith("<<", i) && !input.startsWith("<<<", i)) {
      flush(); i += 2;
      const tabs = input[i] === "-"; if (tabs) i++;
      while (/[ \t]/.test(input[i] || "") && i < input.length) i++;
      let delimiter = "", q = "", literal = false;
      while (i < input.length) {
        const d = input[i];
        if (!q && /[\s;&|<>]/.test(d)) break;
        if (d === "\\") { literal = true; delimiter += input[++i] || ""; i++; continue; }
        if (d === "'" || d === '"') {
          if (!q) { literal = true; q = d; i++; continue; }
          if (q === d) { q = ""; i++; continue; }
        }
        delimiter += d; i++;
      }
      heredocs.push({ end: delimiter, literal, tabs }); continue;
    }
    if (/\s/.test(c)) {
      flush(); i++;
      if (c === "\n") {
        end();
        for (const h of heredocs.splice(0)) {
          let body = "";
          while (i < input.length) {
            const next = input.indexOf("\n", i), stop = next < 0 ? input.length : next;
            const line = input.slice(i, stop); i = stop + 1;
            if ((h.tabs ? line.replace(/^\t+/, "") : line) === h.end) break;
            body += line + "\n";
          }
          if (!h.literal) {
            for (let j = 0; j < body.length; j++) {
              if (body[j] === "\\") { j++; continue; }
              if (body.startsWith("$(", j) || body[j] === "`") {
                const saved = input, savedI = i;
                input = body; i = j; substitution(body[j] === "`"); j = i - 1;
                input = saved; i = savedI;
              }
            }
          }
        }
      }
      continue;
    }
    if (/[;&|()<>]/.test(c)) {
      flush();
      if (c === ">" || c === "<") {
        let op = c; i++;
        if (input[i] === c || input[i] === "|") op += input[i++];
        tokens.push({ value: op, op: true });
      } else { end(); i++; }
      continue;
    }
    active = true; word += c; i++;
  }
  end(); return segments;
}

function checkBash(cmd: string, protectedCwd = false, depth = 0): string | undefined {
  if (depth > 32) return "shell wrapper nesting exceeds guard limit";
  for (const segment of shellSegments(cmd)) {
    const words = segment.filter((t, n) => !t.op && !(n > 0 && segment[n - 1].op)).map(t => t.value);
    let start = 0;
    while (start < words.length) {
      const w = path.basename(words[start]);
      if (/^[A-Za-z_][\w]*=/.test(words[start])) { start++; continue; }
      if (/^(env|command|xargs|time|nohup|nice|timeout)$/.test(w)) {
        start++;
        while (start < words.length && words[start].startsWith("-")) {
          const option = words[start++];
          if (/^(?:-I|-L|-n|-P|-s|-d|-a|-u|--unset|--chdir|-C|--arg-file|--max-args|--max-procs|--replace|-p|--signal|-k|--kill-after|-n|--adjustment)$/.test(option)) start++;
          if (option === "--") break;
        }
        if (w === "timeout") start++;
        if (w === "env" && words.slice(start).every(a => /^[A-Za-z_][\w]*=/.test(a))) return "would print secrets";
        continue;
      }
      break;
    }
    const args = words.slice(start), command = path.basename(args[0] || "");
    if (args.length) args[0] = command;
    const text = args.join(" ");
    if (/^(bash|sh|zsh|eval)$/.test(command)) {
      const codeIndex = command === "eval" ? 1 : args.findIndex(a => /^-[^-]*c/.test(a)) + 1;
      if (codeIndex > 0 && codeIndex < args.length) {
        const why = checkBash(command === "eval" ? args.slice(codeIndex).join(" ") : args[codeIndex], protectedCwd, depth + 1);
        if (why) return why;
      }
    }
    if (/\b(?:shutil\.rmtree|os\.(?:remove|unlink|rmdir)|fs\.(?:rm|unlink))\b/.test(text)) return "deletion needs Shyam's OK";
    for (const [re, why] of DENY) {
      const match = re.exec(text);
      if (match && match.index === 0) return why;
    }
    if (/^(git|gh)$/.test(command) && FORCE_FLAGS.test(text)) return FORCE_REASON;
    const rmWhy = checkRm(text); if (rmWhy) return rmWhy;
    const clob = checkClobber(segment.map(t => t.op ? t.value : JSON.stringify(t.value)).join(" "));
    if (clob) return clob;
    if (segment.some((t, n) => n > 0 && segment[n - 1].value === "<" && SECRET_PATH.test(t.value))) return "touches a secret file";
    if (command === ":" && segment.some(t => t.op && /^>/.test(t.value))) return "truncating files needs Shyam's OK";
    if (/^(cat|less|head|tail|cp|jq|grep|base64|open|source|sed|awk|more|bat|strings|xxd|od|\.)$/.test(command)
        && args.slice(1).some(a => SECRET_PATH.test(a))) return "touches a secret file (.env, auth.json, keys, T3 settings)";
    if (command === "cd") protectedCwd = PROTECTED.test(args[1] || "");
    const mutation = /^(cp|mv|touch|mkdir|ln|install|rsync|chmod|chown|patch|truncate|tee)$/.test(command)
      || /^(sed|perl)$/.test(command) && args.some(a => /^-\w*i/.test(a));
    const targets = segment.filter((t, n) => n > 0 && segment[n - 1].op && /^>/.test(segment[n - 1].value));
    if (targets.some(t => PROTECTED.test(t.value)) || mutation && (protectedCwd || args.slice(1).some(a => PROTECTED.test(a))))
      return "writes into a repo, a T3 worktree or the guard; send the change to a T3 thread";
  }
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
  pi.on("agent_settled", touch);
  pi.on("input", touch);

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
