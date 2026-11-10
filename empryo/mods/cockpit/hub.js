// The hub as the cockpit sees it: threads that need Shyam, grouped by project, and the calls that act on them.

import { exec, hc, home, readTextFile, run, terminals } from "herdr";

const LIVE = ["preparing", "queued", "starting", "running", "waiting", "failed", "interrupted"];
const RUNNING = new Set(["preparing", "queued", "starting", "running"]);
const RUNNING_OR_WAITING = new Set([...RUNNING, "waiting"]);
const KIND = { waiting: "wait", failed: "fail", interrupted: "stop", completed: "done", idle: "idle" };
const IDLE_PAGES = 4;
const DEFAULT_CAP = 6;
const URGENCY = { wait: 0, fail: 1, stop: 2, run: 3, done: 4, idle: 5 };
const TASK_ID = /[A-Z]{2,5}-\d+/;
const REVIEW_TITLE = /^[A-Z]{2,5}-\d+ (?:gate )?review\b/i;
const PAGES = 3;

let idleThreads = { at: 0, list: [] };
const IDLE_EVERY = 60000;
let projects = { at: 0, names: new Map(), roots: new Map() };
const asks = new Map();

export async function call(tool, args) {
  const r = await exec(`${home()}/.local/bin/emp`, ["call", tool, JSON.stringify(args)]);
  if (r.code !== 0) throw new Error(r.stderr.trim() || `${tool} failed`);
  return JSON.parse(r.stdout);
}

async function threads(filter, pages = PAGES) {
  const all = [];
  let cursor;
  for (let page = 0; page < pages; page++) {
    const r = await call("emp_thread_list", { allProjects: true, limit: 100, ...filter, ...(cursor === undefined ? {} : { cursor }) });
    all.push(...r.threads);
    cursor = r.nextCursor;
    if (cursor === null || cursor === undefined) break;
  }
  return all;
}

async function projectNames() {
  if (Date.now() - projects.at < 60000) return projects.names;
  const r = await call("emp_project_list", { limit: 100 });
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
  const cached = asks.get(thread.threadId);
  if (cached?.stamp === thread.updatedAt) return cached.text;
  const { requestIds } = await call("emp_pending_request", { action: "list", threadId: thread.threadId });
  const text = requestIds.length
    ? questionOf(await call("emp_pending_request", { action: "read", threadId: thread.threadId, requestId: requestIds[0] })) || "Waiting for your answer"
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
    session: thread.journalSessionId,
    cwd: thread.cwd,
    kind,
    provider: thread.providerInstanceId,
    model: thread.model ?? "",
    taskType: thread.taskType ?? "",
    review: thread.taskType ? thread.taskType === "review" : REVIEW_TITLE.test(thread.title),
    runs: thread.runCount ?? 0,
    at: Date.parse(thread.updatedAt),
    created: Date.parse(thread.createdAt),
    runStarted: thread.activeRunStartedAt ? Date.parse(thread.activeRunStartedAt) : null,
    status: thread.status,
    context: kind === "fail" && thread.lastError ? plainError(thread.lastError) : CONTEXT[kind] ?? "",
    error: kind === "fail" ? thread.lastError : undefined,
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
    return { key, task: threads[0].task, title: lead.title, project: lead.project, threads, primary: threads[0], kind: threads[0].kind, at: Math.max(...threads.map((c) => c.at)), runSince: running.length ? Math.min(...running.map((c) => c.runStarted)) : null, prs: [...prs.values()] };
  });
}

const TASK_STATUS = { run: "running", wait: "waiting", fail: "failed", stop: "stopped", done: "done", idle: "idle" };

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

export async function load() {
  const [live, finished, names] = await Promise.all([
    threads({ statuses: LIVE }),
    threads({ statuses: ["completed"], settled: false }),
    projectNames(),
  ]);
  const cards = [...live, ...finished].filter((t) => !t.snoozed && !(t.settled && t.status !== "running")).map((t) => card(t, names));
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
    done: count("done"),
    groups: group(cards),
    tasks: taskMap(cards),
  };
}

export const hubStatus = () => call("emp_hub_status", {}).then((s) => ({ circuits: s?.circuits, draining: s?.draining, pid: s?.pid })).catch(() => null);

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

export async function loadVerdict(thread) {
  const stamp = `${thread.key}@${thread.at}`;
  const known = verdicts.get(thread.key);
  if (known?.stamp === stamp && !(known.retryAt <= Date.now())) return;
  try {
    const { items, recentRuns } = await call("emp_thread_read", { threadId: thread.key });
    const last = [...items].reverse().find((i) => i.type === "assistant_message");
    verdicts.set(thread.key, { stamp, verdict: judge(last?.text ?? ""), runModel: recentRuns?.at(-1)?.model ?? "" });
  } catch {
    verdicts.set(thread.key, { stamp, verdict: { state: "unknown", label: "rev ?" }, runModel: known?.runModel ?? "", retryAt: Date.now() + RETRY_VERDICT });
  }
}

