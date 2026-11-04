import { View } from "gpui-kit";
import { v_flex, TextareaState } from "gpui-base";
import { agents, closeOverlay, exec, hc, home, notify, nextCommand, openOverlay, props, run, setShared, shared, terminals, theme } from "herdr";
import { loadOlder, readTranscript } from "./transcript.js";
import { ASKS_HEAD, askRow, asks, asksHeight, clampFrom, composer, conversation, holdFrom, popupBar, status, taskStrip } from "./ui.js";

const SHOW_POLL = 50;
const SHOW_LIMIT = 8000;
const LIVE_STATUSES = new Set(["running", "waiting"]);

async function reusableShow(name, task) {
  const kinds = LIVE_STATUSES.has(task.status) ? ["empryo", "follow"] : ["empryo"];
  const lists = await Promise.all(kinds.map((kind) => exec(`${home()}/.local/bin/hc`, ["ls", "--json", "--label", `emp.show=${kind}`])));
  for (const r of lists) {
    const found = r.code === 0 ? JSON.parse(r.stdout).terminals.find((t) => t.name === name && t.state === "live") : null;
    if (found) return found.address;
  }
  return null;
}

async function openTask(task, cx) {
  const name = `show-${task.key.slice(4, 12)}`;
  const reuse = await reusableShow(name, task);
  if (reuse) return run("terminal.peek", { terminal: reuse });
  const before = terminals().find((t) => t.name === name)?.address;
  let finished = false;
  const shown = exec(`${home()}/.local/bin/emp`, ["show", task.key]).finally(() => (finished = true));
  const until = Date.now() + SHOW_LIMIT;
  while (!finished) {
    const fresh = terminals().find((t) => t.name === name && t.state === "live" && t.address !== before);
    if (fresh) return run("terminal.peek", { terminal: fresh.address });
    if (Date.now() > until) return notify({ title: "Could not open the thread", body: "The terminal did not appear in time.", level: "error" });
    await cx.sleep(SHOW_POLL);
  }
  const r = await shown;
  if (r.code !== 0) notify({ title: "Could not open the thread", body: r.stderr.trim(), level: "error" });
}

const EVERY = 3000;
const IDLE_AFTER = 90000;
const TICK = 60000;
const TYPING_SAVE = 400;
const ELAPSED_EVERY = 5000;
const SENT_KEEP = 40;
const MIN_ROWS = 2;
const MAX_ROWS = 8;
const QUESTION_CLIP = 70;
const PAGE = 10;
const POP_WIDTH = 760;
const POP_HEIGHT = 560;
const POP_LIST = POP_HEIGHT - 120;

export default class Coordinator extends View {
  init(_props, cx) {
    this.pop = props()?.pop ?? null;
    this.editors = new Map();
    if (!this.pop && !shared("co.sent")) setShared("co.sent", { since: Date.now(), items: [] });
    this.typingTimers = new Map();
    this.opening = null;
    this.editing = new Set(this.pop ? this.typing().keys() : []);
    this.sent = "";
    this.box = { width: 800, height: 240 };
    this.contentH = 0;
    this.fromBottom = 0;
    this.prepended = false;
    this.heights = new Map();
    if (this.pop) return;
    this.input = TextareaState.new({ placeholder: "Message the Coordinator, or answer above", rows: MIN_ROWS });
    this.input.set_auto_grow(MIN_ROWS, MAX_ROWS);
    this.input.on("submit", (e, cx) => !e?.shift && this.send(cx));
    this.input.on("change", (_e, cx) => cx.notify());
    this.input.on("focus", (_e, cx) => {
      this.focused = true;
      cx.notify();
    });
    this.input.on("blur", (_e, cx) => {
      this.focused = false;
      cx.notify();
    });
    this.focused = false;
    this.view = null;
    this.error = "";
    this.stamp = "";
    this.open = new Set();
    this.loading = false;
    this.refreshing = false;
    this.shown = PAGE;
    this.drawn = Date.now();
    cx.timer.every(EVERY, (cx) => this.watching() && this.refresh(cx));
    cx.timer.every(TICK, (cx) => cx.notify());
    this.refresh(cx);
    cx.spawn(async (cx) => {
      for (;;) {
        const name = await nextCommand();
        run("layout.show", { id: "coordinator" });
        if (name === "message") cx.timer.after(60, () => this.input.focus());
        if (name === "asks") this.openAsks();
        cx.notify();
      }
    });
  }

