// The hub as the cockpit sees it: threads that need Shyam, grouped by project, and the calls that act on them.

import { exec, home, readTextFile } from "herdr";
import { endsWithAsk } from "./asks.js";

const LIVE = ["preparing", "queued", "starting", "running", "waiting", "failed", "interrupted"];
const RUNNING = new Set(["preparing", "queued", "starting", "running"]);
const KIND = { waiting: "wait", failed: "fail", interrupted: "stop", completed: "done", idle: "idle" };
const IDLE_PAGES = 4;
const DEFAULT_CAP = 6;
const URGENCY = { ask: 0, wait: 1, fail: 2, stop: 3, run: 4, done: 5, idle: 6 };
const TASK_ID = /[A-Z]{2,5}-\d+/;
const REVIEW_TITLE = /^[A-Z]{2,5}-\d+ (?:gate )?review\b/i;
const PAGES = 3;

let idleThreads = { at: 0, list: [] };
const IDLE_EVERY = 60000;
let projects = { at: 0, names: new Map(), roots: new Map() };
const asks = new Map();

function failureMessage(output) {
  let text;
  try {
    text = JSON.parse(output)[0].text;
  } catch {
    return output.trim() || null;
  }
  try {
    return JSON.parse(text).message ?? text;
  } catch {
    return text;
  }
}

export async function call(tool, args) {
  const r = await exec(`${home()}/.local/bin/t3mcp`, ["call", tool, JSON.stringify(args)]);
  if (r.code !== 0) throw new Error(failureMessage(r.stderr) ?? `${tool} failed`);
  const value = JSON.parse(r.stdout);
  if (Array.isArray(value)) throw new Error(failureMessage(r.stdout) ?? `${tool} returned an error response`);
  return value;
}

async function readAll(args) {
  const items = [];
  let read;
  let after;
  do {
    read = await call("t3_thread_read", { ...args, limit: 100, ...(after === undefined ? {} : { afterPosition: after }) });
    items.push(...read.items);
    const advanced = read.items.length > 0 && (after === undefined || read.nextPosition > after);
    after = read.nextPosition;
    if (!advanced) break;
  } while (read.hasMore);
  return { ...read, items };
}

async function threads(filter, pages = PAGES) {
  const all = [];
  let cursor;
  for (let page = 0; page < pages; page++) {
    const r = await call("t3_thread_list", { allProjects: true, includeSubagents: false, limit: 100, ...filter, ...(cursor === undefined ? {} : { cursor }) });
    all.push(...r.threads);
    cursor = r.nextCursor;
    if (cursor === null || cursor === undefined) break;
  }
  return all;
}

export async function projectNames() {
  if (Date.now() - projects.at < 60000) return projects.names;
  const r = await call("t3_project_list", { limit: 100 });
  projects = { at: Date.now(), names: new Map(r.projects.map((p) => [p.id, p.title])), roots: new Map(r.projects.map((p) => [p.id, p.workspaceRoot])) };
  return projects.names;
}

function questionOf(read) {
  const q = read.questions?.[0] ?? read;
  const text = q.question ?? q.prompt ?? q.message ?? q.text ?? q.header ?? "";
  const options = (q.options ?? []).map((o) => o.label ?? o).filter((o) => typeof o === "string");
  return [text, options.length ? `[${options.join(" / ")}]` : ""].filter(Boolean).join(" ");
}

async function askOf(thread) {
  if (thread.pendingUnknown) return "pending request unknown";
  const cached = asks.get(thread.threadId);
  if (cached?.stamp === thread.updatedAt) return cached.text;
  const requestIds = thread.requestIds ?? [];
  const text = requestIds.length
    ? questionOf(await call("t3_pending_request", { action: "read", threadId: thread.threadId, requestId: requestIds[0] })) || "Waiting for your answer"
    : "Waiting for an approval";
  asks.set(thread.threadId, { stamp: thread.updatedAt, text });
  return text;
}

export function shortModel(model) {
  if (!model) return "";
  const parts = model.split("/");
  const id = parts.at(-1);
  if (id === "default" && parts.length > 1) return parts.at(-2);
  if (/^minimax/i.test(id)) return "minimax";
  return id.replace(/^gpt-[\d.]+-/, "").replace(/^claude-/, "").replace(/-[\d.]+(-.*)?$/, "");
}

