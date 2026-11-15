// Proof for the board's "Needs you" column: the classifier on the shapes the board shows,
// then the real board loaded through the real loader with the real T3 calls.
import { register } from "node:module";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

register("./loader.mjs", import.meta.url);

const { columnOf, endsWithAsk } = await import("../../coordinator/mods/cockpit/asks.js");
const { load } = await import("../../coordinator/mods/cockpit/hub.js");

const fail = [];
const check = (name, got, want) => {
  const ok = got === want;
  if (!ok) fail.push(name);
  console.log(`${ok ? "ok  " : "FAIL"} ${name}: ${JSON.stringify(got)}${ok ? "" : ` (wanted ${JSON.stringify(want)})`}`);
};

const thread = (kind, ask = false, i = 0) => ({ key: `${kind}${ask ? "ask" : ""}${i}`, kind, ask, at: 0 });
const grp = (kind, threads) => ({ kind, threads, at: 0 });
const classify = (groups) => {
  const cols = { needs: 0, dead: 0, done: 0, run: 0 };
  for (const g of groups) cols[columnOf(g)] += 1;
  return cols;
};

// The state Shyam saw: 33 failed and 21 stopped cards, none of them asking anything.
const deadRuns = [
  ...Array.from({ length: 33 }, (_, i) => grp("fail", [thread("fail", false, i)])),
  ...Array.from({ length: 21 }, (_, i) => grp("stop", [thread("stop", false, i)])),
];
console.log("state A: 54 failed and stopped threads, decisions.json empty");
check("A needs", classify(deadRuns).needs, 0);
check("A dead", classify(deadRuns).dead, 54);

console.log("state B: the same board with one decisions.json item");
const oneDecision = [...deadRuns, grp("ask", [thread("ask")])];
check("B needs", classify(oneDecision).needs, 1);
check("B dead", classify(oneDecision).dead, 54);
console.log("state C: a real ask must never be hidden");
check("C pending request needs", classify([...deadRuns, grp("wait", [thread("wait")])]).needs, 1);
check("C asked turn needs", classify([...deadRuns, grp("fail", [thread("fail", true)])]).needs, 1);
check("C asked done turn needs", classify([grp("done", [thread("done", true)])]).needs, 1);
check("C plain done turn stays done", classify([grp("done", [thread("done")])]).done, 1);

console.log("how a turn ends:");
check("question", endsWithAsk("Shall I run the migration now?"), true);
check("waiting line", endsWithAsk("I need the Railway token.\n\nWAITING: Railway token"), true);
check("bold question", endsWithAsk("... bring it level?**"), true);
check("list question", endsWithAsk("- Is the frame allowed to reboot?"), true);
check("statement", endsWithAsk("Merged. Nothing else needs you."), false);
check("empty", endsWithAsk(""), false);

// The live board, through the real loader, with a decisions file of our choosing.
const file = join(process.env.TMPDIR ?? tmpdir(), `proof-decisions-${process.pid}.json`);
const decisions = JSON.parse(process.env.PROOF_DECISIONS_ITEMS ?? "[]");
writeFileSync(file, JSON.stringify({ updated: new Date().toISOString(), items: decisions }, null, 2) + "\n");
process.env.PROOF_DECISIONS = file;

const started = Date.now();
const board = await load();
const cols = {};
const needs = [];
for (const g of board.groups) {
  const col = columnOf(g);
  cols[col] = (cols[col] ?? 0) + 1;
  if (col === "needs") needs.push(`${g.task || g.title} [${g.kind}] ${g.primary.context}`);
}
console.log(`live board, ${((Date.now() - started) / 1000).toFixed(1)}s, decisions items: ${decisions.length}`);
console.log(`  ${board.groups.length} groups; columns ${JSON.stringify(cols)}; failed+stopped cards ${board.failed}; dead cards ${board.dead}`);
for (const line of needs) console.log(`  needs: ${line}`);

if (fail.length) {
  console.log(`FAILED ${fail.length}: ${fail.join(", ")}`);
  process.exit(1);
}
console.log("proof: all checks passed");
