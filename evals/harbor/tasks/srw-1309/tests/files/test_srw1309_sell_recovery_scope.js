'use strict';
// SRW-1309: a durable sell record whose client order id cannot be read must
// block only the trade it names. Before this proof one legacy record blocked
// every open trade's exit pass on Bot 1 (evidence/bot1-close-2026-11-18/rca.md).
// No broker traffic is allowed: the facade is read over a sanitized ledger.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');

const root = __dirname;
const { AlpacaPaperExecution } = require(root + '/alpaca_paper_execution.js');
const { buildPublicHealthPayload } = require(root + '/paper_health.js');

const now = Date.parse('2026-11-18T19:00:00.000Z');
const SYMBOL = 'SPY261120C00600000';

// The two real bad root ids from the production ledger, verbatim.
const BAD_OLD = 'thala-TH-261106-90014-exit-tp1-2';
const BAD_TEST = 'thala-TH-TEST-261116-918431-exit-TH-TEST-261116-918431-EXIT-L1-limit';
const BAD_TEST_REPLACEMENT = 'thala-r-8f07c1d4e9b2a6f30c5d8e1b7a4f2c60d9e3b514';
const GOOD = 'thala-TH-261120-7-exit-tp1-L1-limit';
// An id with two possible owners: it blocks both of them.
const AMBIGUOUS = 'thala-TH-foo-exit-bar-exit-TP1-L1-limit';
// Records that only break at runtime: the loader refuses an invalid ledger, so
// these are injected into the loaded ledger in memory.
const INVALID_OWNED = 'thala-TH-261120-77-exit-stop-L1-limit';
const CONFLICT = 'thala-TH-261120-55-exit-stop-L1-limit';
const MISSING_ROOT_CHILD = 'thala-r-0123456789abcdef0123456789abcdef0123456789abcdef';
const MISSING_ROOT = 'thala-TH-261120-66-exit-stop-L1-limit';
// Records with no readable owner: they block nobody and alarm once.
const OWNERLESS = 'thala-legacy';
const INVALID_OWNERLESS = 'junk-sell';
const GHOST_CHILD = 'thala-r-fedcba9876543210fedcba9876543210fedcba9876543210';
// An opaque replacement id with no root id: only its parent id names the trade.
const PARENT_ONLY_CHILD = 'thala-r-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const PARENT_ONLY_PARENT = 'thala-TH-261120-88-exit-stop-L1-limit';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'srw1309-'));
const ledgerPath = path.join(dir, 'broker-ledger.json');
const forbiddenFetch = async () => { throw new Error('broker_transport_forbidden'); };
const build = (ledger = ledgerPath) => new AlpacaPaperExecution({
  ledgerPath: ledger,
  telegramCredentials: { key: 'paper-key', secret: 'paper-secret' },
  instanceLockHeld: () => true,
  now: () => now,
  fetch: forbiddenFetch,
});

const sellRecord = (clientOrderId, contract, quantity, extra = {}) => ({
  owner: 'discord_v2', clientOrderId, contract, side: 'sell', quantity,
  filledQty: 0, brokerOrderId: null, status: 'new', createdAtMs: now, ...extra,
});

// 1. The durable ledger holds the two real bad records and one good record.
const api = build();
api.loadLedger(now);
api.ledger.externalOrders = {
  [BAD_OLD]: sellRecord(BAD_OLD, 'SPXW261106P07395000', 1,
    { filledQty: 1, status: 'filled', brokerOrderId: 'b-old', brokerConfirmed: true, authoritativeStatus: 'filled' }),
  [BAD_TEST]: sellRecord(BAD_TEST, 'SPY261120C00740000', 2,
    { status: 'replaced', brokerOrderId: 'b-test', replacedByBrokerOrderId: 'b-test-2' }),
  [BAD_TEST_REPLACEMENT]: sellRecord(BAD_TEST_REPLACEMENT, 'SPY261120C00740000', 2,
    { status: 'rejected', brokerOrderId: 'b-test-2', rootClientOrderId: BAD_TEST, parentClientOrderId: BAD_TEST }),
  [GOOD]: sellRecord(GOOD, SYMBOL, 3,
    { filledQty: 3, status: 'filled', brokerOrderId: 'b-good', brokerConfirmed: true, authoritativeStatus: 'filled' }),
  [AMBIGUOUS]: sellRecord(AMBIGUOUS, 'SPY261120C00740000', 1, { status: 'new', brokerOrderId: 'b-ambiguous' }),
  [OWNERLESS]: sellRecord(OWNERLESS, 'SPY261120C00740000', 1, { status: 'new', brokerOrderId: 'b-legacy' }),
};
api.persistLedger(now);

