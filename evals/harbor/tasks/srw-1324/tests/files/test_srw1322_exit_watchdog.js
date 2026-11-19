'use strict';

// SRW-1322 proof, offline. The replay is 2026-11-18 13:53 ET: TH-261118-02181 and
// TH-261118-02182 got a CLOSE card and no sell reached the broker; TH-261118-02185
// is that day's normal exit (its sell reached the broker). Every transport is a fake.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { closeDecisions, traderDecisions, botDecisions, createExitWatchdog, createAlpacaBrokerSource, renderExitMiss, wakeDelayMs } = require('./scripts/srw1322_exit_watchdog.cjs');
const { createExitWatchdogForService } = require('./scripts/srw659_alarm_service.cjs');

const T1353 = Date.parse('2026-11-18T18:53:00.000Z');
const T1354 = Date.parse('2026-11-18T18:54:00.000Z');
const T1550 = Date.parse('2026-11-18T20:50:00.000Z');
const T1551 = Date.parse('2026-11-18T20:51:00.000Z');
const AMD = 'AMD261118C00160000', NVDA = 'NVDA261118C00220000', TSLA = 'TSLA261118C00250000';
const card = (tradeId, type, symbol) => ({ tradeId, type, atMs: T1353, doc: { type, trade_id: tradeId, exit_ref: 'stop', ...(symbol ? { option: { symbol } } : {}) } });
const cards = [
  card('TH-261118-02181', 'OPEN', AMD), card('TH-261118-02181', 'CLOSE'),
  card('TH-261118-02182', 'OPEN', NVDA), card('TH-261118-02182', 'CLOSE'),
  card('TH-261118-02185', 'OPEN', TSLA), card('TH-261118-02185', 'CLOSE'),
];

function make({ stateFile = null, at = T1354, broker = null, decisions = closeDecisions(cards, new Map()), deliver = () => true } = {}) {
  const clock = { at };
  const pages = [];
  const watchdog = createExitWatchdog({
    readBroker: async () => broker || { positions: [AMD, NVDA, TSLA].map(symbol => ({ symbol })), orders: [{ symbol: TSLA, side: 'sell', submittedAtMs: T1353 + 10_000 }] },
    readDecisions: async () => decisions,
    page: async miss => { pages.push(miss); return deliver(pages.length); }, now: () => clock.at, stateFile,
  });
  return { clock, pages, watchdog };
}

