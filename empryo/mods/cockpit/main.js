// Board for the hub work: three columns of one card per task, with the selected card published as the current task.

import { View, div } from "gpui-kit";
import { h_flex, v_flex, InputState } from "gpui-base";
import { agents, exec, hc, notify, nextCommand, run, setShared, theme } from "herdr";
import { cleanupNote, cleanupThread, load, loadBacklog, loadVerdict, mergeThread, openThread, queueCap, readTask, runModelOf, sendReply, settle, shepherdrStates, verdictOf } from "./hub.js";
import { prState, refreshPrs } from "./gh.js";
import { COLUMNS, H, ago, card, cardHeight, childRow, columnHead, elapsed, emptyRow, foldedColumn, footer, thumb } from "./ui.js";

const BOARD_EVERY = 10000;
const IDLE_AFTER = 25000;
const ARM_FOR = 4000;
const LOAD_STALE = 25000;
const MIN_COL = 164;
const COLUMN_OF = { wait: "needs", fail: "needs", stop: "needs", run: "run", done: "done" };
const EMPTY = { backlog: "Backlog is empty", needs: "Nothing needs you", run: "Nothing running", ready: "No PRs ready to merge", done: "Nothing to settle" };
const COLUMN_KEYS = COLUMNS.map((c) => c[0]);

export default class Board extends View {
  init(_props, cx) {
    this.handle = cx.focus_handle();
    this.input = InputState.new({ placeholder: "Write a reply" });
    this.input.on("submit", (_e, cx) => this.submitReply(cx));
    this.input.on("focus", () => (this.typing = true));
    this.input.on("blur", () => (this.typing = false));
    this.board = null;
    this.error = "";
    this.loading = false;
    this.loadingSince = 0;
    this.token = 0;
    this.stale = false;
    this.backlog = [];
    this.backlogTasks = {};
    this.enriching = { backlog: 0, prs: 0 };
    this.cursor = null;
    this.published = null;
    this.tasks = new Map();
    this.replyKey = null;
    this.replyThread = null;
    this.typing = false;
    this.settled = new Map();
    this.expanded = new Set();
    this.armed = null;
    this.colW = MIN_COL;
    this.folded = new Set(JSON.parse(localStorage.getItem("folded") ?? '["backlog"]'));
    this.cap = 6;
    this.shepherdr = new Map();
    this.area = { width: 1200, height: 260 };
    this.scrollY = { backlog: 0, needs: 0, run: 0, ready: 0, done: 0 };
    this.reveal = null;
    this.box = Object.fromEntries(COLUMNS.map((c) => [c[0], { width: 300, height: 200 }]));
    this.drawn = Date.now();
    this.layout = { cols: {}, reviewed: [], finished: [], approvable: [] };
    cx.timer.every(BOARD_EVERY, (cx) => this.watching() && this.refresh(cx));
    shepherdrStates().then((states) => (this.shepherdr = states));
    this.refresh(cx);
    cx.spawn(async (cx) => {
      for (;;) {
        this.command(await nextCommand(), cx);
        cx.notify();
      }
    });
  }

  watching() {
    return Date.now() - this.drawn < IDLE_AFTER;
  }

  refresh(cx) {
    if (this.loading && Date.now() - this.loadingSince < LOAD_STALE) return Promise.resolve();
    const token = ++this.token;
    this.loading = true;
    this.loadingSince = Date.now();
    return cx.spawn(async (cx) => {
      try {
        const board = await load();
        if (token !== this.token) return;
        this.board = board;
        this.error = "";
        this.stale = false;
        this.loading = false;
        this.share();
        cx.notify();
        this.enrich(board, cx);
      } catch (error) {
        if (token !== this.token) return;
        this.error = String(error.message);
        this.stale = true;
        this.loading = false;
        cx.notify();
      }
    });
  }

  share() {
    const board = this.board;
    if (board) setShared("hub", { running: board.running, waiting: board.waiting, failed: board.failed, done: board.done, at: board.at, tasks: { ...this.backlogTasks, ...board.tasks } });
  }

  background(slot, work, cx) {
    if (Date.now() - this.enriching[slot] < LOAD_STALE) return;
    this.enriching[slot] = Date.now();
    cx.spawn(async (cx) => {
      try {
        await work();
      } catch {
        this.stale = true;
      }
      this.enriching[slot] = 0;
      cx.notify();
    });
  }

