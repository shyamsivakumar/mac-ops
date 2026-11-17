import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { appHome, closeOverlay, exec, home, props, readTextFile, run, theme } from "herdr";

const STATE = `${home()}/.local/state/herdr-worktrees`;
const SCAN = `${appHome()}/mods/worktrees/scan.sh`;
const CONFIRM_GAP = 400;
const ARM_FOR = 6000;
const FRESH_MS = 1200000;
const POLL_MS = 2000;
const PORT_POLL_MS = 5000;
const HANG_MS = 660000;

const REASONS = {
  t3_thread_unfinished: "A T3 thread is still using it",
  process_cwd_inside: "A running program has its working folder inside it",
  worktree_outside_scope: "Lives outside the folders the cleaner manages",
  worktree_locked: "Locked in Git",
  main_checkout: "Main checkout",
  worktree_dirty: "Has uncommitted changes",
  github_pr_open: "Its pull request is still open",
  github_pr_not_closed_for_head: "No closed or merged pull request for this commit",
  remote_commit_unverified: "This commit is not on GitHub",
  github_pr_state_unavailable: "Could not read the pull request from GitHub",
  github_repository_unknown: "Could not find the GitHub repository",
  head_unknown: "Could not read its current commit",
  detached_not_proven_24h_old: "Detached and not idle for 24 hours",
  worktree_status_unknown: "Could not read its Git status",
  worktree_root_mismatch: "Folder does not match its Git root",
  worktree_missing_or_prunable: "The folder is gone",
  worktree_not_registered: "Git no longer lists this worktree",
  not_needs_a_look: "No longer needs a look. Use Clean for safe worktrees",
  archive_target_exists: "The archive already has a folder with this name",
  archive_on_another_filesystem: "The archive is on another disk, so it can't be moved safely",
};

const GROUPS = [
  ["safe", "Safe to remove", "done"],
  ["prune", "Folder gone, will be pruned", "done"],
  ["look", "Needs a look", "working"],
  ["protected", "In use or protected", "dim"],
];

const T3 = `${home()}/.local/bin/t3mcp`;
const LIVE_THREAD = new Set(["preparing", "queued", "starting", "running", "waiting"]);
const THREAD_POLL_MS = 30000;
const worktreeOf = new Map();

const t3 = async (tool, args) => {
  const r = await exec(T3, ["call", tool, JSON.stringify(args)]);
  if (r.code !== 0) throw new Error(JSON.parse(JSON.parse(r.stderr)[0].text).message);
  return JSON.parse(r.stdout);
};

async function liveThreadUsers() {
  const users = new Map();
  for (let cursor = 0; cursor !== null;) {
    const page = await t3("t3_thread_list", { allProjects: true, settled: false, limit: 100, cursor });
    for (const thread of page.threads.filter((t) => LIVE_THREAD.has(t.status))) {
      const known = worktreeOf.get(thread.threadId);
      const path = known?.updatedAt === thread.updatedAt ? known.path : (await t3("t3_thread_read", { threadId: thread.threadId, limit: 1, runLimit: 1 })).thread.worktreePath;
      worktreeOf.set(thread.threadId, { updatedAt: thread.updatedAt, path });
      if (path) users.set(path, [...(users.get(path) ?? []), thread.threadId]);
    }
    cursor = page.nextCursor ?? null;
  }
  return users;
}

const read = (name) => readTextFile(`${STATE}/${name}`).then((text) => (text ? JSON.parse(text) : null), () => null);
const base = (path) => path.slice(path.lastIndexOf("/") + 1);
const rowName = (row) => (base(row.path) === base(row.repo) ? `${base(row.path.slice(0, row.path.lastIndexOf("/")))}/${base(row.path)}` : base(row.path));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function parseListeners(out) {
  const byPid = new Map();
  let entry = null;
  for (const line of out.split("\n")) {
    const value = line.slice(1);
    if (line[0] === "p") {
      entry = { name: "", ports: new Set() };
      byPid.set(value, entry);
    } else if (line[0] === "c" && entry) entry.name = value;
    else if (line[0] === "n" && entry) {
      const port = Number(value.slice(value.lastIndexOf(":") + 1));
      if (port) entry.ports.add(port);
    }
  }
  return byPid;
}

