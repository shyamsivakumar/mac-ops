// mac-ops deny guard (owner: mac-ops/deny-rules.v1, mac-ops issue #530).
//
// Machine-enforced deny rules for this pi agent directory. The list is the
// single deny list from mac-ops runtime/agents/deny-rules.json;
// scripts/install_deny_rules.py embeds it in SPEC below at install time.
// Do not edit the installed copy by hand: reinstall from mac-ops instead
// (python3 scripts/install_deny_rules.py install).
//
// This guard only denies. It never allows anything and never widens a
// permission: every check returns either a block reason or nothing.
// @ts-nocheck
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SPEC = /*__MAC_OPS_DENY_SPEC__*/{}; // replaced with deny-rules.json by install_deny_rules.py
const HOME = os.homedir();

const ASCEND_ROOTS = (SPEC.ascend_roots || []).map((p) =>
  String(p).startsWith("~") ? HOME + p.slice(1) : p,
);
const SECRET_PATH_RE = new RegExp(SPEC.secret_file_re || "(?!)");
const SECRET_TEXT_RE = new RegExp(SPEC.secret_text_re || "(?!)");
const ASCEND_TEXT_RES = (SPEC.ascend_text_res || []).map((r) => new RegExp(r));
const BASH_DENIES = (SPEC.bash_denies || []).map(([re, why]) => [new RegExp(re), why]);
const MERGE = SPEC.merge_deny || null;
// Only keys that name a location are checked as paths. Prose keys (content,
// pattern, oldText) are not: a document that mentions `.env` or `~/.ssh` is
// not itself a secret, and blocking it would stop the agents from writing
// about this list.
const PATH_KEY = /path|file|dir|folder|target|root|cwd|workspace/i;

function abs(p, cwd) {
  if (!p) return "";
  let s = String(p);
  if (s.startsWith("~")) s = HOME + s.slice(1);
  return path.resolve(cwd || process.cwd(), s);
}

function real(p) {
  try {
    return fs.realpathSync(p);
  } catch {
    return p;
  }
}

function underAscend(a) {
  return ASCEND_ROOTS.some((root) => a === root || a.startsWith(root + path.sep));
}

function secretPath(a) {
  return SECRET_PATH_RE.test(a);
}

// Path-bearing tools (read, edit, write, grep, find, ls, and MCP tools that
// take a path) are denied on Ascend trees; secrets are denied on every
// path-bearing tool except ls, which only lists names.
function checkTool(name, input, cwd) {
  const tool = String(name || "");
  const isBash = tool === "bash" || tool === "powershell";
  if (isBash) return checkBash(String(input.command || ""));
  for (const [key, value] of Object.entries(input || {})) {
    if (typeof value !== "string") continue;
    if (!PATH_KEY.test(key)) continue;
    const a = abs(value, cwd);
    if (!a || a === HOME) continue;
    const r = real(a);
    for (const candidate of a === r ? [a] : [a, r]) {
      if (underAscend(candidate)) return SPEC.ascend_bash_reason;
      if (tool !== "ls" && secretPath(candidate)) return "secret file: " + value;
    }
  }
  return undefined;
}

function checkBash(cmd) {
  for (const [re, why] of BASH_DENIES) {
    if (re.test(cmd)) return why;
  }
  if (MERGE && new RegExp(MERGE.match_re).test(cmd) && !cmd.includes(MERGE.required_flag)) {
    return MERGE.reason;
  }
  if (ASCEND_TEXT_RES.some((re) => re.test(cmd))) return SPEC.ascend_bash_reason;
  const bareLs = /^\s*ls\b/.test(cmd);
  if (!bareLs && SECRET_TEXT_RE.test(cmd)) return SPEC.secret_bash_reason;
  return undefined;
}

export default function (pi) {
  pi.on("tool_call", async (event, ctx) => {
    const cwd = (ctx && ctx.cwd) || process.cwd();
    const why = checkTool(event.toolName, event.input || {}, cwd);
    if (why) {
      return {
        block: true,
        reason: "mac-ops deny rules (#530): " + why + ". This is machine-enforced; route the work instead of working around it.",
      };
    }
    return undefined;
  });
}
