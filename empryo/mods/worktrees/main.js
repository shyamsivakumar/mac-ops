import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { appHome, closeOverlay, exec, home, props, readTextFile, run, theme } from "herdr";

const STATE = `${home()}/.local/state/herdr-worktrees`;
const SCAN = `${appHome()}/mods/worktrees/scan.sh`;
const CONFIRM_GAP = 400;
const ARM_FOR = 6000;
const FRESH_MS = 60000;
const POLL_MS = 2000;
const HANG_MS = 660000;

const REASONS = {
  removal_disabled_no_hub_lease: "Removal disabled: hub cannot exclude concurrent or archived tasks",
  empryo_thread_unfinished: "A hub thread is still using it",
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
    contains_nested_worktree: "Another checkout sits inside it",
    nested_scan_incomplete: "Could not read every folder inside it",
};

const GROUPS = [
  ["safe", "Safe to remove", "done"],
  ["prune", "Folder gone, will be pruned", "done"],
  ["look", "Needs a look", "working"],
  ["protected", "In use or protected", "dim"],
];

const read = (name) => readTextFile(`${STATE}/${name}`).then((text) => (text ? JSON.parse(text) : null), () => null);
const base = (path) => path.slice(path.lastIndexOf("/") + 1);
const rowName = (row) => (base(row.path) === base(row.repo) ? `${base(row.path.slice(0, row.path.lastIndexOf("/")))}/${base(row.path)}` : base(row.path));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

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
    this.error = null;
    this.result = null;
    this.armed = null;
    this.polling = false;
    this.handle = cx.focus_handle();
    cx.timer.after(60, () => this.handle.focus());
    cx.timer.every(POLL_MS, (cx) => this.poll(cx));
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

  start(mode, cx) {
    this.scanning = true;
    this.error = null;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const r = await exec("sh", [SCAN, mode]);
        if (r.code !== 0) throw new Error(r.stderr.trim() || "the scan did not start");
        if (r.stdout.trim() === "busy" && mode === "clean") {
          this.scanning = false;
          this.cleaning = false;
          this.error = "Another scan is running. Wait for it to finish, then press Clean again.";
        }
      } catch (error) {
        this.scanning = false;
        this.cleaning = false;
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
        if (status?.state === "running") {
          if (Date.now() - status.at * 1000 > HANG_MS) throw new Error("The scan took too long");
        } else if (status?.state === "done" || status?.state === "failed") {
          this.data = await read("last.json");
          if (this.data && !this.data.categories) {
            this.data = null;
            throw new Error("cleaner out of date");
          }
          if (status.state === "failed") throw new Error(status.error);
          if (this.cleaning) this.result = await read("clean.json");
          this.finished = status.finished * 1000;
          this.scanning = false;
          this.cleaning = false;
        }
      } catch (error) {
        this.scanning = false;
        this.cleaning = false;
        this.error = error.message;
      } finally {
        this.polling = false;
      }
      cx.notify();
    });
  }

  rows() {
    return (this.data?.rows ?? []).filter((r) => !r.main_checkout);
  }

  cleanable() {
    const c = this.data?.categories;
    return c ? c.safe + c.prune : 0;
  }

  press(cx) {
    const n = this.cleanable();
    if (!this.live() || this.scanning || this.cleaning || !n) return;
    if (!this.armed) {
      this.armed = Date.now();
      cx.timer.after(ARM_FOR, (cx) => {
        this.armed = null;
        cx.notify();
      });
      cx.notify();
      return;
    }
    if (Date.now() - this.armed < CONFIRM_GAP) return;
    this.armed = null;
    this.shown = n;
    this.cleaning = true;
    this.result = null;
    this.start("clean", cx);
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

  row(t, r, i) {
    const group = GROUPS.find((g) => g[0] === r.category);
    return h_flex().id(`wt-${i}`).w_full().gap(10).py(8).px(14).items_start().border_t(1).border_color(t.border)
      .child(div().size(7).rounded(4).flex_none().mt(5).bg(t[group[2]]))
      .child(v_flex().flex_1().min_w(0).gap(2)
        .child(h_flex().gap(8).flex_wrap().items_baseline()
          .child(div().text_size(13).font_medium().text_color(t.foreground).child(rowName(r)))
          .child(div().text_size(12).text_color(t.muted).child(r.branch ?? "detached")))
        .child(div().text_size(12).line_height("17px").text_color(t.muted).child(reasonText(r))))
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
    const label = this.cleaning ? "Cleaning…" : armed ? `Press again to remove ${n}` : n ? `Clean ${n} safe` : "Nothing safe to clean";
    const idle = !this.scanning && !this.cleaning;
    const result = this.result?.rows?.filter((r) => r.category === "removed") ?? [];
    return v_flex().id("wt-root").size_full().min_h(0).bg(t.chrome).text_size(13).track_focus(this.handle)
      .on_key_down((e, cx) => this.key(e, cx))
      .on_mouse_down("left", () => this.handle.focus())
      .child(h_flex().px(14).py(10).gap(10).items_center().flex_none().border_b(1).border_color(t.border)
        .child(div().text_size(15).font_semibold().text_color(t.foreground).child("Worktrees"))
        .child(div().flex_1().text_size(12).text_color(this.error ? t.blocked : t.muted)
          .child(this.error ? `Couldn't scan: ${this.error}` : this.scanning ? (this.cleaning ? "Cleaning, then rescanning…" : "Scanning…") : this.finished ? `Last scan ${clock(this.finished)}` : ""))
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
      .child(v_flex().id("wt-list").flex_1().min_h(0).overflow_y_scroll().children(this.body(t)))
      .child(h_flex().px(14).py(10).gap(12).items_center().flex_none().border_t(1).border_color(t.border)
        .child(div().flex_1().text_size(12).line_height("17px").text_color(t.muted).child("Clean removes only worktrees that pass every check, and prunes entries whose folder is gone. Rows that need a look are never removed. Branches are kept. Nothing is forced."))
        .child(h_flex().id("wt-clean").h(30).px(14).flex_none().items_center().rounded(6)
          .bg(armed ? t.blocked : t.solid).text_color(armed ? t.background : t.solid_foreground).text_size(12.5).font_semibold()
          .opacity(n && idle ? 1 : 0.45).cursor_pointer()
          .on_click((e, cx) => e.click_count > 1 || this.press(cx))
          .child(label)));
  }
}
