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
import { spawnSync } from "node:child_process";
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
const PUSH = SPEC.push_deny;
const PROTECTED = new Set(PUSH.protected);
const FORCE_FLAGS = new Set(PUSH.force_flags);
const MERGE = SPEC.merge_deny || null;
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
  if (isBash) return checkBash(String(input.command || ""), env, cwd);
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

const ASSIGNMENT_RE = /^[A-Za-z_]\w*=/;
const DURATION_RE = /^[\d.]+[smhd]?$/;
const WRAPPERS = new Set(["sudo", "command", "exec", "time", "nohup", "env", "nice", "builtin", "heavy", "timeout", "caffeinate"]);
const SHELLS = new Set(["bash", "sh", "zsh", "dash", "ksh"]);
const COMMAND_NAMES = new Set([...WRAPPERS, ...SHELLS, "git", "gh", "eval"]);
const SEPARATOR_CHARS = ";&|\n()`";
const GIT_VALUE_OPTIONS = new Set(["-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env"]);
const PUSH_VALUE_OPTIONS = new Set(["-o", "--push-option", "--receive-pack", "--exec", "--repo"]);
const BULK_FLAGS = new Set(["--all", "--branches", "--mirror"]);
const GH_VALUE_OPTIONS = new Set(["-R", "--repo", "--hostname"]);
const DIRECTORY_CHANGERS = new Set(["cd", "pushd"]);
const MAX_NESTING = 4;

function baseName(word) {
  return word.slice(word.lastIndexOf("/") + 1);
}

function skipHeredocBodies(text, start, heredocs) {
  let index = start;
  for (const [delimiter, stripTabs] of heredocs) {
    while (index < text.length) {
      const end = text.indexOf("\n", index);
      const line = text.slice(index, end < 0 ? text.length : end);
      index = end < 0 ? text.length : end + 1;
      if ((stripTabs ? line.replace(/^\t+/, "") : line) === delimiter) break;
    }
  }
  return index;
}

function heredocDelimiter(text, start) {
  let delimiter = "";
  let quote = "";
  let index = start;
  while (index < text.length && (quote || !" \t\n;&|()<>".includes(text[index]))) {
    const ch = text[index];
    if (quote) {
      if (ch === quote) quote = "";
      else delimiter += ch;
    } else if (ch === '"' || ch === "'") quote = ch;
    else delimiter += ch;
    index += 1;
  }
  return [delimiter, index];
}

function startsHeredoc(text, index) {
  return text.startsWith("<<", index) && !text.startsWith("<<<", index);
}

function readHeredocStart(text, index) {
  let cursor = index + 2;
  const stripTabs = text.startsWith("-", cursor);
  if (stripTabs) cursor += 1;
  while (cursor < text.length && " \t".includes(text[cursor])) cursor += 1;
  const [delimiter, end] = heredocDelimiter(text, cursor);
  return [[delimiter, stripTabs], end];
}

// The index of the `)` that closes the `$(` whose body starts at `start`.
function substitutionEnd(text, start) {
  let depth = 1;
  let quote = "";
  let heredocs = [];
  let index = start;
  while (index < text.length) {
    const ch = text[index];
    if (quote) {
      if (ch === "\\" && quote === '"') index += 1;
      else if (ch === quote) quote = "";
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "\\") index += 1;
    else if (startsHeredoc(text, index)) {
      const [heredoc, end] = readHeredocStart(text, index);
      heredocs.push(heredoc);
      index = end;
      continue;
    } else if (ch === "\n" && heredocs.length) {
      index = skipHeredocBodies(text, index + 1, heredocs);
      heredocs = [];
      continue;
    } else if (ch === "(") depth += 1;
    else if (ch === ")") {
      depth -= 1;
      if (depth === 0) return index;
    }
    index += 1;
  }
  return text.length;
}

