import { exec, home, readTextFile, writeTextFile } from "herdr";

const DIR = `${home()}/.local/state/herdr-board`;
const FILE = `${DIR}/flow.jsonl`;
const MAX_AGE = 30 * 86400000;
const MAX_LINES = 8000;
const MAX_BYTES = 900000;
const GAP_AFTER = 120000;

let queue = [];
let flushing = false;
let lastPass = 0;

export const logLaneChange = (event) => queue.push(event);
export const logAct = (event) => queue.push(event);

const actId = (e) => `${e.key}|${e.act}|${e.t}`;
const isLane = (e) => !e.gap && !e.act;

export function markPass(now) {
  if (now - lastPass > GAP_AFTER) queue.push({ t: now, gap: true });
  lastPass = now;
}

const isNew = (last, e) => {
  if (e.gap || e.act) return true;
  return e.to === null ? last.has(e.key) && last.get(e.key) !== null : last.get(e.key) !== e.to;
};

const parse = (text) => (text ?? "").split("\n").flatMap((line) => {
  try {
    return [JSON.parse(line)];
  } catch {
    return [];
  }
});

const utf8Length = (text) => [...text].reduce((n, c) => n + (c.codePointAt(0) < 128 ? 1 : c.codePointAt(0) < 2048 ? 2 : c.codePointAt(0) < 65536 ? 3 : 4), 0);

function trim(events, now) {
  const latest = new Map(events.filter(isLane).map((e) => [e.key, e]));
  const pinned = new Set([...latest.values()].filter((e) => e.to !== null));
  let rest = events.filter((e) => !pinned.has(e) && e.t >= now - MAX_AGE).slice(-Math.max(0, MAX_LINES - pinned.size));
  const sizes = new Map([...pinned, ...rest].map((e) => [e, utf8Length(JSON.stringify(e)) + 1]));
  let total = [...sizes.values()].reduce((a, b) => a + b, 0);
  while (total > MAX_BYTES && rest.length) total -= sizes.get(rest.shift());
  const kept = new Set([...pinned, ...rest]);
  return events.filter((e) => kept.has(e));
}

export async function flushFlowLog(now) {
  if (flushing || !queue.length) return;
  flushing = true;
  const batch = queue;
  queue = [];
  try {
    await exec("mkdir", ["-p", DIR]);
    const text = await readTextFile(FILE);
    const events = parse(text);
    const last = new Map(events.filter(isLane).map((e) => [e.key, e.to]));
    const acts = new Set(events.filter((e) => e.act).map(actId));
    const fresh = [];
    for (const e of batch) {
      if (!isNew(last, e)) continue;
      if (e.act && acts.has(actId(e))) continue;
      if (e.act) acts.add(actId(e));
      if (isLane(e)) last.set(e.key, e.to);
      fresh.push(e);
    }
    if (!fresh.length) return;
    const lines = trim([...events, ...fresh], now).map((e) => JSON.stringify(e));
    await writeTextFile(FILE, `${lines.join("\n")}\n`, text);
  } catch (error) {
    queue = [...batch, ...queue].slice(-MAX_LINES);
    throw error;
  } finally {
    flushing = false;
  }
}
