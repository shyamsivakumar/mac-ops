import { exec, home, readTextFile, writeTextFile } from "herdr";

const DIR = `${home()}/.local/state/herdr-board`;
const FILE = `${DIR}/flow.jsonl`;
const MAX_AGE = 30 * 86400000;
const MAX_LINES = 8000;
const MAX_BYTES = 900000;

let queue = [];
let flushing = false;

export const logLaneChange = (event) => queue.push(event);

const isNew = (last, e) => (e.to === null ? last.has(e.key) && last.get(e.key) !== null : last.get(e.key) !== e.to);

export async function flushFlowLog(now) {
  if (flushing || !queue.length) return;
  flushing = true;
  const batch = queue;
  queue = [];
  try {
    await exec("mkdir", ["-p", DIR]);
    const text = await readTextFile(FILE);
    const lines = (text ?? "").split("\n").filter(Boolean);
    const last = new Map(lines.map((line) => JSON.parse(line)).map((e) => [e.key, e.to]));
    const fresh = [];
    for (const e of batch) {
      if (!isNew(last, e)) continue;
      last.set(e.key, e.to);
      fresh.push(JSON.stringify(e));
    }
    if (!fresh.length) return;
    let kept = [...lines, ...fresh].filter((line) => JSON.parse(line).t >= now - MAX_AGE).slice(-MAX_LINES);
    while (kept.join("\n").length > MAX_BYTES) kept = kept.slice(Math.ceil(kept.length / 10));
    await writeTextFile(FILE, `${kept.join("\n")}\n`, text);
  } catch (error) {
    queue = [...batch, ...queue].slice(-MAX_LINES);
    throw error;
  } finally {
    flushing = false;
  }
}