// A facade-only restart reads the same durable ledger, then three kinds of
// record that can only break in memory join it.
const restarted = build();
restarted.loadLedger(now);
assert.equal(restarted.ledgerError, null);
Object.assign(restarted.ledger.externalOrders, {
  [INVALID_OWNED]: sellRecord(INVALID_OWNED, SYMBOL, 1, { filledQty: 5 }),
  [CONFLICT]: sellRecord(CONFLICT, SYMBOL, 1, { brokerOrderId: 'b-55', identityConflict: true }),
  [MISSING_ROOT_CHILD]: sellRecord(MISSING_ROOT_CHILD, SYMBOL, 1,
    { rootClientOrderId: MISSING_ROOT, parentClientOrderId: MISSING_ROOT }),
  [INVALID_OWNERLESS]: { side: 'sell', garbage: true },
  [GHOST_CHILD]: sellRecord(GHOST_CHILD, SYMBOL, 1,
    { rootClientOrderId: 'thala-ghost', parentClientOrderId: 'thala-ghost' }),
  [PARENT_ONLY_CHILD]: sellRecord(PARENT_ONLY_CHILD, SYMBOL, 1, { parentClientOrderId: PARENT_ONLY_PARENT }),
});
const facadeBroker = restarted.finishThalaBroker({}, forbiddenFetch, false);

// 2. The alarm is captured: one alarm per bad record, never one per pass.
const alarms = [];
const realWarn = console.warn;
console.warn = (line) => { alarms.push(String(line)); };

// 3. Another trade's snapshot resolves and never sees another trade's records,
// whatever else is wrong in the ledger.
const other = facadeBroker.getSellRecoverySnapshot({ tradeId: 'TH-261120-7' });
assert.equal(other.records.length, 1, 'only the requested trade records are exposed');
assert.equal(other.records[0].clientOrderId, GOOD);
assert.equal(other.groups.length, 1);
assert.equal(other.groups[0].rootClientOrderId, GOOD);
assert.equal(other.groups[0].authoritativeTerminal, true);
const unknown = facadeBroker.getSellRecoverySnapshot({ tradeId: 'TH-NOT-HERE' });
assert.deepEqual([unknown.groups, unknown.records], [[], []], 'an unrelated trade reads empty evidence');

// 4. Every trade that owns or may own an unreadable record stays blocked, and
// the error says it is the trade's own record.
const OWNERS = ['TH-261106-90014', 'TH-TEST-261116-918431', 'TH-foo', 'TH-foo-exit-bar',
  'TH-261120-77', 'TH-261120-55', 'TH-261120-66', 'TH-261120-88'];
for (const owner of OWNERS) {
  assert.throws(() => facadeBroker.getSellRecoverySnapshot({ tradeId: owner }),
    (error) => error.code === 'external_sell_recovery_unavailable' && error.ownerRecord === true,
    `owner ${owner} stays blocked`);
}

// 5. One alarm per bad record, once per process, ownerless records included.
const FAULTY = [BAD_OLD, BAD_TEST, BAD_TEST_REPLACEMENT, AMBIGUOUS, OWNERLESS, INVALID_OWNED, CONFLICT,
  MISSING_ROOT_CHILD, INVALID_OWNERLESS, GHOST_CHILD, PARENT_ONLY_CHILD];
const alarmLines = () => alarms.filter(line => line.includes('external_sell_record_unparsed'));
assert.equal(alarmLines().length, FAULTY.length, 'one alarm per bad record');
for (const id of FAULTY) assert.equal(alarmLines().filter(line => line.includes(`record=${id} `)).length, 1, id);
assert.ok(alarmLines().some(line => line.includes(`record=${OWNERLESS} trade=none`)), 'an ownerless record names no trade');
facadeBroker.getSellRecoverySnapshot({ tradeId: 'TH-261120-8' });
facadeBroker.getSellRecoverySnapshot({ tradeId: 'TH-261120-9' });
assert.equal(alarmLines().length, FAULTY.length, 'the alarm does not repeat on every exit pass');
assert.deepEqual(restarted.unreadableSellRecords().map(fault => fault.recordId).sort(), [...FAULTY].sort(),
  'health reads every unreadable record');