// The simple commands in `text`, each as the words the shell would pass.
// Quoted text stays inside its word, so a protected branch named inside a PR
// body or a message is never a word of the command that carries it. Heredoc
// bodies are skipped; separators (`;`, `&`, `|`, newline, `(`, `)`, backtick)
// end a command.
function shellCommands(text) {
  const commands = [];
  let words = [];
  let word = "";
  let started = false;
  let quote = "";
  let heredocs = [];
  let index = 0;
  const endWord = () => {
    if (started) words.push(word);
    word = "";
    started = false;
  };
  while (index < text.length) {
    const ch = text[index];
    if (quote) {
      if (ch === quote) quote = "";
      else if (quote === '"' && text.startsWith("$(", index)) {
        const end = substitutionEnd(text, index + 2);
        commands.push(...shellCommands(text.slice(index + 2, end)));
        word += text.slice(index, end + 1);
        index = end + 1;
        continue;
      } else if (quote === '"' && ch === "`" && text.indexOf("`", index + 1) > 0) {
        const end = text.indexOf("`", index + 1);
        commands.push(...shellCommands(text.slice(index + 1, end)));
        word += text.slice(index, end + 1);
        index = end + 1;
        continue;
      } else if (ch === "\\" && quote === '"' && index + 1 < text.length && '"\\$`'.includes(text[index + 1])) {
        word += text[index + 1];
        index += 1;
      } else word += ch;
      index += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
    } else if (ch === "\\" && index + 1 < text.length) {
      if (text[index + 1] !== "\n") {
        word += text[index + 1];
        started = true;
      }
      index += 1;
    } else if (ch === "#" && !started) {
      while (index < text.length && text[index] !== "\n") index += 1;
      continue;
    } else if (startsHeredoc(text, index)) {
      endWord();
      const [heredoc, end] = readHeredocStart(text, index);
      heredocs.push(heredoc);
      index = end;
      continue;
    } else if (ch === "&" && started && "<>".includes(word[word.length - 1])) {
      word += ch;
    } else if (ch === " " || ch === "\t") {
      endWord();
    } else if (SEPARATOR_CHARS.includes(ch)) {
      endWord();
      if (words.length) commands.push(words);
      words = [];
      if (ch === "\n" && heredocs.length) {
        index = skipHeredocBodies(text, index + 1, heredocs);
        heredocs = [];
        continue;
      }
    } else {
      word += ch;
      started = true;
    }
    index += 1;
  }
  endWord();
  if (words.length) commands.push(words);
  return commands;
}

// The command's words after env assignments and wrapper commands. `heavy`,
// `timeout`, `sudo` and the like run the command that follows them, so a push
// or merge behind one is still a push or merge.
function realCommand(words) {
  let index = 0;
  while (index < words.length) {
    const word = words[index];
    if (ASSIGNMENT_RE.test(word)) {
      index += 1;
      continue;
    }
    if (!WRAPPERS.has(baseName(word))) break;
    index += 1;
    while (index < words.length) {
      const argument = words[index];
      const takesValue = words[index - 1].startsWith("-") && !COMMAND_NAMES.has(baseName(argument));
      if (argument.startsWith("-") || ASSIGNMENT_RE.test(argument) || DURATION_RE.test(argument) || takesValue) index += 1;
      else break;
    }
  }
  return words.slice(index);
}

// The script a `bash -c` or `eval` command runs, or undefined.
function shellScript(words) {
  const name = baseName(words[0]);
  if (name === "eval") return words.slice(1).join(" ");
  if (SHELLS.has(name)) {
    for (let position = 1; position < words.length; position += 1) {
      if (/^-[A-Za-z]*c[A-Za-z]*$/.test(words[position]) && position + 1 < words.length) return words[position + 1];
    }
  }
  return undefined;
}

// Every real command in `text`, including those inside `bash -c` and `eval`.
function realCommands(text, depth = 0) {
  const found = [];
  for (const raw of shellCommands(text)) {
    const words = realCommand(raw);
    if (!words.length) continue;
    const script = shellScript(words);
    if (script !== undefined && depth < MAX_NESTING) found.push(...realCommands(script, depth + 1));
    found.push(words);
  }
  return found;
}