function parseCwds(out) {
  const cwds = new Map();
  let pid = null;
  for (const line of out.split("\n")) {
    if (line[0] === "p") pid = line.slice(1);
    else if (line[0] === "n" && pid) cwds.set(pid, line.slice(1));
  }
  return cwds;
}

async function listeningPorts(paths) {
  const listing = await exec("/usr/sbin/lsof", ["-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"]);
  const listeners = parseListeners(listing.stdout);
  const byPath = new Map();
  if (!listeners.size) return byPath;
  const cwdOut = await exec("/usr/sbin/lsof", ["-a", "-d", "cwd", "-p", [...listeners.keys()].join(","), "-Fpn"]);
  const longestFirst = [...paths].sort((a, b) => b.length - a.length);
  for (const [pid, cwd] of parseCwds(cwdOut.stdout)) {
    const path = longestFirst.find((p) => cwd === p || cwd.startsWith(`${p}/`));
    if (!path) continue;
    const { name, ports } = listeners.get(pid);
    const mine = byPath.get(path) ?? [];
    for (const port of ports) if (!mine.some((m) => m.port === port)) mine.push({ port, name });
    byPath.set(path, mine.sort((a, b) => a.port - b.port));
  }
  return byPath;
}

function age(seconds) {
  if (seconds === null || seconds === undefined) return "";
  const m = Math.floor(seconds / 60);
  return m < 60 ? `${Math.max(m, 1)}m old` : m < 1440 ? `${Math.floor(m / 60)}h old` : `${Math.floor(m / 1440)}d old`;
}

