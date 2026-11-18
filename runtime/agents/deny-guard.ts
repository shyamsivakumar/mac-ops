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
const MERGE_RE = MERGE ? new RegExp(MERGE.match_re) : null;
const PIN_RE = new RegExp((MERGE && MERGE.pin_re) || "(?!)");
// Only keys that name a location are checked as paths. Prose keys (content,
// pattern, oldText) are not: a document that mentions `.env` or `~/.ssh` is
// not itself a secret, and blocking it would stop the agents from writing
// about this list.
const PATH_KEY = /path|file|dir|folder|target|root|cwd|workspace/i;
// One directory listing, nothing else: no separators, pipes, redirects or
// substitutions after the command. `ls ~/.ssh` is a name listing;
// `ls ~/.ssh; cat ~/.ssh/id_rsa` is a read of the key and is denied.
const SINGLE_LS = /^\s*ls(?:\s+[^\s;&|<>()$`]+)*\s*$/;
const SHELL_SEPARATORS = /[;&|\n]+/;

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
function checkTool(name, input, cwd, env) {
  const tool = String(name || "");
  const isBash = tool === "bash" || tool === "powershell";
  if (isBash) return checkBash(String(input.command || ""), env);
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

// The merge flags that take a value. The word after one of these is that
// flag's value, so it is never a merge argument of its own.
const MERGE_VALUE_FLAGS = new Set([
  "--body",
  "-b",
  "--body-file",
  "-F",
  "--subject",
  "-t",
  "--author-email",
]);

// The words the shell would pass to `gh`, with quoted text kept as one word.
// A split on whitespace turns the inside of a quoted argument into words of its
// own, so a flag and a commit id written inside a PR subject would read as a
// merge argument.
function mergeWords(segment) {
  const words = [];
  let word = "";
  let quote = "";
  let started = false;
  for (let i = 0; i < segment.length; i += 1) {
    const ch = segment[i];
    if (quote) {
      if (ch === quote) quote = "";
      else if (ch === "\\" && quote === '"' && i + 1 < segment.length) {
        word += segment[i + 1];
        i += 1;
      } else word += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
      continue;
    }
    if (/\s/.test(ch)) {
      if (started) words.push(word);
      word = "";
      started = false;
      continue;
    }
    word += ch;
    started = true;
  }
  if (started) words.push(word);
  return words;
}

// The commit a merge segment pins, or "" when the flag is absent or its value
// is not a commit id. The value must be the next word (or `--flag=value`) of
// the same `gh pr merge` invocation; a pin mentioned elsewhere in the command
// is not an argument to the merge.
function pinnedCommit(segment) {
  const flag = MERGE.required_flag;
  const words = mergeWords(segment);
  let i = 0;
  while (i < words.length) {
    const word = words[i];
    if (word === flag) {
      const value = words[i + 1] || "";
      return PIN_RE.test(value) ? value : "";
    }
    if (word.startsWith(flag + "=")) {
      const value = word.slice(flag.length + 1);
      return PIN_RE.test(value) ? value : "";
    }
    i += MERGE_VALUE_FLAGS.has(word) ? 2 : 1;
  }
  return "";
}

// `gh pr merge` is denied unless both hold:
//   1. the caller is a gate. The role comes from the environment the gate was
//      launched with, never from the command text, so a builder cannot claim
//      it by typing; a command that mentions the role grants nothing.
//   2. the pin is a merge argument: a commit id passed to --match-head-commit
//      in the same `gh pr merge` invocation.
function mergeDeny(cmd, env) {
  if (!MERGE || !MERGE_RE.test(cmd)) return undefined;
  const role = String((env && env[MERGE.role_env]) || "");
  if (role !== MERGE.role_value) return MERGE.reason;
  for (const segment of cmd.split(SHELL_SEPARATORS)) {
    if (!MERGE_RE.test(segment)) continue;
    if (!pinnedCommit(segment)) return MERGE.pin_reason || MERGE.reason;
  }
  return undefined;
}

function checkBash(cmd, env) {
  for (const [re, why] of BASH_DENIES) {
    if (re.test(cmd)) return why;
  }
  const merge = mergeDeny(cmd, env);
  if (merge) return merge;
  if (ASCEND_TEXT_RES.some((re) => re.test(cmd))) return SPEC.ascend_bash_reason;
  if (!SINGLE_LS.test(cmd) && SECRET_TEXT_RE.test(cmd)) return SPEC.secret_bash_reason;
  return undefined;
}

export default function (pi) {
  pi.on("tool_call", async (event, ctx) => {
    const cwd = (ctx && ctx.cwd) || process.cwd();
    const why = checkTool(event.toolName, event.input || {}, cwd, process.env);
    if (why) {
      return {
        block: true,
        reason: "mac-ops deny rules (#530): " + why + ". This is machine-enforced; route the work instead of working around it.",
      };
    }
    return undefined;
  });
}
