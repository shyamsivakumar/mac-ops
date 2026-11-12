import { exec } from "herdr";
import { READ } from "./git.js";

const RECENT_DAYS = 14, MAX_ROWS = 40, GH_EVERY = 60000, MIN_READ_GAP = 5000, GIT_TIMEOUT = 15000, STUCK = 60000;
const FAILED = new Set(["FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"]);
const cache = new Map();
const keyOf = (root, on) => `${on}\0${root}`;

export const branchData = (root, on) => cache.get(keyOf(root, on));

export function worktreeBranches(text) {
  const byBranch = new Map();
  for (const block of text.split("\n\n")) {
    let path = null, branch = null;
    for (const line of block.split("\n")) {
      if (line.startsWith("worktree ")) path = line.slice(9);
      else if (line.startsWith("branch refs/heads/")) branch = line.slice(18);
    }
    if (path && branch) byBranch.set(branch, path);
  }
  return byBranch;
}

export function ciState(rollup) {
  if (!rollup?.length) return null;
  if (rollup.some((c) => FAILED.has(c.conclusion) || FAILED.has(c.state))) return "fail";
  return rollup.some((c) => (c.status && c.status !== "COMPLETED") || c.state === "PENDING" || c.state === "EXPECTED") ? "pending" : "pass";
}

export function prsByBranch(text) {
  const rank = (pr) => (pr.state === "OPEN" ? 1e9 : 0) + pr.number;
  const best = new Map();
  for (const pr of JSON.parse(text)) {
    const kept = best.get(pr.headRefName);
    if (!kept || rank(pr) > rank(kept)) best.set(pr.headRefName, pr);
  }
  return new Map([...best].map(([name, pr]) => [name, { number: pr.number, state: pr.state, url: pr.url, ci: ciState(pr.statusCheckRollup) }]));
}

export async function readBranches(root, on) {
  const key = keyOf(root, on);
  const entry = cache.get(key) ?? { rows: [], base: null, prs: new Map(), ghAt: 0, ghFailed: false, readAt: 0, loading: false, loadingAt: 0 };
  cache.set(key, entry);
  if (entry.loading && Date.now() - entry.loadingAt < STUCK) return;
  entry.loading = true; entry.loadingAt = Date.now();
  try {
    const git = (args) => exec("git", [...READ, ...args], { cwd: root, on, timeout: GIT_TIMEOUT });
    const [refs, trees, origin, remotes] = await Promise.all([
      git(["for-each-ref", "--sort=-committerdate", "--format=%(refname:lstrip=2)%00%(committerdate:unix)%00%(subject)", "refs/heads"]),
      git(["worktree", "list", "--porcelain"]),
      git(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"]),
      git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"]),
    ]);
    const heads = refs.stdout.split("\n").filter(Boolean).map((line) => {
      const [name, time, subject] = line.split("\0");
      return { name, time: Number(time), subject };
    });
    const worktrees = worktreeBranches(trees.stdout), names = new Set(heads.map((h) => h.name));
    const base = [origin.stdout.trim().replace(/^origin\//, ""), "main", "master"].find((n) => names.has(n)) ?? null;
    const baseRef = base && remotes.stdout.split("\n").includes(`origin/${base}`) ? `origin/${base}` : base;
    const cutoff = Date.now() / 1000 - RECENT_DAYS * 86400;
    const shown = heads.filter((h) => h.name !== base && (worktrees.has(h.name) || h.time >= cutoff)).slice(0, MAX_ROWS);
    const counts = new Map();
    if (baseRef) {
      const tally = await git(["for-each-ref", "--format=%(refname:lstrip=2)%00%(ahead-behind:" + baseRef + ")", "refs/heads"]);
      for (const line of tally.stdout.split("\n").filter(Boolean)) {
        const [name, pair] = line.split("\0");
        const [ahead, behind] = pair.split(" ").map(Number);
        counts.set(name, { ahead, behind });
      }
    }

    let { prs, ghAt, ghFailed } = entry;
    if (Date.now() - ghAt >= GH_EVERY) {
      const r = await exec("gh", ["pr", "list", "--state", "all", "--limit", "100", "--json", "headRefName,number,state,statusCheckRollup,url"], { cwd: root, on, timeout: 20000 }).catch(() => null);
      ghAt = Date.now();
      ghFailed = r?.code !== 0;
      if (!ghFailed) prs = prsByBranch(r.stdout);
    }

    const row = (h) => {
      const tally = counts.get(h.name) ?? null;
      const pr = prs.get(h.name) ?? null;
      return { name: h.name, subject: h.subject, time: h.time, ahead: tally?.ahead ?? null, behind: tally?.behind ?? null, worktree: worktrees.get(h.name) ?? null,
        pr, isBase: h.name === base, done: h.name !== base && Boolean(pr && pr.state !== "OPEN") };
    };
    const rows = shown.map(row).sort((a, b) => a.done - b.done);
    const baseHead = heads.find((h) => h.name === base);
    if (baseHead) rows.unshift(row(baseHead));
    Object.assign(entry, { rows, base, baseRef, prs, ghAt, ghFailed, readAt: Date.now() });
  } finally {
    entry.loading = false;
  }
}

export const branchesStale = (root, on) => {
  const entry = cache.get(keyOf(root, on));
  return !entry || Date.now() - entry.readAt >= MIN_READ_GAP;
};
