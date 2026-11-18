// What really needs Shyam: a pending request, a coordinator decision, or a turn that ends by asking him.
// A failed or interrupted run that asks nothing is a dead run, not an ask.

const TRAILING = /[\s>*_`"'”’)\]]+$/;
const WAITING = /\bWAITING:/;

export const NEEDS = "needs";
export const STUCK = "stuck";
export const DEAD = "dead";

// The last thing a turn said is a question, or a WAITING: line, when it ends that way.
export function endsWithAsk(text) {
  const lines = (text ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  const last = (lines.at(-1) ?? "").replace(TRAILING, "");
  return last.endsWith("?") || WAITING.test(last);
}

// The column a group of threads belongs to. Decisions and asked turns need Shyam; dead runs do not.
function columnOf(group) {
  if (group.kind === "ask" || group.kind === "wait") return NEEDS;
  if (group.threads.some((thread) => thread.ask)) return NEEDS;
  if (group.threads.some((thread) => thread.kind === "run")) return "run";
  if (group.kind === "fail" || group.kind === "stop") return DEAD;
  return "done";
}

const acting = (group) => group.threads.some((thread) => thread.kind === "run");

// A fix round finished after the CI failure was reported, so the failing result may be stale.
const fixFinished = (group, gh) => group.threads.some((thread) => !thread.review && thread.at > (gh.ciAt || Infinity));

export const UNROUTED_AFTER = 600000;
export const STALL_AFTER = 1200000;

export const reviewThread = (group) => group.threads.filter((thread) => thread.kind === "done" && thread.review).sort((a, b) => b.at - a.at)[0] ?? null;

// The last agent activity of a group, when every thread that is really working on it has been silent past the stall ceiling.
// Queued and preparing threads never stall: they are not working yet.
// A board restored from the cache or kept stale has old thread times, so it reports no stall until fresh data arrives.
export function stallOf(group, now) {
  if (!group.trusted) return null;
  const working = group.threads.filter((thread) => thread.kind === "run" && (thread.status === "running" || thread.status === "starting"));
  if (!working.length) return null;
  const last = Math.max(...working.map((thread) => thread.at));
  return now - last > STALL_AFTER ? last : null;
}

// The feedback trail of an open PR: the failure that was reported, when it was first acted on, and the commits since.
// A failure counts as acted on by a fix round started after it, any builder activity after it, a send-back from the board, or a fix commit.
// `live` is false once CI no longer fails and the review no longer objects; the trail then shows the fix until the PR is approved.
// The trail cannot see a settled round that pushed no commits.
export function trailOf(group, now, reviewFailed) {
  const { status, gh, pr } = group.info;
  if (status !== "open" || !gh) return null;
  const review = reviewThread(group);
  const ci = gh.ci === "fail";
  const humanChanges = gh.review === "CHANGES_REQUESTED" && Boolean(gh.changesAt);
  const changes = !ci && (humanChanges || (review && (gh.review === "CHANGES_REQUESTED" || reviewFailed())));
  const failure = ci || !changes ? gh.failure : { at: humanChanges ? gh.changesAt : review.at, checks: [] };
  if (!failure) return null;
  const live = ci || Boolean(changes);
  const round = group.threads.filter((thread) => !thread.review && thread.created > failure.at).sort((a, b) => a.created - b.created)[0];
  const fixes = (gh.commits ?? []).filter((commit) => commit.at > failure.at).map((commit) => ({ ...commit, url: `https://github.com/${pr.repo}/commit/${commit.oid}` }));
  const actedAt = [round?.created, ...group.threads.filter((thread) => !thread.review).map((thread) => thread.at), group.sentAt, fixes[0]?.at].filter((at) => at > failure.at);
  const routedIn = actedAt.length ? Math.min(...actedAt) - failure.at : null;
  return { at: failure.at, live, review: !failure.checks.length, checks: failure.checks, routedIn, fixes, unrouted: Boolean(group.trusted) && live && routedIn === null && !acting(group) && now - failure.at > UNROUTED_AFTER };
}

// Why a group needs Shyam, in display order: a question, a stall, then the facts of its open PR when no thread is acting on it.
// `reviewFailed` is called only for an open PR that nobody is acting on.
export function needReasons(group, reviewFailed, now) {
  const column = columnOf(group);
  const reasons = column === NEEDS ? ["question"] : [];
  if (stallOf(group, now) !== null) reasons.push("stalled");
  const { status, gh } = group.info;
  if ((column !== NEEDS && column !== "done") || status !== "open" || acting(group)) return reasons;
  if (trailOf(group, now, reviewFailed)?.unrouted) reasons.push("unrouted");
  if (gh?.ci === "fail" && !fixFinished(group, gh)) reasons.push("ci");
  if (gh?.review === "CHANGES_REQUESTED" || reviewFailed()) reasons.push("changes");
  if (gh && !gh.draft && gh.mergeable === "CONFLICTING") reasons.push("conflict");
  return reasons;
}

// The lane of a group, from live facts only: a question for Shyam, other reasons the coordinator can fix, thread state, then the open PR's CI and review.
// `reviewCleared` is called only for an open PR whose CI is not failing or pending.
export function laneOf(group, reasons, reviewCleared) {
  if (reasons.includes("question")) return NEEDS;
  if (reasons.length) return STUCK;
  const column = columnOf(group);
  if (column !== "done" || group.info.status !== "open") return column;
  const ci = group.info.gh?.ci ?? "loading";
  if (ci === "fail") return STUCK;
  if (ci === "pending" || ci === "loading") return "checks";
  return reviewCleared() ? "ready" : "review";
}
