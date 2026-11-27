import { View } from "gpui-kit";
import { v_flex, TextareaState } from "gpui-base";
import { agents, appHome, closeOverlay, exec, hc, home, layout, notify, nextCommand, openOverlay, props, readTextFile, run, setShared, shared, theme } from "herdr";
import { answerCause, boardAnswer, decisionsMessage, isStale, restored } from "./answers.js";
import { boardGlance, FLOW_FILE, parseFlow } from "./board.js";
import { chipLabel, draftText, imagePathSpans, loadOlder, materialize, pathImages, readTranscript, SESSION_NAME } from "./transcript.js";
import { askRow, clampFrom, composer, conversation, emptyPop, holdFrom, questionPop, status, taskStrip, TURN_ESTIMATE, turnKey } from "./ui.js";

async function swapChat() {
  const tree = JSON.parse(JSON.stringify(layout()));
  const split = (function find(node) {
    if (node.id === "work-split") return node;
    for (const child of node.children ?? []) {
      const hit = find(child);
      if (hit) return hit;
    }
    return null;
  })(tree);
  const from = split?.children.findIndex((c) => c.id === "coordinator");
  if (from === undefined || from < 0) return;
  const [chat] = split.children.splice(from, 1);
  split.children.splice(from === 0 ? 1 : 0, 0, chat);
  const result = await exec(`${home()}/.local/bin/herdr-app`, ["do", "layout.set", JSON.stringify({ layout: tree })]);
  if (result.code) notify({ title: "Chat not moved", body: result.stderr.trim(), level: "error" });
}

const failureMessage = (stderr) => JSON.parse(JSON.parse(stderr)[0].text).message;

async function openTask(task) {
  const r = await exec(`${home()}/.local/bin/t3mcp`, ["call", "t3_thread_read", JSON.stringify({ threadId: task.key, limit: 1, runLimit: 1 })]);
  if (r.code !== 0) return notify({ title: "Could not open the thread", body: failureMessage(r.stderr), level: "error" });
  const { link } = JSON.parse(r.stdout).thread;
  if (!link?.startsWith("https://app.t3.codes/threads/")) return notify({ title: "Could not open the thread", body: "T3 thread link not available", level: "error" });
  const opened = await exec("/usr/bin/open", [link]);
  if (opened.code !== 0) notify({ title: "Could not open the thread", body: opened.stderr.trim(), level: "error" });
}

const EVERY = 3000;
const IDLE_AFTER = 90000;
const TICK = 60000;
const TYPING_SAVE = 400;
const ELAPSED_EVERY = 5000;
const SENT_KEEP = 40;
const MIN_ROWS = 2;
const MAX_ROWS = 8;
const KEYS = [{ keystroke: "cmd-alt-v", action: "coordinator_preview", context: "CoordinatorBox" }];
let keysBound = false;
let chipCount = 0;
const PAGE = 10;
const CALM = 400;
const POP_WIDTH = 640;
const POP_HEIGHT = 560;
const DECISIONS_FILE = `${home()}/Code/coordinator/decisions.json`;

// An alarm Shyam answered stays quiet for four hours. The acknowledgement
// is a record the shift reads, not a guess about the board: the shift
// never silences an alarm nobody answered, and the board file has more
// than one writer, so a lost board item says nothing. The command writes
// the record for the cause the panel showed, so another cause of the same
// alarm, which nobody answered, is not silenced. The command is the
// installed one. An alarm that was never raised has no record: the
// command says so, and the panel says so too, because an alarm that
// cannot be acknowledged is an alarm that raises again.
async function acknowledgeAlarm(id, cause) {
  if (!cause) return;
  const r = await exec(`${home()}/.local/bin/alarms.py`, ["ack", id, cause]);
  // The command exits 0 when the acknowledgement was written. Any other
  // exit means the acknowledgement did not reach the file, and the alarm
  // can raise again on the next tick, so Shyam is told. An alarm on the
  // board always has a key, so even the "no raised key" exit is a fault
  // worth naming.
  if (r.code !== 0) {
    notify({ title: "The alarm was not acknowledged", body: `${id}: ${(r.stderr || "").trim() || `alarms exited ${r.code}`}. The alarm can raise again on the next tick.`, level: "warning" });
  }
}

const ANSWER_EXPIRY = 30000;
const sending = new Set();

const askOf = ({ id, group, title, why, cause, kind, options }) => ({
  id: String(id),
  group,
  text: String(title),
  why,
  cause: cause ? String(cause) : "",
  action: kind === "action",
  choices: kind === "action"
    ? [{ kind: "done", text: "Done", label: "Done", detail: "", rec: false }]
    : options.map((o) => ({ kind: "option", text: o.label, label: o.label, detail: o.detail, rec: Boolean(o.recommended) })),
});