  enrich(board, cx) {
    this.background("backlog", async () => {
      const queue = await loadBacklog();
      this.backlog = queue.backlog;
      this.backlogTasks = queue.tasks;
      this.share();
      cx.notify();
    }, cx);
    this.background("prs", async () => {
      await refreshPrs(board.groups.filter((g) => !g.threads.some((c) => c.kind === "run")).flatMap((g) => g.prs).filter((p) => p.state === "open"));
      cx.notify();
      await Promise.all(this.groups().filter((g) => this.mergeCandidate({ ...g, info: this.prInfo(g) })).map((g) => this.reviewOf(g)).filter(Boolean).map((th) => loadVerdict(th).catch(() => undefined)));
      this.cap = await queueCap().catch(() => 6);
    }, cx);
  }

  groups() {
    return (this.board?.groups ?? []).flatMap((g) => {
      const threads = g.threads.filter((c) => !(this.settled.get(c.key) >= c.at));
      return threads.length ? [{ ...g, threads, primary: threads[0], lead: threads.find((c) => c.led) ?? threads[0], kind: threads[0].kind }] : [];
    });
  }

  prInfo(g) {
    const states = g.prs.map((pr) => ({ pr, gh: prState(pr), state: (prState(pr)?.state ?? pr.state).toUpperCase() }));
    const open = states.filter((x) => x.state === "OPEN").sort((a, b) => b.pr.number - a.pr.number)[0];
    if (open) return { status: "open", pr: open.pr, gh: open.gh };
    const merged = states.find((x) => x.state === "MERGED");
    return merged ? { status: "merged", pr: merged.pr, gh: merged.gh } : { status: "none", pr: null, gh: null };
  }

  verdictFor(g) {
    const review = this.reviewOf(g);
    return review ? verdictOf(review) : null;
  }

  mergeCandidate(g) {
    return g.info.status === "open" && !g.threads.some((c) => c.kind === "run");
  }

  reviewOf(g) {
    return g.threads.filter((c) => c.kind === "done" && /review/i.test(c.title)).sort((a, b) => b.at - a.at)[0] ?? null;
  }

  columns(t, now) {
    const cols = Object.fromEntries(COLUMN_KEYS.map((k) => [k, { rows: [], count: 0, groups: [] }]));
    const groups = this.groups();
    for (const g of groups) {
      g.info = this.prInfo(g);
      cols[this.mergeCandidate(g) ? "ready" : COLUMN_OF[g.kind]].groups.push(g);
    }
    for (const g of this.backlog) cols.backlog.groups.push(g);
    const reviewed = cols.done.groups.flatMap((g) => g.threads).filter((c) => /review/i.test(c.title));
    const cb = {
      press: (key, cx) => {
        this.handle.focus();
        this.cursor = key;
        cx.notify();
      },
      reply: (cx) => this.openReply(this.current(), cx),
      open: () => this.openEntry(this.current()),
      settle: (cx) => this.settleEntry(this.current(), cx),
      toggle: (key, cx) => {
        this.toggle(this.entryOf(key).group.key);
        cx.notify();
      },
      settleReviewed: (cx) => this.settleReviewed(cx),
      settleAll: (cx) => this.settleAll(cx),
      approve: (cx) => this.approve(this.current(), cx),
      approveAll: (cx) => this.approveAll(cx),
      queue: (cx) => this.queue(this.current(), cx),
      openPr: () => this.openPr(this.current()),
      fold: (key, cx) => {
        this.toggleFold(key);
        cx.notify();
      },
    };
    for (const key of COLUMN_KEYS) {
      const col = cols[key];
      const narrow = this.colW < 220;
      const variant = key === "ready" ? "ready" : key === "backlog" ? "backlog" : "std";
      for (const g of col.groups) {
        col.count += 1;
        if (this.folded.has(key)) continue;
        const gkey = `g:${g.key}`;
        const expanded = this.expanded.has(g.key);
        const replying = this.replyKey === gkey;
        const selected = this.cursor === gkey;
        const c = { ...g.primary, title: g.title, task: g.task };
        const view = (extra) => ({ c, count: g.threads.length, expanded, mark: this.cursorMark(replying), narrow, now, variant, armed: this.armed, merged: g.info?.status === "merged", pr: g.info?.pr, gh: g.info?.gh, verdict: this.verdictFor(g), runModel: runModelOf(c), state: g.threads.map((x) => this.shepherdr.get(x.key)).find(Boolean), since: g.runSince, reviewed: g.threads.some((x) => /review/i.test(x.title)), ...extra });
        const entry = { key: gkey, col: key, group: g, thread: null };
        col.rows.push({ key: gkey, h: cardHeight(replying), entry, el: () => card(t, entry, view({ selected, replying, canSettle: g.threads.some((x) => x.kind === "done") }), this.input, cb) });
        if (!expanded) continue;
        for (const th of g.threads.slice(1)) {
          const tkey = `t:${th.key}`;
          const child = { key: tkey, col: key, group: g, thread: th };
          col.rows.push({ key: tkey, h: H.child, entry: child, el: () => childRow(t, child, view({ c: th, selected: this.cursor === tkey }), cb) });
        }
      }
      col.summary = this.summary(key, col, now);
    }
    const approvable = cols.ready.groups.filter((g) => g.info.status === "open" && g.info.pr).map((g) => ({ name: g.task || g.title, number: g.info.pr.number, group: g }));
    this.layout = { cols, reviewed, finished: cols.done.groups.flatMap((g) => g.threads).filter((c) => c.kind === "done"), approvable };
    return { cols, cb, state: { colW: this.colW, armed: this.armed, reviewed: reviewed.length, done: cols.done.count, approvable: approvable.length, running: this.board?.running ?? 0, cap: this.cap } };
  }

