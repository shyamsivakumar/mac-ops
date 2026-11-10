import { View } from "gpui-kit";
import { v_flex, TextareaState } from "gpui-base";
import { agents, appHome, closeOverlay, exec, hc, home, layout, notify, nextCommand, openOverlay, props, run, setShared, shared, terminals, theme } from "herdr";
import { chipLabel, draftText, imagePathSpans, loadOlder, materialize, pathImages, readTranscript } from "./transcript.js";
import { askRow, choicesOf, clampFrom, composer, conversation, holdFrom, popupBar, questionPop, status, taskStrip, TURN_ESTIMATE } from "./ui.js";

const SHOW_POLL = 50;
const SHOW_LIMIT = 8000;
const LIVE_STATUSES = new Set(["running", "waiting"]);

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
const EDIT_KEYS = [
  ["cmd-a", "SelectAll"],
  ["cmd-c", "Copy"],
  ["cmd-x", "Cut"],
  ["cmd-v", "Paste"],
  ["cmd-z", "Undo"],
  ["cmd-shift-z", "Redo"],
  ["alt-shift-left", "SelectToPreviousWordStart"],
  ["alt-shift-right", "SelectToNextWordEnd"],
  ["cmd-shift-left", "SelectToStartOfLine"],
  ["cmd-shift-right", "SelectToEndOfLine"],
  ["cmd-shift-up", "SelectToStart"],
  ["cmd-shift-down", "SelectToEnd"],
  ["alt-left", "MoveToPreviousWord"],
  ["alt-right", "MoveToNextWord"],
  ["cmd-left", "MoveToStartOfLine"],
  ["cmd-right", "MoveToEndOfLine"],
  ["cmd-up", "MoveToStart"],
  ["cmd-down", "MoveToEnd"],
  ["alt-backspace", "DeleteToPreviousWordStart"],
  ["cmd-backspace", "DeleteToBeginningOfLine"],
].map(([keystroke, action]) => ({ keystroke, action: `input::${action}`, context: "Input" }));
const KEYS = [...EDIT_KEYS, { keystroke: "cmd-alt-v", action: "coordinator_preview", context: "CoordinatorBox" }];
let keysBound = false;
let chipCount = 0;
const QUESTION_CLIP = 70;
const PAGE = 10;
const CALM = 400;
const POP_WIDTH = 640;
const POP_HEIGHT = 560;

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
      const typed = this.asks().find((a) => this.editing.has(a.text));
      cx.timer.after(60, () => (typed ? this.editor(typed.text) : this.handle).focus());
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
    if (!keysBound) {
      cx.bind_keys(KEYS);
      keysBound = true;
    }
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
        if (name === "swap") swapChat();
        cx.notify();
      }
    });
  }

  openAsks() {
    if (!this.asks().length) return;
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
        this.view = await readTranscript(cx);
        if (this.known !== undefined && this.fromBottom > 0) this.shown += Math.max(0, this.view.turns.length - this.known);
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
    return list.map((a) => a.text).join("\n");
  }

  indexOf(list) {
    return this.onReview ? list.length : list.findIndex((a) => a.text === this.stepQ);
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
    const target = list.find((a) => this.editing.has(a.text)) ?? list.find((a) => !drafts.has(a.text));
    if (target) this.stepQ = target.text;
    else this.toReview(list);
  }

  sync(list) {
    if (this.onReview) {
      if (this.reviewSig === this.sigOf(list)) return;
      this.reviewSig = this.sigOf(list);
      this.changed = true;
      this.calmUntil = Date.now() + CALM;
    } else if (!list.some((a) => a.text === this.stepQ)) {
      const drafts = this.drafts();
      this.stepQ = (list.find((a) => !drafts.has(a.text)) ?? list[0])?.text ?? null;
      this.calmUntil = Date.now() + CALM;
    }
  }

  stepTo(step, cx) {
    const list = this.asks();
    if (step >= list.length) this.toReview(list);
    else {
      this.onReview = false;
      this.stepQ = list[Math.max(0, step)].text;
    }
    this.inEditor = false;
    this.handle.focus();
    cx.notify();
  }

  pick(q, choice, cx) {
    const list = this.asks();
    const at = list.findIndex((a) => a.text === q);
    if (at < 0) return;
    const drafts = this.drafts();
    const same = drafts.get(q)?.kind === choice.kind && drafts.get(q).text === choice.text;
    if (same) drafts.delete(q);
    else drafts.set(q, { kind: choice.kind, text: choice.text });
    this.setDrafts(drafts);
    this.keepTyping(q, "");
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    this.stepTo(same ? at : at + 1, cx);
  }

  take(a, cx) {
    const at = this.asks().findIndex((x) => x.text === a.text);
    if (this.drafts().has(a.text)) return this.stepTo(at + 1, cx);
    const choice = choicesOf(a).find((c) => c.rec);
    if (choice) this.pick(a.text, choice, cx);
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
    else if (k === "r" && !review) this.reply(a.text, cx);
    else if (review && n >= 0 && n < list.length) this.stepTo(n, cx);
    else if (!review && n >= 0 && n < choicesOf(a).length) this.pick(a.text, choicesOf(a)[n], cx);
    else return;
    cx.stop_propagation();
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
    const at = this.asks().findIndex((a) => a.text === q);
    this.stepTo(text ? at + 1 : at, cx);
  }

  accept(cx) {
    const drafts = this.drafts();
    for (const { text: q, recommended } of this.asks()) {
      if (!recommended || drafts.has(q)) continue;
      drafts.set(q, { kind: recommended.kind === "text" ? "reply" : recommended.kind, text: recommended.text });
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
    const lines = this.answers(this.drafts()).map(({ n, q, text }) => `${n}. ${q.length > QUESTION_CLIP ? `${q.slice(0, QUESTION_CLIP - 1)}…` : q}: ${text}`);
    return [lines.join("\n"), this.pop ? "" : draftText(this.input.content()).trim()].filter(Boolean).join("\n\n");
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
    this.fromBottom = holdFrom(this.fromBottom, this.contentH - (this.grew - this.grewAbove), this.contentH, this.box.height, this.prepended);
    if (this.grew !== 0) this.prepended = false;
    this.grew = 0;
    this.grewAbove = 0;
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
      pick: (q, choice, cx) => this.pick(q, choice, cx),
      go: (i, cx) => this.stepTo(i, cx),
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
      image: (ref) => this.wantImage(ref, cx),
      draft: () => draftText(this.input.content()),
      preview: this.preview,
      boxHandle: this.boxHandle,
      minRows: MIN_ROWS,
      maxRows: MAX_ROWS,
      togglePreview: (cx) => this.togglePreview(cx),
      attachments: (text) => pathImages(text).images,
      openImage: (path) => exec("open", [path]),
      working: info?.status === "working",
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
    if (this.pop) {
      this.sync(list);
      const form = { answers, drafts, editing: this.editing, editor: (q) => this.editor(q), sending: this.sent === "sending", step: Math.max(0, this.indexOf(list)), changed: this.changed };
      return v_flex().id("co-pop").size_full().bg(t.chrome).track_focus(this.handle)
        .on_key_down((e, cx) => this.askKey(e, cx))
        .child(list.length ? questionPop(t, list, form, cb) : popupBar(t, "No open questions", cb));
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
