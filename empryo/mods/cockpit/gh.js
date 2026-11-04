import { exec } from "herdr";

const TTL = 60000;
const RETRY = 60000;
const FRESH = 600000;
const POOL = 4;
const FINAL = new Set(["MERGED", "CLOSED"]);
const FAILED = new Set(["FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "ERROR", "STARTUP_FAILURE"]);
const PENDING = new Set(["PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS", "WAITING"]);

const cache = new Map();

export const prKey = (pr) => `${pr.repo}#${pr.number}`;
export const prState = (pr) => cache.get(prKey(pr))?.data ?? null;
export const prEntries = (prs) => prs.map((pr) => [prKey(pr), prState(pr), cache.get(prKey(pr))?.at ?? 0]);
export const seedPrs = (entries) => entries.forEach(([key, data, at]) => cache.set(key, { at, data }));
export const prFresh = (pr) => Date.now() - (cache.get(prKey(pr))?.at ?? 0) < FRESH;

function ciOf(rollup) {
  if (!rollup?.length) return "none";
  const states = rollup.map((c) => (c.__typename === "StatusContext" ? c.state : c.status === "COMPLETED" ? c.conclusion : c.status));
  if (states.some((s) => FAILED.has(s))) return "fail";
  if (states.some((s) => PENDING.has(s))) return "pending";
  return "pass";
}

async function fetchPr(pr) {
  const r = await exec("gh", ["pr", "view", String(pr.number), "--repo", pr.repo, "--json", "state,mergeable,reviewDecision,statusCheckRollup,url,headRefName,isDraft"]);
  if (r.code !== 0) throw new Error(r.stderr.trim() || "gh pr view failed");
  const j = JSON.parse(r.stdout);
  return { state: j.state, mergeable: j.mergeable, review: j.reviewDecision, ci: ciOf(j.statusCheckRollup), url: j.url, draft: j.isDraft, branch: j.headRefName };
}

export async function refreshPrs(prs) {
  const now = Date.now();
  const due = new Map();
  for (const pr of prs) {
    const entry = cache.get(prKey(pr));
    if (entry && (FINAL.has(entry.data?.state) || now - entry.at < TTL || now - (entry.failedAt ?? 0) < RETRY)) continue;
    due.set(prKey(pr), pr);
  }
  const queue = [...due.values()];
  await Promise.all(Array.from({ length: Math.min(POOL, queue.length) }, async () => {
    for (let pr = queue.shift(); pr; pr = queue.shift()) {
      try {
        cache.set(prKey(pr), { at: Date.now(), data: await fetchPr(pr) });
      } catch {
        cache.set(prKey(pr), { ...(cache.get(prKey(pr)) ?? { at: 0, data: null }), failedAt: Date.now() });
      }
    }
  }));
}