  summary(key, col, now) {
    if (!col.groups.length) return [["empty", "dim"]];
    const groups = col.groups;
    const seg = (n, text, tone) => (n ? [[`${n} ${text}`, tone]] : []);
    const oldest = ["oldest " + ago(Math.min(...groups.map((g) => g.at)), now), "dim"];
    if (key === "needs") {
      return [...seg(groups.filter((g) => g.kind === "wait").length, "waiting", "blocked"), ...seg(groups.filter((g) => g.kind === "fail").length, "failed", "blocked"), ...seg(groups.filter((g) => g.kind === "stop").length, "stopped", "blocked"), oldest];
    }
    if (key === "run") {
      const started = groups.map((g) => g.runSince).filter(Boolean);
      const capSeg = this.board.running >= this.cap ? ["at cap", "blocked"] : [`${this.cap - this.board.running} free`, "dim"];
      return started.length ? [capSeg, [`longest ${elapsed(now - Math.min(...started))}`, "working"]] : [capSeg];
    }
    if (key === "ready") {
      const ci = (g) => g.info.gh?.ci ?? "loading";
      return [
        ...seg(groups.filter((g) => ci(g) === "pass").length, "pass", "done"),
        ...seg(groups.filter((g) => ci(g) === "fail").length, "failing", "blocked"),
        ...seg(groups.filter((g) => g.info.gh?.mergeable === "CONFLICTING").length, "conflict", "blocked"),
        ...seg(groups.filter((g) => ci(g) === "pending" || ci(g) === "loading").length, "pending", "working"),
      ];
    }
    if (key === "done") {
      const reviewedCards = groups.filter((g) => g.threads.some((c) => /review/i.test(c.title))).length;
      return [...seg(reviewedCards, "reviewed", "done"), ...seg(col.count - reviewedCards, "unreviewed", "dim"), oldest];
    }
    const queued = groups.filter((g) => g.threads.some((x) => /queued/i.test(this.shepherdr.get(x.key) ?? ""))).length;
    return [...seg(queued, "queued", "idle"), oldest];
  }

  toggleFold(key) {
    this.folded.has(key) ? this.folded.delete(key) : this.folded.add(key);
    localStorage.setItem("folded", JSON.stringify([...this.folded]));
    const cur = this.current();
    if (!cur || !this.folded.has(cur.col)) return;
    const from = COLUMN_KEYS.indexOf(cur.col);
    const row = this.entries(cur.col).findIndex((r) => r.key === this.cursor);
    for (let d = 1; d < COLUMN_KEYS.length; d++) {
      for (const i of [from - d, from + d]) {
        const open = COLUMN_KEYS[i];
        const list = open && !this.folded.has(open) ? this.entries(open) : [];
        if (list.length) return this.moveTo(list[Math.min(row, list.length - 1)].key);
      }
    }
  }

  cursorMark(replying) {
    return this.handle.is_focused() || replying ? "focus" : "idle";
  }

