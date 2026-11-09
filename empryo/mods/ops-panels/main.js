// Read-only pop-ups: model providers, the task queue and hub health (cockpit toolbar), memory (status bar).

import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { closeOverlay, exec, home, notify, props, readTextFile, theme } from "herdr";

const EMP = `${home()}/.local/bin/emp`;
const EMPQ = `${home()}/.local/bin/empq`;
const HEALTH_FILE = `${home()}/Code/coordinator/queue/health.json`;
const EMPRYO_CONFIG = `${home()}/.empryo/config.json`;
const HOLD_MS = 15 * 60000;
const PROVIDERS = [["zai-coding-plan", "GLM"], ["minimax", "MiniMax"], ["subscriptions/gpt", "GPT"], ["subscriptions/cursor", "Cursor"], ["subscriptions/claude", "Claude"]];
const TITLES = { models: "Models", queue: "Queue", hub: "Hub", memory: "Memory" };
const MEM_REFRESH = 10000;
const MEM_ROWS = 14;
const PS_LINE = /^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/;
const AGENT_KINDS = [["Claude", /(^|\/)claude(\s|$)/], ["Codex", /(^|\/)codex(\s|$)/]];
const RUNTIME_KINDS = [["node", /(^|\/)node(\s|$)/], ["python", /(^|\/)[Pp]ython[\d.]*(\s|$)/]];
const QUEUE_LINE = /^#(\d+) p(\d+) (\S+) (.*?)(?: \(failed (\d+)x\))?$/;

