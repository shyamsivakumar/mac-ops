// mac-ops deny guard (owner: mac-ops/deny-rules.v1, mac-ops issue #530).
//
// Machine-enforced deny rules for this pi agent directory. The list is
// runtime/agents/deny-rules.json; scripts/install_deny_rules.py embeds it in
// SPEC below at install time. Do not edit the installed copy: reinstall.
//
// Each rule belongs to a family whose mode is "ask" or "deny". A deny blocks the
// call. An ask shows the owner a confirm dialog in the interactive TUI and
// blocks in every other mode (rpc, json, print). Shell commands are judged by
// the installed deny-merge-guard.py, so pi and Claude Code share one
// implementation. A hook that cannot run blocks the command.
// @ts-nocheck
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const SPEC = /*__MAC_OPS_DENY_SPEC__*/{}; // replaced with the rules by install_deny_rules.py
const HOME = process.env.HOME || "";
const PREFIX = /^mac-ops deny rules \(#530\): /;
const SECRET_PATH_RE = new RegExp(SPEC.secret_file_re);
const SECRET_TEXT_RE = new RegExp(SPEC.secret_text_re);
const ASCEND_TEXT_RES = SPEC.ascend_text_res.map((r) => new RegExp(r));
const MODES = SPEC.family_modes;
const WRITE_TOOLS = new Set(["edit", "write"]);
const BASH_TOOLS = new Set(["bash", "powershell"]);
// Only keys that name a location are checked as paths: a document that
// mentions `.env` is not itself a secret.
const PATH_KEY = /path|file|dir|folder|target|root|cwd|workspace/i;
// One directory listing, nothing else: `ls ~/.ssh` lists names, while
// `ls ~/.ssh; cat ~/.ssh/id_rsa` reads the key.
const SINGLE_LS = /^\s*ls(?:\s+[^\s;&|<>()$`]+)*\s*$/;

function abs(p, cwd) {
  const s = String(p).startsWith("~") ? HOME + String(p).slice(1) : String(p);
  return path.resolve(cwd || process.cwd(), s);
}

function real(p) {
  const rest = [];
  let head = p;
  for (;;) {
    try {
      return path.join(fs.realpathSync(head), ...rest);
    } catch {
      const parent = path.dirname(head);
      if (parent === head) return p;
      rest.unshift(path.basename(head));
      head = parent;
    }
  }
}

const ASCEND_ROOTS = SPEC.ascend_roots.flatMap((root) => [root, real(root)]);

function underAscend(a) {
  return ASCEND_ROOTS.some((root) => a === root || a.startsWith(root + path.sep));
}

function finding(family, reason, logged = false) {
  return { family, reason, logged, mode: MODES[family] === "ask" ? "ask" : "deny" };
}

function programOf(command) {
  const word = command.trim().split(/\s+/).find((token) => !/^[A-Za-z_]\w*=/.test(token));
  return word ? path.basename(word) : "";
}

function audit(decision, family, tool, text, sessionId) {
  const line = {
    time: new Date().toISOString(),
    runtime: "pi",
    session_id: sessionId,
    tool,
    family,
    decision,
  };
  if (BASH_TOOLS.has(tool)) line.program = programOf(text);
  else line.target = (SECRET_PATH_RE.test(text) ? "[secret]" : text).slice(0, 200);
  try {
    fs.mkdirSync(path.dirname(SPEC.audit_log), { recursive: true });
    fs.appendFileSync(SPEC.audit_log, JSON.stringify(line) + "\n");
  } catch {}
}

function hookFindings(command, env, cwd, sessionId) {
  const payload = JSON.stringify({ tool_name: "Bash", tool_input: { command }, cwd, session_id: sessionId });
  const proc = spawnSync("python3", [SPEC.hook_path], { input: payload, env, encoding: "utf8", timeout: 10000 });
  if (proc.error || proc.status !== 0) {
    return [{ family: "guard", mode: "deny", logged: true, reason: "the shell command guard did not run, so the command is blocked" }];
  }
  if (!proc.stdout.trim()) return [];
  const out = JSON.parse(proc.stdout).hookSpecificOutput;
  const reason = out.permissionDecisionReason.replace(PREFIX, "").split("\ncommand:")[0];
  const family = (reason.match(/^\[([^\]]+)\]/) || [])[1] || "hook";
  return [{ family, mode: out.permissionDecision === "ask" ? "ask" : "deny", logged: true, reason }];
}

function bashFindings(command, env, cwd, sessionId, ascendSession) {
  const found = hookFindings(command, env, cwd, sessionId);
  if (found.some((f) => f.mode === "deny")) return found;
  if (!ascendSession && ASCEND_TEXT_RES.some((re) => re.test(command))) found.push(finding("ascend", SPEC.ascend_bash_reason));
  if (!SINGLE_LS.test(command) && SECRET_TEXT_RE.test(command)) found.push(finding("secret_files", SPEC.secret_bash_reason));
  return found;
}

// Path-bearing tools are checked against the Ascend tree and secret files;
// ls only lists names, so it skips the secret check. Writing a secret file is
// denied; reading one asks.
function toolFindings(name, input, cwd, env, sessionId, ascendSession) {
  const tool = String(name || "");
  if (tool === "bash" || tool === "powershell") return bashFindings(String(input.command || ""), env, cwd, sessionId, ascendSession);
  const found = [];
  for (const [key, value] of Object.entries(input || {})) {
    if (typeof value !== "string" || !PATH_KEY.test(key)) continue;
    const a = abs(value, cwd);
    if (a === HOME) continue;
    for (const candidate of new Set([a, real(a)])) {
      if (!ascendSession && underAscend(candidate)) found.push(finding("ascend", SPEC.ascend_bash_reason));
      if (tool !== "ls" && SECRET_PATH_RE.test(candidate)) {
        const family = WRITE_TOOLS.has(tool) ? "protected_removal" : "secret_files";
        found.push(finding(family, "secret file: " + value));
      }
    }
  }
  return found;
}

function unlogged(found) {
  return [...new Map(found.filter((f) => !f.logged).map((f) => [f.family, f])).values()];
}

function blocked(found, asked) {
  const why = [...new Set(found.map((f) => f.reason))].join("; ");
  const tail = asked
    ? "This needs the owner's approval, which only an interactive thread can give."
    : "This is machine-enforced; route the work instead of working around it.";
  return { block: true, reason: "mac-ops deny rules (#530): " + why + ". " + tail };
}

export default function (pi) {
  let sessionDir = process.cwd();
  pi.on("session_start", async (_event, ctx) => {
    sessionDir = ctx.cwd;
  });
  pi.on("tool_call", async (event, ctx) => {
    try {
      return await decide(event, ctx, sessionDir);
    } catch (error) {
      return blocked([{ reason: "guard error: " + (error && error.message) }], false);
    }
  });
}

async function decide(event, ctx, sessionDir) {
  const cwd = (ctx && ctx.cwd) || process.cwd();
  const sessionId = ctx.sessionManager.getSessionId();
  const env = { ...process.env, CLAUDE_PROJECT_DIR: sessionDir, MAC_OPS_DENY_RUNTIME: "pi" };
  const ascendSession = underAscend(abs(sessionDir));
  const input = event.input || {};
  const found = toolFindings(event.toolName, input, cwd, env, sessionId, ascendSession);
  if (!found.length) return undefined;
  const tool = String(event.toolName || "");
  const text = BASH_TOOLS.has(tool) ? String(input.command || "") : real(abs(String(input.path || input.file_path || cwd), cwd));
  const family = [...new Set(found.map((f) => f.family))].join(",");
  const hard = found.filter((f) => f.mode === "deny");
  if (hard.length) {
    for (const f of unlogged(hard)) audit("deny", f.family, tool, text, sessionId);
    return blocked(hard, false);
  }
  for (const f of unlogged(found)) audit("ask", f.family, tool, text, sessionId);
  if (ctx.mode !== "tui") return blocked(found, true);
  const message = [...new Set(found.map((f) => f.reason))].join("\n") + "\n" + (BASH_TOOLS.has(tool) ? "command: " : tool + ": ") + text.slice(0, 300) + "\ncwd: " + cwd;
  const approved = await ctx.ui.confirm("mac-ops deny rules: " + family, message);
  audit(approved === true ? "approved" : "declined", family, tool, text, sessionId);
  return approved === true ? undefined : blocked(found, true);
}
