// Status bar for the work: US market clock and the live SRW paper trader's /health, this Mac's load and the
// `heavy` queue, the M1 Woodpecker runners. Read-only; each source polls on its own cadence.

import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { exec, home, notify, shared, theme } from "herdr";
import { readFile } from "fs/promises";

const SRW_HEALTH = "https://srw-telegram-paper-production.up.railway.app/health";
const M1_PROBE = [
  'export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"',
  'n=$(pgrep -fl "woodpecker-local-[0-9]+/workspace" | grep -o "woodpecker-local-[0-9]*" | sort -u | wc -l)',
  'd=$(docker --context colima-woodpecker ps --format "{{.Image}}" 2>/dev/null | grep -vc "^local/woodpecker")',
  'echo $n $d $(sysctl -n vm.loadavg | tr -d "{}")',
].join("; ");
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

const sunday = (year, month, nth) => 1 + ((7 - new Date(Date.UTC(year, month, 1)).getUTCDay()) % 7) + 7 * (nth - 1);

function newYork(ms) {
  const year = new Date(ms).getUTCFullYear();
  const dst = ms >= Date.UTC(year, 2, sunday(year, 2, 2), 7) && ms < Date.UTC(year, 10, sunday(year, 10, 1), 6);
  const d = new Date(ms - (dst ? 4 : 5) * 3600000);
  return { day: d.getUTCDay(), minutes: d.getUTCHours() * 60 + d.getUTCMinutes(), date: d.toISOString().slice(0, 10), ms: d.getTime() };
}

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
    this.m1 = null;
    this.hub = null;
    this.health = null;
    this.load = null;
    this.at = {};
    this.busy = new Set();
    this.width = 1200;
    cx.timer.every(5000, (cx) => this.tick(cx));
    this.tick(cx);
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
    this.poll(cx, "health", 30000, () => readFile(HEALTH_FILE, "utf8").then(JSON.parse, () => null));
    this.poll(cx, "m1", 20000, async () => {
      const r = await exec("sh", ["-c", M1_PROBE], { on: "m1" }).catch(() => null);
      const [native, docker, load] = r ? r.stdout.trim().split(/\s+/) : [];
      return r && r.code === 0 ? { native: Number(native), docker: Number(docker), load: Number(load) } : null;
    });
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

    const ci = this.m1;
    const busy = ci ? ci.native + ci.docker : 0;

    const b = this.hub;
    const hubColor = !b ? t.dim : b.waiting ? t.blocked : b.running ? t.working : t.muted;

    const hl = this.health;
    const stale = !hl || Date.now() - hl.checked_at * 1000 > HEALTH_STALE_MS;
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
      .child(plain("Tasks", b ? `${b.running}/${HUB_CAP} run${b.waiting ? ` · ${b.waiting} waiting` : ""}` : "n/a", hubColor, "Empryo tasks running (cap 6) and waiting for you"))
      .child(healthEl)
      .child(item(srwColor, "SRW", srwDetail, srwTip))
      .when(this.load !== null && roomy, (el) => el.child(plain("M4", `load ${this.load.toFixed(2)}`, t.muted, "load average, 1 minute")))
      .when(tight, (el) => el.child(plain("heavy", h ? ([running && `${running} run`, paused && `${paused} paused`, queued && `${queued} queued`].filter(Boolean).join(" · ") || "idle") : "n/a", heavyColor, "mac-ops heavy status")))
      .child(plain("M1 CI", ci ? (busy ? `${busy} busy` : "idle") : "n/a", busy ? t.working : t.muted, ci ? `${ci.native} native · ${ci.docker} docker · load ${ci.load}` : "M1 not reachable"))
      .child(div().flex_1());
  }
}