const stamp = (ms) => (ms ? `${new Date(ms).toTimeString().slice(0, 5)}` : "");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const providerName = (key) => PROVIDERS.find(([id]) => id === key)?.[1] ?? key;
const short = (model) => model.replace(/^(zai-coding-plan|subscriptions)\//, "");

function providerOf(model) {
  const known = PROVIDERS.find(([id]) => model.startsWith(`${id}/`) || model.startsWith(`${id}-`));
  return known?.[0] ?? null;
}

function span(ms) {
  const m = Math.max(0, Math.floor(ms / 60000));
  return m < 1 ? "under a minute" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`;
}

const gigabytes = (kb) => `${(kb / 1048576).toFixed(1)} GB`;
const megabytes = (kb) => (kb >= 1048576 ? gigabytes(kb) : `${Math.round(kb / 1024)} MB`);
const kindOf = (kinds, command) => kinds.find(([, pattern]) => pattern.test(command))?.[0] ?? null;
const since = (ms) => `${span(Date.now() - ms)} ago`;
const until = (ms) => (ms > Date.now() ? `in ${span(ms - Date.now())}` : "now");
const epoch = (value) => (typeof value === "number" ? value : Date.parse(value));

function circuitLine(c) {
  if (c.state === "closed") return { text: "up", tone: "done" };
  const failures = c.recentFailures ? ` · ${plural(c.recentFailures, "recent failure")}` : "";
  const failedAt = c.openUntil ? epoch(c.openUntil) - HOLD_MS : null;
  if (c.state === "open") return { text: `out · ${c.openUntil ? `retries ${until(epoch(c.openUntil))}` : "retry time unknown"}${failures}`, tone: "blocked" };
  if (c.probing) return { text: "trying now", tone: "working" };
  return { text: `waiting to retry${failedAt ? ` · last failed ${since(failedAt)}` : ""} · next task will try it`, tone: "muted" };
}

function reasonNote(c) {
  if (c.lastError === undefined) return "Restart the hub to see provider errors (emp drain --restart).";
  if (c.lastError === null) return "The hub saw a fallback switch but no provider error text.";
  return `Last error: ${c.lastError} (${since(Date.parse(c.lastErrorAt))})`;
}

export default class Panels extends View {
  init(_props, cx) {
    const p = props() ?? {};
    this.overlay = p.overlay ?? null;
    this.panel = p.panel ?? "models";
    this.seed = p.seed ?? {};
    this.data = null;
    this.error = null;
    this.busy = false;
    this.handle = cx.focus_handle();
    cx.timer.after(60, () => this.handle.focus());
    this.load(cx);
    if (this.panel === "memory") cx.timer.every(MEM_REFRESH, (cx) => this.load(cx));
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

  hubStatus() {
    return this.json(EMP, ["call", "emp_hub_status", "{}"]);
  }

  async read_models() {
    const [status, config] = await Promise.all([this.hubStatus(), this.readFile(EMPRYO_CONFIG)]);
    return { circuits: status.circuits, fallback: config.modelFallback };
  }

  async read_queue() {
    const [status, list, health] = await Promise.all([this.json(EMPQ, ["status"]), exec(EMPQ, ["list"]), this.readFile(HEALTH_FILE)]);
    if (list.code !== 0) throw new Error(list.stderr.trim() || "empq list failed");
    const items = list.stdout.split("\n").filter(Boolean).map((line) => {
      const m = QUEUE_LINE.exec(line);
      return m ? { id: m[1], priority: m[2], tool: m[3], title: m[4], attempts: Number(m[5] ?? 0) } : { id: "?", priority: "?", tool: "", title: line, attempts: 0 };
    });
    return { ...status, items, dispatched: health?.dispatcher_last_run };
  }

  async read_hub() {
    const [health, status] = await Promise.all([this.readFile(HEALTH_FILE), this.hubStatus()]);
    const ps = await exec("ps", ["-o", "lstart=", "-p", String(status.pid)]);
    return { health, draining: status.draining, pid: status.pid, started: ps.code === 0 ? Date.parse(ps.stdout.trim()) : null };
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

  cancelDrain(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.notify();
    cx.spawn(async (cx) => {
      let cancelled = false;
      try {
        const r = await exec(EMP, ["drain", "--cancel"]);
        if (r.code !== 0) throw new Error(r.stderr.trim() || "emp drain --cancel failed");
        cancelled = true;
        this.data = await this.read_hub();
        notify({ title: "Drain cancelled", level: "success", timeout: 2500 });
      } catch (error) {
        if (cancelled) notify({ title: "Drain cancelled, but the panel could not refresh", body: error.message, level: "warning" });
        else notify({ title: "Could not cancel the drain", body: error.message, level: "error" });
      }
      this.busy = false;
      cx.notify();
    });
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

  models(t) {
    const circuits = this.data?.circuits ?? this.seed.hub?.circuits;
    if (!circuits) return [this.note(t, "Provider status is not available yet.")];
    const out = new Set(Object.entries(circuits).filter(([, c]) => c.state === "open").map(([key]) => key));
    const rows = [...PROVIDERS.map(([id]) => id), ...Object.keys(circuits).filter((id) => !PROVIDERS.some(([known]) => known === id))].filter((id) => circuits[id]).flatMap((id) => {
      const c = circuits[id];
      const { text, tone } = circuitLine(c);
      const row = this.line(t, providerName(id), text, tone);
      return c.state !== "closed" ? [row, this.note(t, reasonNote(c))] : [row];
    });
    const fallback = Object.entries(this.data?.fallback ?? {}).map(([primary, chain]) => h_flex().w_full().px(14).py(3).gap(6).flex_wrap().items_baseline()
      .children([primary, ...chain].flatMap((model, i) => [
        ...(i ? [div().text_size(11).text_color(t.dim).child("→")] : []),
        div().text_size(12).font_medium().text_color(out.has(providerOf(model)) ? t.blocked : i ? t.muted : t.foreground).child(short(model)),
      ])));
    return [this.section(t, "Providers"), ...rows, this.section(t, "Fallback order, first choice then what it falls back to"), ...(this.data ? fallback : [this.note(t, "Loading the fallback order…")])];
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
    const why = (i) => (i.attempts ? `Failed ${plural(i.attempts, "time")}. The dispatcher retries it, up to 3 attempts.` : full ? `Waiting for a free slot. ${d.live} of ${d.cap} are running.` : `Waiting for the next dispatcher run${d.dispatched ? `, last ran ${since(Date.parse(d.dispatched))}` : ""}.`);
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

  hub(t) {
    const d = this.data;
    const health = d?.health;
    const problems = health?.problems ?? this.seed.health?.problems ?? [];
    const warnings = health?.warnings ?? this.seed.health?.warnings ?? [];
    const tokens = health?.coordinator?.context_tokens;
    const draining = d ? d.draining : this.seed.hub?.draining;
    const lines = [
      this.section(t, "Health"),
      ...(health ? [this.line(t, "Last check", since(health.checked_at * 1000), Date.now() - health.checked_at * 1000 > 300000 ? "working" : undefined)] : []),
      ...problems.map((p) => this.note(t, p, "blocked")),
      ...warnings.map((w) => this.note(t, w, "working")),
      ...(problems.length + warnings.length ? [] : [this.note(t, "No problems or warnings.", "done")]),
      this.section(t, "Coordinator"),
      this.line(t, "Context", tokens ? `Coordinator ${Math.round(tokens / 1000)}k tokens` : "unknown"),
      ...(health?.coordinator ? [this.line(t, "State", `${health.coordinator.status} · terminal ${health.coordinator.terminal}`)] : []),
      this.section(t, "Hub"),
      ...(d?.started ? [this.line(t, "Uptime", span(Date.now() - d.started)), this.line(t, "Last restart", `${stamp(d.started)}, ${since(d.started)}`)] : [this.note(t, d ? "Start time not available." : "Loading…")]),
      ...(health ? [this.line(t, "Running", `${health.running} of ${health.cap}`), this.line(t, "Waiting in queue", String(health.queue)), this.line(t, "Dispatcher", `last ran ${since(Date.parse(health.dispatcher_last_run))}`)] : []),
      this.line(t, "Drain", draining ? "Draining. New work is held until it ends." : "Not draining", draining ? "working" : undefined),
    ];
    if (draining && d) {
      lines.push(h_flex().w_full().px(14).pt(8).child(h_flex().id("cancel-drain").h(28).px(12).items_center().rounded(6).bg(t.solid).text_color(t.solid_foreground).text_size(12).font_semibold()
        .opacity(this.busy ? 0.5 : 1).cursor_pointer().on_click((e, cx) => e.click_count > 1 || this.cancelDrain(cx)).child(this.busy ? "Cancelling…" : "Cancel drain")));
    }
    return lines;
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
