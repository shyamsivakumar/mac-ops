import { home } from "herdr";

export const FLOW_FILE = `${home()}/.local/state/herdr-board/flow.jsonl`;

const laneEvent = (e) => e && typeof e === "object" && typeof e.t === "number" && !e.gap && !e.act && "to" in e;

export function parseFlow(text) {
  const events = [];
  for (const line of text.split("\n")) {
    if (!line) continue;
    let e;
    try {
      e = JSON.parse(line);
    } catch {
      continue;
    }
    if (laneEvent(e)) events.push(e);
  }
  return events.sort((a, b) => a.t - b.t);
}

export function boardGlance(events, windows) {
  const out = new Map();
  for (const w of windows) {
    const inside = events.filter((e) => e.t > w.from && e.t <= w.to);
    const last = new Map(inside.map((e) => [e.key, e.to]));
    const done = [...last].filter(([, lane]) => lane === "done").map(([key]) => key);
    out.set(w.id, {
      done: done.length,
      merged: done.filter((key) => inside.some((e) => e.key === key && e.to === "done" && e.pr)).length,
      unreviewed: new Set(inside.filter((e) => e.to === "review").map((e) => e.key)).size,
      since: w.from,
      known: w.known,
    });
  }
  return out;
}