  entries(key) {
    return this.layout.cols[key]?.rows.filter((r) => r.entry) ?? [];
  }

  entryOf(key) {
    for (const k of COLUMN_KEYS) {
      const r = this.layout.cols[k]?.rows.find((x) => x.key === key);
      if (r) return r.entry;
    }
    return null;
  }

  current() {
    return this.entryOf(this.cursor);
  }

  threadOf(entry) {
    return entry.thread ?? entry.group.lead ?? entry.group.primary;
  }

  toggle(groupKey) {
    this.expanded.has(groupKey) ? this.expanded.delete(groupKey) : this.expanded.add(groupKey);
  }

  moveTo(key) {
    this.cursor = key;
    this.reveal = key;
  }

  step(by) {
    const cur = this.current();
    const list = this.entries(cur?.col ?? COLUMN_KEYS.find((k) => this.entries(k).length));
    if (!list.length) return;
    const at = list.findIndex((r) => r.key === this.cursor);
    this.moveTo(list[Math.min(list.length - 1, Math.max(0, at < 0 ? 0 : at + by))].key);
  }

  shift(by) {
    const cur = this.current();
    const from = cur ? COLUMN_KEYS.indexOf(cur.col) : -1;
    const row = cur ? this.entries(cur.col).findIndex((r) => r.key === this.cursor) : 0;
    for (let i = from + by; i >= 0 && i < COLUMN_KEYS.length; i += by) {
      const list = this.entries(COLUMN_KEYS[i]);
      if (list.length) return this.moveTo(list[Math.min(row, list.length - 1)].key);
    }
  }

  nextEntry() {
    const all = COLUMN_KEYS.flatMap((k) => this.entries(k));
    if (!all.length) return notify({ title: "Nothing needs you", level: "success", timeout: 2000 });
    const at = all.findIndex((r) => r.key === this.cursor);
    this.moveTo(all[(at + 1) % all.length].key);
  }

  command(name, cx) {
    run("layout.show", { id: "cockpit" });
    this.handle.focus();
    if (name === "next") this.nextEntry();
    const e = this.current();
    if (name === "settle" && e) this.settleEntry(e, cx);
    if (name === "open" && e) this.openEntry(e);
  }

  openEntry(e) {
    if (!e) return;
    const thread = this.threadOf(e);
    if (!thread.session) return notify({ title: "No Empryo session yet", body: "Send a message first.", level: "info", timeout: 3000 });
    openThread(thread, thread.kind === "run" || thread.kind === "wait");
  }

  openReply(e, cx) {
    if (!e) return;
    this.cursor = e.key;
    this.replyKey = e.key;
    this.replyThread = this.threadOf(e);
    this.reveal = e.key;
    this.input.set_value("");
    cx.timer.after(60, () => this.input.focus());
    cx.notify();
  }

  closeInput() {
    this.replyKey = null;
    this.handle.focus();
  }

  submitReply(cx) {
    const text = this.input.value().trim();
    const thread = this.replyThread;
    if (!text || !thread || !this.replyKey) return;
    this.closeInput();
    this.attempt(`Sent to ${thread.task || thread.title}`, () => sendReply(thread.key, text), cx);
  }

  publish(entry, cx) {
    const thread = this.threadOf(entry);
    const base = { key: thread.key, task: entry.group.task, title: entry.group.title, project: thread.project };
    const known = this.tasks.get(thread.key);
    if (known) return setShared("task", { ...base, ...known });
    setShared("task", { ...base, worktree: null, branch: null, repo: null });
    readTask(thread).then((info) => {
      this.tasks.set(thread.key, info);
      if (this.published === entry.key) setShared("task", { ...base, ...info });
      cx.notify();
    }).catch(() => undefined);
  }

  settleThreads(threads, cx) {
    if (!threads.length) return notify({ title: "Only finished threads can be settled", level: "info", timeout: 2500 });
    for (const c of threads) this.settled.set(c.key, c.at);
    const label = threads.length === 1 ? `Settled ${threads[0].task || threads[0].title}` : `Settled ${threads.length} threads`;
    const undo = () => threads.forEach((c) => this.settled.delete(c.key));
    this.attempt(label, async () => {
      for (const c of threads) {
        await settle(c.key);
        await this.cleanup(c);
      }
    }, cx, undo);
    cx.notify();
  }

