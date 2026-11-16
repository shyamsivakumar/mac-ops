// Phone alerts: a card newly in Needs you, or newly Ready, goes to the pi-coord-phone relay as one batched message.
// The alerted map and the sender lease live in shared state, so only one board copy in any space sends.

import { hc, notify, setShared, shared } from "herdr";
import { NEED_CHIP } from "./ui.js";

export const CHECK_EVERY = 180000;
const KEY = "cockpit.alerts";
const SEEN_KEY = "alert-seen";
const ON_KEY = "alerts-on";
const LEASE_FOR = 600000;
const RENEW_AFTER = 60000;
const MIN_GAP = 300000;
const MAX_ITEMS = 8;
const MAX_PENDING = 20;
const MAX_ABSENT = 2;
const RELAY = "pi-coord-phone";
const EMPTY = { on: true, owner: null, at: 0, seen: null, pending: [], dropped: 0, absent: {}, sentAt: 0, sent: null, failed: "" };

let primed = false;

export const alertState = () => ({ ...EMPTY, ...(shared(KEY) ?? {}) });
const write = (patch) => setShared(KEY, { ...alertState(), ...patch });

export function hydrateAlerts() {
  if (shared(KEY)) return;
  write({ on: localStorage.getItem(ON_KEY) !== "0", seen: JSON.parse(localStorage.getItem(SEEN_KEY) ?? "null") });
}

export function setAlertsOn(on) {
  localStorage.setItem(ON_KEY, on ? "1" : "0");
  write({ on, seen: on ? null : alertState().seen, pending: [], dropped: 0, failed: "" });
}

export const leaseOpen = (copy, now) => {
  const s = alertState();
  return !s.owner || s.owner === copy || now - s.at >= LEASE_FOR;
};

function claim(copy, now) {
  const s = alertState();
  if (!leaseOpen(copy, now)) return false;
  if (s.owner !== copy || now - s.at >= RENEW_AFTER) write({ owner: copy, at: now });
  return true;
}

export function holds(lane, reasons) {
  if (lane === "needs") return reasons.map((reason) => ({ token: `needs:${reason}`, lane, word: NEED_CHIP[reason][0] }));
  return lane === "ready" ? [{ token: "ready", lane, word: "" }] : [];
}

const itemOf = (row, news) => ({
  key: row.key,
  lane: news[0].lane,
  tokens: news.map((n) => n.token),
  text: [row.label, news[0].lane === "needs" ? news.map((n) => n.word).join(" + ") : "", row.pr ? `(#${row.pr})` : ""].filter(Boolean).join(" "),
});

const LANE_NAME = { needs: "Needs you", ready: "Ready" };

export function messageOf(items, dropped = 0) {
  const shown = items.slice(0, MAX_ITEMS);
  const parts = Object.keys(LANE_NAME).flatMap((lane) => {
    const texts = shown.filter((i) => i.lane === lane).map((i) => i.text);
    return texts.length ? [`${LANE_NAME[lane]}: ${texts.join("; ")}`] : [];
  });
  const more = items.length - shown.length + dropped;
  return `Mirror: Board: ${parts.join(" | ")}${more > 0 ? ` | +${more} more` : ""}`;
}

async function relayAddress() {
  const ls = await hc(["ls"]);
  if (ls.code !== 0) throw new Error(ls.stderr.trim() || `hc ls exited ${ls.code}`);
  const relay = JSON.parse(ls.stdout).terminals.find((t) => t.name === RELAY);
  if (!relay) throw new Error(`relay ${RELAY} not found`);
  if (relay.status === "blocked") throw new Error(`relay ${RELAY} is blocked by an open dialog`);
  return relay.address;
}

async function deliver(text) {
  const sent = await hc(["send", await relayAddress(), text]);
  if (sent.code !== 0) throw new Error(sent.stderr.trim() || `hc send exited ${sent.code}`);
  return sent.stdout.trim();
}

const sameItem = (a, b) => a.key === b.key && a.tokens[0] === b.tokens[0];
const unique = (items) => items.filter((item, i) => items.findIndex((x) => sameItem(x, item)) === i);

function capped(items, dropped) {
  const over = Math.max(0, items.length - MAX_PENDING);
  return { pending: items.slice(over), dropped: dropped + over };
}

async function send(items, dropped, text, at) {
  try {
    const out = await deliver(text);
    write({ sent: { at, text, out }, failed: "" });
  } catch (error) {
    const s = alertState();
    const failed = String(error.message);
    write({ failed, ...capped(unique([...items, ...s.pending]), dropped + s.dropped) });
    if (failed !== s.failed) notify({ title: "Board alert (phone relay down)", body: text.replace(/^Mirror: /, ""), level: "warning" });
  }
}

export function checkAlerts(rows, copy, now) {
  if (!alertState().on || !claim(copy, now)) return;
  const s = alertState();
  const seeding = !primed || !s.seen;
  const prev = s.seen ?? {};
  const seen = {};
  const fresh = [];
  for (const row of rows) {
    const before = prev[row.key] ?? [];
    const tokens = row.unsettled ? before : row.held.map((h) => h.token);
    if (tokens.length) seen[row.key] = tokens;
    if (seeding || row.asleep || row.unsettled) continue;
    const news = row.held.filter((h) => !before.includes(h.token));
    if (news.length) fresh.push(itemOf(row, news));
  }
  const absent = {};
  for (const key of Object.keys(prev)) {
    if (rows.some((row) => row.key === key)) continue;
    const count = (s.absent[key] ?? 0) + 1;
    if (count > MAX_ABSENT) continue;
    seen[key] = prev[key];
    absent[key] = count;
  }
  primed = true;
  const queued = unique([...s.pending, ...fresh]).filter((item) => seen[item.key]?.includes(item.tokens[0]));
  const due = queued.length > 0 && now - s.sentAt >= MIN_GAP;
  const backlog = capped(queued, s.dropped);
  const text = due ? messageOf(backlog.pending, backlog.dropped) : "";
  if (due || JSON.stringify([seen, absent, backlog]) !== JSON.stringify([s.seen, s.absent, { pending: s.pending, dropped: s.dropped }])) {
    write({ seen, absent, ...(due ? { pending: [], dropped: 0, sentAt: now } : backlog) });
    localStorage.setItem(SEEN_KEY, JSON.stringify(seen));
  }
  if (due) send(backlog.pending, backlog.dropped, text, now);
}