const CONTEXT = { idle: "Not started", run: "Running", fail: "The last run failed", stop: "The run was interrupted", done: "Finished, not settled" };

export function plainError(raw) {
  const text = raw.replace(/^session\/\w+:\s*/, "").replace(/\b(.{6,}?)(?: — \1)+/g, "$1");
  const model = text.match(/^Model "(?:subscriptions\/)?([^"]+)" is not available/);
  if (model) return `Model ${model[1]} isn't available`;
  const tool = text.match(/failed the same way (\d+) times/);
  if (tool) return `Stopped: the same tool failed ${tool[1]} times`;
  if (text.includes("stream stalled")) return "Stalled with no output";
  const provider = text.match(/^Provider request failed \(HTTP (4\d\d)\) from (?:api\.)?(\w+)\./);
  if (provider) return `${provider[2][0].toUpperCase()}${provider[2].slice(1)} rejected the request (HTTP ${provider[1]})`;
  return text;
}

function card(thread, names) {
  const kind = RUNNING.has(thread.status) ? "run" : KIND[thread.status];
  const task = TASK_ID.exec(thread.title)?.[0] ?? "";
  const led = task && thread.title.startsWith(`${task} · `);
  return {
    key: thread.threadId,
    task,
    led,
    title: led ? thread.title.slice(task.length + 3) : thread.title,
    project: names.get(thread.projectId) ?? "No project",
    projectId: thread.projectId,
    link: thread.link,
    kind,
    model: thread.model ?? "",
    taskType: thread.taskType ?? "",
    review: thread.taskType ? thread.taskType === "review" : REVIEW_TITLE.test(thread.title),
    at: Date.parse(thread.updatedAt),
    created: Date.parse(thread.createdAt),
    runStarted: thread.activeRunStartedAt ? Date.parse(thread.activeRunStartedAt) : null,
    status: thread.status,
    ask: Boolean(thread.ask),
    context: thread.pendingUnknown ? "pending request unknown" : kind === "fail" && thread.lastError ? plainError(thread.lastError) : kind === "done" && thread.askText ? thread.askText : CONTEXT[kind] ?? "",
    error: kind === "fail" ? thread.lastError ?? CONTEXT.fail : undefined,
    prs: (thread.pullRequests ?? []).map((p) => ({ repo: p.repository, number: p.number, url: p.url, state: p.state })),
  };
}

const byUrgency = (a, b) => URGENCY[a.kind] - URGENCY[b.kind] || b.at - a.at;