  async cleanup(c) {
    const name = c.task || c.title;
    try {
      const note = cleanupNote(await cleanupThread(c.key));
      if (note) notify({ title: name, body: note, level: "info", timeout: 5000 });
    } catch (error) {
      notify({ title: `Cleanup failed · ${name}`, body: error.message, level: "error" });
    }
  }

  taskThread(group) {
    const own = group.threads.filter((c) => !/review/i.test(c.title));
    return own.find((c) => c.led) ?? own[0] ?? group.primary;
  }

  merge(groups, cx) {
    cx.spawn(async (cx) => {
      for (const g of groups) {
        const name = g.task || g.title;
        try {
          const r = await mergeThread(this.taskThread(g).key);
          if (r.merged) notify({ title: `Merged #${r.pullRequest} · ${name}`, body: cleanupNote(r.cleanup) ?? "Done", level: "success", timeout: 5000 });
          else notify({ title: `Not merged · ${name}`, body: r.refused, level: "error", timeout: 9000 });
        } catch (error) {
          notify({ title: `Merge failed · ${name}`, body: error.message, level: "error" });
        }
      }
      await this.refresh(cx);
      cx.notify();
    });
  }

  settleEntry(e, cx) {
    if (!e) return;
    const threads = e.thread ? [e.thread] : e.group.threads;
    this.settleThreads(threads.filter((c) => c.kind === "done"), cx);
  }

  confirm(kind, key, go, cx) {
    if (this.armed?.kind === kind && this.armed.key === key) {
      this.armed = null;
      return go();
    }
    this.armed = { kind, key };
    cx.timer.after(ARM_FOR, (cx) => {
      if (this.armed?.kind === kind && this.armed.key === key) this.armed = null;
      cx.notify();
    });
    cx.notify();
  }

  settleReviewed(cx) {
    const threads = this.layout.reviewed;
    if (threads.length) this.confirm("settle", "all", () => this.settleThreads(threads, cx), cx);
  }

  settleAll(cx) {
    const threads = this.layout.finished;
    if (threads.length) this.confirm("settle-all", "all", () => this.settleThreads(threads, cx), cx);
  }

  tell(text, label, cx) {
    const info = agents().find((a) => a.space_name === "Coordinator");
    if (!info) return notify({ title: "The Coordinator isn't running", level: "error" });
    this.attempt(label, async () => {
      await hc(["send", info.address, text]);
    }, cx);
  }

  approve(e, cx) {
    const pr = e?.group.info?.status === "open" ? e.group.info.pr : null;
    if (!pr) return;
    this.confirm("approve", e.key, () => this.merge([e.group], cx), cx);
  }

  approveAll(cx) {
    const prs = this.layout.approvable;
    if (!prs.length) return;
    this.confirm("approve-all", "all", () => this.merge(prs.map((p) => p.group), cx), cx);
  }

  queue(e, cx) {
    if (e?.col !== "backlog") return;
    const name = e.group.task || e.group.title;
    this.confirm("queue", e.key, () => this.tell(`Queue ${name}: start it when a slot frees`, `Queued ${name}`, cx), cx);
  }

  openPr(e) {
    const info = e?.group.info;
    if (info?.pr) exec("open", [info.gh?.url ?? info.pr.url]);
  }

  attempt(label, work, cx, undo) {
    cx.spawn(async (cx) => {
      try {
        await work();
        notify({ title: label, level: "success", timeout: 2000 });
      } catch (error) {
        undo?.();
        notify({ title: `${label.split(" ")[0]} failed`, body: error.message, level: "error" });
      }
      await this.refresh(cx);
      cx.notify();
    });
  }

  key(e, cx) {
    if (this.typing) {
      if (e.key !== "escape") return;
      this.closeInput();
    } else if (!this.browse(e, cx)) return;
    cx.stop_propagation();
    cx.notify();
  }

