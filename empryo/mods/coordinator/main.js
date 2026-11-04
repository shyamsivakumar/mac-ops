import { View } from "gpui-kit";
import { v_flex, TextareaState } from "gpui-base";
import { agents, exec, hc, home, notify, nextCommand, run, shared, theme } from "herdr";
import { loadOlder, readTranscript } from "./transcript.js";
import { asks, composer, conversation, status, taskStrip } from "./ui.js";

const SESSION_GONE = `
test -d "$1" || exit 0
test -d "$1/.empryo/sessions/$2" && exit 1
dir=$(sqlite3 -readonly "$3" "SELECT session_dir FROM threads WHERE id = '$2'" 2>/dev/null)
test -n "$dir" && test -d "$dir" && exit 1
exit 0
`;

const sessionGone = async (cwd, session) => (await exec("sh", ["-c", SESSION_GONE, "sh", cwd, session, `${home()}/.empryo/threads.db`])).code === 0;

async function openTask(id, task) {
  const history = !task.running && (await sessionGone(task.cwd, task.session));
  const argv = task.running || history
    ? [`${home()}/.local/bin/emp`, "follow", task.key]
    : ["/opt/homebrew/bin/empryo", "--session", task.session, "--cwd", task.cwd];
  const label = task.running ? "follow" : history ? "history" : "empryo";
  run("tab.new", { name: `${id} · ${label}`, folder: task.cwd, argv });
}

const EVERY = 3000;
const IDLE_AFTER = 15000;
const MIN_ROWS = 2;
const MAX_ROWS = 8;
const QUESTION_CLIP = 70;
const PAGE = 10;

export default class Coordinator extends View {
  init(_props, cx) {
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
    this.shown = PAGE;
    this.sent = "";
    this.drafts = new Map();
    this.editors = new Map();
    this.editing = new Set();
    this.box = { width: 800, height: 240 };
    this.drawn = Date.now();
    cx.timer.every(EVERY, (cx) => this.watching() && this.refresh(cx));
    this.refresh(cx);
    cx.spawn(async (cx) => {
      for (;;) {
        const name = await nextCommand();
        run("layout.show", { id: "coordinator" });
        if (name === "message") cx.timer.after(60, () => this.input.focus());
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
    cx.spawn(async (cx) => {
      try {
        this.view = await readTranscript();
        if (this.known !== undefined) this.shown += Math.max(0, this.view.turns.length - this.known);
        this.known = this.view.turns.length;
        this.error = "";
        this.prune();
      } catch (error) {
        this.error = String(error.message);
      }
      const v = this.view;
      const stamp = JSON.stringify([v?.rev, v?.activity, v?.activityAt, v?.tokens, this.error]);
      if (stamp === this.stamp) return;
      this.stamp = stamp;
      cx.notify();
    });
  }

  prune() {
    const live = new Set(this.view.asks.map((a) => a.text));
    for (const map of [this.drafts, this.editors]) {
      for (const q of map.keys()) if (!live.has(q)) map.delete(q);
    }
    for (const q of this.editing) if (!live.has(q)) this.editing.delete(q);
  }

  answers() {
    return (this.view?.asks ?? []).flatMap(({ text: q }, n) => (this.drafts.has(q) ? [{ n: n + 1, q, ...this.drafts.get(q) }] : []));
  }

  editor(q) {
    if (!this.editors.has(q)) {
      const state = TextareaState.new({ placeholder: "Your reply", rows: 1 });
      state.set_auto_grow(1, 4);
      state.on("submit", (e, cx) => !e?.shift && this.commit(q, cx));
      state.on("change", (_e, cx) => cx.notify());
      this.editors.set(q, state);
    }
    return this.editors.get(q);
  }

  choose(q, kind, text, cx) {
    const current = this.drafts.get(q);
    if (current?.kind === kind && current.text === text) this.drafts.delete(q);
    else this.drafts.set(q, { kind, text });
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    cx.notify();
  }

  reply(q, cx) {
    const state = this.editor(q);
    const draft = this.drafts.get(q);
    state.set_value(draft?.kind === "reply" ? draft.text : "");
    this.editing.add(q);
    cx.notify();
    cx.timer.after(60, () => state.focus());
  }

  commit(q, cx) {
    const text = this.editor(q).value().trim();
    if (text) this.drafts.set(q, { kind: "reply", text });
    else if (this.drafts.get(q)?.kind === "reply") this.drafts.delete(q);
    this.editing.delete(q);
    cx.notify();
  }

  accept(cx) {
    for (const { text: q, recommended } of this.view?.asks ?? []) {
      if (!recommended || this.drafts.has(q)) continue;
      this.drafts.set(q, { kind: recommended.kind === "text" ? "reply" : recommended.kind, text: recommended.text });
    }
    cx.notify();
  }

  clear(q, cx) {
    this.drafts.delete(q);
    this.editing.delete(q);
    this.editors.get(q)?.set_value("");
    cx.notify();
  }

  message() {
    const lines = this.answers().map(({ n, q, text }) => `${n}. ${q.length > QUESTION_CLIP ? `${q.slice(0, QUESTION_CLIP - 1)}…` : q}: ${text}`);
    return [lines.join("\n"), this.input.value().trim()].filter(Boolean).join("\n\n");
  }

  send(cx) {
    const text = this.message();
    const info = this.info();
    if (!text || !info || this.sent === "sending") return;
    this.sent = "sending";
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        await hc(["send", info.address, text]);
        this.input.set_value("");
        this.drafts.clear();
        this.editing.clear();
        for (const state of this.editors.values()) state.set_value("");
        this.sent = "sent";
      } catch (error) {
        this.sent = "";
        notify({ title: "Send failed", body: error.message, level: "error" });
      }
      cx.notify();
      cx.timer.after(2500, (cx) => {
        this.sent = "";
        cx.notify();
      });
      this.refresh(cx);
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
        this.view = await loadOlder(PAGE);
        this.known = this.view.turns.length;
        this.shown += PAGE;
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
    const answers = this.answers();
    const cb = {
      tasks: shared("hub")?.tasks ?? {},
      isOpen: (key) => this.open.has(key),
      toggle: (key, cx) => this.toggle(key, cx),
      shown: this.shown,
      loading: this.loading,
      more: (cx) => {
        this.shown += PAGE;
        cx.notify();
      },
      older: (cx) => this.older(cx),
      choose: (q, kind, text, cx) => this.choose(q, kind, text, cx),
      reply: (q, cx) => this.reply(q, cx),
      commit: (q, cx) => this.commit(q, cx),
      clear: (q, cx) => this.clear(q, cx),
      accept: (cx) => this.accept(cx),
      send: (cx) => this.send(cx),
      open: (id, task) => openTask(id, task),
      link: (url) => exec("open", [url]),
      size: (size, cx) => {
        if (size.width === this.box.width && size.height === this.box.height) return;
        this.box = size;
        cx.notify();
      },
    };
    const strip = taskStrip(t, this.view, cb, this.box.width);
    return v_flex().id("co-root").size_full().min_h(0).bg(t.chrome)
      .child(status(t, info, this.view, now, this.box.width))
      .when(strip, (el) => el.child(strip))
      .when(this.view?.asks.length, (el) => el.child(asks(t, this.view.asks, { answers, drafts: this.drafts, editing: this.editing, editor: (q) => this.editor(q), sending: this.sent === "sending" }, cb)))
      .child(conversation(t, this.view, this.error, now, cb))
      .child(composer(t, info, this.input, this.sent, this.focused, answers, cb));
  }
}