  openAsks() {
    const list = this.asks();
    if (!list.length) return;
    const height = Math.min(POP_HEIGHT, ASKS_HEAD + Math.min(asksHeight(list), POP_LIST));
    openOverlay({ mod: "coordinator", kind: "dialog", width: POP_WIDTH, height, props: { pop: "asks" } });
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
        await openTask(task, cx);
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
    return agents().find((a) => a.space_name === "Coordinator") ?? null;
  }

  refresh(cx) {
    if (this.refreshing) return;
    this.refreshing = true;
    cx.spawn(async (cx) => {
      try {
        this.view = await readTranscript(cx);
        if (this.known !== undefined) this.shown += Math.max(0, this.view.turns.length - this.known);
        this.known = this.view.turns.length;
        this.error = "";
        this.prune();
      } catch (error) {
        this.error = String(error.message);
      }
      this.refreshing = false;
      const v = this.view;
      const stamp = JSON.stringify([v?.rev, v?.activity, v?.activityAt, v?.tokens, this.error, this.info()?.status === "working" && v?.activity ? Math.floor(Date.now() / ELAPSED_EVERY) : 0]);
      if (stamp === this.stamp) return;
      this.stamp = stamp;
      const published = JSON.stringify(v?.asks ?? []);
      if (published !== this.published) {
        this.published = published;
        setShared("co.asks", v?.asks ?? []);
      }
      cx.notify();
    });
  }

