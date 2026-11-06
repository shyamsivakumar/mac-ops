// Read-only pop-ups opened from the cockpit toolbar: model providers, the task queue and hub health.

import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { closeOverlay, exec, home, notify, props, readTextFile, theme } from "herdr";

const EMP = `${home()}/.local/bin/emp`;
const EMPQ = `${home()}/.local/bin/empq`;
const HEALTH_FILE = `${home()}/Code/coordinator/queue/health.json`;
const EMPRYO_CONFIG = `${home()}/.empryo/config.json`;
const HUB_LOG = `${home()}/.empryo-hub/hub.log`;
const HUB_LOG_LINES = "4000";
const HOLD_MS = 15 * 60000;
const CIRCUIT_LINE = /^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) circuit for (\S+) (?:OPEN for \d+ min after \d+ failures|reopened after a failed probe) \((.*)\)$/;
const FALLBACK_ONLY = /^(?:Falling back to|Switched to fallback model)/i;
const PROVIDERS = [["zai-coding-plan", "GLM"], ["minimax", "MiniMax"], ["subscriptions/gpt", "GPT"], ["subscriptions/cursor", "Cursor"], ["subscriptions/claude", "Claude"]];
const TITLES = { models: "Models", queue: "Queue", hub: "Hub" };
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

const since = (ms) => `${span(Date.now() - ms)} ago`;
const until = (ms) => (ms > Date.now() ? `in ${span(ms - Date.now())}` : "now");
const epoch = (value) => (typeof value === "number" ? value : Date.parse(value));

function lastReasons(logText) {
  const reasons = {};
  for (const line of logText.split("\n")) {
    const m = CIRCUIT_LINE.exec(line);
    if (m) reasons[m[2]] = { at: Date.parse(m[1].replace(" ", "T")), text: m[3] };
  }
  return reasons;
}

function circuitLine(c) {
  if (c.state === "closed") return { text: "up", tone: "done" };
  const failures = c.recentFailures ? ` · ${plural(c.recentFailures, "recent failure")}` : "";
  const failedAt = c.openUntil ? epoch(c.openUntil) - HOLD_MS : null;
  if (c.state === "open") return { text: `out · ${c.openUntil ? `retries ${until(epoch(c.openUntil))}` : "retry time unknown"}${failures}`, tone: "blocked" };
  if (c.probing) return { text: "trying now", tone: "working" };
  return { text: `waiting to retry${failedAt ? ` · last failed ${since(failedAt)}` : ""} · next task will try it`, tone: "muted" };
}

function reasonNote(reason) {
  if (!reason) return "The hub log has no failure recorded for this provider.";
  const when = Number.isNaN(reason.at) ? "" : ` (${since(reason.at)})`;
  const text = reason.text.replace(/\x1b\[[0-?]*[ -\/]*[@-~]/g, "").replace(/[\x00-\x1f\x7f\s]+/g, " ").trim();
  return FALLBACK_ONLY.test(text) ? `The hub logged only a fallback switch, not the provider's own error${when}.` : `Last logged: ${text}${when}`;
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
    cx.spawn(async (cx) => {
      try {
        this.data = await this[`read_${this.panel}`]();
      } catch (error) {
        this.error = error.message;
      }
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
    const [status, config, log] = await Promise.all([this.hubStatus(), this.readFile(EMPRYO_CONFIG), exec("tail", ["-n", HUB_LOG_LINES, HUB_LOG])]);
    return { circuits: status.circuits, fallback: config.modelFallback, reasons: log.code === 0 ? lastReasons(log.stdout) : {} };
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
      return c.state !== "closed" && this.data ? [row, this.note(t, reasonNote(this.data.reasons[id]))] : [row];
    });
    const fallback = Object.entries(this.data?.fallback ?? {}).map(([primary, chain]) => h_flex().w_full().px(14).py(3).gap(6).flex_wrap().items_baseline()
      .children([primary, ...chain].flatMap((model, i) => [
        ...(i ? [div().text_size(11).text_color(t.dim).child("→")] : []),
        div().text_size(12).font_medium().text_color(out.has(providerOf(model)) ? t.blocked : i ? t.muted : t.foreground).child(short(model)),
      ])));
    return [this.section(t, "Providers"), ...rows, this.section(t, "Fallback order, first choice then what it falls back to"), ...(this.data ? fallback : [this.note(t, "Loading the fallback order…")])];
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
