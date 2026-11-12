// GitHub tickets as the board sees them: the ticket CLI's list and show, and which ticket a thread came from.

import { exec, home, readTextFile } from "herdr";
import { firstMessage, vendorOf } from "./hub.js";

const TICKET = `${home()}/.local/bin/ticket`;
const LIST_TIMEOUT = 30000;
const SHOW_TIMEOUT = 60000;
const ACT_TIMEOUT = 150000;
const LIST_EVERY = 60000;
const ORIGIN_BATCH = 8;
const SHOW_BATCH = 2;
const RETRY_AFTER = 300000;
const TICKET_LINE = /^Ticket: (https:\/\/github\.com\/([^/\s]+\/[^/\s]+)\/issues\/(\d+))/;
const LINEAR_URL = /https:\/\/linear\.app\/[^\s)>\]"'`]+\/issue\/[^\s)>\]"'`]+/;

export const STALE_TEXT = { offline: "GitHub offline", auth: "GitHub auth failed", rate_limit: "GitHub rate limited", error: "GitHub error" };

async function runTicket(args, timeout) {
  const r = await exec(TICKET, args, { timeout });
  if (r.code !== 0) throw new Error(r.stderr.trim() || r.stdout.trim() || `ticket ${args[0]} failed`);
  return r.stdout;
}

let listing = null;
let last = { at: 0, data: null };

export function listIssues(fresh) {
  if (!fresh && last.data && Date.now() - last.at < LIST_EVERY) return Promise.resolve(last.data);
  listing ??= runTicket(["list", "--json", ...(fresh ? ["--fresh"] : [])], LIST_TIMEOUT)
    .then((out) => (last = { at: Date.now(), data: JSON.parse(out) }).data)
    .finally(() => (listing = null));
  return listing;
}

export const issueRef = (issue) => `${issue.repo}#${issue.number}`;

export function issueGroup(issue) {
  const at = Date.parse(issue.updatedAt);
  const title = issue.key ? issue.title.slice(issue.key.length).replace(/^[\s·:-]+/, "") : issue.title;
  const thread = { key: `issue:${issueRef(issue)}`, task: issue.key ?? "", led: Boolean(issue.key), title, project: issue.repo.split("/")[1], projectId: null, link: issue.url, session: null, cwd: null, kind: "idle", provider: "", model: "", taskType: issue.type ?? "", review: false, runs: 0, at, created: at, runStarted: null, status: "idle", context: "", prs: [], issue };
  return { key: issue.key ?? issueRef(issue), task: issue.key ?? "", title, project: thread.project, threads: [thread], primary: thread, kind: "idle", at, runSince: null, prs: [], issue };
}

let config = null;

export async function loadConfig() {
  if (config) return config;
  const text = await readTextFile(`${home()}/.empryo/tickets.json`);
  if (text === null) throw new Error("tickets.json not found in ~/.empryo");
  config = JSON.parse(text);
  return config;
}

export const showIssue = async (ref) => JSON.parse(await runTicket(["show", ref, "--json"], SHOW_TIMEOUT));

const lastLine = (out) => out.trim().split("\n").filter(Boolean).at(-1) ?? "";
export const ticketStart = async (ref) => lastLine(await runTicket(["start", ref], ACT_TIMEOUT));
export const ticketAbandon = async (ref, reason) => (await runTicket(["abandon", ref, "--reason", reason], ACT_TIMEOUT)).trim().split("\n").join("; ");
export const setIssueField = (ref, family, value) => runTicket(["set", ref, `--${family}`, value], SHOW_TIMEOUT);

export const startBlock = (show) => {
  if (!show) return "Loading the ticket";
  if (show.state !== "OPEN") return `Issue is ${show.state.toLowerCase()}`;
  const open = show.blockers.filter((b) => b.state === "OPEN");
  if (open.length) return `Blocked by open ${open.map((b) => `${b.repo.split("/")[1]}#${b.number}`).join(", ")}`;
  if (show.problems.length) return show.problems[0];
  return null;
};

export function pickerOptions(cfg, family) {
  const aliases = Object.entries(cfg.models);
  if (family === "stage") return cfg.labels.stage;
  if (family === "priority") return [...cfg.labels.priority, "none"];
  if (family === "builder") return [...aliases.map(([a]) => a), "none"];
  return [...aliases.filter(([, m]) => !m.noGate).map(([a]) => a), "none"];
}

const origins = new Map();

export const originOf = (thread) => origins.get(thread.key) ?? null;
export const originEntries = (threads) => threads.filter((c) => origins.has(c.key)).map((c) => [c.key, origins.get(c.key)]);
export const seedOrigins = (entries) => entries.forEach(([key, value]) => origins.set(key, value));

export function parseOrigin(text) {
  const match = TICKET_LINE.exec(text ?? "");
  const linear = LINEAR_URL.exec(text ?? "")?.[0].replace(/[.,;]+$/, "") ?? null;
  return { ticket: match ? { url: match[1], repo: match[2], number: Number(match[3]) } : null, linear };
}

const latestIntent = (show) => show.ledger.filter((e) => e.kind === "intent").reduce((a, b) => (b.attempt > (a?.attempt ?? 0) ? b : a), null);

export const requestedModel = (cfg, show) => {
  const intent = latestIntent(show);
  return intent ? `${cfg.models[intent.builder].selection.instanceId}/${cfg.models[intent.builder].selection.model}` : null;
};

export const changedSinceLaunch = (show) => {
  const intent = latestIntent(show);
  return Boolean(intent) && intent.bodyHash !== show.bodyHash;
};

const modelId = (model) => `${vendorOf(model)}:${model.split("/").at(-1)}`;

export const fellBack = (requested, effective) => (requested && effective && modelId(requested) !== modelId(effective) ? requested : null);

const due = (origin) => !(origin?.retryAt > Date.now());

export async function loadOrigins(threads) {
  const todo = threads.filter((c) => !origins.has(c.key) || (origins.get(c.key).failed && due(origins.get(c.key)))).slice(0, ORIGIN_BATCH);
  const read = await Promise.allSettled(todo.map(async (c) => parseOrigin(await firstMessage(c.key))));
  read.forEach((r, i) => origins.set(todo[i].key, r.status === "fulfilled" ? r.value : { ticket: null, linear: null, failed: true, retryAt: Date.now() + RETRY_AFTER }));
  const pending = threads.filter((c) => origins.get(c.key)?.ticket && origins.get(c.key).requested === undefined && due(origins.get(c.key))).slice(0, SHOW_BATCH);
  let shown = 0;
  if (pending.length) {
    const cfg = await loadConfig();
    const results = await Promise.allSettled(pending.map(async (c) => requestedModel(cfg, await showIssue(`${origins.get(c.key).ticket.repo}#${origins.get(c.key).ticket.number}`))));
    results.forEach((r, i) => {
      const origin = origins.get(pending[i].key);
      origins.set(pending[i].key, r.status === "fulfilled" ? { ...origin, requested: r.value } : { ...origin, retryAt: Date.now() + RETRY_AFTER });
    });
    shown = results.filter((r) => r.status === "fulfilled").length;
  }
  return read.some((r) => r.status === "fulfilled") || shown > 0;
}
