// Status bar for the work: US market clock and the live SRW paper trader's /health, this Mac's load and the
// `heavy` queue, the Empryo hub (socket and launchd job) and the mod error count.
// Read-only; each source polls on its own cadence.

import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { appHome, exec, home, nextCommand, notify, openOverlay, setShared, shared, theme } from "herdr";
import { readFile } from "fs/promises";

const SRW_HEALTH = "https://srw-telegram-paper-production.up.railway.app/health";
const HOLIDAYS = new Set([
  "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
  "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]);
const EARLY_CLOSE = new Set(["2026-11-27", "2026-12-24"]);
const OPEN = 570;
const HUB_LIVE = ["preparing", "queued", "starting", "running", "waiting"];
const HUB_CAP = 6;
const HEALTH_FILE = `${home()}/Code/coordinator/queue/health.json`;
const HEALTH_STALE_MS = 300000;
const POLL_LIMIT = 60000;
const WT_DIR = `${home()}/.local/state/herdr-worktrees`;
const WT_SCAN = `${appHome()}/mods/worktrees/scan.sh`;
const WT_EVERY = 600000;
const WT_HANG = 660000;
const WT_MAX_LOAD = 10;
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
const HUB_JOB = "dev.coordinator.emp-hub";
const HUB_PROBE = `test -S "$1" && echo socket=up || echo socket=missing; launchctl print gui/$(id -u)/${HUB_JOB} 2>&1`;
const HUB_RESTART = `launchctl kickstart -k gui/$(id -u)/${HUB_JOB}`;
const HUB_HEALTH_EVERY = 15000;
const HUB_STALE_MS = 120000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const healthStale = (hl) => !hl || Date.now() - hl.checked_at * 1000 > HEALTH_STALE_MS;

const sunday = (year, month, nth) => 1 + ((7 - new Date(Date.UTC(year, month, 1)).getUTCDay()) % 7) + 7 * (nth - 1);

function newYork(ms) {
  const year = new Date(ms).getUTCFullYear();
  const dst = ms >= Date.UTC(year, 2, sunday(year, 2, 2), 7) && ms < Date.UTC(year, 10, sunday(year, 10, 1), 6);
  const d = new Date(ms - (dst ? 4 : 5) * 3600000);
  return { day: d.getUTCDay(), minutes: d.getUTCHours() * 60 + d.getUTCMinutes(), date: d.toISOString().slice(0, 10), ms: d.getTime() };
}

const readJson = (path) => readFile(path, "utf8").then(JSON.parse).catch(() => null);

const usageColor = (t, used) => (used > 80 ? t.blocked : used >= 50 ? t.working : t.done);

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
    this.hub = null;
    this.health = undefined;
    this.wt = undefined;
    this.load = null;
    this.mem = null;
    this.claude = null;
    this.minimax = null;
    this.modErrors = null;
    this.hubHealth = null;
    this.at = {};
    this.published = "";
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
      if (name === "health") this.publish();
      cx.notify();
    });
  }

  publish() {
    const hl = this.health;
    const payload = {
      health: hl === undefined ? undefined : { stale: healthStale(hl), problems: hl?.problems ?? [], warnings: hl?.warnings ?? [] },
    };
    const stamp = JSON.stringify(payload);
    if (stamp === this.published) return;
    this.published = stamp;
    setShared("ops", payload);
  }

  async readWorktrees() {
    try {
      const status = await readFile(`${WT_DIR}/status.json`, "utf8").then(JSON.parse, () => null);
      const now = Date.now();
      if (status?.state === "running" && now - status.at * 1000 <= WT_HANG) return { ...this.wt, scanning: true };
      const due = now - Math.max((status?.finished ?? 0) * 1000, this.wtTried ?? 0) >= WT_EVERY;
      if (due && this.load !== null && this.load < WT_MAX_LOAD) {
        this.wtTried = now;
        const r = await exec("sh", [WT_SCAN, "scan"]);
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
    const board = shared("hub");
    if (board && Date.now() - board.at < 30000) this.hub = board;
    else {
      this.poll(cx, "hub", 15000, async () => {
        const r = await exec(`${home()}/.local/bin/emp`, ["call", "emp_thread_list", JSON.stringify({ allProjects: true, limit: 100, statuses: HUB_LIVE })]).catch(() => null);
        const threads = r && r.code === 0 ? JSON.parse(r.stdout).threads : null;
        return threads && {
          running: threads.filter((t) => t.status !== "waiting").length,
          waiting: threads.filter((t) => t.status === "waiting").length,
          at: Date.now(),
        };
      });
    }
    this.poll(cx, "mem", MEM_EVERY, async () => {
      const r = await exec("memory_pressure", [], { timeout: 10000 }).catch(() => null);
      const free = r && r.code === 0 ? /free percentage: (\d+)%/.exec(r.stdout) : null;
      return free ? Number(free[1]) : null;
    });
    this.poll(cx, "modErrors", ERRORS_EVERY, async () => {
      const r = await exec(HERDR_APP, ["status"]).catch(() => null);
      return r && r.code === 0 ? JSON.parse(r.stdout).errors : null;
    });
    this.poll(cx, "hubHealth", HUB_HEALTH_EVERY, async () => {
      const r = await exec("sh", ["-c", HUB_PROBE, "sh", `${home()}/.empryo-hub/hub.sock`]).catch(() => null);
      const board = shared("hub");
      return r && {
        socket: r.stdout.startsWith("socket=up"),
        state: /^\tstate = (\S+)/m.exec(r.stdout)?.[1] ?? "not loaded",
        pid: /^\tpid = (\d+)/m.exec(r.stdout)?.[1],
        board: board && { at: board.at, running: board.running },
      };
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
      const plan = r && r.code === 0 ? JSON.parse(r.stdout).model_remains.find((m) => m.model_name === "general") : null;
      return plan && {
        at: Date.now(),
        windows: [
          [`${(plan.end_time - plan.start_time) / 3600000}h`, minimaxWindow(plan.current_interval_remaining_percent, plan.start_time, plan.end_time)],
          ["wk", minimaxWindow(plan.current_weekly_remaining_percent, plan.weekly_start_time, plan.weekly_end_time)],
        ],
      };
    });
    this.poll(cx, "wt", this.wt?.scanning ? 4000 : 30000, () => this.readWorktrees());
    this.poll(cx, "health", 30000, () => readFile(HEALTH_FILE, "utf8").then(JSON.parse, () => null));
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
      const paced = source.windows.map(([name, w]) => [name, pace(w, this.clock)]).filter(([, p]) => p);
      if (!paced.length) return null;
      const stale = Date.now() - source.at > CLAUDE_STALE_MS;
      const el = h_flex().gap(5).items_center().flex_none().child(div().text_color(t.dim).child(label));
      paced.forEach(([name, p], i) => {
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

    const hh = this.hubHealth;
    const readAge = hh?.board ? Date.now() - hh.board.at : null;
    const hubDown = hh && (hh.state !== "running" || !hh.socket);
    const hubStale = hh && !hubDown && readAge !== null && readAge > HUB_STALE_MS;
    const hubReasons = hh ? [hh.state !== "running" && `the launchd job is ${hh.state}`, !hh.socket && "hub.sock is missing"].filter(Boolean) : [];
    const hubEl = !hh ? null : hubDown
      ? item(t.blocked, "hub down", hh.state !== "running" ? hh.state : "no socket", `Hub down: ${hubReasons.join(" and ")}. Restart with: ${HUB_RESTART}`)
      : hubStale
        ? item(t.working, "hub stale", `read ${span(Math.round(readAge / 60000))} ago`, `The cockpit's last hub read was ${span(Math.round(readAge / 60000))} ago (limit 2m). The launchd job is running (pid ${hh.pid}) and hub.sock exists, so the hub may be hung or the cockpit stopped polling. Restart with: ${HUB_RESTART}`)
        : item(t.done, "hub", "", `The launchd job is running (pid ${hh.pid}) and hub.sock exists${readAge === null ? "" : `. The cockpit read the hub ${Math.round(readAge / 1000)}s ago`}.`);

    const srw = this.srw;
    const poll = srw?.telegram?.pollHealth;
    const srwOk = srw?.ok && srw.ready && poll?.state === "ok";
    const srwColor = !srw || !srw.ok ? t.blocked : srwOk ? t.done : t.working;
    const srwDetail = !srw ? "unreachable" : !srw.ok ? "not ok" : srw.heartbeat !== "running" ? srw.heartbeat : poll?.state !== "ok" ? `poll ${poll.state.replaceAll("_", " ")}` : `poll ${Math.round(poll.gapMs / 1000)}s`;
    const srwTip = srw ? `heartbeat ${srw.heartbeat} · session ${srw.marketSession} · telegram ${poll?.state} · discord ${srw.signalSource?.discord?.state} · jev ${srw.jev?.status}` : "GET /health failed";

    const h = this.heavy;
    const running = h?.jobs.filter((j) => j.state === "running").length ?? 0;
    const paused = h?.jobs.filter((j) => j.state === "paused").length ?? 0;
    const queued = h?.queue.length ?? 0;
    const heavyColor = paused > 0 ? t.working : t.muted;

    const b = this.hub;
    const hubColor = !b ? t.dim : b.waiting ? t.blocked : b.running ? t.working : t.muted;

    const hl = this.health;
    const stale = healthStale(hl);
    const issues = stale ? ["health check not running"] : [...hl.problems, ...hl.warnings];
    const healthColor = stale || hl.problems.length ? t.blocked : hl.warnings.length ? t.working : t.done;
    const healthEl = h_flex().id("health").gap(6).items_center().flex_none().cursor_pointer()
      .on_click(() => notify({ title: issues.length ? "Hub health" : "Hub health: all clear", body: issues.join("\n"), level: healthColor === t.blocked ? "error" : issues.length ? "warning" : "success" }))
      .tooltip(issues.length ? issues.join(" · ") : "Empryo hub, Coordinator, dispatcher: all ok")
      .child(div().size(6).rounded(3).bg(healthColor))
      .child(div().text_color(issues.length ? healthColor : t.foreground).font_medium().child(issues[0] ?? "health"));

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
      .child(plain("Tasks", b ? `${b.running}/${HUB_CAP} run${b.waiting ? ` · ${b.waiting} waiting` : ""}` : "n/a", hubColor, "Empryo tasks running (cap 6) and waiting for you"))
      .child(healthEl)
      .when(hubEl !== null && (roomy || hubDown || hubStale), (el) => el.child(hubEl))
      .child(item(srwColor, "SRW", srwDetail, srwTip))
      .when(this.load !== null && roomy, (el) => el.child(plain("M4", `load ${this.load.toFixed(2)}`, t.muted, "load average, 1 minute")))
      .when(tight, (el) => el.child(plain("heavy", h ? ([running && `${running} run`, paused && `${paused} paused`, queued && `${queued} queued`].filter(Boolean).join(" · ") || "idle") : "n/a", heavyColor, "mac-ops heavy status")))
      .when(memEl !== null, (el) => el.child(memEl))
      .when(tight && this.claude !== null, (el) => el.child(usage("Claude", this.claude)))
      .when(roomy && this.minimax !== null, (el) => el.child(usage("MiniMax", this.minimax)))
      .child(div().flex_1());
  }
}
