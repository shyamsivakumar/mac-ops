"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const ledger = require("./strategy_trial_ledger");
const {runDailyShadow} = require("./strategy_daily_shadow");

const day = "2026-11-11";
const env = {RAILWAY_SERVICE_BOT2_INTAKE_URL: "bot2.example", BOT2_WEBHOOK_SECRET: "test-secret"};

function setup(t, fixtureMode = false) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "bot2-shadow-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const ledgerPath = path.join(dir, "ledger.jsonl");
  const recordPath = path.join(dir, "telegram.jsonl");
  fs.writeFileSync(recordPath, "");
  ledger.appendEvent(ledgerPath, {type: "daily_shadow_completed", day, fixtureMode, summary: {}});
  const options = {day, now: new Date(day + "T22:00:00Z"), ledgerPath, fixtureMode, env,
    telegram: {recordPath, inputKind: "synthetic"}, ...(fixtureMode ? {handler() {}} : {})};
  const events = (type) => ledger.queryLedger(ledgerPath, {type});
  return {options, events};
}

function response(body, status = 200) {
  return {ok: status >= 200 && status < 300, status, async json() { return body; }};
}

test("records injected Bot 2 response and deduplicates identical replays", async (t) => {
  const {options, events} = setup(t);
  const body = {date: day, alerts: [{id: 1}], decisions: []};
  let calls = 0;
  options.fetch = async (url, request) => {
    calls++;
    assert.equal(url, "https://bot2.example/today?date=" + day);
    assert.equal(request.headers["x-bot2-secret"], "test-secret");
    assert.equal(request.redirect, "error");
    return response(body);
  };
  assert.equal((await runDailyShadow(options)).status, "idempotent_replay");
  await runDailyShadow(options);
  const records = events("bot2_day_compiled");
  assert.equal(calls, 2);
  assert.equal(records.length, 1);
  assert.deepEqual(records[0].event.compiled, body);
  assert.equal(records[0].event.fixtureMode, false);
  assert.equal(records[0].event.supersedesSeq, null);
  assert.equal(events("telegram_day_compiled").length, 1);
});

test("changed response supersedes the previous compile", async (t) => {
  const {options, events} = setup(t);
  let version = 0;
  options.fetch = async () => response({date: day, version: ++version});
  await runDailyShadow(options);
  await runDailyShadow(options);
  const records = events("bot2_day_compiled");
  assert.equal(records.length, 2);
  assert.equal(records[1].event.supersedesSeq, records[0].seq);
});

for (const [label, fetch] of [
  ["non-OK response", async () => response({}, 503)],
  ["date mismatch", async () => response({date: "2026-11-10"})],
  ["unreachable endpoint", async () => { throw new Error("unreachable"); }]
]) {
  test(label + " leaves Telegram compilation intact", async (t) => {
    const {options, events} = setup(t);
    options.fetch = fetch;
    assert.equal((await runDailyShadow(options)).status, "idempotent_replay");
    assert.equal(events("bot2_day_compiled").length, 0);
    assert.equal(events("telegram_day_compiled").length, 1);
  });
}

test("fixture runs never fetch Bot 2 even when configured", async (t) => {
  const {options, events} = setup(t, true);
  let calls = 0;
  options.fetch = async () => { calls++; return response({date: day}); };
  const originalFetch = global.fetch;
  const oldHost = process.env.RAILWAY_SERVICE_BOT2_INTAKE_URL;
  const oldSecret = process.env.BOT2_WEBHOOK_SECRET;
  process.env.RAILWAY_SERVICE_BOT2_INTAKE_URL = env.RAILWAY_SERVICE_BOT2_INTAKE_URL;
  process.env.BOT2_WEBHOOK_SECRET = env.BOT2_WEBHOOK_SECRET;
  global.fetch = options.fetch;
  t.after(() => {
    global.fetch = originalFetch;
    if (oldHost === undefined) delete process.env.RAILWAY_SERVICE_BOT2_INTAKE_URL;
    else process.env.RAILWAY_SERVICE_BOT2_INTAKE_URL = oldHost;
    if (oldSecret === undefined) delete process.env.BOT2_WEBHOOK_SECRET;
    else process.env.BOT2_WEBHOOK_SECRET = oldSecret;
  });
  await runDailyShadow(options);
  assert.equal(calls, 0);
  assert.equal(events("bot2_day_compiled").length, 0);
  assert.equal(events("telegram_day_compiled").length, 1);
});
