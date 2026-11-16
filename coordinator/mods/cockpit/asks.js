// What really needs Shyam: a pending request, a coordinator decision, or a turn that ends by asking him.
// A failed or interrupted run that asks nothing is a dead run, not an ask.

const TRAILING = /[\s>*_`"'”’)\]]+$/;
const WAITING = /\bWAITING:/;

export const NEEDS = "needs";
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

// Why a group needs Shyam, in display order: a question, then the facts of its open PR when no thread is acting on it.
// `reviewFailed` is called only for an open PR that nobody is acting on.
export function needReasons(group, reviewFailed) {
  const column = columnOf(group);
  const reasons = column === NEEDS ? ["question"] : [];
  const { status, gh } = group.info;
  if ((column !== NEEDS && column !== "done") || status !== "open" || acting(group)) return reasons;
  if (gh?.ci === "fail" && !fixFinished(group, gh)) reasons.push("ci");
  if (gh?.review === "CHANGES_REQUESTED" || reviewFailed()) reasons.push("changes");
  if (gh && !gh.draft && gh.mergeable === "CONFLICTING") reasons.push("conflict");
  return reasons;
}

// The lane of a group, from live facts only: its reasons to need Shyam, thread state, then the open PR's CI and review.
// `reviewCleared` is called only for an open PR whose CI is not failing or pending.
export function laneOf(group, reasons, reviewCleared) {
  if (reasons.length) return NEEDS;
  const column = columnOf(group);
  if (column !== "done" || group.info.status !== "open") return column;
  const ci = group.info.gh?.ci ?? "loading";
  if (ci === "fail") return "cifail";
  if (ci === "pending" || ci === "loading") return "checks";
  return reviewCleared() ? "ready" : "review";
}