// The commit a merge's words pin, or "" when the flag is absent or its value
// is not a commit id. The value must be the next word (or `--flag=value`) of
// the same merge invocation; a pin mentioned elsewhere in the command is not
// an argument to the merge.
function pinnedCommit(words) {
  const flag = MERGE.required_flag;
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

// The group and action words of a gh command, plus the words after them.
// Options before the action, such as `-R owner/repo`, are skipped.
function ghCommand(words) {
  const positionals = [];
  let index = 1;
  while (index < words.length && positionals.length < 2) {
    const word = words[index];
    if (word.startsWith("-")) index += GH_VALUE_OPTIONS.has(word) ? 2 : 1;
    else {
      positionals.push(word);
      index += 1;
    }
  }
  return { positionals, rest: words.slice(index) };
}

// A real merge command is denied unless both hold:
//   1. the caller is a gate. The role comes from the environment the gate was
//      launched with, never from the command text, so a builder cannot claim
//      it by typing; a command that mentions the role grants nothing.
//   2. the pin is a merge argument: a commit id passed to --match-head-commit
//      in the same merge invocation.
function mergeDeny(commands, env) {
  if (!MERGE) return undefined;
  const isGate = String((env && env[MERGE.role_env]) || "") === MERGE.role_value;
  for (const words of commands) {
    if (baseName(words[0]) !== "gh") continue;
    const { positionals, rest } = ghCommand(words);
    if (positionals[0] !== "pr" || positionals[1] !== "merge") continue;
    if (!isGate) return MERGE.reason;
    if (!pinnedCommit(rest)) return MERGE.pin_reason || MERGE.reason;
  }
  return undefined;
}

// The destination branch a push argument writes to.
function destinationRef(token) {
  let ref = token.replace(/^\++/, "");
  if (ref.includes(":")) ref = ref.slice(ref.indexOf(":") + 1);
  ref = ref.replace(/^\^+/, "");
  return ref.startsWith("refs/heads/") ? ref.slice("refs/heads/".length) : ref;
}

// The arguments after `git ... push` and the directory git runs in, or
// undefined when this is not a push. The directory is null when `--git-dir`
// or `--work-tree` makes it unknown.
function pushArguments(words, directory) {
  let index = 1;
  while (index < words.length && words[index].startsWith("-")) {
    const word = words[index];
    if (word === "-C" && index + 1 < words.length && directory) directory = path.resolve(directory, words[index + 1]);
    else if (["--git-dir", "--work-tree"].includes(word.split("=")[0])) directory = null;
    index += GIT_VALUE_OPTIONS.has(word) ? 2 : 1;
  }
  if (index < words.length && words[index] === "push") return { args: words.slice(index + 1), directory };
  return undefined;
}

function gitOutput(directory, args) {
  const proc = spawnSync("git", ["-C", directory, ...args], { encoding: "utf8", timeout: 5000 });
  return proc.status === 0 ? String(proc.stdout).trim() : "";
}

// The branch names a push without a refspec writes (the checked-out branch and
// the upstream branch it tracks), or undefined when they cannot be resolved.
function implicitDestinations(directory) {
  if (!directory) return undefined;
  const branch = gitOutput(directory, ["symbolic-ref", "--short", "-q", "HEAD"]);
  if (!branch) return undefined;
  const upstream = gitOutput(directory, ["config", "--get", `branch.${branch}.merge`]);
  return upstream ? [branch, destinationRef(upstream)] : [branch];
}

// Deny a force-push, a bulk push, and a push that can write a protected
// branch. The first bare word after `push` is the repository argument when
// another word follows it: it names a remote or a URL, never a destination
// branch, so a task-branch push to a remote called `main` is not a push to
// main. A lone bare word is read both as a refspec, so `git push main` stays
// refused, and as a remote, so `git push origin` is an implicit push. An
// implicit push (no refspec, or `HEAD`) writes the current branch and its
// upstream: it is refused when either is protected, and refused when the
// branch cannot be resolved (detached HEAD, unknown directory, or a `cd`
// earlier in the command).
function pushVerdict(args, directory, moved) {
  const bare = [];
  let hasRepoOption = false;
  let optionsDone = false;
  let forced = false;
  let bulk = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!optionsDone && arg === "--") optionsDone = true;
    else if (!optionsDone && arg.startsWith("-")) {
      const name = arg.split("=")[0];
      if (name.startsWith("--force") || FORCE_FLAGS.has(name)) forced = true;
      else if (/^-[A-Za-z]+$/.test(arg) && arg.slice(1).includes("f")) forced = true;
      if (BULK_FLAGS.has(name)) bulk = true;
      if (PUSH_VALUE_OPTIONS.has(name)) {
        hasRepoOption = hasRepoOption || name === "--repo";
        if (!arg.includes("=")) index += 1;
      }
    } else bare.push(arg);
  }
  if (forced || bare.some((token) => token.startsWith("+") && token.length > 1)) return PUSH.force_reason;
  const lone = !hasRepoOption && bare.length === 1;
  const refspecs = hasRepoOption || lone ? bare : bare.slice(1);
  if (bulk || refspecs.some((token) => token === ":" || token.includes("*"))) return PUSH.bulk_reason;
  if (refspecs.some((token) => PROTECTED.has(destinationRef(token)))) return PUSH.protected_reason;
  if (lone || !refspecs.length || refspecs.some((token) => token === "HEAD" || token === "@")) {
    const destinations = moved ? undefined : implicitDestinations(directory);
    if (!destinations) return PUSH.ambiguous_reason;
    if (destinations.some((name) => PROTECTED.has(name))) return PUSH.protected_reason;
  }
  return undefined;
}

function pushDeny(commands, directory) {
  let moved = false;
  for (const words of commands) {
    const name = baseName(words[0]);
    moved = moved || DIRECTORY_CHANGERS.has(name);
    if (name !== "git") continue;
    const parsed = pushArguments(words, directory);
    if (!parsed) continue;
    const why = pushVerdict(parsed.args, parsed.directory, moved);
    if (why) return why;
  }
  return undefined;
}

function checkBash(cmd, env, cwd) {
  const commands = realCommands(cmd);
  const decided = mergeDeny(commands, env) || pushDeny(commands, cwd);
  if (decided) return decided;
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