  prune() {
    const live = new Set(this.view.asks.map((a) => a.text));
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

  keepTyping(q, text) {
    this.typingTimers.get(q)?.cancel();
    const typing = this.typing();
    if ((typing.get(q) ?? "") === text) return;
    if (text) typing.set(q, text);
    else typing.delete(q);
    this.setTyping(typing);
  }

  asks() {
    return this.pop ? shared("co.asks") ?? [] : this.view?.asks ?? [];
  }

  answers(drafts) {
    return this.asks().flatMap(({ text: q }, n) => (drafts.has(q) ? [{ n: n + 1, q, ...drafts.get(q) }] : []));
  }

  editor(q) {
    if (!this.editors.has(q)) {
      const state = TextareaState.new({ placeholder: "Your reply", rows: 1 });
      state.set_auto_grow(1, 4);
      state.on("submit", (e, cx) => !e?.shift && this.commit(q, cx));
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

  choose(q, kind, text, cx) {
    const drafts = this.drafts();
    const current = drafts.get(q);
    if (current?.kind === kind && current.text === text) drafts.delete(q);
    else drafts.set(q, { kind, text });
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    cx.notify();
  }

  reply(q, cx) {
    const state = this.editor(q);
    const draft = this.drafts().get(q);
    state.set_value(this.typing().get(q) ?? (draft?.kind === "reply" ? draft.text : ""));
    this.editing.add(q);
    cx.notify();
    cx.timer.after(60, () => state.focus());
  }

  commit(q, cx) {
    const text = this.editor(q).value().trim();
    const drafts = this.drafts();
    if (text) drafts.set(q, { kind: "reply", text });
    else if (drafts.get(q)?.kind === "reply") drafts.delete(q);
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    cx.notify();
  }

  accept(cx) {
    const drafts = this.drafts();
    for (const { text: q, recommended } of this.asks()) {
      if (!recommended || drafts.has(q)) continue;
      drafts.set(q, { kind: recommended.kind === "text" ? "reply" : recommended.kind, text: recommended.text });
    }
    this.setDrafts(drafts);
    cx.notify();
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

  message() {
    const lines = this.answers(this.drafts()).map(({ n, q, text }) => `${n}. ${q.length > QUESTION_CLIP ? `${q.slice(0, QUESTION_CLIP - 1)}…` : q}: ${text}`);
    return [lines.join("\n"), this.pop ? "" : this.input.value().trim()].filter(Boolean).join("\n\n");
  }

  send(cx) {
    const text = this.message();
    const info = this.info();
    if (!text || !info || this.sent === "sending") return;
    this.sent = "sending";
    this.fromBottom = 0;
    const kept = shared("co.sent") ?? { since: Date.now(), items: [] };
    const items = [...kept.items, { at: Date.now(), text }];
    const trimmed = items.length > SENT_KEEP;
    const keep = items.slice(-SENT_KEEP);
    setShared("co.sent", { since: trimmed ? keep[0].at : kept.since, items: keep });
    const overlay = props()?.overlay;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        await hc(["send", info.address, text]);
        if (!this.pop) this.input.set_value("");
        this.setDrafts(new Map());
        this.setTyping(new Map());
        this.editing.clear();
        for (const state of this.editors.values()) state.set_value("");
        this.sent = "sent";
        if (this.pop) closeOverlay(overlay);
      } catch (error) {
        this.sent = "";
        notify({ title: "Send failed", body: error.message, level: "error" });
      }
      cx.notify();
      cx.timer.after(2500, (cx) => {
        this.sent = "";
        cx.notify();
      });
      if (!this.pop) this.refresh(cx);
    });
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
        this.known = this.view.turns.length;
        this.shown += PAGE;
        this.prepended = true;
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
    this.fromBottom = clampFrom(this.fromBottom, this.contentH, this.box.height);
    const drafts = this.drafts();
    const answers = this.answers(drafts);
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
      choose: (q, kind, text, cx) => this.choose(q, kind, text, cx),
      reply: (q, cx) => this.reply(q, cx),
      commit: (q, cx) => this.commit(q, cx),
      clear: (q, cx) => this.clear(q, cx),
      accept: (cx) => this.accept(cx),
      send: (cx) => this.send(cx),
      openAsks: () => this.openAsks(),
      close: () => closeOverlay(props()?.overlay),
      opening: this.opening,
      open: (id, task, cx) => this.openTask(id, task, cx),
      sender: (from) => agents().find((a) => a.address === from)?.tab_name ?? from,
      link: (url) => (/^https?:\/\//i.test(url) ? exec("open", [url]) : notify({ title: "Link not opened", body: "Only web links open from the chat.", level: "info", timeout: 2500 })),
      heights: this.heights,
      working: info?.status === "working",
      turnSize: (key, height, cx) => {
        const known = this.heights.get(key);
        if (known !== undefined && Math.abs(known - height) < 1) return;
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
        this.fromBottom = holdFrom(this.fromBottom, this.contentH, size.height, this.box.height, this.prepended);
        this.prepended = false;
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
    const form = { answers, drafts, editing: this.editing, editor: (q) => this.editor(q), sending: this.sent === "sending" };
    if (this.pop) {
      return v_flex().id("co-pop").size_full().bg(t.chrome)
        .child(popupBar(t, list.length, cb))
        .when(list.length, (el) => el.child(asks(t, list, form, cb, POP_LIST)));
    }
    const strip = taskStrip(t, this.view, cb, this.box.width);
    return v_flex().id("co-root").size_full().min_h(0).bg(t.chrome)
      .child(status(t, info, this.view, now, this.box.width, this.error))
      .when(strip, (el) => el.child(strip))
      .when(list.length, (el) => el.child(askRow(t, list, answers.length, cb)))
      .child(conversation(t, this.view, this.error, now, cb))
      .child(composer(t, info, this.input, this.sent, this.focused, answers, cb));
  }
}
