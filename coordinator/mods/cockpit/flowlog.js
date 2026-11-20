import { exec, home, readTextFile, writeTextFile } from "herdr";

const DIR = `${home()}/.local/state/herdr-board`;
const FILE = `${DIR}/flow.jsonl`;
const MAX_AGE = 30 * 86400000;
const MAX_LINES = 8000;
const MAX_BYTES = 900000;
const GAP_AFTER = 120000;
const IO_TIMEOUT = 15000;

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

export const readFlow = async () => parse(await readTextFile(FILE));

export function awayCounts(events, from, to, isMerged) {
  const last = new Map();
  for (const e of events) if (isLane(e) && e.t > from && e.t <= to) last.set(e.key, e);
  const final = (lane) => [...last.values()].filter((e) => e.to === lane);
  const done = final("done");
  return {
    stuck: final("stuck").length,
    done: done.length,
    merged: done.filter((e) => isMerged(e.key)).length,
    inReview: final("review").filter((e) => e.pr !== null).length,
  };
}

const WEEK = 7 * 86400000;
const MIN_NEEDS_STAY = 60000;

export function actRates(events, now) {
  const rows = new Map();
  const byKey = new Map();
  for (const e of events) if (!e.gap) byKey.set(e.key, [...(byKey.get(e.key) ?? []), e]);
  for (const list of byKey.values()) {
    const lanes = list.filter(isLane);
    const acts = list.filter((e) => e.act && (e.from ?? "needs") === "needs");
    const starts = lanes.filter((e) => e.to === "needs" && e.src && e.t >= now - WEEK);
    for (const entry of starts) {
      const end = lanes.find((e) => e.t > entry.t && e.to !== "needs");
      const next = starts.find((e) => e.t > entry.t);
      const act = acts.find((e) => e.t >= entry.t && (!next || e.t < next.t));
      const row = rows.get(entry.src) ?? { src: entry.src, entered: 0, acted: 0, ignored: 0 };
      if (!act && (end ? end.t : now) - entry.t < MIN_NEEDS_STAY) continue;
      row.entered += 1;
      if (act) row.acted += 1;
      else if (end) row.ignored += 1;
      rows.set(entry.src, row);
    }
  }
  const since = Math.min(...events.filter((e) => isLane(e) && e.to === "needs" && e.src).map((e) => e.t));
  return { rows: [...rows.values()].sort((a, b) => b.entered - a.entered), since: Number.isFinite(since) ? since : null };
}

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

const within = (cx, work) => Promise.race([
  work,
  cx.sleep(IO_TIMEOUT).then(() => {
    throw new Error(`no answer after ${IO_TIMEOUT / 1000}s`);
  }),
]);

async function appendBatch(cx, batch, now) {
  const text = await within(cx, readTextFile(FILE));
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
  await within(cx, writeTextFile(FILE, `${lines.join("\n")}\n`, text));
}

export async function flushFlowLog(now, cx) {
  if (flushing || !queue.length) return;
  flushing = true;
  const batch = queue;
  queue = [];
  try {
    await within(cx, exec("mkdir", ["-p", DIR]));
    try {
      await appendBatch(cx, batch, now);
    } catch {
      await appendBatch(cx, batch, now);
    }
  } catch (error) {
    queue = [...batch, ...queue].slice(-MAX_LINES);
    console.error(`flow log flush failed, ${batch.length} events requeued: ${error.message}`);
  } finally {
    flushing = false;
  }
}