const NEEDS_FRESH = 300000;

function boardNeeds(now) {
  const published = shared("cockpit.needs");
  return published && now - published.at <= NEEDS_FRESH ? published.n : null;
}

const clock = (at) => {
  const d = new Date(at);
  return `${d.getHours() % 12 || 12}:${String(d.getMinutes()).padStart(2, "0")}`;
};

export default class Coordinator extends View {
  init(_props, cx) {
    this.pop = props()?.pop ?? null;
    this.editors = new Map();
    if (!this.pop && !shared("co.sent")) setShared("co.sent", { since: Date.now(), items: [] });
    this.typingTimers = new Map();
    this.opening = null;
    this.editing = new Set(this.pop ? this.typing().keys() : []);
    // The cause each open reply is bound to: the one the panel showed
    // when the reply started, not the one it shows when the reply is
    // sent. It is kept in the shared state, so a reply the popup
    // restores keeps the cause it belongs to.
    this.replyCauses = new Map(shared("co.replyCauses") ?? []);
    this.sent = "";
    this.box = { width: 800, height: 240 };
    this.contentH = 0;
    this.fromBottom = 0;
    this.prepended = false;
    this.grew = 0;
    this.grewAbove = 0;
    this.heights = new Map();
    this.images = new Map();
    this.imageTail = Promise.resolve();
    if (this.pop) {
      this.handle = cx.focus_handle();
      this.inEditor = false;
      this.onReview = false;
      this.stepQ = null;
      this.reviewSig = "";
      this.calmUntil = 0;
      this.changed = false;
      this.firstOpen();
      const typed = this.asks().find((a) => this.editing.has(a.id));
      cx.timer.after(60, () => (typed ? this.editor(typed.id) : this.handle).focus());
      return;
    }
    this.input = TextareaState.new({ placeholder: "Message the Coordinator, or answer above", rows: MIN_ROWS });
    this.input.set_auto_grow(MIN_ROWS, MAX_ROWS);
    this.input.on("submit", (e, cx) => !e?.shift && this.send(cx));
    this.input.on("change", (_e, cx) => {
      this.chipImagePaths();
      cx.notify();
    });
    this.input.on("paste_other", (_e, cx) => this.pasteImage(cx));
    this.input.on("focus", (_e, cx) => {
      this.focused = true;
      cx.notify();
    });
    this.input.on("blur", (_e, cx) => {
      this.focused = false;
      cx.notify();
    });
    this.focused = false;
    this.preview = false;
    this.chipping = false;
    this.boxHandle = cx.focus_handle();
    this.rootHandle = cx.focus_handle();
    this.glance = new Map();
    this.flowStat = "";
    this.glanceRev = -1;
    if (!keysBound) {
      cx.bind_keys(KEYS);
      keysBound = true;
    }
    this.view = null;
    this.error = "";
    this.decisions = { items: [], error: "" };
    this.decisionsStat = "";
    this.stamp = "";
    this.open = new Set();
    this.loading = false;
    this.refreshing = false;
    this.shown = PAGE;
    this.drawn = Date.now();
    cx.timer.every(EVERY, (cx) => {
      this.takeAnswers(cx);
      if (this.watching()) this.refresh(cx);
    });
    cx.timer.every(TICK, (cx) => cx.notify());
    this.refresh(cx);
    cx.spawn(async (cx) => {
      for (;;) {
        const name = await nextCommand();
        run("layout.show", { id: "coordinator" });
        if (name === "message") cx.timer.after(60, () => this.input.focus());
        if (name === "asks") this.openAsks();
        if (name === "swap") swapChat();
        cx.notify();
      }
    });
  }

  openAsks() {
    openOverlay({ mod: "coordinator", kind: "dialog", width: POP_WIDTH, height: POP_HEIGHT, props: { pop: "asks" } });
  }

  async close() {
    for (const q of this.editing) this.keepTyping(q, this.editor(q).value());
  }