function clock(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function reasonText(row) {
  if (row.gone) return row.category === "prune" ? "The folder is gone. Clean will prune the entry." : "The folder is gone, but Git has it locked, so it stays.";
  const words = row.reasons.filter((r) => r !== "worktree_dirty").map((r) => REASONS[r] ?? r.replaceAll("_", " "));
  const work = [];
  if (row.uncommitted) work.push(plural(row.uncommitted, "uncommitted file"));
  if (row.unpushed) work.push(plural(row.unpushed, "unpushed commit"));
  return [...words, ...(work.length ? [work.join(", ")] : [])].join(". ") || "Passed every safety check";
}

export default class Worktrees extends View {
  init(_props, cx) {
    this.overlay = props()?.overlay ?? null;
    this.born = Date.now();
    this.data = null;
    this.finished = 0;
    this.scanning = false;
    this.cleaning = false;
    this.archiving = false;
    this.error = null;
    this.result = null;
    this.archiveResult = null;
    this.selected = new Set();
    this.armed = null;
    this.armedArchive = null;
    this.queued = null;
    this.pressedAt = 0;
    this.polling = false;
    this.ports = new Map();
    this.scanningPorts = false;
    this.threadUsers = null;
    this.scanningThreads = false;
    this.handle = cx.focus_handle();
    cx.timer.after(60, () => this.handle.focus());
    cx.timer.every(POLL_MS, (cx) => this.poll(cx));
    cx.timer.every(PORT_POLL_MS, (cx) => this.pollPorts(cx));
    this.pollPorts(cx);
    cx.timer.every(THREAD_POLL_MS, (cx) => this.pollThreads(cx));
    this.pollThreads(cx);
    cx.spawn(async (cx) => {
      this.data = await read("last.json");
      const status = await read("status.json");
      this.finished = status?.state === "done" ? status.finished * 1000 : 0;
      cx.notify();
      if (status?.state === "running" && Date.now() - status.at * 1000 < HANG_MS) {
        this.scanning = true;
        cx.notify();
      } else if (Date.now() - this.finished > FRESH_MS) this.start("scan", cx);
    });
  }

  live() {
    return Date.now() - this.born >= CONFIRM_GAP;
  }

  start(mode, cx, paths = []) {
    this.pressedAt = Date.now();
    this.scanning = true;
    this.error = null;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const r = await exec("sh", [SCAN, mode, "start", ...paths]);
        if (r.code !== 0) throw new Error(r.stderr.trim() || "the scan did not start");
        if (r.stdout.trim() === "busy" && mode !== "scan") {
          this.scanning = false;
          this.cleaning = false;
          this.archiving = false;
          this.error = `Another scan is running. Wait for it to finish, then press ${mode === "clean" ? "Clean" : "Archive"} again.`;
        }
      } catch (error) {
        this.scanning = false;
        this.cleaning = false;
        this.archiving = false;
        this.error = error.message;
      }
      cx.notify();
    });
  }

  poll(cx) {
    if (!this.scanning || this.polling) return;
    this.polling = true;
    cx.spawn(async (cx) => {
      try {
        const status = await read("status.json");
        if (status?.state === "running" || (status && status.at < Math.floor(this.pressedAt / 1000))) {
          if (Date.now() - Math.max(status.at * 1000, this.pressedAt) > HANG_MS) throw new Error("The scan took too long");
        } else if (status?.state === "done" || status?.state === "failed") {
          this.data = await read("last.json");
          if (this.data && !this.data.categories) {
            this.data = null;
            throw new Error("cleaner out of date");
          }
          if (this.archiving) {
            this.archiveResult = await read("archive.json");
            this.selected = new Set();
          }
          this.dropStaleSelection();
          if (status.state === "failed") throw new Error(status.error);
          if (this.cleaning) this.result = await read("clean.json");
          this.finished = status.finished * 1000;
          this.scanning = false;
          this.cleaning = false;
          this.archiving = false;
          const queued = this.queued;
          this.queued = null;
          if (queued) this.launch(queued, cx);
        }
      } catch (error) {
        this.queued = null;
        this.scanning = false;
        this.cleaning = false;
        this.archiving = false;
        this.error = error.message;
      } finally {
        this.polling = false;
      }
      cx.notify();
    });
  }

  pollPorts(cx) {
    const paths = [...this.rows(), ...(this.data?.excluded_rows ?? [])].filter((r) => !r.gone).map((r) => r.path);
    if (this.scanningPorts || !paths.length) return;
    this.scanningPorts = true;
    cx.spawn(async (cx) => {
      try {
        const next = await listeningPorts(paths);
        const changed = JSON.stringify([...next]) !== JSON.stringify([...this.ports]);
        this.ports = next;
        if (changed) cx.notify();
      } finally {
        this.scanningPorts = false;
      }
    });
  }

  pollThreads(cx) {
    if (this.scanningThreads) return;
    this.scanningThreads = true;
    cx.spawn(async (cx) => {
      try {
        this.threadUsers = await liveThreadUsers();
      } catch {
        this.threadUsers = null;
      } finally {
        this.scanningThreads = false;
      }
      cx.notify();
    });
  }

  chips(t, path, key) {
    return (this.ports.get(path) ?? []).map((p) => div().id(`port-${key}-${p.port}`).flex_none().h(17).px(5).flex().items_center().rounded(4)
      .text_size(11).bg(t.accent + "1f").text_color(t.accent).cursor_pointer().hover((s) => s.bg(t.accent + "38"))
      .tooltip(`${p.name} · open http://localhost:${p.port}`)
      .on_click((e, cx) => {
        if (e.click_count > 1) return;
        cx.stop_propagation();
        exec("open", [`http://localhost:${p.port}`]);
      })
      .child(`:${p.port} ${p.name}`));
  }

  rows() {
    return (this.data?.rows ?? []).filter((r) => !r.main_checkout && r.category !== "removed");
  }

  cleanable() {
    const c = this.data?.categories;
    return c ? c.safe + c.prune : 0;
  }

  confirmed(field, cx) {
    if (this[field] === null) {
      this[field] = Date.now();
      cx.timer.after(ARM_FOR, (cx) => {
        this[field] = null;
        cx.notify();
      });
      cx.notify();
      return false;
    }
    if (Date.now() - this[field] < CONFIRM_GAP) return false;
    this[field] = null;
    return true;
  }

  press(cx) {
    const n = this.cleanable();
    if (!this.live() || this.cleaning || this.archiving) return;
    if (this.queued) {
      if (this.queued.mode === "clean") this.queued = null;
      cx.notify();
      return;
    }
    if (!n || !this.confirmed("armed", cx)) return;
    if (this.scanning) {
      this.queued = { mode: "clean" };
      cx.notify();
      return;
    }
    this.launch({ mode: "clean" }, cx);
  }

  launch({ mode, paths }, cx) {
    if (mode === "clean") {
      this.shown = this.cleanable();
      this.cleaning = true;
    } else this.archiving = true;
    this.result = null;
    this.archiveResult = null;
    this.start(mode, cx, paths);
  }

  archivable() {
    return this.rows().filter((r) => r.category === "look" && !r.gone);
  }

  dropStaleSelection() {
    const live = new Set(this.archivable().map((r) => r.path));
    this.selected = new Set([...this.selected].filter((p) => live.has(p)));
  }

  chosen() {
    return this.archivable().filter((r) => this.selected.has(r.path));
  }

  toggle(paths, cx) {
    const all = paths.every((p) => this.selected.has(p));
    for (const p of paths) all ? this.selected.delete(p) : this.selected.add(p);
    this.armedArchive = null;
    cx.notify();
  }

  pressArchive(cx) {
    const chosen = this.chosen();
    if (!this.live() || this.cleaning || this.archiving) return;
    if (this.queued) {
      if (this.queued.mode === "archive") this.queued = null;
      cx.notify();
      return;
    }
    if (!chosen.length || !this.confirmed("armedArchive", cx)) return;
    const paths = chosen.map((r) => r.path);
    if (this.scanning) {
      this.queued = { mode: "archive", paths };
      cx.notify();
      return;
    }
    this.launch({ mode: "archive", paths }, cx);
  }

  openFolder(row) {
    run("tab.new", { name: rowName(row), folder: row.path });
    closeOverlay(this.overlay);
  }

  key(e, cx) {
    if (e.is_held || e.key !== "escape") return;
    closeOverlay(this.overlay);
    cx.stop_propagation();
  }

  tile(t, label, n, color) {
    return v_flex().flex_1().gap(2).p(10).rounded(6).bg(t.raised).border_1().border_color(t.border)
      .child(div().text_size(22).font_semibold().text_color(n ? t[color] : t.dim).child(String(n)))
      .child(div().text_size(12).text_color(t.muted).child(label));
  }

  checkbox(t, id, on, go) {
    return div().id(id).size(15).flex_none().mt(2).flex().items_center().justify_center().rounded(3).border_1()
      .border_color(on ? t.solid : t.input).bg(on ? t.solid : t.raised).text_size(11).text_color(t.solid_foreground)
      .cursor_pointer().on_click((e, cx) => e.click_count > 1 || go(cx))
      .child(on ? "✓" : "");
  }

  row(t, r, i) {
    const group = GROUPS.find((g) => g[0] === r.category);
    const archivable = r.category === "look" && !r.gone;
    return h_flex().id(`wt-${i}`).w_full().gap(10).py(8).px(14).items_start().border_t(1).border_color(t.border)
      .child(archivable ? this.checkbox(t, `pick-${i}`, this.selected.has(r.path), (cx) => this.toggle([r.path], cx)) : div().size(7).rounded(4).flex_none().mt(5).bg(t[group[2]]))
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(h_flex().gap(8).min_w(0).items_baseline()
          .child(div().min_w(0).truncate().text_size(13).font_medium().text_color(t.foreground).child(rowName(r)))
          .child(div().min_w(0).truncate().text_size(12).text_color(t.muted).child(r.branch ?? "detached")))
        .child(div().text_size(12).line_height("17px").text_color(t.muted).child(reasonText(r)))
        .when(this.ports.has(r.path), (el) => el.child(h_flex().pt(2).gap(4).flex_wrap().items_center().children(this.chips(t, r.path, i)))))
      .child(div().text_size(12).text_color(t.dim).flex_none().w(70).child(age(r.age_seconds)))
      .child(div().w(96).flex_none().flex().justify_end()
        .when(r.category === "look" && !r.gone, (el) => el.child(this.small(t, `open-${i}`, "Open folder", () => this.openFolder(r)))));
  }

  small(t, id, label, go) {
    return div().id(id).h(24).px(8).flex().items_center().rounded(4).border_1().border_color(t.input).bg(t.raised)
      .text_size(12).text_color(t.foreground).cursor_pointer().hover((s) => s.bg(t.selected))
      .on_click((e, cx) => e.click_count > 1 || go(cx))
      .child(label);
  }

  excluded(t) {
    const rows = this.data?.excluded_rows ?? [];
    if (!rows.length) return [];
    const out = [div().w_full().px(14).pt(16).pb(2).text_size(14).font_semibold().text_color(t.foreground).child(`Not managed by the cleaner · ${plural(rows.length, "worktree")}`),
      div().w_full().px(14).pb(4).text_size(12).line_height("17px").text_color(t.muted).child("The cleaner never inspects these repositories for removal. This list is read-only, so there is nothing to clean here.")];
    for (const repo of [...new Set(rows.map((r) => r.repo))]) {
      const mine = rows.filter((r) => r.repo === repo);
      out.push(div().w_full().px(14).pt(10).pb(4).text_size(12).font_semibold().text_color(t.foreground).child(`${base(repo)}  ·  ${plural(mine.length, "worktree")}  ·  ${mine[0].reason}`));
      mine.forEach((r, i) => out.push(h_flex().id(`ex-${base(repo)}-${i}`).w_full().gap(10).py(6).px(14).items_start().border_t(1).border_color(t.border)
        .child(v_flex().flex_1().min_w(0).gap(2)
          .child(h_flex().gap(8).flex_wrap().items_baseline()
            .child(div().text_size(13).font_medium().text_color(t.foreground).child(base(r.path)))
            .child(div().text_size(12).text_color(t.muted).child(r.branch ?? "detached")))
          .child(div().text_size(12).text_color(t.muted).child(this.exclusionDetail(r)))
          .when(this.ports.has(r.path), (el) => el.child(h_flex().pt(2).gap(4).flex_wrap().items_center().children(this.chips(t, r.path, `ex-${base(repo)}-${i}`)))))
        .child(div().text_size(12).text_color(t.dim).flex_none().w(70).child(age(r.age_seconds)))));
    }
    return out;
  }

  exclusionDetail(r) {
    const state = r.gone ? "folder is gone" : r.dirty === null ? "status unknown" : r.dirty ? plural(r.uncommitted, "uncommitted file") : "clean";
    if (!this.threadUsers) return `${state}. T3 thread use unknown`;
    const users = this.threadUsers.get(r.path) ?? [];
    return users.length ? `${state}. Used by ${plural(users.length, "T3 thread")}` : `${state}. No T3 thread uses it`;
  }

  body(t) {
    const rows = this.rows();
    const repos = [...new Set(rows.map((r) => r.repo))].sort((a, b) => base(a).localeCompare(base(b)));
    const order = GROUPS.map((g) => g[0]);
    const out = [];
    for (const repo of repos) {
      const mine = rows.filter((r) => r.repo === repo).sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category));
      out.push(div().w_full().px(14).pt(12).pb(4).text_size(12).font_semibold().text_color(t.foreground).child(`${base(repo)}  ·  ${plural(mine.length, "worktree")}`));
      mine.forEach((r, i) => out.push(this.row(t, r, `${base(repo)}-${i}`)));
    }
    return out;
  }

  render() {
    const t = theme();
    const c = this.data?.categories;
    const n = this.cleanable();
    const armed = this.armed !== null;
    const label = this.cleaning ? "Cleaning…" : this.queued?.mode === "clean" ? "Clean after scan" : armed ? `Press again to remove ${n}` : n ? `Clean ${n} safe` : "Nothing safe to clean";
    const idle = !this.scanning && !this.cleaning && !this.archiving;
    const look = this.archivable();
    const chosen = this.chosen().length;
    const armedArchive = this.armedArchive !== null;
    const running = this.cleaning || this.archiving;
    const archiveLabel = this.archiving ? "Archiving…" : this.queued?.mode === "archive" ? `Archive ${this.queued.paths.length} after scan` : armedArchive ? `Press again to archive ${chosen}` : chosen ? `Archive ${chosen}` : "Archive";
    const archived = this.archiveResult?.archived ?? [];
    const refused = this.archiveResult?.refused ?? [];
    const result = this.result?.rows?.filter((r) => r.category === "removed") ?? [];
    return v_flex().id("wt-root").size_full().min_h(0).bg(t.chrome).text_size(13).track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .on_mouse_down("left", () => this.handle.focus())
      .child(h_flex().px(14).py(10).gap(10).items_center().flex_none().border_b(1).border_color(t.border)
        .child(div().text_size(15).font_semibold().text_color(t.foreground).child("Worktrees"))
        .child(div().flex_1().text_size(12).text_color(this.error ? t.blocked : t.muted)
          .child(this.error ? `Couldn't scan: ${this.error}` : this.scanning ? (this.cleaning ? "Cleaning, then rescanning…" : this.archiving ? "Archiving, then rescanning…" : this.queued ? `Scanning, then ${this.queued.mode === "clean" ? "cleaning" : "archiving"}…` : "Scanning…") : this.finished ? `Last scan ${clock(this.finished)}` : ""))
        .child(this.small(t, "wt-rescan", this.scanning ? "Scanning…" : "Rescan", (cx) => idle && this.live() && this.start("scan", cx)))
        .child(this.small(t, "wt-close", "Close", () => closeOverlay(this.overlay))))
      .when(Boolean(c), (el) => el.child(h_flex().gap(10).p(14).flex_none()
        .child(this.tile(t, "safe to remove", c.safe + c.prune, "done"))
        .child(this.tile(t, "need a look: uncommitted or unpushed work", c.look, "working"))
        .child(this.tile(t, "in use or protected", c.protected, "muted"))))
      .when(!c && !this.error, (el) => el.child(div().p(14).text_color(t.muted).child(this.scanning ? "Scanning, this takes about a minute…" : "No scan yet.")))
      .when(Boolean(this.result), (el) => el.child(v_flex().mx(14).mb(10).p(10).gap(2).flex_none().rounded(6).bg(t.raised).border_1().border_color(t.border)
        .child(div().text_size(13).font_medium().text_color(t.done).child(`Removed ${plural(this.result.removed, "worktree")}, pruned ${plural(this.result.pruned, "entry")}`))
        .when(this.result.removed + this.result.pruned !== this.shown, (el) => el.child(div().text_size(12).text_color(t.working).child(`${this.shown} were shown as safe. ${this.result.removed + this.result.pruned} were still safe when Clean ran; the rest were skipped.`)))
        .children(result.map((r) => div().text_size(12).text_color(t.muted).child(`${base(r.repo)}  ·  ${rowName(r)}`)))))
      .when(Boolean(this.archiveResult), (el) => el.child(v_flex().mx(14).mb(10).p(10).gap(2).flex_none().rounded(6).bg(t.raised).border_1().border_color(t.border)
        .child(div().text_size(13).font_medium().text_color(archived.length ? t.done : t.working).child(`Archived ${archived.length} to ${this.archiveResult.archive_dir.replace(home(), "~")}`))
        .children(archived.map((r) => div().text_size(12).text_color(t.muted).child(`${base(r.repo)}  ·  ${rowName(r)}`)))
        .children(refused.map((r) => div().text_size(12).text_color(t.working).child(`Skipped ${r.repo ? `${base(r.repo)}  ·  ` : ""}${base(r.path)}: ${r.reasons.map((x) => REASONS[x] ?? x.replaceAll("_", " ")).join(". ")}`)))))
      .when(look.length > 0, (el) => el.child(h_flex().id("wt-pick-all").px(14).py(6).gap(10).items_center().flex_none().border_t(1).border_color(t.border)
        .child(this.checkbox(t, "pick-all", chosen === look.length, (cx) => this.toggle(look.map((r) => r.path), cx)))
        .child(div().flex_1().text_size(12).text_color(t.muted).child(`Select all in Needs a look (${look.length})`))))
      .child(v_flex().id("wt-list").flex_1().min_h(0).overflow_y_scroll().children(this.body(t)).children(this.excluded(t)))
      .child(h_flex().px(14).py(10).gap(12).items_center().flex_none().border_t(1).border_color(t.border)
        .child(v_flex().flex_1().min_w(0).gap(4)
          .child(div().text_size(12).line_height("17px").text_color(t.muted).child("Clean removes worktrees that pass every check. Archive moves the folder to ~/.local/state/archive, keeps the branch and pins the commit. Nothing is deleted.")))
        .child(h_flex().id("wt-archive").h(30).px(14).flex_none().items_center().rounded(6)
          .bg(armedArchive ? t.blocked : t.solid).text_color(armedArchive ? t.background : t.solid_foreground).text_size(12.5).font_semibold()
          .opacity((chosen || this.queued?.mode === "archive") && !running ? 1 : 0.45).cursor_pointer()
          .on_click((e, cx) => e.click_count > 1 || this.pressArchive(cx))
          .child(archiveLabel))
        .child(h_flex().id("wt-clean").h(30).px(14).flex_none().items_center().rounded(6)
          .bg(armed ? t.blocked : t.solid).text_color(armed ? t.background : t.solid_foreground).text_size(12.5).font_semibold()
          .opacity(n && !running ? 1 : 0.45).cursor_pointer()
          .on_click((e, cx) => e.click_count > 1 || this.press(cx))
          .child(label)));
  }
}