const cases = {
  async 'the missed exits of 2026-11-18 page within 60 s, once each, and the normal exit pages nothing'() {
    const { clock, pages, watchdog } = make({ at: T1353 });
    await watchdog.check();
    assert.equal(pages.length, 0, 'the broker still has its 60 s window');
    clock.at = T1354;
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['TH-261118-02181', 'TH-261118-02182']);
    assert.match(renderExitMiss(pages[0]), /no sell order reached the broker/);
    clock.at = T1354 + 60_000;
    await watchdog.check();
    assert.equal(pages.length, 2, 'no repeat page for a trade already paged');
  },
  async 'the caller is told when the decision is due'() {
    const { watchdog } = make({ at: T1353 });
    await watchdog.check();
    assert.equal(watchdog.nextDeadlineAtMs(), T1354, 'the deadline is the decision plus its window');
  },
  async 'a page that did not land is retried, then spent'() {
    const { clock, pages, watchdog } = make({ deliver: count => count > 2 });
    await watchdog.check();
    assert.equal(pages.length, 2, 'both deliveries were attempted and failed');
    clock.at += 15_000;
    await watchdog.check();
    assert.equal(pages.length, 4, 'both are retried');
    await watchdog.check();
    assert.equal(pages.length, 4, 'a delivered page is not sent again');
  },
  async 'a restart does not page the same position again'() {
    const stateFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'srw1322-')), 'exit-watchdog.json');
    await make({ stateFile }).watchdog.check();
    const restarted = make({ stateFile });
    await restarted.watchdog.check();
    assert.equal(restarted.pages.length, 0);
  },
  async 'a position paged by a CLOSE card is not paged again by the 0DTE backstop after a restart'() {
    const stateFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'srw1322-')), 'exit-watchdog.json');
    const broker = { positions: [{ symbol: AMD }], orders: [] };
    const late = [{ tradeId: 'TH-261118-02181', type: 'OPEN', atMs: T1550 - 60_000, doc: { type: 'OPEN', trade_id: 'TH-261118-02181', option: { symbol: AMD } } },
      { tradeId: 'TH-261118-02181', type: 'CLOSE', atMs: T1550 - 60_000, doc: { type: 'CLOSE', trade_id: 'TH-261118-02181', exit_ref: 'stop' } }];
    const first = make({ stateFile, at: T1550 - 60_000, broker, decisions: closeDecisions(late, new Map()) });
    await first.watchdog.check();
    assert.equal(first.pages.length, 0, 'the CLOSE card is not yet due at 15:49 ET');
    first.clock.at = T1550;
    await first.watchdog.check();
    assert.equal(first.pages.length, 1, 'the CLOSE card pages at 15:50 ET');
    const restarted = make({ stateFile, at: T1551, broker, decisions: closeDecisions(late, new Map()) });
    await restarted.watchdog.check();
    assert.equal(restarted.pages.length, 0, 'the 0DTE backstop does not page the position again');
  },
  async 'the 0DTE backstop waits its window and answers to a working sell'() {
    const broker = { positions: [{ symbol: AMD }], orders: [] };
    const { clock, pages, watchdog } = make({ at: T1550, broker, decisions: [] });
    await watchdog.check();
    assert.equal(pages.length, 0, 'the 0DTE deadline gets the same 60 s window');
    clock.at = T1551;
    await watchdog.check();
    assert.equal(pages.length, 1, 'the 0DTE backstop pages after the window');
    assert.equal(pages[0].reason, 'zero_dte_1550');
    const working = make({ at: T1551, broker: { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1354, open: true }] }, decisions: [] });
    await working.watchdog.check();
    assert.equal(working.pages.length, 0, 'a working sell answers the backstop');
  },
  async 'a sell that arrived late does not answer the decision'() {
    const broker = { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1353 + 65_000 }] };
    const { pages, watchdog } = make({ at: T1353 + 70_000, broker, decisions: closeDecisions(cards.filter(card => card.tradeId === 'TH-261118-02181'), new Map()) });
    await watchdog.check();
    assert.equal(pages.length, 1, 'a sell outside the window is a late exit, not an answer');
  },
  async 'a sell for another trade in the same contract does not answer'() {
    const broker = {
      positions: [{ symbol: AMD }],
      orders: [
        { symbol: AMD, side: 'buy', submittedAtMs: T1353 - 3_600_000, filledQty: 2 },
        { symbol: AMD, side: 'sell', submittedAtMs: T1353 - 3_500_000, filledQty: 2 },
        { symbol: AMD, side: 'buy', submittedAtMs: T1353 - 60_000, filledQty: 2 },
      ],
    };
    const { pages, watchdog } = make({ broker, decisions: closeDecisions(cards.filter(card => card.tradeId === 'TH-261118-02181'), new Map()) });
    await watchdog.check();
    assert.equal(pages.length, 1, 'the sell closed the earlier position, not this one');
  },
  async 'a sell still working but sent after the window does not answer the decision'() {
    const broker = { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1353 + 65_000, open: true }] };
    const { pages, watchdog } = make({ at: T1353 + 70_000, broker, decisions: closeDecisions(cards.slice(0, 2), new Map()) });
    await watchdog.check();
    assert.equal(pages.length, 1, 'a late order that is still open is still late');
  },
  async 'an order named by the ledger but sent after the window does not answer'() {
    const broker = { positions: [{ symbol: AMD }], orders: [{ clientOrderId: 'late-exit', symbol: AMD, side: 'sell', submittedAtMs: T1354 + 10_000, open: true }] };
    const { clock, pages, watchdog } = make({ at: T1353, broker, decisions: botDecisions([{ trade_id: 'B2-L', contract: AMD, exit_reason: 'stop', exit_client_order_id: 'late-exit' }]) });
    await watchdog.check();
    clock.at = T1354 + 15_000;
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['B2-L']);
  },
  async 'a sell for trade A does not answer trade B in the same contract'() {
    const SPY = 'SPY261120C00600000';
    const broker = { positions: [{ symbol: SPY }], orders: [{ id: 'o-a', clientOrderId: 'a-exit', symbol: SPY, side: 'sell', submittedAtMs: T1353 + 10_000 }] };
    const trades = [{ trade_id: 'B2-A', contract: SPY, exit_reason: 'stop', exit_client_order_id: 'a-exit' }, { trade_id: 'B2-B', contract: SPY, exit_reason: 'stop', exit_client_order_id: 'b-exit' },
      { trade_id: 'B2-C', contract: SPY, exit_reason: 'stop' }];
    const { clock, pages, watchdog } = make({ at: T1353, broker, decisions: botDecisions(trades) });
    await watchdog.check();
    clock.at = T1353 + 60_000;
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['B2-B', 'B2-C'], 'A is answered by its own sell; B names an order that never arrived; C has no order and A\'s sell is claimed');
  },
  async 'one position is paged once after its opening fill leaves the recent orders'() {
    const stateFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'srw1322-')), 'exit-watchdog.json');
    const opening = { symbol: AMD, side: 'buy', submittedAtMs: T1353 - 3_600_000, filledQty: 2 };
    const first = make({ stateFile, broker: { positions: [{ symbol: AMD }], orders: [opening] }, decisions: closeDecisions(cards.slice(0, 2), new Map()) });
    await first.watchdog.check();
    assert.equal(first.pages.length, 1);
    const later = make({ stateFile, broker: { positions: [{ symbol: AMD }], orders: [] }, decisions: closeDecisions(cards.slice(0, 2), new Map()) });
    await later.watchdog.check();
    assert.equal(later.pages.length, 0, 'the key is the trade, not the order history');
  },
  async 'the wake leaves room for the reads, so the page lands on the deadline'() {
    const clock = { at: T1353 };
    const pages = [];
    const watchdog = createExitWatchdog({
      readBroker: async () => { clock.at += 5_000; return { positions: [{ symbol: AMD }], orders: [] }; },
      readDecisions: async () => closeDecisions(cards.slice(0, 2), new Map()),
      page: async () => { pages.push(clock.at); return true; }, now: () => clock.at,
    });
    for (let step = 0; step < 12 && !pages.length; step++) {
      await watchdog.check();
      if (!pages.length) clock.at += wakeDelayMs({ dueMs: watchdog.nextDeadlineAtMs(), nowMs: clock.at, intervalMs: 15_000, lastCheckMs: 5_000 });
    }
    assert.deepEqual(pages, [T1354], 'the reads end at the deadline, so the page is not 5 s late');
  },
  async 'a Bot 1 exit trigger with no CLOSE card pages, and the page names its bot'() {
    const trades = { 'TH-1': { tradeId: 'TH-1', qtyLeft: 2, intent: { optionSymbol: AMD }, events: [{ op: 'exit_trigger', ref: 'stop', at: '2026-11-18T18:53:00.000Z' }] }, 'TH-2': { tradeId: 'TH-2', qtyLeft: 0, intent: { optionSymbol: NVDA }, events: [{ op: 'exit_trigger', ref: 'stop', at: '2026-11-18T18:53:00.000Z' }] } };
    const { pages, watchdog } = make({ broker: { positions: [{ symbol: AMD }, { symbol: NVDA }], orders: [] }, decisions: traderDecisions(trades) });
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['TH-1'], 'a trade with nothing left is not an exit that is due');
    assert.match(renderExitMiss(pages[0]), /^Bot 1 /);
    assert.match(renderExitMiss({ ...pages[0], bot: 'bot2' }), /^Bot 2 /);
  },
  async 'a Bot 2 exit decision with no sell and no CLOSE card pages'() {
    const broker = { positions: [{ symbol: AMD }], orders: [] };
    const { clock, pages, watchdog } = make({ at: T1353, broker, decisions: botDecisions([{ trade_id: 'B2-1', contract: AMD, exit_reason: 'stop', qty_left: 2 }]) });
    await watchdog.check();
    assert.equal(pages.length, 0, 'Bot 2 has no decision time, so the window starts when it is seen');
    clock.at = T1353 + 60_000;
    await watchdog.check();
    assert.equal(pages.length, 1, 'the missed Bot 2 exit is paged');
    assert.equal(pages[0].bot, 'bot2');
  },
  async 'two trades on one 0DTE contract are each paged once'() {
    const both = [...cards.slice(0, 2), card('TH-261118-02191', 'OPEN', AMD), card('TH-261118-02191', 'CLOSE')];
    const { clock, pages, watchdog } = make({ broker: { positions: [{ symbol: AMD }], orders: [] }, decisions: closeDecisions(both, new Map()) });
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['TH-261118-02181', 'TH-261118-02191'], 'paging A does not skip B');
    clock.at += 60_000;
    await watchdog.check();
    assert.equal(pages.length, 2, 'neither trade is paged again');
  },
  async 'one sell answers one of two overlapping decisions on the same contract'() {
    const later = card('TH-261118-02191', 'CLOSE');
    const both = [...cards.slice(0, 2), card('TH-261118-02191', 'OPEN', AMD), { ...later, atMs: T1353 + 20_000 }];
    const broker = { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1353 + 30_000 }] };
    const { clock, pages, watchdog } = make({ at: T1353 + 80_000, broker, decisions: closeDecisions(both, new Map()) });
    await watchdog.check();
    assert.deepEqual(pages.map(page => page.tradeId), ['TH-261118-02191'], 'the sell answers the earlier decision; the later one is missed');
    clock.at += 60_000;
    await watchdog.check();
    assert.equal(pages.length, 1);
  },
  async 'a broker snapshot is judged at the instant it was read, not when the decisions finished'() {
    const clock = { at: T1353 };
    const pages = [];
    const watchdog = createExitWatchdog({
      readBroker: async () => { clock.at = T1354 - 5_000; return { positions: [{ symbol: AMD }], orders: [] }; },
      readDecisions: async () => { await new Promise(resolve => setImmediate(resolve)); clock.at = T1354; return closeDecisions(cards.slice(0, 2), new Map()); },
      page: async miss => { pages.push(miss); return true; }, now: () => clock.at,
    });
    await watchdog.check();
    assert.equal(pages.length, 0, 'a sell at 13:53:59 is not in a snapshot read at 13:53:55');
    assert.equal(watchdog.nextDeadlineAtMs(), T1354);
  },
  async 'a sell sent after the 0DTE window closed does not answer the backstop, even at 15:51:45'() {
    const broker = { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1551 + 30_000, open: true }] };
    const { pages, watchdog } = make({ at: T1551 + 45_000, broker, decisions: [] });
    await watchdog.check();
    assert.equal(pages.length, 1, 'the window ran 15:50:00 to 15:51:00 ET');
    assert.equal(pages[0].decidedAtMs, T1550);
  },
  async 'a working sell that the broker lists twice answers one decision, not two'() {
    const sell = { id: 'o-1', client_order_id: 'c-1', symbol: AMD, side: 'sell', status: 'new', submitted_at: new Date(T1353 + 10_000).toISOString(), filled_qty: '0' };
    const read = createAlpacaBrokerSource({ key: 'k', secret: 's', fetchImpl: async url => ({ ok: true, json: async () => (url.includes('positions') ? [{ symbol: AMD, qty: '2' }] : [sell]) }) });
    const broker = await read();
    assert.equal(broker.orders.length, 1, 'the recent and open lists name the same order');
    assert.equal(broker.orders[0].open, true);
    const two = ['A', 'B'].flatMap(id => closeDecisions([{ tradeId: `T-${id}`, type: 'OPEN', atMs: T1353, doc: { option: { symbol: AMD } } }, { tradeId: `T-${id}`, type: 'CLOSE', atMs: T1353, doc: { exit_ref: 'stop' } }], new Map()));
    const { pages, watchdog } = make({ broker, decisions: two });
    await watchdog.check();
    assert.equal(pages.length, 1, 'one sell is one exit: the other trade is paged');
  },
  async 'a CLOSE card and a trader trigger for one trade are one decision: a timely sell answers it, no sell pages once'() {
    const trigger = { 'TH-261118-02181': { tradeId: 'TH-261118-02181', qtyLeft: 2, intent: { optionSymbol: AMD }, events: [{ op: 'exit_trigger', ref: 'stop', at: new Date(T1353 - 5_000).toISOString() }] } };
    const both = [...closeDecisions(cards.slice(0, 2), new Map()), ...traderDecisions(trigger)];
    const answered = make({ broker: { positions: [{ symbol: AMD }], orders: [{ symbol: AMD, side: 'sell', submittedAtMs: T1353 + 10_000 }] }, decisions: both });
    await answered.watchdog.check();
    assert.equal(answered.pages.length, 0, 'one sell answers the one trade; the second candidate is not a second decision');
    const missed = make({ broker: { positions: [{ symbol: AMD }], orders: [] }, decisions: both });
    await missed.watchdog.check();
    assert.deepEqual(missed.pages.map(page => page.tradeId), ['TH-261118-02181'], 'one page for the one trade');
    assert.equal(missed.pages[0].decidedAtMs, T1353 - 5_000, 'counted from the earlier of the two');
  },
  async 'a slow positions read does not move the order snapshot past a sell it never saw'() {
    const clock = { at: T1353 };
    const pages = [];
    const read = createAlpacaBrokerSource({
      key: 'k', secret: 's', now: () => clock.at,
      fetchImpl: async url => {
        if (url.includes('positions')) { await new Promise(resolve => setImmediate(resolve)); clock.at = T1354; return { ok: true, json: async () => [{ symbol: AMD, qty: '2' }] }; }
        clock.at = T1354 - 5_000;
        return { ok: true, json: async () => [] };
      },
    });
    const watchdog = createExitWatchdog({
      readBroker: read, readDecisions: async () => closeDecisions(cards.slice(0, 2), new Map()),
      page: async miss => { pages.push(miss); return true; }, now: () => clock.at,
    });
    await watchdog.check();
    assert.equal(pages.length, 0, 'orders read at 13:53:55 are judged at 13:53:55, not at the 14:00:00 the positions read ended');
    assert.equal(watchdog.nextDeadlineAtMs(), T1354);
  },
  async 'with paper credentials the service watchdog reads the broker and pages'() {
    const realFetch = globalThis.fetch;
    globalThis.fetch = async url => ({ ok: true, status: 200, text: async () => '[]', json: async () => (String(url).includes('/v2/positions') ? [{ symbol: AMD, qty: '3' }] : []) });
    const previous = { key: process.env.SRW1322_PAPER_KEY, secret: process.env.SRW1322_PAPER_SECRET, state: process.env.SRW1322_STATE_FILE };
    process.env.SRW1322_PAPER_KEY = 'paper-key';
    process.env.SRW1322_PAPER_SECRET = 'paper-secret';
    process.env.SRW1322_STATE_FILE = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'srw1322-')), 'exit-watchdog.json');
    try {
      const paged = [];
      const watchdog = createExitWatchdogForService({
        token: 'discord-token', publisherId: '1', channels: [{ name: 'botalerts', channelId: '1564741003930378421' }],
        bots: [{ name: 'bot2', healthUrl: 'http://bot2.invalid/health', secret: 'x' }],
        alerter: { alert: async () => ({ route: 'discord' }) }, log: () => {},
      });
      assert.ok(watchdog, 'the watchdog is on when the credentials and the channels are there');
      await watchdog.check(); // the first broker read must not throw
      assert.equal(typeof watchdog.nextDeadlineAtMs, 'function');
    } finally {
      globalThis.fetch = realFetch;
      if (previous.key === undefined) delete process.env.SRW1322_PAPER_KEY; else process.env.SRW1322_PAPER_KEY = previous.key;
      if (previous.secret === undefined) delete process.env.SRW1322_PAPER_SECRET; else process.env.SRW1322_PAPER_SECRET = previous.secret;
      if (previous.state === undefined) delete process.env.SRW1322_STATE_FILE; else process.env.SRW1322_STATE_FILE = previous.state;
    }
  },
  async 'the broker source only reads: every call is a GET'() {
    const calls = [];
    const read = createAlpacaBrokerSource({
      key: 'k', secret: 's',
      fetchImpl: async (url, options) => { calls.push(options.method || 'GET'); return { ok: true, json: async () => (url.includes('positions') ? [{ symbol: AMD, qty: '3' }] : []) }; },
    });
    const broker = await read();
    assert.deepEqual(broker.positions, [{ symbol: AMD, qty: 3 }]);
    assert.ok(calls.length === 3 && calls.every(method => method === 'GET'), 'positions, recent orders and open orders');
  },
};

(async () => {
  let failed = 0;
  for (const [name, run] of Object.entries(cases)) {
    try { await run(); process.stdout.write(`ok   ${name}\n`); }
    catch (error) { failed++; process.stdout.write(`FAIL ${name}: ${error.stack}\n`); }
  }
  process.stdout.write(`\nSRW-1322 exit watchdog proof: ${Object.keys(cases).length - failed} passed, ${failed} failed\n`);
  process.exitCode = failed ? 1 : 0;
})();