export async function shepherdrStates() {
  const text = await readTextFile(`${home()}/Code/coordinator/migration/index.md`);
  const states = new Map();
  for (const line of (text ?? "").split("\n")) {
    const cells = line.split("|").map((c) => c.trim());
    if (cells.length > 5 && cells[4].startsWith("mcp:")) states.set(cells[4], cells[3]);
  }
  return states;
}

export async function queueCap() {
  const text = await readTextFile(`${home()}/Code/coordinator/queue/config.json`);
  const cap = text ? Number(JSON.parse(text).cap) : DEFAULT_CAP;
  return Number.isFinite(cap) && cap > 0 ? cap : DEFAULT_CAP;
}

const SHOW_POLL = 50;
const SHOW_LIMIT = 8000;

async function reusableShow(name, thread) {
  const kinds = RUNNING_OR_WAITING.has(thread.status) ? ["empryo", "follow"] : thread.session ? ["empryo"] : ["history", "empryo"];
  const lists = await Promise.all(kinds.map((kind) => exec(`${home()}/.local/bin/hc`, ["ls", "--json", "--label", `emp.show=${kind}`])));
  for (const r of lists) {
    const found = r.code === 0 ? JSON.parse(r.stdout).terminals.find((t) => t.name === name && t.state === "live") : null;
    if (found) return found.address;
  }
  return null;
}

export const showName = (key) => `show-${key.slice(4, 12)}`;

export const empryoWindows = () => terminals().filter((t) => t.state === "live" && t.labels?.["emp.show"] === "empryo").map((t) => t.name);

export async function closeWindow(key) {
  const r = await hc(["kill", showName(key)]);
  if (r.code !== 0) throw new Error(r.stderr.trim() || `Could not close ${showName(key)}`);
}

export async function openThread(thread, cx) {
  const name = showName(thread.key);
  const reuse = await reusableShow(name, thread);
  if (reuse) return run("terminal.peek", { terminal: reuse });
  const before = terminals().find((t) => t.name === name)?.address;
  let finished = false;
  const shown = exec(`${home()}/.local/bin/emp`, ["show", thread.key]).finally(() => (finished = true));
  const until = Date.now() + SHOW_LIMIT;
  while (!finished) {
    const fresh = terminals().find((t) => t.name === name && t.state === "live" && t.address !== before);
    if (fresh) return run("terminal.peek", { terminal: fresh.address });
    if (Date.now() > until) throw new Error("The terminal did not appear in time.");
    await cx.sleep(SHOW_POLL);
  }
  const r = await shown;
  if (r.code !== 0) throw new Error(r.stderr.trim());
}

export const sendArgs = (key, message) => ({ threadId: key, message, mode: "auto" });
export const sendReply = (key, message) => call("emp_thread_send", sendArgs(key, message));
export const settle = (key) => call("emp_thread_organize", { threadId: key, action: "settle" });
export const mergeThread = (key, expectedRevision) => call("emp_thread_merge", { threadId: key, expectedRevision });
export const mergePlan = (key) => call("emp_thread_merge", { threadId: key, dryRun: true });
export const cleanupThread = (key) => call("emp_thread_cleanup", { threadId: key });

const QUIET_KEEPS = /no worktree on disk|main checkout/;

export function cleanupNote(result) {
  if (result.action === "removed") return result.branchRemoved ? "Worktree and branch removed" : `Worktree removed, branch kept: ${result.branchNote}`;
  return QUIET_KEEPS.test(result.reason) ? null : `Worktree kept: ${result.reason}`;
}

export function mergeNotice(results) {
  const merged = results.filter((r) => r.merged).length;
  const refused = results.length - merged;
  const items = results.map((r) => ({ name: r.name, ok: r.merged, text: r.text || "Merged" }));
  const [only] = results;
  const text = only && results.length === 1
    ? only.merged ? `Merged ${only.name}${only.text ? `: ${only.text}` : ""}` : `Not merged · ${only.name}: ${only.text}`
    : [merged && `Merged ${merged}`, refused && `${refused} not merged`].filter(Boolean).join(", ");
  return { level: refused ? "error" : "success", text, items };
}

export async function readTask(thread) {
  const { thread: read } = await call("emp_thread_read", { threadId: thread.key, limit: 1 });
  return { worktree: read.worktreePath ?? null, branch: read.branch ?? null, repo: projects.roots.get(thread.projectId) ?? null };
}

export async function readTicket(thread) {
  const [opening, latest] = await Promise.all([
    call("emp_thread_read", { threadId: thread.key, afterPosition: 0, limit: 10 }),
    call("emp_thread_read", { threadId: thread.key, limit: 20, maxCharsPerItem: 20000 }),
  ]);
  const report = [...latest.items].reverse().find((i) => i.type === "assistant_message");
  return { record: latest.thread, text: opening.items.find((i) => i.type === "user_message")?.text ?? null, report: report?.text ?? null };
}