// 6. The executor: the real exit pass of the other trades still sells.
const executorFile = path.join(root, 'thala_v2_executor.js');
const executorModule = new Module(executorFile, module);
executorModule.filename = executorFile;
executorModule.paths = Module._nodeModulePaths(root);
const source = fs.readFileSync(executorFile, 'utf8');
executorModule._compile(source.replace('stop, handle, advance, reconcileStartup,',
  'probe: { advanceOpen, handleSellRefusal }, stop, handle, advance, reconcileStartup,'), executorFile);
const { createThalaV2Executor } = executorModule.exports;

const submits = [];
const broker = {
  ...facadeBroker,
  getOptionQuote: async () => ({ bid: 0.5, ask: 0.6, at: now }),
  getUnderlyingPrice: async () => ({ price: 700 }),
  submitOrder: async (order) => { submits.push(order); return { id: `b-submit-${submits.length}`, ...order }; },
};
const openTrade = (tradeId, extra = {}) => ({
  tradeId, state: 'open', qty: 6, qtyLeft: 6, sellLegs: 0, fill: 1,
  intent: { optionSymbol: SYMBOL, underlying: 'SPY', entry: { tick: 0.01 } },
  plan: {}, exitsDone: [], soldByRef: {}, events: [], ...extra,
});
const trades = {
  // A stop that has triggered.
  'TH-261120-7': openTrade('TH-261120-7', { qtyLeft: 3,
    plan: { stop: { basis: 'optionPrice', optionPrice: 0.6, qtyFrac: 1 } } }),
  // A CLOSE card waiting to be executed.
  'TH-261120-8': openTrade('TH-261120-8', { pendingClose: { seq: 2184, exitRef: 'stop', qtyFrac: 'all_remaining',
    order: { type: 'limit', limit: 0.5, stepToBidAfterSecs: 60, validSecs: 300 } } }),
  // The 15:55 time exit.
  'TH-261120-9': openTrade('TH-261120-9', { timeArmed: true, timeAtMs: now - 1000 }),
  // An unrelated trade that already holds a usable pending attempt.
  'TH-261120-11': openTrade('TH-261120-11', { qtyLeft: 2,
    pendingSellAttempt: { ref: 'stop', qty: 2, leg: 1, bid: 0.5 } }),
  // The owners of the unreadable records.
  ...Object.fromEntries(OWNERS.map(owner => [owner, openTrade(owner)])),
  // A trade whose blocker is stale and that holds a usable pending attempt.
  'TH-261120-12': openTrade('TH-261120-12', { qtyLeft: 2,
    pendingSellAttempt: { ref: 'stop', qty: 2, leg: 1, bid: 0.5 },
    sellRecoveryBlocked: { reason: 'external_sell_recovery_unavailable', atMs: now - 60_000 } }),
  // A trade whose blocker is stale: the evidence is readable again.
  'TH-261120-10': openTrade('TH-261120-10', { sellRecoveryBlocked: {
    reason: 'external_sell_recovery_unavailable', atMs: now - 60_000 } }),
};
const state = { trades };
const exec = createThalaV2Executor({ broker, clock: () => now, store: { load: () => state, save: () => {} } });