  browse(e, cx) {
    const m = e.modifiers;
    if (m.platform || m.control || m.alt) return false;
    const c = this.current();
    const k = e.key;
    if (k === "j" || k === "down") this.step(1);
    else if (k === "k" || k === "up") this.step(-1);
    else if (k === "h") this.shift(-1);
    else if (k === "l") this.shift(1);
    else if (k === "g") this.moveTo((m.shift ? this.entries(c?.col).at(-1) : this.entries(c?.col)[0])?.key);
    else if (k === "right" && c?.group.threads.length > 1) this.expanded.add(c.group.key);
    else if (k === "left" && c) {
      this.expanded.delete(c.group.key);
      this.moveTo(`g:${c.group.key}`);
    } else if ((k === "enter" || k === "o") && c) this.openEntry(c);
    else if (k === "r" && c) this.openReply(c, cx);
    else if (k === "S") this.settleReviewed(cx);
    else if (k === "A") this.settleAll(cx);
    else if (k === "a") this.approve(c, cx);
    else if (k === "M") this.approveAll(cx);
    else if (k === "q") this.queue(c, cx);
    else if (k === "p") this.openPr(c);
    else if (k === "f" && c) this.toggleFold(c.col);
    else if (k === "b") this.toggleFold("backlog");
    else if (k === "s" && c) this.settleEntry(c, cx);
    else if (k === "R") this.refresh(cx);
    else return false;
    return true;
  }

  column(t, key, col, state, cb) {
    const view = this.box[key].height;
    let total = 0;
    for (const r of col.rows) {
      r.y = total;
      total += r.h;
    }
    const target = this.reveal && col.rows.find((r) => r.key === this.reveal);
    if (target) {
      if (target.y < this.scrollY[key] || target.h > view) this.scrollY[key] = target.y;
      else if (target.y + target.h > this.scrollY[key] + view) this.scrollY[key] = target.y + target.h - view;
      this.reveal = null;
    }
    this.scrollY[key] = Math.min(Math.max(0, this.scrollY[key]), Math.max(0, total - view));
    const first = Math.max(0, col.rows.findIndex((r) => r.y + r.h > this.scrollY[key]));
    const shift = this.scrollY[key] - (col.rows[first]?.y ?? 0);
    const visible = [];
    let shown = -shift;
    for (const r of col.rows.slice(first)) {
      if (shown >= view) break;
      visible.push(r.el());
      shown += r.h;
    }
    if (!col.rows.length) visible.push(emptyRow(t, !this.board ? (this.error ? "Hub unreachable. R to retry" : "Loading…") : EMPTY[key]));
    return v_flex().id(`col-${key}`).w(this.colW).flex_none().h_full().border_r(key === "done" ? 0 : 1).border_color(t.border)
      .child(columnHead(t, key, col, state, cb))
      .child(
        v_flex().id(`list-${key}`).flex_1().min_h(0).overflow_hidden().relative().pt(4)
          .on_size_change((size, cx) => {
            const old = this.box[key];
            if (size.width === old.width && size.height === old.height) return;
            this.box[key] = size;
            cx.notify();
          })
          .on_scroll_wheel((e, cx) => {
            this.scrollY[key] -= e.delta.y;
            cx.notify();
          })
          .child(v_flex().w_full().flex_none().relative().top(-shift).children(visible))
          .when(total > view, (el) => el.child(thumb(t, this.scrollY[key], view, total))));
  }

  render(cx) {
    const t = theme();
    const now = Date.now();
    this.drawn = now;
    if (this.board && now - this.board.at > 2 * BOARD_EVERY) this.refresh(cx);
    const folded = COLUMN_KEYS.filter((k) => this.folded.has(k)).length;
    this.colW = Math.max(MIN_COL, Math.floor((this.area.width - folded * H.folded) / Math.max(1, COLUMN_KEYS.length - folded)));
    const { cols, cb, state } = this.columns(t, now);
    const all = COLUMN_KEYS.flatMap((k) => cols[k].rows.filter((r) => r.entry));
    if (!all.some((r) => r.key === this.cursor)) this.cursor = all[0]?.key ?? null;
    if (this.cursor !== this.published) {
      this.published = this.cursor;
      const entry = this.current();
      if (entry) this.publish(entry, cx);
    }
    return v_flex().id("ck-root").size_full().min_h(0).bg(t.chrome).text_size(13).track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .on_mouse_down("left", () => this.handle.focus())
      .child(
        div().id("ck-area").flex_1().min_h(0).min_w(0).w_full()
          .on_size_change((size, cx) => {
            if (size.width === this.area.width && size.height === this.area.height) return;
            this.area = size;
            cx.notify();
          })
          .child(h_flex().id("ck-cols").size_full().overflow_x_scroll()
            .children(COLUMN_KEYS.map((k) => (this.folded.has(k) ? foldedColumn(t, k, cols[k], state, cb) : this.column(t, k, cols[k], state, cb))))))
      .child(footer(t, this.area.width, this.stale));
  }
}
