// Status bar for the work: US market clock and the live SRW paper trader's /health, this Mac's load and the
// `heavy` queue and the mod error count.
// Read-only; each source polls on its own cadence.

import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { appHome, exec, home, nextCommand, openOverlay, theme } from "herdr";
import { readFile } from "fs/promises";

const SRW_HEALTH = "https://srw-telegram-paper-production.up.railway.app/health";
const HOLIDAYS = new Set([
  "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
  "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]);
const EARLY_CLOSE = new Set(["2026-11-27", "2026-12-24"]);
const OPEN = 570;
const POLL_LIMIT = 60000;
const WT_DIR = `${home()}/.local/state/herdr-worktrees`;
const WT_SCAN = `${appHome()}/mods/worktrees/scan.sh`;
const WT_EVERY = 600000;
const WT_HANG = 660000;
const WT_MAX_LOAD = 10;
const WT_FORCE_AFTER = 1800000;
const WT_LAST = `${WT_DIR}/last.json`;
const T3_CREDENTIALS = `${home()}/.config/t3mcp/credentials.json`;
const T3_EVERY = 600000;
const T3_WARN = 3 * 86400000;
const CLAUDE_USAGE = `${home()}/.claude/plugins/claude-hud/.usage-cache.json`;
const CLAUDE_FIVE_HOUR = 5 * 3600000;
const CLAUDE_WEEK = 7 * 86400000;
const CLAUDE_STALE_MS = 600000;
const MMX_ENV = ["PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "mmx", "quota", "show", "--output", "json", "--non-interactive"];
const USAGE_EVERY = 60000;
const PACE_SLACK = 5;
const MEM_EVERY = 30000;
const MEM_LOW = 15;
const MEM_PANEL = [560, 520];
const HERDR_APP = `${home()}/.local/bin/herdr-app`;
const ERRORS_EVERY = 30000;
const ERRORS_PANEL = [640, 440];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LOGIN_ERROR = /log in|cookie|unauthori[sz]ed/i;

const sunday = (year, month, nth) => 1 + ((7 - new Date(Date.UTC(year, month, 1)).getUTCDay()) % 7) + 7 * (nth - 1);

function newYork(ms) {
  const year = new Date(ms).getUTCFullYear();
  const dst = ms >= Date.UTC(year, 2, sunday(year, 2, 2), 7) && ms < Date.UTC(year, 10, sunday(year, 10, 1), 6);
  const d = new Date(ms - (dst ? 4 : 5) * 3600000);
  return { day: d.getUTCDay(), minutes: d.getUTCHours() * 60 + d.getUTCMinutes(), date: d.toISOString().slice(0, 10), ms: d.getTime() };
}

const readJson = (path) => readFile(path, "utf8").then(JSON.parse).catch(() => null);

const usageColor = (t, used) => (used > 80 ? t.blocked : used >= 50 ? t.working : t.done);

function srwStatus(srw) {
  if (!srw) return { level: "blocked", detail: "unreachable", tip: "GET /health failed" };
  const discord = srw.signalSource?.discord;
  const poll = srw.telegram?.pollHealth;
  const tip = [
    `heartbeat ${srw.heartbeat}`,
    `session ${srw.marketSession}`,
    discord ? `discord ${discord.state}` : `telegram ${poll?.state}`,
    discord && `queue ${discord.queueDepth}`,
    discord?.lastError && `last error ${discord.lastError}`,
    `jev ${srw.jev?.status}`,
  ].filter(Boolean).join(" · ");
  if (!srw.ok) return { level: "blocked", detail: "not ok", tip };
  if (srw.heartbeat !== "running") return { level: "blocked", detail: `heartbeat ${srw.heartbeat}`, tip };
  if (!discord) {
    if (!srw.ready || poll?.state !== "ok") return { level: "working", detail: `poll ${String(poll?.state).replaceAll("_", " ")}`, tip };
    return { level: "done", detail: `poll ${Math.round(poll.gapMs / 1000)}s`, tip };
  }
  const problem = !srw.ready ? "not ready"
    : discord.state !== "ready" ? `discord ${String(discord.state).replaceAll("_", " ")}`
    : !discord.connected ? "discord disconnected"
    : discord.inputBlocked ? "discord input blocked"
    : discord.queueOverflow ? "discord queue overflow"
    : discord.lastError ? "discord error"
    : null;
  return problem ? { level: "working", detail: problem, tip } : { level: "done", detail: "discord ready", tip };
}

function clockAt(ms) {
  const d = new Date(ms);
  const time = d.toTimeString().slice(0, 5);
  return ms - Date.now() > 18 * 3600000 ? `${WEEKDAYS[d.getDay()]} ${time}` : time;
}

function pace(w, now) {
  if (w.used === null || !(w.reset > now)) return null;
  const start = w.reset - w.span;
  const elapsed = Math.min(100, ((now - start) / w.span) * 100);
  const ahead = w.used > elapsed + PACE_SLACK;
  return { used: w.used, elapsed, ahead, reset: w.reset, runout: ahead ? start + ((now - start) * 100) / w.used : null };
}

const claudeWindow = (used, reset, span) => ({ used, reset: reset ? Date.parse(reset) : null, span });

const minimaxWindow = (remaining, start, end) => ({ used: 100 - remaining, reset: end, span: end - start });

const trading = (ny) => ny.day > 0 && ny.day < 6 && !HOLIDAYS.has(ny.date);
const span = (m) => (m >= 1440 ? `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h` : m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}` : `${m}m`);

function market(now) {
  const ny = newYork(now);
  const close = EARLY_CLOSE.has(ny.date) ? 780 : 960;
  if (trading(ny) && ny.minutes >= OPEN && ny.minutes < close) return { open: true, text: `open · closes in ${span(close - ny.minutes)}` };
  let ahead = trading(ny) && ny.minutes < OPEN ? 0 : 1;
  while (ahead && !trading(newYork(now + ahead * 86400000))) ahead++;
  return { open: false, text: `closed · opens in ${span(ahead * 1440 + OPEN - ny.minutes)}` };
}

export default class Ops extends View {
  init(_props, cx) {
    this.clock = Date.now();
    this.srw = null;
    this.heavy = null;
    this.wt = undefined;
    this.load = null;
    this.mem = null;
    this.claude = null;
    this.minimax = null;
    this.t3 = null;
    this.modErrors = null;
    this.at = {};
    this.busy = new Set();
    this.width = 1200;
    cx.timer.every(5000, (cx) => this.tick(cx));
    this.tick(cx);
    cx.spawn(async () => {
      for (;;) {
        if ((await nextCommand()) === "memory") this.openMemory();
      }
    });
  }

  openMemory() {
    openOverlay({ mod: "ops-panels", kind: "dialog", width: MEM_PANEL[0], height: MEM_PANEL[1], props: { panel: "memory", seed: { free: this.mem ?? undefined } } });
  }

  openErrors() {
    openOverlay({ mod: "ops-panels", kind: "dialog", width: ERRORS_PANEL[0], height: ERRORS_PANEL[1], props: { panel: "errors", seed: { errors: this.modErrors ?? undefined } } });
  }

  due(name, every) {
    if (Date.now() - (this.at[name] ?? 0) < every) return false;
    this.at[name] = Date.now();
    return true;
  }

  poll(cx, name, every, read) {
    if (this.busy.has(name) || !this.due(name, every)) return;
    this.busy.add(name);
    const limit = cx.timer.after(POLL_LIMIT, (cx) => {
      this[name] = null;
      cx.notify();
    });
    cx.spawn(async (cx) => {
      try {
        this[name] = await read();
      } finally {
        limit.cancel();
        this.busy.delete(name);
      }
      cx.notify();
    });
  }

  async readWorktrees() {
    try {
      const status = await readFile(`${WT_DIR}/status.json`, "utf8").then(JSON.parse, () => null);
      const now = Date.now();
      if (status?.state === "running" && now - status.at * 1000 <= WT_HANG) return { ...this.wt, scanning: true };
      const due = now - Math.max((status?.finished ?? 0) * 1000, this.wtTried ?? 0) >= WT_EVERY;
      const lastGood = await exec("stat", ["-f", "%m", WT_LAST]);
      const overdue = now - (lastGood.code === 0 ? Number(lastGood.stdout) * 1000 : 0) > WT_FORCE_AFTER;
      if (due && (overdue || (this.load !== null && this.load < WT_MAX_LOAD))) {
        this.wtTried = now;
        const r = await exec("nice", ["-n", "10", "sh", WT_SCAN, "scan"]);
        return r.code === 0 && r.stdout.trim() === "started" ? { ...this.wt, scanning: true } : null;
      }
      return status?.state === "done" ? { finished: status.finished } : due ? this.wt : null;
    } catch {
      return null;
    }
  }

  tick(cx) {
    this.clock = Date.now();
    this.poll(cx, "srw", market(this.clock).open ? 30000 : 300000, () => fetch(SRW_HEALTH).then((r) => r.json(), () => null));
    this.poll(cx, "heavy", 15000, async () => {
      const r = await exec("heavy", ["status"]);
      return r.code === 0 ? JSON.parse(r.stdout) : null;
    });
    this.poll(cx, "load", 10000, async () => {
      const r = await exec("sysctl", ["-n", "vm.loadavg"]).catch(() => null);
      return r && r.code === 0 ? Number(r.stdout.replace(/[{}]/g, "").trim().split(/\s+/)[0]) : null;
    });
    this.poll(cx, "mem", MEM_EVERY, async () => {
      const r = await exec("memory_pressure", [], { timeout: 10000 }).catch(() => null);
      const free = r && r.code === 0 ? /free percentage: (\d+)%/.exec(r.stdout) : null;
      return free ? Number(free[1]) : null;
    });
    this.poll(cx, "modErrors", ERRORS_EVERY, async () => {
      const r = await exec(HERDR_APP, ["status"]).catch(() => null);
      return r && r.code === 0 ? JSON.parse(r.stdout).errors : null;
    });
    this.poll(cx, "claude", USAGE_EVERY, async () => {
      const cache = await readJson(CLAUDE_USAGE);
      if (!cache || cache.data.apiUnavailable) return null;
      const { data, timestamp } = cache;
      return {
        at: timestamp,
        windows: [
          ["5h", claudeWindow(data.fiveHour, data.fiveHourResetAt, CLAUDE_FIVE_HOUR)],
          ["wk", claudeWindow(data.sevenDay, data.sevenDayResetAt, CLAUDE_WEEK)],
        ],
      };
    });
    this.poll(cx, "minimax", USAGE_EVERY, async () => {
      const r = await exec("/usr/bin/env", MMX_ENV, { timeout: 20000 }).catch(() => null);
      if (r && r.code !== 0 && LOGIN_ERROR.test(r.stderr + r.stdout)) return { at: Date.now(), login: true, windows: [] };
      const plan = r && r.code === 0 ? JSON.parse(r.stdout).model_remains.find((m) => m.model_name === "general") : null;
      return plan && {
        at: Date.now(),
        windows: [
          [`${(plan.end_time - plan.start_time) / 3600000}h`, minimaxWindow(plan.current_interval_remaining_percent, plan.start_time, plan.end_time)],
          ["wk", minimaxWindow(plan.current_weekly_remaining_percent, plan.weekly_start_time, plan.weekly_end_time)],
        ],
      };
    });
    this.poll(cx, "t3", T3_EVERY, async () => {
      const credentials = await readJson(T3_CREDENTIALS);
      return credentials && { expires: Number(credentials.expires_at) * 1000 };
    });
    this.poll(cx, "wt", this.wt?.scanning ? 4000 : 30000, () => this.readWorktrees());
    cx.notify();
  }

  render() {
    const t = theme();
    const now = market(this.clock);
    const item = (color, label, detail, tip) => {
      const el = h_flex().gap(6).items_center().flex_none()
        .child(div().size(6).rounded(3).bg(color))
        .child(div().text_color(t.foreground).font_medium().child(label))
        .child(div().text_color(t.muted).child(detail));
      return tip ? el.tooltip(tip) : el;
    };
    const plain = (label, detail, color, tip) => {
      const el = h_flex().gap(5).items_center().flex_none()
        .child(div().text_color(t.dim).child(label))
        .child(div().text_color(color ?? t.muted).font_medium().child(detail));
      return tip ? el.tooltip(tip) : el;
    };

    const usage = (label, source) => {
      if (!source) return null;
      if (source.login) return plain(`${label}:`, "log in again", t.working, "MiniMax session expired. Run `mmx auth login` in a terminal.");
      const paced = source.windows.map(([name, w]) => [name, w.used === null ? "n/a" : pace(w, this.clock)]).filter(([, p]) => p);
      if (!paced.length) return null;
      const stale = Date.now() - source.at > CLAUDE_STALE_MS;
      const el = h_flex().gap(5).items_center().flex_none().child(div().text_color(t.dim).child(label));
      paced.forEach(([name, p], i) => {
        if (p === "n/a") {
          if (i) el.child(div().text_color(t.dim).child("·"));
          el.child(div().text_color(t.dim).font_medium().child(`${name} n/a`).tooltip(`No ${name} usage figure in the cache${stale ? `, last refreshed ${clockAt(source.at)}` : ""}.`));
          return;
        }
        const text = `${name} ${Math.round(p.used)}%${p.ahead ? " ▲" : ""}`;
        const detail = p.ahead ? `At this pace you run out before the window resets at ${clockAt(p.reset)}, around ${clockAt(p.runout)}. ${Math.round(p.used)}% used, ${Math.round(p.elapsed)}% of the window gone.`
          : `${Math.round(p.used)}% used, ${Math.round(p.elapsed)}% of the window gone. Resets ${clockAt(p.reset)}.`;
        if (i) el.child(div().text_color(t.dim).child("·"));
        el.child(div().text_color(stale ? t.dim : usageColor(t, p.used)).font_medium().child(text).tooltip(stale ? `Cache last refreshed ${clockAt(source.at)}. ${detail}` : detail));
      });
      return el;
    };

    const memEl = this.mem === null ? null : h_flex().id("mem").gap(5).items_center().flex_none().cursor_pointer()
      .on_click((e) => e.click_count > 1 || this.openMemory())
      .tooltip("Free memory. Click to see which agent processes use the most.")
      .child(div().text_color(t.dim).child("mem"))
      .child(div().text_color(this.mem < MEM_LOW ? t.blocked : t.muted).font_medium().child(`${this.mem}% free`));

    const errors = this.modErrors ?? [];
    const errorEl = errors.length === 0 ? null : h_flex().id("mod-errors").gap(6).items_center().flex_none().cursor_pointer()
      .on_click((e) => e.click_count > 1 || this.openErrors())
      .tooltip(`${errors.length === 1 ? "A mod failed" : "Mods failed"} to load or reload, so the old version may still be running. Click for the error text.`)
      .child(div().size(6).rounded(3).bg(t.blocked))
      .child(div().text_color(t.blocked).font_medium().child(`${errors.length} mod error${errors.length === 1 ? "" : "s"}`))
      .child(div().text_color(t.muted).child(/^mod (\S+?):/.exec(errors[0])?.[1] ?? "app"));

    const t3Left = this.t3 === null ? Infinity : this.t3.expires - Date.now();
    const t3Date = this.t3 === null ? "" : `${MONTHS[new Date(this.t3.expires).getMonth()]} ${new Date(this.t3.expires).getDate()}`;
    const t3El = t3Left > T3_WARN ? null : plain("T3", t3Left <= 0 ? `login expired ${t3Date}` : `login expires ${t3Date}`, t3Left <= 0 ? t.blocked : t.working, "run t3mcp login");

    const srw = this.srw;
    const { level: srwLevel, detail: srwDetail, tip: srwTip } = srwStatus(srw);
    const srwColor = t[srwLevel];

    const h = this.heavy;
    const running = h?.jobs.filter((j) => j.state === "running").length ?? 0;
    const paused = h?.jobs.filter((j) => j.state === "paused").length ?? 0;
    const queued = h?.queue.length ?? 0;
    const heavyColor = paused > 0 ? t.working : t.muted;

    const roomy = this.width >= 1280;
    const tight = this.width >= 980;
    return h_flex().size_full().px(10).gap(roomy ? 12 : 9).items_center().bg(t.chrome).border_t(1).border_color(t.border).text_size(11).overflow_hidden()
      .on_size_change((size, cx) => {
        if (Math.abs(size.width - this.width) < 1) return;
        this.width = size.width;
        cx.notify();
      })
      .child(item(now.open ? t.done : t.dim, "NYSE", now.text))
      .when(errorEl !== null, (el) => el.child(errorEl))
      .child(item(srwColor, "SRW", srwDetail, srwTip))
      .when(this.load !== null && roomy, (el) => el.child(plain("M4", `load ${this.load.toFixed(2)}`, t.muted, "load average, 1 minute")))
      .when(tight, (el) => el.child(plain("heavy", h ? ([running && `${running} run`, paused && `${paused} paused`, queued && `${queued} queued`].filter(Boolean).join(" · ") || "idle") : "n/a", heavyColor, "mac-ops heavy status")))
      .when(t3El !== null, (el) => el.child(t3El))
      .when(memEl !== null, (el) => el.child(memEl))
      .when(tight && this.claude !== null, (el) => el.child(usage("Claude", this.claude)))
      .when(roomy && this.minimax !== null, (el) => el.child(usage("MiniMax", this.minimax)))
      .child(div().flex_1());
  }
}
