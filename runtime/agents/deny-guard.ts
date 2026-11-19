// mac-ops deny guard (owner: mac-ops/deny-rules.v1, mac-ops issue #530).
//
// Machine-enforced deny rules for this pi agent directory. The list is
// runtime/agents/deny-rules.json; scripts/install_deny_rules.py embeds it in
// SPEC below at install time. Do not edit the installed copy: reinstall.
//
// The guard only denies. Every check returns a block reason or nothing. Shell
// commands are judged by the installed deny-merge-guard.py (the push and merge
// rules), so pi and Claude Code share one implementation. A hook that cannot
// run blocks the command.
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

function hookReason(command, env, cwd) {
  const payload = JSON.stringify({ tool_name: "Bash", tool_input: { command }, cwd });
  const proc = spawnSync("python3", [SPEC.hook_path], { input: payload, env, encoding: "utf8", timeout: 10000 });
  if (proc.error || proc.status !== 0) return "the shell command guard did not run, so the command is blocked";
  if (!proc.stdout.trim()) return undefined;
  return JSON.parse(proc.stdout).hookSpecificOutput.permissionDecisionReason.replace(PREFIX, "");
}

function checkBash(command, env, cwd) {
  const decided = hookReason(command, env, cwd);
  if (decided) return decided;
  if (ASCEND_TEXT_RES.some((re) => re.test(command))) return SPEC.ascend_bash_reason;
  if (!SINGLE_LS.test(command) && SECRET_TEXT_RE.test(command)) return SPEC.secret_bash_reason;
  return undefined;
}

// Path-bearing tools are denied on Ascend trees; secrets are denied on every
// path-bearing tool except ls, which only lists names.
function checkTool(name, input, cwd, env) {
  const tool = String(name || "");
  if (tool === "bash" || tool === "powershell") return checkBash(String(input.command || ""), env, cwd);
  for (const [key, value] of Object.entries(input || {})) {
    if (typeof value !== "string" || !PATH_KEY.test(key)) continue;
    const a = abs(value, cwd);
    if (a === HOME) continue;
    for (const candidate of new Set([a, real(a)])) {
      if (underAscend(candidate)) return SPEC.ascend_bash_reason;
      if (tool !== "ls" && SECRET_PATH_RE.test(candidate)) return "secret file: " + value;
    }
  }
  return undefined;
}

export default function (pi) {
  pi.on("tool_call", async (event, ctx) => {
    const cwd = (ctx && ctx.cwd) || process.cwd();
    const why = checkTool(event.toolName, event.input || {}, cwd, process.env);
    if (!why) return undefined;
    return {
      block: true,
      reason: "mac-ops deny rules (#530): " + why + ". This is machine-enforced; route the work instead of working around it.",
    };
  });
}
