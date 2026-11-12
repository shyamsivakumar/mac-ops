// Read-only pop-ups: the task queue (cockpit toolbar), memory and mod errors (status bar).

import { View, div } from "gpui-kit";
import { TextView, h_flex, v_flex } from "gpui-base";
import { closeOverlay, exec, home, props, readTextFile, theme } from "herdr";

const HERDR_APP = `${home()}/.local/bin/herdr-app`;
const COORDQ = `${home()}/.local/bin/coordq`;
const DISPATCH_LAST_FILE = `${home()}/Code/coordinator/queue/dispatch.last`;
const TITLES = { queue: "Queue", memory: "Memory", errors: "Mod errors" };
const MEM_REFRESH = 10000;
const MEM_ROWS = 14;
const PS_LINE = /^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/;
const AGENT_KINDS = [["Claude", /(^|\/)claude(\s|$)/], ["Codex", /(^|\/)codex(\s|$)/]];
const RUNTIME_KINDS = [["node", /(^|\/)node(\s|$)/], ["python", /(^|\/)[Pp]ython[\d.]*(\s|$)/]];
const QUEUE_LINE = /^#(\d+) p(\d+) (\S+) (.*?)(?: \(failed (\d+)x\))?$/;

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function span(ms) {
  const m = Math.max(0, Math.floor(ms / 60000));
  return m < 1 ? "under a minute" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`;
}

const gigabytes = (kb) => `${(kb / 1048576).toFixed(1)} GB`;
const megabytes = (kb) => (kb >= 1048576 ? gigabytes(kb) : `${Math.round(kb / 1024)} MB`);
const kindOf = (kinds, command) => kinds.find(([, pattern]) => pattern.test(command))?.[0] ?? null;
const since = (ms) => `${span(Date.now() - ms)} ago`;

export default class Panels extends View {
  init(_props, cx) {
    const p = props() ?? {};
    this.overlay = p.overlay ?? null;
    this.panel = p.panel ?? "queue";
    this.seed = p.seed ?? {};
    this.data = null;
    this.error = null;
    this.handle = cx.focus_handle();
    cx.timer.after(60, () => this.handle.focus());
    this.load(cx);
    if (this.panel === "memory" || this.panel === "errors") cx.timer.every(MEM_REFRESH, (cx) => this.load(cx));
  }

  load(cx) {
    if (this.loading) return;
    this.loading = true;
    cx.spawn(async (cx) => {
      try {
        this.data = await this[`read_${this.panel}`]();
        this.error = null;
      } catch (error) {
        this.error = error.message;
      }
      this.loading = false;
      cx.notify();
    });
  }

  async json(command, args) {
    const r = await exec(command, args);
    if (r.code !== 0) throw new Error(r.stderr.trim() || `${command} failed`);
    return JSON.parse(r.stdout);
  }

  async readFile(path) {
    const text = await readTextFile(path);
    return text && JSON.parse(text);
  }

  async read_queue() {
    const [status, list, last] = await Promise.all([this.json(COORDQ, ["status"]), exec(COORDQ, ["list"]), readTextFile(DISPATCH_LAST_FILE)]);
    if (list.code !== 0) throw new Error(list.stderr.trim() || "coordq list failed");
    const items = list.stdout.split("\n").filter(Boolean).map((line) => {
      const m = QUEUE_LINE.exec(line);
      return m ? { id: m[1], priority: m[2], tool: m[3], title: m[4], attempts: Number(m[5] ?? 0) } : { id: "?", priority: "?", tool: "", title: line, attempts: 0 };
    });
    return { ...status, items, dispatched: last ? Number(last) * 1000 : null };
  }

  async read_errors() {
    return (await this.json(HERDR_APP, ["status"])).errors;
  }

  async read_memory() {
    const [pressure, size, ps] = await Promise.all([exec("memory_pressure", []), exec("sysctl", ["-n", "hw.memsize"]), exec("ps", ["-axo", "pid=,ppid=,rss=,etime=,command="])]);
    const free = /free percentage: (\d+)%/.exec(pressure.stdout);
    if (pressure.code !== 0 || !free) throw new Error("memory_pressure gave no free percentage");
    if (size.code !== 0 || ps.code !== 0) throw new Error(size.stderr.trim() || ps.stderr.trim() || "ps failed");
    const procs = new Map(ps.stdout.split("\n").map((line) => PS_LINE.exec(line)).filter(Boolean)
      .map(([, pid, ppid, rss, etime, command]) => [Number(pid), { pid: Number(pid), ppid: Number(ppid), rss: Number(rss), etime, command }]));
    const agentOf = (p) => {
      for (let cur = p; cur; cur = procs.get(cur.ppid)) if (kindOf(AGENT_KINDS, cur.command)) return cur;
      return null;
    };
    const sessions = new Map();
    const loose = [];
    for (const p of procs.values()) {
      const root = agentOf(p);
      if (root) {
        const s = sessions.get(root.pid) ?? { label: kindOf(AGENT_KINDS, root.command), pid: root.pid, etime: root.etime, command: root.command, rss: 0, count: 0 };
        s.rss += p.rss;
        s.count += 1;
        sessions.set(root.pid, s);
      } else if (kindOf(RUNTIME_KINDS, p.command)) loose.push({ label: kindOf(RUNTIME_KINDS, p.command), pid: p.pid, etime: p.etime, command: p.command, rss: p.rss, count: 1 });
    }
    const rows = [...sessions.values(), ...loose].sort((a, b) => b.rss - a.rss);
    const totalKb = Number(size.stdout.trim()) / 1024;
    return { free: Number(free[1]), totalKb, rows: rows.slice(0, MEM_ROWS), agentKb: [...sessions.values()].reduce((sum, s) => sum + s.rss, 0) };
  }

  key(e, cx) {
    if (e.is_held || e.key !== "escape") return;
    closeOverlay(this.overlay);
    cx.stop_propagation();
  }

  section(t, title) {
    return div().w_full().px(14).pt(12).pb(4).text_size(11).font_semibold().text_color(t.muted).child(title);
  }

  line(t, label, value, tone) {
    return h_flex().w_full().px(14).min_h(22).gap(10).items_start()
      .child(div().w(110).flex_none().text_size(12).text_color(t.muted).child(label))
      .child(div().flex_1().min_w(0).text_size(12.5).line_height("17px").text_color(tone ? t[tone] : t.foreground).child(value));
  }

  note(t, text, tone) {
    return div().w_full().px(14).py(2).text_size(12.5).line_height("17px").text_color(tone ? t[tone] : t.muted).child(text);
  }

  errors(t) {
    const list = this.data ?? this.seed.errors;
    if (!list) return [this.note(t, "Loading mod errors…")];
    if (!list.length) return [this.note(t, "No mod errors.", "done")];
    return list.flatMap((raw, i) => {
      const m = /^mod (\S+?): ([\s\S]*)$/.exec(raw);
      const text = (m ? m[2] : raw).trim().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
      const name = m ? m[1] : "app";
      return [this.section(t, name), div().w_full().px(14).py(2).text_size(12).text_color(t.blocked).child(TextView.html(`err-${i}-${name}`, `<span>${text}</span>`).selectable(true))];
    });
  }

  memory(t) {
    const d = this.data;
    const free = d?.free ?? this.seed.free;
    if (free === undefined) return [this.note(t, "Loading memory…")];
    const lines = [
      this.section(t, "System"),
      this.line(t, "Free", `${free}%`, free < 15 ? "blocked" : undefined),
    ];
    if (!d) return [...lines, this.note(t, "Loading processes…")];
    lines.push(
      this.line(t, "Used", `${gigabytes((d.totalKb * (100 - free)) / 100)} of ${gigabytes(d.totalKb)}`),
      this.line(t, "Agent sessions", `${gigabytes(d.agentKb)} across Claude and Codex, with everything they started`),
      this.section(t, "Largest agents and runtimes, by resident memory"),
    );
    for (const r of d.rows) {
      lines.push(
        h_flex().w_full().px(14).pt(4).gap(8).items_baseline()
          .child(div().w(52).flex_none().text_size(12).font_medium().text_color(t.foreground).child(r.label))
          .child(div().w(64).flex_none().text_size(12.5).text_color(t.foreground).child(megabytes(r.rss)))
          .child(div().flex_1().min_w(0).text_size(12).text_color(t.muted).child(`pid ${r.pid} · up ${r.etime}${r.count > 1 ? ` · ${r.count} processes` : ""}`)),
        this.note(t, r.command.length > 90 ? `${r.command.slice(0, 89)}…` : r.command, "dim"),
      );
    }
    return lines;
  }

  queue(t) {
    const d = this.data;
    if (!d) return [this.line(t, "Running", `${this.seed.running} of ${this.seed.cap}`), this.note(t, "Loading the queue…")];
    const full = d.live >= d.cap;
    const why = (i) => (i.attempts >= 3 ? `Failed ${i.attempts} times and will not be retried.` : i.attempts ? `Failed ${plural(i.attempts, "time")}. The dispatcher retries it, up to 3 attempts.` : full ? `Waiting for a free slot. ${d.live} of ${d.cap} are running.` : `Waiting for the next dispatcher run${d.dispatched ? `, last ran ${since(d.dispatched)}` : ""}.`);
    return [
      this.section(t, "Slots"),
      this.line(t, "Running", `${d.live} of ${d.cap}`, full ? "working" : undefined),
      this.line(t, "Waiting", String(d.queued), d.queued ? "working" : undefined),
      this.section(t, "Waiting items"),
      ...(d.items.length ? d.items.flatMap((i) => [
        h_flex().w_full().px(14).pt(4).gap(8).items_baseline()
          .child(div().flex_none().text_size(12).text_color(t.dim).child(`#${i.id} · p${i.priority}`))
          .child(div().flex_1().min_w(0).text_size(12.5).text_color(t.foreground).child(i.title)),
        this.note(t, why(i)),
      ]) : [this.note(t, "Nothing is waiting.")]),
    ];
  }

  render() {
    const t = theme();
    return v_flex().id("ops-panel").size_full().min_h(0).bg(t.chrome).text_size(13).track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .on_mouse_down("left", () => this.handle.focus())
      .child(h_flex().px(14).py(10).gap(10).items_center().flex_none().border_b(1).border_color(t.border)
        .child(div().text_size(15).font_semibold().text_color(t.foreground).child(TITLES[this.panel]))
        .child(div().flex_1().text_size(12).text_color(this.error ? t.blocked : t.muted).child(this.error ? `Couldn't read: ${this.error}` : ""))
        .child(h_flex().id("panel-close").h(24).px(10).items_center().rounded(5).border_1().border_color(t.input).bg(t.raised).text_size(12).text_color(t.foreground).cursor_pointer()
          .hover((s) => s.bg(t.selected)).on_click(() => closeOverlay(this.overlay)).child("Close")))
      .child(v_flex().id("panel-body").flex_1().min_h(0).overflow_y_scroll().pb(10).children(this[this.panel](t)));
  }
}