export function group(cards) {
  const groups = new Map();
  for (const c of cards) {
    const key = c.task || c.key;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  return [...groups].map(([key, threads]) => {
    threads.sort(byUrgency);
    const lead = threads.find((c) => c.led) ?? threads[0];
    const running = threads.filter((c) => c.kind === "run" && c.status !== "queued");
    const prs = new Map(threads.flatMap((c) => c.prs).map((p) => [`${p.repo}#${p.number}`, p]));
    return { key, task: threads[0].task, title: lead.title, project: lead.project, threads, primary: threads[0], kind: threads[0].kind, at: Math.max(...threads.map((c) => c.at)), runSince: running.some((c) => c.runStarted) ? Math.min(...running.map((c) => c.runStarted).filter(Boolean)) : null, prs: [...prs.values()] };
  });
}

const TASK_STATUS = { run: "running", wait: "waiting", ask: "waiting", fail: "failed", stop: "stopped", done: "done", idle: "idle" };

function taskMap(cards) {
  const tasks = {};
  for (const c of [...cards].sort((a, b) => b.at - a.at)) {
    if (c.task && !tasks[c.task]) tasks[c.task] = { status: TASK_STATUS[c.kind], title: c.title, key: c.key };
  }
  return tasks;
}

async function idleList() {
  if (Date.now() - idleThreads.at > IDLE_EVERY) idleThreads = { at: Date.now(), list: await threads({ statuses: ["idle"], settled: false }, IDLE_PAGES) };
  return idleThreads.list;
}

const runStarts = new Map();
const failures = new Map();

async function runStartOf(thread) {
  const known = runStarts.get(thread.threadId);
  if (known && known.run === thread.latestRunId) return known.at;
  const read = await call("t3_thread_read", { threadId: thread.threadId, limit: 1, runLimit: 1 }).catch(() => null);
  const run = read?.recentRuns?.at(-1);
  if (!run || !(run.status === "running" || run.runId === read.thread.activeRunId)) return null;
  runStarts.set(thread.threadId, { run: thread.latestRunId, at: run.startedAt });
  return run.startedAt;
}

const FAILURE_TAIL = 40;
const ASK_TAIL = 8;
const TAIL_BATCH = 12;
const lastLine = (text) => (text ?? "").split("\n").map((line) => line.trim()).filter(Boolean).at(-1) ?? null;
const DECISIONS_FILE = `${home()}/Code/coordinator/decisions.json`;
const DECISIONS_EVERY = 30000;
const DECISIONS_RETRY = 10000;
let asked = { at: 0, items: [], cards: [] };

// The coordinator's own ask list, as cards on the board.
async function questions() {
  if (Date.now() - asked.at < (asked.ok ? DECISIONS_EVERY : DECISIONS_RETRY)) return asked.cards;
  let file;
  try {
    file = JSON.parse(await readTextFile(DECISIONS_FILE));
  } catch {
    asked = { at: Date.now(), ok: false, items: asked.items, cards: asked.cards };
    return asked.cards;
  }
  const items = Array.isArray(file?.items) ? file.items : [];
  const at = Date.parse(file?.updated ?? "") || Date.now();
  const cards = items.filter((item) => item && item.id && item.title).map((item) => ({
    key: `ask:${item.id}`,
    task: "",
    led: false,
    title: String(item.title),
    project: item.group ? String(item.group) : "Coordinator",
    projectId: null,
    link: null,
    kind: "ask",
    model: "",
    taskType: "",
    review: false,
    at,
    created: at,
    runStarted: null,
    status: "waiting",
    context: item.why ? String(item.why) : "The coordinator asks for a decision",
    prs: [],
  }));
  asked = { at: Date.now(), ok: true, items, cards };
  return cards;
}
const TEXT_CAP = 50000;
const TAIL_CAP = 2000;
const TEXT_CHUNKS = 6;

// The end of a long message, so an ask on the last line is not missed.
async function endOf(thread, item) {
  let text = item.text ?? "";
  let offset = item.textTruncated ? item.nextTextOffset : null;
  for (let i = 0; offset !== null && offset !== undefined && i < TEXT_CHUNKS; i++) {
    const chunk = await call("t3_thread_read", { threadId: thread.threadId, itemId: item.itemId, textOffset: offset, maxCharsPerItem: TEXT_CAP }).catch(() => null);
    const next = chunk?.items?.find((item) => item.type === "assistant_message");
    if (!next) break;
    text += next.text ?? "";
    offset = next.textTruncated ? next.nextTextOffset : null;
  }
  return text;
}

// The last assistant message and error of a thread, cached until the thread changes.
async function tailOf(thread, items) {
  const known = failures.get(thread.threadId);
  if (known?.stamp === thread.updatedAt) return known;
  const from = thread.itemCount - items;
  try {
    const read = await call("t3_thread_read", { threadId: thread.threadId, view: "activity", limit: 100, maxCharsPerItem: TAIL_CAP, ...(from > 0 ? { afterPosition: from } : {}) });
    const reversed = [...read.items].reverse();
    const message = reversed.find((item) => item.type === "assistant_message");
    const error = reversed.find((item) => item.type === "error");
    const text = message ? await endOf(thread, message) : "";
    const value = { stamp: thread.updatedAt, ask: Boolean(message) && endsWithAsk(text), text: lastLine(text), error: error?.text ?? error?.title ?? null };
    failures.set(thread.threadId, value);
    return value;
  } catch {
    return { unread: true, ask: false, text: null, error: null };
  }
}

export async function load() {
  const [live, finished, names, questionsAsked] = await Promise.all([
    threads({ statuses: LIVE }),
    threads({ statuses: ["completed"], settled: false }),
    projectNames(),
    questions(),
  ]);
  for (let offset = 0; offset < live.length; offset += 8) {
    await Promise.all(live.slice(offset, offset + 8).map(async (thread) => {
      try {
        const waiting = await call("t3_pending_request", { action: "list", threadId: thread.threadId });
        thread.requestIds = waiting.requestIds;
        if (waiting.requestIds.length) thread.status = "waiting";
      } catch {
        thread.pendingUnknown = true;
      }
      if (RUNNING.has(thread.status)) thread.activeRunStartedAt = await runStartOf(thread);
      if (thread.status === "failed") {
        const tail = await tailOf(thread, FAILURE_TAIL);
        thread.lastError = tail.unread ? CONTEXT.fail : tail.error ?? "No failure text recorded";
        thread.ask = tail.ask;
        thread.askText = tail.text;
      } else if (thread.status === "interrupted") {
        const tail = await tailOf(thread, ASK_TAIL);
        thread.ask = tail.ask;
        thread.askText = tail.text;
      }
    }));
  }
  for (let offset = 0; offset < finished.length; offset += TAIL_BATCH) {
    await Promise.all(finished.slice(offset, offset + TAIL_BATCH).map(async (thread) => {
      const tail = await tailOf(thread, ASK_TAIL);
      thread.ask = tail.ask;
      thread.askText = tail.text;
    }));
  }
  const cards = [...live, ...finished].filter((t) => !t.snoozed && !(t.settled && t.status !== "running")).map((t) => card(t, names));
  cards.push(...questionsAsked);
  await Promise.all(cards.filter((c) => c.kind === "wait").map(async (c) => {
    const thread = live.find((t) => t.threadId === c.key);
    c.context = await askOf(thread).catch(() => "Waiting for your answer");
  }));
  const count = (kind) => cards.filter((c) => c.kind === kind).length;
  return {
    at: Date.now(),
    running: count("run"),
    waiting: count("wait"),
    failed: count("fail") + count("stop"),
    dead: cards.filter((c) => (c.kind === "fail" || c.kind === "stop") && !c.ask).length,
    done: count("done"),
    groups: group(cards),
    tasks: taskMap(cards),
  };
}

export async function queueStatus() {
  const r = await exec("coordq", ["status"]);
  if (r.code !== 0) return null;
  const q = JSON.parse(r.stdout);
  return [q.cap, q.live, q.queued].every(Number.isFinite) ? q : null;
}

export async function loadBacklog() {
  const [idle, names] = await Promise.all([idleList(), projectNames()]);
  const queued = idle.filter((t) => !t.snoozed && !(t.settled && t.status !== "running")).map((t) => card(t, names));
  return { backlog: group(queued).sort((a, b) => a.at - b.at), tasks: taskMap(queued) };
}

const verdicts = new Map();
const RETRY_VERDICT = 30000;

const NO_FINDING = /^(none|n\/a|0)\b/i;

function judge(text) {
  const last = text.split("\n").map((l) => l.trim()).filter(Boolean).at(-1);
  const crit = /(\d+)\s+critical/i.exec(text);
  const major = /(\d+)\s+major/i.exec(text);
  const counts = crit || major ? `${Number(crit?.[1] ?? 0)}C ${Number(major?.[1] ?? 0)}M` : "verdict FAIL";
  if (last === "VERDICT: PASS") return { state: "pass", label: "rev pass" };
  if (last === "VERDICT: FAIL") return { state: "fail", label: `rev ${counts}` };
  if (crit || major) {
    return Number(crit?.[1] ?? 0) + Number(major?.[1] ?? 0) === 0 ? { state: "pass", label: "rev pass" } : { state: "fail", label: `rev ${counts}` };
  }
  const findings = [...text.matchAll(/^[\s\-*]*\**(?:critical|major)\**\s*[—:–-]\s*\**\s*(.*)$/gim)].filter((m) => !NO_FINDING.test(m[1]));
  if (findings.length) return { state: "fail", label: `rev ${findings.length} found` };
  if (/\b(no (critical|major|blocking)[a-z ]*(findings|issues)|no findings|lgtm|approved|passes?)\b/i.test(text)) return { state: "pass", label: "rev pass" };
  return { state: "unknown", label: "rev ?" };
}

export const verdictEntries = (threads) => threads.filter((c) => verdicts.has(c.key)).map((c) => [c.key, verdicts.get(c.key)]);
export const seedVerdicts = (entries) => entries.forEach(([key, value]) => verdicts.set(key, value));
export const verdictOf = (thread) => verdicts.get(thread.key)?.verdict ?? null;
export const runModelOf = (thread) => verdicts.get(thread.key)?.runModel ?? "";

const VENDORS = [[/gpt|codex/i, "openai"], [/claude|opus|sonnet|haiku|anthropic/i, "anthropic"], [/glm|zai|zhipu/i, "zhipu"], [/minimax/i, "minimax"], [/cursor/i, "cursor"]];
export const vendorOf = (model) => (model ? VENDORS.find(([pattern]) => pattern.test(model))?.[1] ?? null : null);

function vendorGate(verdict, reviewModel, authorModel) {
  if (verdict.state !== "pass" && verdict.state !== "unknown") return verdict;
  const reviewer = vendorOf(reviewModel);
  const author = vendorOf(authorModel);
  if (!author || !reviewer) return { ...verdict, note: "author unknown: vendor not checked" };
  return reviewer === author ? { state: "fail", label: "rev ✗ same vendor" } : verdict;
}

const newestRun = (read) => (read?.recentRuns ?? []).reduce((latest, run) =>
  !latest || run.ordinal > latest.ordinal ? run : latest, null);

const actualModel = (read, fallback) => {
  const run = newestRun(read)?.model;
  return vendorOf(run) ? run : fallback || "";
};

export async function loadVerdict(thread, author) {
  const stamp = `${thread.key}@${thread.at}+${author?.key}@${author?.at}`;
  const known = verdicts.get(thread.key);
  if (known?.stamp === stamp && !(known.retryAt <= Date.now())) return;
  try {
    const [read, authorRead] = await Promise.all([
      readAll({ threadId: thread.key }),
      author ? call("t3_thread_read", { threadId: author.key, limit: 1 }) : null,
    ]);
    const run = newestRun(read);
    const last = [...read.items].reverse().find((i) => i.type === "assistant_message" && i.runId === run?.runId);
    const runModel = run?.model ?? "";
    const verdict = vendorGate(judge(last?.text ?? ""), actualModel(read, thread.model), author ? actualModel(authorRead, author.model) : "");
    verdicts.set(thread.key, { stamp, verdict, runModel });
  } catch {
    verdicts.set(thread.key, { stamp, verdict: { state: "unverified", label: "rev ? unreadable, retrying" }, runModel: known?.runModel ?? "", retryAt: Date.now() + RETRY_VERDICT });
  }
}

export async function queueCap() {
  const text = await readTextFile(`${home()}/Code/coordinator/queue/config.json`);
  const cap = text ? Number(JSON.parse(text).cap) : DEFAULT_CAP;
  return Number.isFinite(cap) && cap > 0 ? cap : DEFAULT_CAP;
}

export async function openThread(thread) {
  if (!thread.link?.startsWith("https://app.t3.codes/threads/")) throw new Error("T3 thread link not available");
  const result = await exec("/usr/bin/open", [thread.link]);
  if (result.code !== 0) throw new Error("Could not open T3 thread");
}

export const sendArgs = (key, message) => ({ threadId: key, message, mode: "auto" });
export const sendReply = (key, message) => call("t3_thread_send", sendArgs(key, message));
export const settle = (key) => call("t3_thread_organize", { threadId: key, action: "settle" });
const ASCEND = new Set(["action-underwriting-hub", "ascend-mcp", "data-ops", "dbt", "omni"]);
const relays = new Map();

export async function mergePlan(card) {
  try {
    const pr = card.info?.pr;
    if (!pr || !/^[\w.-]+\/[\w.-]+$/.test(pr.repo) || !Number.isInteger(pr.number) || pr.number <= 0) return { refused: "No valid PR on this card" };
    if (ASCEND.has(pr.repo.split("/").at(-1).toLowerCase())) return { refused: "Ascend repos cannot merge from Cockpit" };
    const r = await exec("gh", ["pr", "view", String(pr.number), "-R", pr.repo, "--json", "state,isDraft,mergeable,headRefOid"]);
    if (r.code !== 0) throw new Error(r.stderr.trim() || "PR lookup failed");
    const head = JSON.parse(r.stdout);
    if (head.state !== "OPEN" || head.isDraft || head.mergeable !== "MERGEABLE") return { refused: "PR must be open, ready and mergeable" };
    if (!/^[a-f0-9]{40}$/.test(head.headRefOid)) return { refused: "PR head SHA unknown" };
    const review = card.threads.filter((t) => t.review && t.kind === "done").sort((a, b) => b.at - a.at)[0];
    if (!review || !card.threads.some((t) => !t.review && t.key !== review.key)) return { refused: "No separate review thread found" };
    const read = await readAll({ threadId: review.key, maxCharsPerItem: 50000 });
    const run = newestRun(read);
    if (read.thread?.activeRunId || (run && run.status !== "completed")) return { refused: "Review still running" };
    const last = [...read.items].reverse().find((i) => i.type === "assistant_message" && i.runId === run?.runId);
    const lines = (last?.text ?? "").trim().split("\n").map((l) => l.trim());
    if (run?.status !== "completed" || lines.at(-1) !== "VERDICT: PASS" || last?.textTruncated) return { refused: "Review must end with VERDICT: PASS" };
    if ((run.executedModel ?? run.model).replace(/^subscriptions\//, "") !== "claude-opus-5-5") return { refused: "Reviewer run must use claude-opus-5-5" };
    const checks = lines.filter((l) => /^CHECK:/.test(l));
    const checked = checks.length === 1 ? /^CHECK: PASS ([a-f0-9]{40})$/.exec(checks[0]) : null;
    if (checked?.[1] !== head.headRefOid) return { refused: "Review CHECK must PASS the current head SHA" };
    return { sha: head.headRefOid, repo: pr.repo, number: pr.number };
  } catch (error) {
    return { refused: `Merge preflight failed: ${error.message}` };
  }
}

export async function mergeThread(card, plan) {
  const fresh = await mergePlan(card);
  if (fresh.refused) return fresh;
  if (!plan || fresh.sha !== plan.sha || fresh.repo !== plan.repo || fresh.number !== plan.number) return { refused: "Merge plan changed; approve again" };
  const key = `${fresh.repo}#${fresh.number}@${fresh.sha}`;
  if (relays.has(key)) return relays.get(key);
  let retain = false;
  const queue = (async () => {
    const names = await call("t3_project_list", { limit: 100 });
    const repoName = fresh.repo.split("/").at(-1);
    const matches = names.projects.filter((p) => p.workspaceRoot?.replace(/\/$/, "").split("/").at(-1) === repoName);
    if (matches.length !== 1) return { refused: "PR repository project is unknown or ambiguous" };
    const title = `${card.task || card.key} merge relay #${fresh.number} ${fresh.sha.slice(0, 8)}`;
    const command = `gh pr merge ${fresh.number} -R ${fresh.repo} --squash --match-head-commit ${fresh.sha}`;
    const message = `Run exactly: ${command}\nStop on any refusal. Report the merge commit. Do not retry or change the command.`;
    retain = true;
    const r = await exec("coordq", ["start", JSON.stringify({ projectId: matches[0].id, taskType: "worker", title, message })]);
    if (r.code !== 0) {
      retain = false;
      throw new Error(r.stderr.trim() || "Relay queue failed; retry available");
    }
    const id = /^(?:queued|started) #(\d+)\s*$/.exec(r.stdout.trim())?.[1];
    if (!id) throw new Error("Relay response unknown; check queue before retrying");
    return { queued: true, text: `queued #${id}` };
  })().catch((error) => ({ refused: error.message })).then((result) => {
    if (!retain) relays.delete(key);
    return result;
  });
  relays.set(key, queue);
  return queue;
}

export function mergeNotice(results) {
  const refused = results.some((r) => !r.queued);
  return { level: refused ? "error" : "success", text: results.map((r) => `${r.name}: ${r.text}`).join(", "), items: results.map((r) => ({ name: r.name, ok: r.queued, text: r.text })) };
}

export async function readTask(thread) {
  const { thread: read } = await call("t3_thread_read", { threadId: thread.key, limit: 1 });
  return { worktree: read.worktreePath ?? null, branch: read.branch ?? null, repo: projects.roots.get(thread.projectId) ?? null };
}

export async function firstMessage(key) {
  const read = await call("t3_thread_read", { threadId: key, limit: 1 });
  return read.items.find((i) => i.type === "user_message")?.text ?? null;
}

export async function readTicket(thread) {
  const [opening, latest] = await Promise.all([
    call("t3_thread_read", { threadId: thread.key, limit: 1 }),
    readAll({ threadId: thread.key, maxCharsPerItem: 20000 }),
  ]);
  const report = [...latest.items].reverse().find((i) => i.type === "assistant_message");
  return { record: latest.thread, text: opening.items.find((i) => i.type === "user_message")?.text ?? null, report: report?.text ?? null };
}