(async () => {
  // The stop of an unrelated trade runs.
  await exec.probe.advanceOpen(trades['TH-261120-7']);
  // The CLOSE card of an unrelated trade runs.
  await exec.probe.advanceOpen(trades['TH-261120-8']);
  // The time exit of an unrelated trade runs.
  await exec.probe.advanceOpen(trades['TH-261120-9']);
  await exec.probe.advanceOpen(trades['TH-261120-11']);
  const sent = submits.map(order => order.client_order_id).sort();
  assert.deepEqual(sent, [
    'thala-TH-261120-11-exit-stop-L1-limit',
    'thala-TH-261120-7-exit-stop-L1-limit',
    'thala-TH-261120-8-exit-stop-L1-limit',
    'thala-TH-261120-9-exit-time-L1-limit',
  ], 'stop, CLOSE card, time exit and a usable pending attempt of unrelated trades all sell');

  // The owners stay blocked for their own exit pass only, with or without a
  // usable pending attempt.
  for (const owner of OWNERS) {
    const trade = trades[owner];
    await assert.rejects(exec.probe.advanceOpen(trade), /external_sell_recovery_unavailable/,
      `owner ${owner} cannot sell`);
    const refusal = Object.assign(new Error('external_sell_recovery_unavailable'),
      { code: 'external_sell_recovery_unavailable' });
    assert.equal(await exec.probe.handleSellRefusal(trade, refusal), true);
    const pending = openTrade(owner, { pendingSellAttempt: { ref: 'stop', qty: 2, leg: 1, bid: 0.5 } });
    await assert.rejects(exec.probe.advanceOpen(pending), /external_sell_recovery_unavailable/,
      `owner ${owner} with a pending attempt cannot resend`);
  }
  assert.equal(submits.length, 4, 'a blocked trade never sells');

  // A stale blocker is cleared once the evidence is readable again.
  await exec.probe.advanceOpen(trades['TH-261120-10']);
  assert.equal(trades['TH-261120-10'].sellRecoveryBlocked, undefined,
    'a resolved recovery blocker is not a blocker any more');
  await exec.probe.advanceOpen(trades['TH-261120-12']);
  assert.equal(trades['TH-261120-12'].sellRecoveryBlocked, undefined,
    'a stale blocker clears for a trade that holds a usable pending attempt');
  assert.equal(submits.length, 5, 'the usable pending attempt resent once the blocker cleared');

  // 7. Health names the blocked trades and refuses to report a ready exit path.
  const blocked = exec.blockedExitTrades();
  assert.deepEqual(blocked.map(row => row.tradeId).sort(), [...OWNERS].sort());
  const green = { singleOwner: true, stateWritable: true, brokerReconciled: true, brokerAccountRead: true,
    brokerPositionsRead: true, brokerOpenOrdersRead: true, exitManagerRunning: true, exitsRunning: true,
    exitDataCapacity: 5, requiredQuotesFresh: true, deploymentKnown: false, telegramBasisAt: 0 };
  const signal = { mode: 'discord', discord: { state: 'ready', connected: true, historyPending: false } };
  const healthState = (facts) => ({ runtimeMode: 'discord-only', heartbeat: 'running', discordReadiness: facts,
    thala: { openTrades: 5, pendingOrders: 0 } });
  const healthy = buildPublicHealthPayload(healthState({ ...green, exitBlockedTrades: [] }), null, signal, null, now);
  assert.equal(healthy.exitsReady, true, 'no blocked trade keeps the exit path ready');
  const degraded = buildPublicHealthPayload(healthState({ ...green, exitBlockedTrades: blocked }), null, signal, null, now);
  assert.equal(degraded.exitsReady, false, 'a blocked exit pass is not a ready exit path');
  assert.deepEqual(degraded.exitsBlockedTrades.map(row => row.tradeId).sort(), [...OWNERS].sort(),
    'health names the blocked trades');
  assert.ok(degraded.discordOnlyReadiness.exitFailReasons.includes('exit_trade_blocked'));
  // An unreadable record with no owner blocks no exit, and health still shows it.
  const faults = restarted.unreadableSellRecords();
  const ownerlessOnly = buildPublicHealthPayload(
    healthState({ ...green, exitBlockedTrades: [], sellRecordFaults: faults }), null, signal, null, now);
  assert.equal(ownerlessOnly.exitsReady, true, 'an ownerless record blocks no exit path');
  assert.ok(ownerlessOnly.sellRecordFaults.some(fault => fault.recordId === OWNERLESS), 'health shows the ownerless record');

  console.warn = realWarn;
  exec.stop();
  fs.rmSync(dir, { recursive: true, force: true });
  console.log('PASS scoped sell recovery: other trades stop, CLOSE and time exit run; owners stay blocked; health names them');
})().catch((error) => {
  console.warn = realWarn;
  try { exec.stop(); } catch { /* the executor may already be stopped */ }
  console.error(error);
  process.exitCode = 1;
});