  openTask(id, task, cx) {
    if (this.opening === id) return;
    this.opening = id;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        await openTask(task);
      } finally {
        this.opening = null;
        cx.notify();
      }
    });
  }

  watching() {
    return Date.now() - this.drawn < IDLE_AFTER;
  }

  info() {
    const pi = agents().filter((a) => a.space_name === "Coordinator" && a.app === "pi");
    return pi.find((a) => a.tab_name === SESSION_NAME) ?? pi[0] ?? null;
  }

  wantImage(ref, cx) {
    const known = this.images.get(ref.key);
    if (known) return known;
    const entry = { state: "loading" };
    this.images.set(ref.key, entry);
    const before = this.imageTail;
    let release;
    this.imageTail = new Promise((resolve) => {
      release = resolve;
    });
    cx.spawn(async (cx) => {
      await before;
      try {
        const done = await materialize(ref);
        Object.assign(entry, done ? { state: "ready", ...done } : { state: "missing" });
      } catch {
        entry.state = "failed";
      }
      release();
      cx.notify();
    });
    return entry;
  }

  refresh(cx) {
    if (this.refreshing) return;
    this.refreshing = true;
    cx.spawn(async (cx) => {
      try {
        await this.readDecisions();
        this.prune();
        this.view = await readTranscript(cx);
        await this.readGlance();
        if (this.known !== undefined && this.fromBottom > 0) this.shown += Math.max(0, this.view.turns.length - this.known);
        this.known = this.view.turns.length;
        this.error = "";
      } catch (error) {
        this.error = String(error.message);
      }
      this.refreshing = false;
      const v = this.view;
      const stamp = JSON.stringify([v?.rev, v?.activity, v?.activityAt, v?.tokens, v?.model, v?.errored, this.error, this.decisionsStat, this.flowStat, this.info()?.status === "working" && v?.activity ? Math.floor(Date.now() / ELAPSED_EVERY) : 0]);
      if (stamp === this.stamp) return;
      this.stamp = stamp;
      const published = JSON.stringify(this.decisions);
      if (published !== this.published) {
        this.published = published;
        setShared("co.asks", this.decisions);
      }
      cx.notify();
    });
  }

  async readGlance() {
    const stat = await exec("stat", ["-f", "%Fm %z", FLOW_FILE]);
    const seen = stat.code === 0 ? stat.stdout.trim() : "";
    if (seen === this.flowStat && this.view.rev === this.glanceRev) return;
    this.flowStat = seen;
    this.glanceRev = this.view.rev;
    const text = seen ? await readTextFile(FLOW_FILE) : null;
    const cards = this.view.turns.filter((m) => m.status);
    const windows = cards.map((m, i) => ({
      id: turnKey(m),
      from: cards[i - 1]?.at ?? m.at,
      to: m.at,
      known: i > 0,
    }));
    this.glance = text === null ? new Map() : boardGlance(parseFlow(text), windows);
  }

  async readDecisions() {
    const stat = await exec("stat", ["-f", "%Fm %z %i", DECISIONS_FILE]);
    const seen = stat.code === 0 ? stat.stdout.trim() : "";
    if (seen === this.decisionsStat) return;
    this.decisionsStat = seen;
    const at = seen ? Number.parseFloat(seen) * 1000 : 0;
    if (!seen) {
      this.decisions = { items: [], error: "", at };
      return;
    }
    const file = await exec("cat", [DECISIONS_FILE]);
    if (file.code !== 0) {
      this.decisionsStat = "";
      this.decisions = { items: [], error: `decisions.json: ${file.stderr.trim()}`, at };
      return;
    }
    try {
      this.decisions = { items: JSON.parse(file.stdout).items.map(askOf), error: "", at };
      await exec(`${home()}/.local/bin/coordq`, ["decision", "sync"]);
    } catch (error) {
      this.decisions = { items: [], error: `decisions.json: ${error.message}`, at };
    }
  }

  prune() {
    if (this.decisions.error) return;
    const live = new Set(this.decisions.items.map((a) => a.id));
    const decided = this.decided();
    const gone = Object.keys(decided).filter((id) => !live.has(id));
    if (gone.length) {
      for (const id of gone) delete decided[id];
      setShared("co.decided", decided);
    }
    const drafts = this.drafts();
    for (const q of drafts.keys()) if (!live.has(q)) drafts.delete(q);
    if (drafts.size !== this.drafts().size) this.setDrafts(drafts);
    const typing = this.typing();
    for (const q of typing.keys()) if (!live.has(q)) typing.delete(q);
    if (typing.size !== this.typing().size) this.setTyping(typing);
    for (const q of this.editors.keys()) if (!live.has(q)) this.editors.delete(q);
    for (const q of this.editing) if (!live.has(q)) this.editing.delete(q);
  }

  drafts() {
    return new Map(shared("co.drafts") ?? []);
  }

  setDrafts(drafts) {
    setShared("co.drafts", [...drafts]);
  }

  typing() {
    return new Map(shared("co.typing") ?? []);
  }

  setTyping(typing) {
    setShared("co.typing", [...typing]);
  }

  setReplyCauses(causes) {
    setShared("co.replyCauses", [...causes]);
  }

  keepTyping(q, text) {
    this.typingTimers.get(q)?.cancel();
    const typing = this.typing();
    if ((typing.get(q) ?? "") === text) return;
    if (text) typing.set(q, text);
    else typing.delete(q);
    this.setTyping(typing);
  }

  decided() {
    return { ...shared("co.decided") };
  }

  decisionsError() {
    return (this.pop ? shared("co.asks") : this.decisions)?.error ?? "";
  }

  decisionsAt() {
    return (this.pop ? shared("co.asks") : this.decisions)?.at ?? 0;
  }

  asks() {
    const items = (this.pop ? shared("co.asks") : this.decisions)?.items ?? [];
    const decided = this.decided();
    return [...items.filter((a) => !decided[a.id]), ...items.filter((a) => decided[a.id])];
  }

  answers(drafts) {
    return this.asks().flatMap((a, n) => {
      if (!drafts.has(a.id)) return [];
      const draft = drafts.get(a.id);
      // The answer carries the cause it was bound to when it was made,
      // not the cause the board shows now: an alarm that was replaced in
      // between is not acknowledged in the answer's place.
      // The cause is the one the answer was bound to when it was made,
      // and never the one the board shows now: an answer that was not
      // bound carries no cause, so it acknowledges nothing.
      return [{ n: n + 1, id: a.id, q: a.text, shown: a.cause ?? "", cause: answerCause(draft, a.cause), kind: draft.kind, text: draft.text }];
    });
  }

  // An answer belongs to the alarm it was given for. When the alarm is
  // replaced between the answer and the send, the answer is dropped and
  // Shyam is told: sending it would answer the alarm that is there now,
  // and he never answered that one. An answer that was never bound to a
  // cause is dropped too, for the same reason: it cannot be shown to
  // belong to the alarm that is there now.
  dropStaleDrafts() {
    const drafts = this.drafts();
    const stale = [];
    for (const [id, draft] of drafts) {
      const shown = this.asks().find((a) => a.id === id)?.cause ?? "";
      if (isStale(draft, shown)) stale.push(id);
    }
    if (!stale.length) return;
    for (const id of stale) drafts.delete(id);
    this.setDrafts(drafts);
    notify({ title: "The answer was dropped", body: `${stale.length} answer(s) went to an alarm that changed. Choose the answer again.`, level: "warning" });
  }

  editor(q) {
    if (!this.editors.has(q)) {
      const state = TextareaState.new({ placeholder: "Your reply", rows: 1 });
      state.set_auto_grow(1, 4);
      state.on("submit", (e, cx) => !e?.shift && this.commit(q, cx));
      state.on("focus", () => (this.inEditor = true));
      state.on("blur", () => (this.inEditor = false));
      state.on("change", (_e, cx) => {
        this.typingTimers.get(q)?.cancel();
        this.typingTimers.set(q, cx.timer.after(TYPING_SAVE, () => this.keepTyping(q, state.value())));
        cx.notify();
      });
      const typed = this.typing().get(q);
      if (typed) state.set_value(typed);
      this.editors.set(q, state);
    }
    return this.editors.get(q);
  }

  sigOf(list) {
    return list.map((a) => a.id).join("\n");
  }

  indexOf(list) {
    return this.onReview ? list.length : list.findIndex((a) => a.id === this.stepQ);
  }

  toReview(list) {
    this.onReview = true;
    this.stepQ = null;
    this.changed = false;
    this.reviewSig = this.sigOf(list);
    this.calmUntil = Date.now() + CALM;
  }

  firstOpen() {
    const list = this.asks();
    const drafts = this.drafts();
    const decided = this.decided();
    const target = list.find((a) => this.editing.has(a.id)) ?? list.find((a) => !drafts.has(a.id) && !decided[a.id]);
    if (target) this.stepQ = target.id;
    else this.toReview(list);
  }

  sync(list) {
    if (this.onReview) {
      if (this.reviewSig === this.sigOf(list)) return;
      this.reviewSig = this.sigOf(list);
      this.changed = true;
      this.calmUntil = Date.now() + CALM;
    } else if (!list.some((a) => a.id === this.stepQ)) {
      const drafts = this.drafts();
      const decided = this.decided();
      this.stepQ = (list.find((a) => !drafts.has(a.id) && !decided[a.id]) ?? list[0])?.id ?? null;
      this.calmUntil = Date.now() + CALM;
    }
  }

  stepTo(step, cx, exact = false) {
    const list = this.asks();
    const from = this.indexOf(list);
    const decided = this.decided();
    const dir = step >= from ? 1 : -1;
    let to = step;
    if (!exact) while (to >= 0 && to < list.length && decided[list[to].id]) to += dir;
    if (to < 0) to = from;
    if (to >= list.length) this.toReview(list);
    else {
      this.onReview = false;
      this.stepQ = list[Math.max(0, to)].id;
    }
    this.inEditor = false;
    this.handle.focus();
    cx.notify();
  }

  // The cause of the ask as it is shown now. The answer is bound to it,
  // and the cause is half of the alarm's key, so an alarm that is
  // replaced between the answer and the send is not acknowledged in the
  // answer's place.
  causeOf(q) {
    return this.asks().find((a) => a.id === q)?.cause ?? "";
  }

  pick(q, choice, cx) {
    const list = this.asks();
    const at = list.findIndex((a) => a.id === q);
    if (at < 0) return;
    const drafts = this.drafts();
    const cause = this.causeOf(q);
    // The same choice for a cause that is not the one the draft was
    // bound to is a new answer, for the cause that is shown now.
    const same = drafts.get(q)?.kind === choice.kind
      && drafts.get(q).text === choice.text
      && (drafts.get(q)?.cause ?? "") === cause;
    if (same) drafts.delete(q);
    else drafts.set(q, { kind: choice.kind, text: choice.text, cause });
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    this.stepTo(same ? at : at + 1, cx, same);
  }

  take(a, cx) {
    const at = this.asks().findIndex((x) => x.id === a.id);
    if (this.drafts().has(a.id)) return this.stepTo(at + 1, cx);
    const choice = a.choices.find((c) => c.rec);
    if (choice) this.pick(a.id, choice, cx);
  }

  sendReview(cx) {
    const list = this.asks();
    this.sync(list);
    if (!this.onReview || Date.now() < this.calmUntil) return;
    this.send(cx);
  }

  askKey(e, cx) {
    const m = e.modifiers;
    if (e.is_held || this.inEditor || m.platform || m.control || m.alt) return;
    const list = this.asks();
    this.sync(list);
    if (Date.now() < this.calmUntil) return;
    const review = this.onReview;
    const at = this.indexOf(list);
    const a = list[at];
    if (!review && !a) return;
    const k = e.key;
    const n = /^[1-9]$/.test(k) ? Number(k) - 1 : -1;
    if (k === "enter") {
      if (review) return;
      this.take(a, cx);
    } else if (k === "s" && review) this.sendReview(cx);
    else if (k === "k" || k === "left" || k === "up") this.stepTo(at - 1, cx);
    else if (!review && (k === "j" || k === "right" || k === "down")) this.stepTo(at + 1, cx);
    else if (k === "a") this.accept(cx);
    else if (k === "r" && !review) this.reply(a.id, cx);
    else if (review && n >= 0 && n < list.length) this.stepTo(n, cx, true);
    else if (!review && n >= 0 && n < a.choices.length) this.pick(a.id, a.choices[n], cx);
    else return;
    cx.stop_propagation();
  }

  reply(q, cx) {
    const state = this.editor(q);
    const draft = this.drafts().get(q);
    const shown = this.causeOf(q);
    const typed = this.typing().get(q);
    const saved = this.replyCauses.get(q);
    // The reply is bound to the cause it was started for. Text that was
    // saved for another cause keeps that cause, so the answer is dropped
    // instead of being sent for the alarm that is there now. Text saved
    // without a cause is not restored at all: it cannot be bound to the
    // alarm on the board now.
    const { text, bound } = restored(draft, typed, saved, shown);
    if (typed !== undefined && !text) {
      const typing = this.typing();
      typing.delete(q);
      this.setTyping(typing);
    }
    this.replyCauses.set(q, bound);
    this.setReplyCauses(this.replyCauses);
    state.set_value(text);
    this.editing.add(q);
    cx.notify();
    cx.timer.after(60, () => state.focus());
  }

  commit(q, cx) {
    const text = this.editor(q).value().trim();
    const drafts = this.drafts();
    const bound = this.replyCauses.get(q);
    if (text && bound === undefined) {
      // A restored reply whose cause is not known: the alarm it belongs
      // to may not be the one on the board now, so it is dropped rather
      // than sent for an alarm nobody answered.
      notify({ title: "The reply was dropped", body: "The reply was restored without the alarm it belongs to. Write it again.", level: "warning" });
      const typing = this.typing();
      typing.delete(q);
      this.setTyping(typing);
      drafts.delete(q);
    } else if (text) {
      drafts.set(q, { kind: "reply", text, cause: bound });
    }
    else if (drafts.get(q)?.kind === "reply") drafts.delete(q);
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    const at = this.asks().findIndex((a) => a.id === q);
    this.stepTo(text ? at + 1 : at, cx, !text);
  }

  accept(cx) {
    const drafts = this.drafts();
    const decided = this.decided();
    for (const a of this.asks()) {
      const rec = a.choices.find((c) => c.rec);
      if (!rec || drafts.has(a.id) || decided[a.id]) continue;
      // The answer is bound to the cause that is shown now, like every
      // other answer.
      drafts.set(a.id, { kind: rec.kind, text: rec.text, cause: a.cause ?? "" });
    }
    this.setDrafts(drafts);
    this.stepTo(this.asks().length, cx);
  }

  clear(q, cx) {
    const drafts = this.drafts();
    drafts.delete(q);
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    cx.notify();
  }

  chipImagePaths() {
    if (this.chipping) return;
    const { text, tokens } = this.input.content();
    const loose = imagePathSpans(text).filter((s) => !tokens.some((t) => t.range.start < s.end && t.range.end > s.start));
    if (!loose.length) return;
    this.chipping = true;
    for (const s of loose.reverse()) {
      this.input.replace_range_with_token({ start: s.start, end: s.end }, { id: `img-${Date.now().toString(36)}-${chipCount++}`, text: s.path, label: chipLabel(s.path) });
    }
    this.chipping = false;
  }

  pasteImage(cx) {
    cx.spawn(async (cx) => {
      const dir = `${appHome()}/data/coordinator/paste`;
      const at = Date.now();
      const file = `${dir}/${at}.png`;
      await exec("mkdir", ["-p", dir]);
      const saved = await exec("osascript", [
        "-e", "set png to the clipboard as \u00abclass PNGf\u00bb",
        "-e", `set f to open for access POSIX file "${file}" with write permission`,
        "-e", "set eof f to 0",
        "-e", "write png to f",
        "-e", "close access f",
      ]);
      if (saved.code !== 0) return;
      const time = new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
      this.input.replace_with_token({ id: `img-${at.toString(36)}-${chipCount++}`, text: file, label: `📷 Pasted image ${time}` });
      cx.notify();
    });
  }

  togglePreview(cx) {
    this.preview = !this.preview;
    this.focused = false;
    cx.timer.after(60, () => (this.preview ? this.boxHandle : this.input).focus());
    cx.notify();
  }

  message() {
    const answered = this.answers(this.drafts());
    return [answered.length ? decisionsMessage(answered) : "", this.pop ? "" : draftText(this.input.content()).trim()].filter(Boolean).join("\n\n");
  }

  logSent(text) {
    const kept = shared("co.sent") ?? { since: Date.now(), items: [] };
    const items = [...kept.items, { at: Date.now(), text }];
    const trimmed = items.length > SENT_KEEP;
    const keep = items.slice(-SENT_KEEP);
    setShared("co.sent", { since: trimmed ? keep[0].at : kept.since, items: keep });
  }

  async recordAnswers(answered) {
    const decided = this.decided();
    const drafts = this.drafts();
    const typing = this.typing();
    for (const a of answered) {
      decided[a.id] = { text: a.text, at: Date.now() };
      drafts.delete(a.id);
      typing.delete(a.id);
      this.editing.delete(a.id);
      this.editors.get(a.id)?.set_value("");
    }
    setShared("co.decided", decided);
    this.setDrafts(drafts);
    this.setTyping(typing);
    await exec(`${home()}/.local/bin/coordq`, ["decision", "answered", ...answered.map((x) => x.id)]);
    // The answer is the acknowledgement: the alarm stays quiet for
    // four hours. The shift reads the record, so the alarm comes
    // back on its own when the four hours are over.
    for (const a of answered) await acknowledgeAlarm(a.id, a.cause);
  }

  takeAnswers(cx) {
    for (const [id, request] of Object.entries(shared("co.answer") ?? {})) {
      if (request.sending) continue;
      const claimed = { ...request, sending: true, took: Date.now() };
      setShared("co.answer", { ...shared("co.answer"), [id]: claimed });
      cx.spawn(async (cx) => {
        let result = { label: request.label, ok: false, reason: "Not confirmed. Check the Coordinator chat before answering again." };
        try {
          result = { label: request.label, ...(await this.sendBoardAnswer(id, request)) };
        } finally {
          if (shared("co.answer")?.[id]?.took === claimed.took) {
            const pending = { ...shared("co.answer") };
            delete pending[id];
            setShared("co.answer", pending);
          }
          setShared("co.answered", { ...shared("co.answered"), [id]: result });
          cx.notify();
        }
      });
    }
  }

  async sendBoardAnswer(id, request) {
    if (Date.now() - request.at > ANSWER_EXPIRY) return { ok: false, reason: "Expired before it was sent." };
    if (sending.has(id)) return { ok: false, reason: "Already sending." };
    sending.add(id);
    try {
      const file = await exec("cat", [DECISIONS_FILE]);
      if (file.code !== 0) return { ok: false, reason: `decisions.json: ${file.stderr.trim()}` };
      let items;
      try {
        items = JSON.parse(file.stdout).items.map(askOf);
      } catch (error) {
        return { ok: false, reason: `decisions.json: ${error.message}` };
      }
      const resolved = boardAnswer(id, request, items, this.decided());
      if (resolved.dropped) return { ok: false, reason: resolved.dropped };
      const info = this.info();
      if (!info) return { ok: false, reason: "The Coordinator is not running." };
      const text = decisionsMessage([resolved.answer]);
      this.logSent(text);
      const r = await hc(["send", info.address, text]);
      if (r.code !== 0) return { ok: false, reason: r.stderr.trim() || `hc send exited ${r.code}` };
      await this.recordAnswers([resolved.answer]);
      return { ok: true };
    } finally {
      sending.delete(id);
    }
  }

  send(cx) {
    this.dropStaleDrafts();
    const text = this.message();
    const answered = this.answers(this.drafts());
    const typed = this.pop ? "" : draftText(this.input.content()).trim();
    const info = this.info();
    if (!text || !info || this.sent === "sending") return;
    if (answered.some((a) => sending.has(a.id))) return notify({ title: "Already sending", body: "An answer for one of these decisions is on its way.", level: "warning" });
    for (const a of answered) sending.add(a.id);
    this.sent = "sending";
    this.fromBottom = 0;
    this.logSent(text);
    const overlay = props()?.overlay;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const r = await hc(["send", info.address, text]);
        if (r.code !== 0) throw new Error(r.stderr.trim() || `hc send exited ${r.code}`);
        if (!this.pop && draftText(this.input.content()).trim() === typed) this.input.set_value("");
        await this.recordAnswers(answered);
        this.sent = "sent";
        if (this.pop) closeOverlay(overlay);
      } catch (error) {
        this.sent = "";
        notify({ title: "Send failed", body: error.message, level: "error" });
      } finally {
        for (const a of answered) sending.delete(a.id);
      }
      cx.notify();
      cx.timer.after(2500, (cx) => {
        this.sent = "";
        cx.notify();
      });
      if (!this.pop) this.refresh(cx);
    });
  }

  latestCard() {
    return this.view?.turns.filter((m) => m.status).at(-1) ?? null;
  }

  replyTo(need, cx) {
    const typed = draftText(this.input.content()).trim();
    const line = `Re ${need.id} (${need.text}): `;
    this.input.set_value(typed ? `${typed}\n${line}` : line);
    cx.timer.after(60, () => this.input.focus());
    cx.notify();
  }

  glanceKey(e, cx) {
    const m = e.modifiers;
    if (e.is_held || this.focused || !this.rootHandle.is_focused() || this.preview || m.platform || m.control || m.alt || m.shift) return;
    const card = this.latestCard();
    if (!card) return;
    const n = /^[1-3]$/.test(e.key) ? Number(e.key) - 1 : -1;
    if (e.key === "f") {
      if (!card.status.foldable) return;
      this.toggle(`fold-${turnKey(card)}`, cx);
    } else if (n >= 0 && card.status.needs[n]) this.replyTo(card.status.needs[n], cx);
    else return;
    cx.stop_propagation();
  }

  toggle(key, cx) {
    this.open.has(key) ? this.open.delete(key) : this.open.add(key);
    cx.notify();
  }

  older(cx) {
    if (this.loading) return;
    this.loading = true;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        this.view = await loadOlder(cx, PAGE);
        await this.readGlance();
        this.known = this.view.turns.length;
        this.shown += PAGE;
        this.prepended = true;
      } catch (error) {
        this.error = String(error.message);
      } finally {
        this.loading = false;
        cx.notify();
      }
    });
  }

  render(cx) {
    const t = theme();
    const now = Date.now();
    this.drawn = now;
    const info = this.info();
    this.fromBottom = holdFrom(this.fromBottom, this.contentH - (this.grew - this.grewAbove), this.contentH, this.box.height, this.prepended);
    if (this.grew !== 0) this.prepended = false;
    this.grew = 0;
    this.grewAbove = 0;
    const drafts = this.drafts();
    const answers = this.answers(drafts);
    const newest = this.latestCard();
    const cb = {
      tasks: shared("hub")?.tasks ?? {},
      width: this.box.width,
      pendingId: this.view?.pendingId ?? "",
      isOpen: (key) => this.open.has(key),
      toggle: (key, cx) => this.toggle(key, cx),
      shown: this.shown,
      loading: this.loading,
      more: (cx) => {
        this.shown += PAGE;
        this.prepended = true;
        cx.notify();
      },
      older: (cx) => this.older(cx),
      pick: (q, choice, cx) => this.pick(q, choice, cx),
      go: (i, cx) => this.stepTo(i, cx, true),
      back: (cx) => this.stepTo(this.indexOf(this.asks()) - 1, cx),
      skip: (cx) => this.stepTo(this.indexOf(this.asks()) + 1, cx),
      reply: (q, cx) => this.reply(q, cx),
      commit: (q, cx) => this.commit(q, cx),
      clear: (q, cx) => this.clear(q, cx),
      accept: (cx) => this.accept(cx),
      send: (cx) => (this.pop ? this.sendReview(cx) : this.send(cx)),
      openAsks: () => this.openAsks(),
      close: () => closeOverlay(props()?.overlay),
      opening: this.opening,
      open: (id, task, cx) => this.openTask(id, task, cx),
      sender: (from) => agents().find((a) => a.address === from)?.tab_name ?? from,
      link: (url) => (/^https?:\/\//i.test(url) ? exec("open", [url]) : notify({ title: "Link not opened", body: "Only web links open from the chat.", level: "info", timeout: 2500 })),
      heights: this.heights,
      glance: this.glance,
      clock,
      newestKey: newest ? turnKey(newest) : "",
      boardNeeds: boardNeeds(now),
      quiet: (m) => {
        const g = this.glance.get(turnKey(m));
        return m.status?.lone && !m.status.question && g?.known && g.done === 0 && g.unreviewed === 0;
      },
      replyTo: (need, cx) => this.replyTo(need, cx),
      focusLog: () => this.rootHandle.focus(),
      image: (ref) => this.wantImage(ref, cx),
      draft: () => draftText(this.input.content()),
      preview: this.preview,
      boxHandle: this.boxHandle,
      minRows: MIN_ROWS,
      maxRows: MAX_ROWS,
      togglePreview: (cx) => this.togglePreview(cx),
      attachments: (text) => pathImages(text).images,
      openImage: (path) => exec("open", [path]),
      working: info?.status === "working" && !this.view?.errored,
      turnSize: (key, height, cx, above) => {
        const known = this.heights.get(key);
        if (known !== undefined && Math.abs(known - height) < 1) return;
        if (above) this.grewAbove += height - (known ?? TURN_ESTIMATE);
        this.heights.set(key, height);
        cx.notify();
      },
      fromBottom: this.fromBottom,
      contentH: this.contentH,
      viewH: this.box.height,
      wheel: (dy, cx) => {
        this.fromBottom = clampFrom(this.fromBottom + dy, this.contentH, this.box.height);
        cx.notify();
      },
      measure: (size, cx) => {
        if (size.height === this.contentH) return;
        this.grew += size.height - this.contentH;
        this.contentH = size.height;
        cx.notify();
      },
      latest: (cx) => {
        this.fromBottom = 0;
        cx.notify();
      },
      size: (size, cx) => {
        if (size.width === this.box.width && size.height === this.box.height) return;
        if (size.width !== this.box.width) this.heights.clear();
        this.box = size;
        cx.notify();
      },
    };
    const list = this.asks();
    const decided = this.decided();
    if (this.pop) {
      this.sync(list);
      const form = { answers, drafts, decided, clock, editing: this.editing, editor: (q) => this.editor(q), sending: this.sent === "sending", step: Math.max(0, this.indexOf(list)), changed: this.changed };
      return v_flex().id("co-pop").size_full().bg(t.chrome).track_focus(this.handle)
        .on_key_down((e, cx) => this.askKey(e, cx))
        .child(list.length ? questionPop(t, list, form, cb, this.decisionsAt(), now) : emptyPop(t, this.decisionsError(), cb, this.decisionsAt(), now));
    }
    const strip = taskStrip(t, this.view, cb, this.box.width);
    const open = list.filter((a) => !decided[a.id]);
    const error = this.decisionsError();
    return v_flex().id("co-root").size_full().min_h(0).bg(t.chrome).track_focus(this.rootHandle).on_key_down((e, cx) => this.glanceKey(e, cx))
      .child(status(t, info, this.view, now, this.box.width, this.error))
      .when(strip, (el) => el.child(strip))
      .when(open.length || error, (el) => el.child(askRow(t, open, open.filter((a) => drafts.has(a.id)).length, error, cb, this.decisionsAt(), now)))
      .child(conversation(t, this.view, this.error, now, cb))
      .child(composer(t, info, this.input, this.sent, this.focused, answers, cb));
  }
}
