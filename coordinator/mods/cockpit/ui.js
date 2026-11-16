// Elements of the board. Every row has a fixed height, so each column can window itself.

import { div } from "gpui-kit";
import { shared } from "herdr";
import { v_flex, h_flex, Input, TextView } from "gpui-base";
import { shortModel } from "./hub.js";
import { changedSinceLaunch, issueRef, pickerOptions, startBlock } from "./tickets.js";

export const H = { bar: 26, search: 30, head: 46, sub: 20, card: 86, foot: 18, title: 30, reason: 28, child: 24, reply: 34, chips: 18, empty: 50, folded: 44 };
const TONE = { ask: "blocked", wait: "blocked", fail: "blocked", stop: "working", run: "working", done: "done", idle: "idle" };
const CI_TONE = { pass: "done", fail: "blocked", pending: "working", none: "dim" };
const CI_MARK = { pass: "✓", fail: "✗", pending: "…", none: "—" };
const VERDICT_MARK = { pass: "✓", fail: "✗", unknown: "?", unverified: "?", loading: "…" };
const VERDICT_TONE = { pass: "done", fail: "blocked", unknown: "dim", unverified: "dim", loading: "working" };
export const LOADING_VERDICT = { state: "loading", label: "rev …" };
export const canMerge = (verdict) => verdict?.state === "pass" || verdict?.state === "unknown";
const MERGE = { MERGEABLE: ["merge ✓", "done", "Mergeable"], CONFLICTING: ["merge ✗", "blocked", "Merge conflict"], UNKNOWN: ["merge ?", "dim", "Merge status unknown"] };
const DRAFT = ["Draft", "dim", "Draft PR, not ready to merge"];
const mergeOf = (gh) => (gh?.draft ? DRAFT : MERGE[gh?.mergeable] ?? MERGE.UNKNOWN);
export const COLUMNS = [["needs", "Needs you", "blocked", "Needs you"], ["run", "Working", "working", "Working"], ["checks", "Checks running", "idle", "Checks"], ["cifail", "CI failed", "blocked", "CI failed"], ["review", "Review pending", "working", "Review"], ["ready", "Approved/Ready", "accent", "Ready"], ["done", "Done · not settled", "done", "Done"], ["backlog", "Backlog", "idle", "Backlog"], ["dead", "Dead runs", "idle", "Dead"]];
export const PR_LANES = new Set(["checks", "cifail", "review", "ready"]);
const COLUMN_NAME = Object.fromEntries(COLUMNS.map((c) => [c[0], c[3]]));
export const COLUMN_LIMIT = { needs: 10, ready: 10 };
const AGED_COLUMNS = new Set(["needs", "cifail", "ready"]);
const DAY = 86400000;
const AMBER_AFTER = DAY;
const RED_AFTER = 3 * DAY;
const stop = (_e, cx) => cx.stop_propagation();
const selectOnly = (key, cb) => (e, cx) => {
  cb.press(key, e, cx);
  cx.stop_propagation();
};

export const hasReason = (c, variant) => variant === "std" && c.kind === "fail" && Boolean(c.context);
export const cardHeight = (replying, reason, chips) => H.card + (replying ? H.reply : 0) + (reason ? H.reason : 0) + (chips ? H.chips : 0);

export function ago(at, now) {
  const m = Math.floor((now - at) / 60000);
  return m < 1 ? "now" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`;
}

export function elapsed(ms) {
  const m = Math.floor(ms / 60000);
  return m < 1 ? "<1m" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${Math.floor(m / 1440)}d`;
}

const clip = (text, n) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

function action(t, id, hint, label, run, tip, bare, tone) {
  const el = h_flex().id(id).h(18).px(5).gap(4).items_center().flex_none().rounded(4).border_1().border_color(tone ? t[tone] + "88" : t.input).bg(tone ? t[tone] + "22" : t.raised)
    .text_size(10.5).font_medium().text_color(t.foreground).cursor_pointer().hover((s) => s.bg(t.selected))
    .on_mouse_down("left", stop).on_click((_e, cx) => run(cx))
    .when(!bare, (e) => e.child(div().text_size(9.5).text_color(t.dim).child(hint)))
    .child(label);
  return tip ? el.tooltip(tip) : el;
}

function fitSummary(parts, room) {
  const fit = [];
  let used = 0;
  for (const part of parts) {
    used += part[0].length * 5 + 8;
    if (used - 8 > room) break;
    fit.push(part);
  }
  return fit;
}

const buttonWidth = (label, bare) => label.length * 5.6 + 12 + (bare ? 0 : 10);

function headButton(t, id, glyph, tip, run) {
  return div().id(id).size(18).flex_none().flex().items_center().justify_center().rounded(4).text_size(12).text_color(t.muted)
    .cursor_pointer().hover((s) => s.bg(t.selected).text_color(t.foreground)).on_mouse_down("left", stop).on_click((_e, cx) => run(cx)).tooltip(tip).child(glyph);
}

const limitOf = (key) => COLUMN_LIMIT[key];
const overLimit = (key, col) => limitOf(key) !== undefined && col.total > limitOf(key);
const countText = (key, col, state) => {
  if (key === "run") return `${state.running}/${state.cap}`;
  if (limitOf(key) === undefined) return String(col.count);
  const load = `${col.total}/${limitOf(key)}`;
  return col.count === col.total ? load : `${col.count} · ${load}`;
};
const limitTip = (key, col) => (limitOf(key) === undefined ? "" : overLimit(key, col) ? `Over the limit of ${limitOf(key)}: review before more work finishes${col.count === col.total ? "" : ` (${col.total} on the board, filters and snoozes ignored)`}` : `Limit of ${limitOf(key)}`);

export function columnHead(t, key, col, state, cb) {
  const [, label, tone, short] = COLUMNS.find((c) => c[0] === key);
  const over = overLimit(key, col);
  const capped = (key === "run" && state.running >= state.cap) || over;
  const tight = state.colW < 260;
  const cramped = state.colW < 200;
  const count = countText(key, col, state);
  const tip = [state.popup ? "" : `${state.collapsed ? "Show" : "Hide"} ${label}`, limitTip(key, col)].filter(Boolean).join(". ");
  const settleReviewed = key === "done" && state.reviewed > 0 && !tight ? { label: state.armed?.kind === "settle" ? `Confirm ${state.reviewed}` : `Settle ${state.reviewed}` } : null;
  const bulk = key === "done" && state.done > 0
    ? { id: "settle-all", hint: "A", label: state.armed?.kind === "settle-all" ? `Confirm ${state.done}` : tight ? `Settle ${state.done}` : `Settle all ${state.done}`, run: (cx) => cb.settleAll(cx), tip: `Settle all ${state.done} (A)` }
    : key === "ready" && col.count > 0
    ? { id: "approve-all", hint: "M", label: state.armed?.kind === "approve-all" ? `Confirm ${state.approvable}` : tight ? `Approve ${state.approvable}` : `Approve all ${state.approvable}`, run: (cx) => cb.approveAll(cx), tip: state.approvable ? `Approve all ${state.approvable} (M)` : `${state.nothing} (M)`, dim: state.approvable === 0 }
    : null;
  const extra = key === "needs" && state.failed > 0
    ? { id: "retry-failed", hint: "F", label: `Retry ${state.failed}`, run: (cx) => cb.retry(cx), tip: `Retry the ${state.failed} failed cards, grouped by error (F)` }
    : state.conflicts[key] > 0
    ? { id: "rebase-all", hint: "U", label: state.armed?.kind === "rebase-all" && state.armed.key === key ? `Confirm ${state.conflicts[key]}` : `Rebase ${state.conflicts[key]}`, run: (cx) => cb.rebaseAll(cx, key), tip: `Send the ${state.conflicts[key]} conflicting PRs here back for a rebase (U does every lane)` }
    : null;
  const summary = fitSummary(col.summary, state.colW - 28 - [settleReviewed, extra, bulk].filter(Boolean).reduce((sum, b) => sum + buttonWidth(b.label, tight) + 4, 0));
  const buttons = [settleReviewed, extra, bulk].filter(Boolean).map((b) => ({ ...b, bare: tight }));
  return v_flex().id(`fold-${key}`).h(H.head).flex_none().border_b(1).border_color(t.border)
    .when(!state.popup, (el) => el.cursor_pointer().on_click((_e, cx) => cb.fold(key, cx)))
    .when(Boolean(tip), (el) => el.tooltip(tip))
    .child(h_flex().h(H.head - H.sub).px(10).gap(cramped ? 4 : 6).items_center().overflow_hidden()
      .when(!state.popup && !cramped, (el) => el.child(div().w(10).text_size(9).text_color(t.dim).child(state.collapsed ? "▸" : "▾")))
      .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
      .child(div().flex_none().text_size(11).font_semibold().text_color(t.foreground).child(state.popup ? label : short))
      .child(div().flex_1())
      .child(div().flex_none().text_size(11).font_semibold().text_color(capped ? t.blocked : col.count ? t[tone] : t.dim).when(over, (el) => el.px(tight ? 2 : 4).rounded(3).bg(t.blocked + "22")).child(count))
      .child(state.popup ? headButton(t, "pop-close", "✕", "Close", () => cb.close()) : headButton(t, `pop-${key}`, "⤢", `Open ${label} in a pop-up`, () => cb.expand(key))))
    .child(h_flex().h(H.sub).px(10).gap(8).items_center().overflow_hidden()
      .children(summary.map(([text, summaryTone]) => div().flex_none().text_size(9.5).text_color(summaryTone === "dim" ? t.muted : t[summaryTone]).child(text)))
      .when(!summary.length, (el) => el.child(div().flex_1().min_w(0).truncate().text_size(9.5).text_color(col.summary[0][1] === "dim" ? t.muted : t[col.summary[0][1]]).child(col.summary[0][0])))
      .child(div().flex_1())
      .when(Boolean(settleReviewed), (el) => el.child(action(t, "settle-reviewed", "S", settleReviewed.label, (cx) => cb.settleReviewed(cx))))
      .when(Boolean(extra), (el) => el.child(action(t, extra.id, extra.hint, extra.label, extra.run, extra.tip, tight, "blocked")))
      .when(Boolean(bulk), (el) => el.child(action(t, bulk.id, bulk.hint, bulk.label, bulk.run, bulk.tip, tight).when(Boolean(bulk.dim), (d) => d.opacity(0.5)))));
}

const BAR_GAP = 6;
const NOTICE_MIN = 140;
const HINT_ROOM = 64;
const NOTICE_TONE = { success: "done", error: "blocked", info: "muted" };
const barCost = (item) => (item.label.length + (item.more?.length ?? 0)) * 6.2 + 12;
function projectItem(v) {
  if (!v.project) return { id: "project", prio: 3, label: "Project · all", tip: "Showing every project. Click to show one project only (P)." };
  return { id: "project", prio: -1, label: `Project · ${v.project}${v.projectCount ? "" : " · no cards"}`, tone: "working", tip: `Showing only ${v.project}. Bulk actions touch only these cards. Click to change (P).` };
}

function barItems(v) {
  const { worktrees: w, slots } = v;
  const asks = shared("co.asks")?.items ?? [];
  const decided = shared("co.decided") ?? {};
  const waiting = asks.filter((a) => !decided[a.id]);
  const sent = asks.length - waiting.length;
  const decisions = [asks.length ? { id: "decisions", prio: -1, command: "coordinator.asks", label: `Decisions · ${waiting.length} waiting${sent ? ` · ${sent} sent` : ""}`, tone: waiting.length ? "blocked" : undefined, tip: `${waiting.slice(0, 3).map((a) => a.text).join(" · ")}${waiting.length > 3 ? ` · and ${waiting.length - 3} more` : ""}. Click to answer.` } : { id: "decisions", prio: -1, command: "coordinator.asks", label: "Decisions · none", tip: "Nothing is waiting for your answer. Click to open the decisions panel." }];
  const old = w?.failed && w.scannedAt ? ` · ${ago(w.scannedAt, Date.now())} old` : "";
  const failedScan = w?.failed ? [{ id: "wtfail", prio: 1, label: `worktree scan failed: ${w.failed}`, tone: "muted", tip: `The last worktree scan failed: ${w.failed}. ${w.scannedAt ? "The numbers beside it come from the last good scan." : "There is no earlier result."}` }] : [];
  const hasCounts = w && w.stale !== undefined;
  return [
    ...decisions,
    ...failedScan,
    { id: "wt", prio: 0, label: hasCounts ? `Worktrees · ${w.stale} stale${old}` : "Worktrees", more: hasCounts && w.look ? ` · ${w.look} need a look` : "", tone: hasCounts && w.stale && !w.failed ? "working" : undefined, tip: hasCounts ? `${w.stale} safe to clean or prune · ${w.look} need a look${w.failed ? ` (from the last good scan, ${ago(w.scannedAt, Date.now())} ago)` : ""}. Click to review and clean.` : "Linked Git worktrees. Click to review and clean them." },
    projectItem(v),
    ...(v.snoozed ? [{ id: "snoozed", prio: 2, label: `Snoozed ${v.snoozed}`, tip: `${v.snoozed} snoozed cards are hidden but still count toward the column limits. Click to list or wake them (Z).` }] : []),
    { id: "queue", prio: 4, label: slots ? `Queue · ${slots.live}/${slots.cap} · ${slots.queued} queued` : "Queue · unavailable", tone: slots && slots.live >= slots.cap ? "working" : undefined, tip: "Running tasks against the cap, and what is waiting. Click to open." },
  ];
}

export function fitBar(width, v) {
  if (v.compact) return [];
  const room = width - 20 - HINT_ROOM - (v.notice ? NOTICE_MIN + BAR_GAP : 0);
  const fits = (list) => list.reduce((sum, x) => sum + barCost(x), 0) + (list.length - 1) * BAR_GAP <= room;
  let shown = barItems(v);
  const wt = shown.find((x) => x.id === "wt");
  if (!fits(shown)) wt.more = "";
  while (shown.length > 1 && !fits(shown)) shown = shown.filter((x) => x !== shown.reduce((a, b) => (b.prio > a.prio ? b : a)));
  return shown;
}

function noticeLine(t, notice, cb) {
  return h_flex().id("bar-notice").flex_1().min_w(0).gap(4).items_center().overflow_hidden()
    .child(h_flex().id("bar-notice-text").flex_1().min_w(0).h(18).gap(6).items_center().cursor_pointer().on_mouse_down("left", stop).on_click((_e, cx) => cb.notice(cx)).tooltip(notice.text)
      .child(div().size(6).flex_none().rounded(3).bg(t[NOTICE_TONE[notice.level]]))
      .child(div().flex_1().min_w(0).truncate().text_size(10.5).text_color(t.muted).child(notice.text)))
    .child(headButton(t, "bar-notice-x", "✕", "Dismiss", () => cb.dismiss()));
}

export function toolbar(t, width, v, cb) {
  return h_flex().id("ck-bar").h(H.bar).px(10).gap(BAR_GAP).items_center().flex_none().overflow_hidden().border_b(1).border_color(t.border)
    .children(fitBar(width, v).map((x) => action(t, `bar-${x.id}`, "", x.label + (x.more ?? ""), (cx) => (x.command ? cb.command(x.command) : cb.panel(x.id, cx)), x.tip, true, x.tone)))
    .when(Boolean(v.notice), (el) => el.child(noticeLine(t, v.notice, cb)))
    .when(!v.notice, (el) => el.child(div().flex_1()))
    .when(v.stale, (el) => el.child(div().flex_none().text_size(9.5).text_color(t.working).child("stale")))
    .child(keysHint(t, cb));
}

export function foldedColumn(t, key, col, state, cb) {
  const [, label, tone, short] = COLUMNS.find((c) => c[0] === key);
  const capped = (key === "run" && state.running >= state.cap) || overLimit(key, col);
  return v_flex().id(`col-${key}`).w(H.folded).flex_none().h_full().items_center().pt(8).gap(4).border_r(1).border_color(t.border)
    .cursor_pointer().hover((s) => s.bg(t.raised)).on_click((_e, cx) => cb.fold(key, cx)).tooltip([`Show ${label}`, limitTip(key, col)].filter(Boolean).join(". "))
    .child(div().text_size(9).text_color(t.dim).child("▸"))
    .child(div().text_size(11).font_semibold().text_color(capped ? t.blocked : col.count ? t[tone] : t.dim).child(countText(key, col, state)))
    .child(div().text_size(8.5).text_color(t.dim).child(short));
}

export function emptyRow(t, text) {
  return div().h(H.empty).flex().items_center().justify_center().text_size(11).text_color(t.dim).child(text);
}

function actions(t, key, canSettle, cb, bare) {
  return h_flex().gap(4).flex_none()
    .child(action(t, `re-${key}`, "r", "Reply", (cx) => cb.reply(cx), "Reply to the thread (r)", bare))
    .child(action(t, `op-${key}`, "o", "Open", (cx) => cb.open(cx), "Open the thread (o)", bare))
    .when(canSettle && !bare, (el) => el.child(action(t, `se-${key}`, "s", "Settle", (cx) => cb.settle(cx), "Settle (s)")));
}

function fold(t, key, count, expanded, cb) {
  return div().id(`fold-${key}`).flex_none().px(4).rounded(3).text_size(10).text_color(t.dim).cursor_pointer().hover((s) => s.text_color(t.foreground))
    .on_mouse_down("left", stop).on_click((_e, cx) => cb.toggle(key, cx)).tooltip(`${count} threads`).child(`${expanded ? "▾" : "▸"} ${count}`);
}

function chip(t, text, tone, tip) {
  const el = div().flex_none().px(4).h(13).flex().items_center().rounded(3).bg(t[tone] + "22").text_size(9.5).font_medium().text_color(tone === "dim" ? t.muted : t[tone]).child(text);
  return tip ? el.id(`chip-${tip}`).tooltip(tip) : el;
}

function linkChip(t, id, text, tone, url, tip, cb) {
  return div().id(id).flex_none().px(4).h(13).flex().items_center().rounded(3).bg(t[tone] + "22").text_size(9.5).font_medium().text_color(t[tone])
    .cursor_pointer().hover((s) => s.bg(t[tone] + "44")).on_mouse_down("left", stop).on_click(() => cb.link(url)).tooltip(tip).child(text);
}

const PRIORITY_TONE = { 1: "blocked", 2: "working" };

function issueChips(t, issue) {
  return h_flex().h(H.chips).w_full().flex_none().gap(3).items_center().overflow_hidden()
    .children(issue.problems.map((p) => chip(t, clip(p, 28), "blocked", p)))
    .child(chip(t, issue.stage ?? "no stage", issue.stage === "todo" ? "accent" : "dim"))
    .when(Boolean(issue.priority), (el) => el.child(chip(t, `P${issue.priority}`, PRIORITY_TONE[issue.priority] ?? "dim")))
    .when(Boolean(issue.builder), (el) => el.child(chip(t, `build ${issue.builder}`, "dim")))
    .when(Boolean(issue.reviewer), (el) => el.child(chip(t, `rev ${issue.reviewer}`, "dim")));
}

function originChips(t, e, v, cb) {
  const ticket = v.origin?.ticket;
  return h_flex().min_w(0).gap(3).items_center().overflow_hidden()
    .when(Boolean(ticket), (el) => el.child(linkChip(t, `tk-${e.key}`, `#${ticket.number}`, "accent", ticket.url, `${ticket.repo}#${ticket.number} on GitHub`, cb)))
    .when(Boolean(v.origin?.linear), (el) => el.child(linkChip(t, `ln-${e.key}`, "Linear", "muted", v.origin.linear, "Open the Linear issue", cb)))
    .when(Boolean(v.fell), (el) => el.child(chip(t, "fell back", "working", `Asked for ${shortModel(v.fell)}`)));
}

function modelParts(c, runModel) {
  const base = shortModel(c.model);
  const used = shortModel(runModel);
  const label = [c.taskType, base].filter(Boolean).join(" · ");
  return { label, used: used && used !== base ? used : "" };
}

function modelChips(t, c, runModel) {
  const { label, used } = modelParts(c, runModel);
  return h_flex().gap(3).flex_none().items_center()
    .when(Boolean(label), (el) => el.child(chip(t, label, "dim", c.model || undefined)))
    .when(Boolean(used), (el) => el.child(chip(t, `→ ${used}`, "working", `Ran on ${runModel}`)));
}

const COLD_AFTER = 300000;
const CLAUDE_MODEL = /claude|opus|sonnet|haiku/i;
const NEEDS_KINDS = new Set(["wait", "fail", "stop"]);

const isCold = (v) => (v.variant === "pr" || NEEDS_KINDS.has(v.c.kind)) && v.now - v.c.at > COLD_AFTER && CLAUDE_MODEL.test(v.c.model || v.runModel);

const chipWidth = (text) => 8 + text.length * 5.5;

function readyFit(v, narrow) {
  const [mergeLabel] = mergeOf(v.gh);
  const { label, used } = modelParts(v.c, v.runModel);
  const room = v.colW - 36 - (v.count > 1 ? 30 : 0) - (v.merged ? chipWidth("merged") + 6 : 0);
  const core = chipWidth(`#${v.pr.number}`) + chipWidth("CI ✓") + chipWidth(mergeLabel) + 6;
  const modelWidth = (label ? chipWidth(label) + 3 : 0) + (used ? chipWidth(`→ ${used}`) + 3 : 0);
  const revWidth = chipWidth("rev ✓") + 3;
  const rev = !narrow && core + revWidth <= room;
  const model = core + (rev ? revWidth : 0) + modelWidth <= room;
  return { rev, model, short: core > room };
}

function prChips(t, v, fit) {
  const gh = v.gh;
  const verdict = v.verdict;
  const [mergeLabel, mergeTone, mergeTip] = mergeOf(gh);
  const ci = gh ? gh.ci : "none";
  const { label, used } = modelParts(v.c, v.runModel);
  const dropped = [!fit.rev && `Review ${verdict?.label ?? "none yet"}`, !fit.model && label && `Model ${label}`, !fit.model && used && `Ran on ${used}`].filter(Boolean);
  const prTip = [`PR #${v.pr.number}${gh?.draft ? " (draft)" : ""}`, ...dropped].join(" · ");
  return h_flex().h(H.foot).flex_1().min_w(0).gap(3).items_center().overflow_hidden()
    .child(chip(t, `#${v.pr.number}`, "accent", prTip))
    .child(chip(t, `CI ${gh ? CI_MARK[ci] ?? "?" : "…"}`, CI_TONE[ci] ?? "dim", gh ? `CI ${ci}` : "CI loading"))
    .when(fit.rev, (el) => el.child(chip(t, `rev ${verdict ? VERDICT_MARK[verdict.state] ?? "?" : "—"}`, verdict ? VERDICT_TONE[verdict.state] ?? "dim" : "dim", verdict?.label ?? "No review yet")))
    .when(fit.rev && Boolean(verdict?.note), (el) => el.child(chip(t, verdict.note, "dim", verdict.note)))
    .child(chip(t, fit.short ? (gh?.draft ? "D" : mergeLabel.slice(-1)) : mergeLabel, mergeTone, mergeTip));
}

function statusLine(v) {
  const { c, variant, now } = v;
  if (variant === "backlog") return c.issue ? issueRef(c.issue) : c.context;
  if (c.kind === "run") return c.status === "queued" ? "Queued" : v.since ? `Running ${elapsed(now - v.since)}${v.quiet ? ` · quiet ${elapsed(now - c.at)}` : ""}` : "Running";
  if (c.kind === "done") return v.reviewed ? "Ready to settle" : "Not reviewed yet";
  return c.context;
}

function ageTone(col, ms) {
  if (!AGED_COLUMNS.has(col)) return "muted";
  return ms >= RED_AFTER ? "blocked" : ms >= AMBER_AFTER ? "working" : "muted";
}

function columnAge(t, e, v) {
  const ms = v.now - v.entered;
  const age = ago(v.entered, v.now);
  const named = v.col === "backlog" && v.c.issue ? `Updated ${elapsed(ms)} ago` : `In ${COLUMN_NAME[v.col]} for ${elapsed(ms)}`;
  const text = v.narrow ? age : v.col === "backlog" && v.c.issue ? `updated ${age}` : `in ${COLUMN_NAME[v.col]} ${age}`;
  return div().id(`age-${e.key}`).flex_none().text_size(10).text_color(t[ageTone(v.col, ms)]).tooltip(named).child(text);
}

export function card(t, e, v, input, cb) {
  const { c, count, expanded, selected, mark, replying, now, canSettle, variant, opening } = v;
  const isPr = variant === "pr";
  const narrow = v.narrow;
  const reason = hasReason(c, variant);
  const issue = c.issue;
  const line = isPr ? null : reason ? "Failed" : statusLine(v);
  const fit = isPr ? readyFit(v, narrow) : null;
  const refused = isPr && Boolean(v.refusal);
  const armedHere = v.armed?.key === e.key ? v.armed.kind : null;
  const readyActions = h_flex().gap(4).h(H.foot).min_w(0).when(!refused, (el) => el.flex_1()).items_center().overflow_hidden()
    .when(v.col === "ready", (el) => el.child(action(t, `ap-${e.key}`, "a", armedHere === "approve" ? "Confirm" : "Approve merge", (cx) => cb.approve(cx), armedHere === "approve" ? "Press again to queue the merge relay" : v.blocked ? v.refusal : v.plan?.sha ? `Queue relay #${v.plan.number} ${v.plan.sha.slice(0, 8)}` : "Checking merge plan", narrow).when(v.blocked, (a) => a.opacity(0.5))))
    .when(v.conflict, (el) => el.child(action(t, `rb-${e.key}`, "u", armedHere === "rebase" ? "Confirm" : "Rebase", (cx) => cb.rebase(cx), armedHere === "rebase" ? "Press again to send it back for a rebase" : "Send the builder back to rebase on origin/main and resolve the conflicts (u)", narrow, "blocked")))
    .child(action(t, `pr-${e.key}`, "p", "PR", () => cb.openPr(), "Open the PR (p)", narrow))
    .child(action(t, `op-${e.key}`, "o", narrow ? "Open" : "Thread", (cx) => cb.open(cx), "Open the thread (o)", narrow))
    .when(canSettle && !narrow, (el) => el.child(action(t, `se-${e.key}`, "s", "Settle", (cx) => cb.settle(cx))));
  const quick = variant === "backlog"
    ? h_flex().gap(4).flex_none()
      .when(!issue, (el) => el.child(action(t, `qu-${e.key}`, "q", armedHere === "queue" ? "Confirm" : "Queue", (cx) => cb.queue(cx), armedHere === "queue" ? "Press again to queue" : "Queue this task")))
      .child(action(t, `op-${e.key}`, "o", issue ? "GitHub" : "Open", (cx) => cb.open(cx), issue ? "Open the issue on GitHub (o)" : "Open the thread (o)", narrow))
    : c.kind === "ask"
    ? h_flex().gap(4).flex_none().child(action(t, `op-${e.key}`, "o", narrow ? "Open" : "Decisions", (cx) => cb.command("coordinator.asks"), "Open the coordinator's decisions panel (o)"))
    : actions(t, e.key, canSettle, cb, narrow);
  const meta = h_flex().gap(6).flex_none().items_center().on_mouse_down("left", selectOnly(e.key, cb))
    .when(count > 1, (el) => el.child(fold(t, e.key, count, expanded, cb)))
    .when(v.merged, (el) => el.child(chip(t, "merged", "done")))
    .when(isCold(v), (el) => el.child(chip(t, "cold", "dim", "Prompt cache expired: the next message re-reads the whole context")))
    .when(!refused && (!isPr || fit.model), (el) => el.child(modelChips(t, c, v.runModel)));
  const status = refused
    ? h_flex().id(`why-${e.key}`).flex_1().min_w(0).gap(5).items_center().tooltip(v.refusal).on_mouse_down("left", selectOnly(e.key, cb))
      .child(div().size(6).flex_none().rounded(3).bg(t.blocked))
      .child(div().flex_1().min_w(0).truncate().text_size(10).text_color(t.blocked).child(v.refusal))
    : isPr
    ? prChips(t, v, fit).tooltip(v.plan?.sha ? `Relay #${v.plan.number} ${v.plan.sha.slice(0, 8)}` : "Checking merge plan").on_mouse_down("left", selectOnly(e.key, cb))
    : h_flex().flex_1().min_w(0).gap(5).items_center()
      .child(div().size(6).flex_none().rounded(3).bg(v.quiet ? t.muted : t[TONE[c.kind]]))
      .child(div().flex_1().min_w(0).truncate().text_size(10).text_color(t.muted).child(line));
  const foot = selected
    ? h_flex().h(H.foot).w_full().flex_none().gap(6).items_center().child(isPr ? readyActions : quick)
      .when(refused, (el) => el.child(div().id(`why-${e.key}`).flex_1().min_w(0).truncate().text_size(10).text_color(t.blocked).tooltip(v.refusal).child(v.refusal)))
    : h_flex().h(H.foot).w_full().flex_none().gap(6).items_center().child(status).child(meta);
  const body = v_flex().id(`card-${e.key}`).w_full().h(cardHeight(false, reason, issue) - 4).overflow_hidden().rounded(6).bg(selected ? t.raised : t.surface).border_1()
    .when(!selected, (el) => el.cursor_pointer().hover((s) => s.bg(t.raised)))
    .border_color(selected ? (mark === "focus" ? t.accent : t.input) : t.border).px(8).py(5).gap(2)
    .on_mouse_down("left", (ev, cx) => cb.press(e.key, ev, cx))
    .on_mouse_move((ev) => cb.drag(ev))
    .on_click((_e, cx) => cb.click(e.key, cx))
    .child(h_flex().h(18).flex_none().gap(6).items_center()
      .when(Boolean(c.task), (el) => el.child(div().flex_none().text_size(11.5).font_semibold().text_color(t.foreground).child(c.task)))
      .when(!c.task, (el) => el.child(div().min_w(0).truncate().text_size(11).font_medium().text_color(t.muted).child(c.project ?? "thread")))
      .child(originChips(t, e, v, cb))
      .when(v.asleep, (el) => el.child(chip(t, "snoozed", "dim", "Snoozed: hidden unless you search for it")))
      .when(Boolean(v.sent), (el) => el.child(chip(t, v.sent, "working", "Already sent to the Coordinator. Pressing again is skipped until the card changes.")))
      .child(div().flex_1())
      .child(opening === e.key ? div().flex_none().text_size(10).font_medium().text_color(t.accent).child("Opening…") : v.col === "run" ? div().flex_none().text_size(10).text_color(t.muted).child(ago(c.at, now)) : columnAge(t, e, v)))
    .child(div().w_full().h(H.title).flex_none().overflow_hidden().text_size(11.5).line_height("15px").text_color(t.foreground).child(c.title))
    .when(Boolean(issue), (el) => el.child(issueChips(t, issue)))
    .when(reason, (el) => el.child(div().id(`err-${e.key}`).w_full().h(H.reason - 2).flex_none().overflow_hidden().text_size(10).line_height("13px").text_color(t.muted).tooltip(c.error).child(c.context)))
    .child(div().flex_1())
    .child(foot);
  const cardEl = div().h(cardHeight(false, reason, issue)).w_full().flex_none().px(6).pb(4).child(body);
  if (!replying) return cardEl;
  return v_flex().w_full().flex_none().child(cardEl)
    .child(h_flex().h(H.reply).px(6).pt(2).gap(6).items_start()
      .when(Boolean(v.replyLabel), (el) => el.child(div().flex_none().pt(7).text_size(10.5).font_medium().text_color(t.accent).child(narrow ? "Note" : v.replyLabel)))
      .child(Input.new(input).flex_1().min_w(0).h(28).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_size(11.5).text_color(t.foreground)));
}

export function childRow(t, e, v, cb) {
  const { c, selected, mark, now, opening } = v;
  return h_flex().id(`row-${e.key}`).h(H.child).w_full().flex_none().pl(22).pr(8).gap(6).items_center().rounded(4)
    .when(selected, (el) => el.bg(t.raised).border_1().border_color(mark === "focus" ? t.accent : t.input))
    .when(!selected, (el) => el.cursor_pointer().hover((s) => s.bg(t.raised)))
    .on_mouse_down("left", (ev, cx) => cb.press(e.key, ev, cx))
    .on_mouse_move((ev) => cb.drag(ev))
    .on_click((_e, cx) => cb.click(e.key, cx))
    .child(div().size(6).flex_none().rounded(3).bg(t[TONE[c.kind]]))
    .child(div().flex_1().min_w(0).truncate().text_size(10.5).text_color(t.muted).child(c.title))
    .when(selected, (el) => el.child(actions(t, e.key, c.kind === "done", cb)))
    .child(opening === e.key ? div().flex_none().text_size(9.5).font_medium().text_color(t.accent).child("Opening…") : div().flex_none().text_size(9.5).text_color(t.muted).child(ago(c.at, now)));
}

export const DEC_WIDTH = 920;
const DEC_CAP = 640;
export const DEC_HEIGHT = DEC_CAP;
const DEC_SIDE = 280;
const REPORT_HEIGHT = 200;
const DEC_STRIP = 240;
const SETTLEABLE = ["done", "fail", "stop"];
export const NOTE_LABEL = "Send back with a note";

function checkWords(gh, verdict) {
  const ci = { pass: "CI passing", fail: "CI failing", pending: "CI running", none: "no CI" }[gh?.ci] ?? "CI not loaded";
  const merge = { MERGEABLE: "mergeable", CONFLICTING: "has merge conflicts" }[gh?.mergeable] ?? "merge state unknown";
  return `${ci}, ${merge}, ${verdict ? verdict.label.replace(/^rev /, "review ") : "no review yet"}.`;
}

const OK = ["✓", "done"];
const BAD = ["✗", "blocked"];
const WAIT = ["…", "working"];
const UNKNOWN = ["?", "dim"];
const CI_CHECK = { pass: [...OK, "All checks passed"], fail: [...BAD, "A check failed"], pending: [...WAIT, "Checks are still running"], none: [...UNKNOWN, "No checks are configured"] };
const MERGE_STATE = {
  CLEAN: [...OK, "All requirements are met"],
  HAS_HOOKS: [...OK, "All requirements are met"],
  BLOCKED: [...BAD, "Blocked by a branch rule or a required review"],
  BEHIND: [...WAIT, "Behind the base branch"],
  UNSTABLE: [...WAIT, "A check that is not required has failed"],
  DRAFT: [...WAIT, "Still a draft"],
  DIRTY: [...BAD, "Has conflicts with the base branch"],
};
const CONFLICTS = { MERGEABLE: [...OK, "No conflicts"], CONFLICTING: [...BAD, "Conflicts with the base branch"] };
const HUMAN_REVIEW = { APPROVED: "approved on GitHub", CHANGES_REQUESTED: "changes requested on GitHub", REVIEW_REQUIRED: "no GitHub review yet" };

function checksOf(gh, verdict) {
  const loaded = (map, key, none) => map[key] ?? (gh ? [...UNKNOWN, none] : [...WAIT, "Not loaded yet"]);
  const agent = verdict ? { pass: "agent review found nothing blocking", fail: `agent review ${verdict.label.replace(/^rev /, "")}`, unknown: "agent review unclear", unverified: "review unreadable, retrying", loading: "checking the agent review" }[verdict.state] : "no agent review yet";
  const human = HUMAN_REVIEW[gh?.review] ?? "no GitHub verdict";
  const reviewMark = verdict?.state === "fail" || gh?.review === "CHANGES_REQUESTED" ? BAD : verdict?.state === "pass" ? OK : verdict?.state === "loading" ? WAIT : UNKNOWN;
  return [
    ["CI", ...loaded(CI_CHECK, gh?.ci, "CI state not reported")],
    ["Merge state", ...loaded(MERGE_STATE, gh?.mergeState, "Merge state not reported")],
    ["Conflicts", ...loaded(CONFLICTS, gh?.mergeable, "GitHub has not worked out conflicts yet")],
    ["Review", ...reviewMark, `${agent[0].toUpperCase()}${agent.slice(1)}, ${human}`],
  ];
}

export function decisionOf(col, g, info, verdict, now) {
  const name = g.task || g.title;
  const c = g.primary;
  const pr = info.status === "open" ? info.pr : null;
  const settle = (col === "done" || col === "dead") && g.threads.some((x) => SETTLEABLE.includes(x.kind));
  const sendBack = (col === "ready" || col === "review") && pr && verdict?.state === "fail";
  const other = [
    { id: "open", key: "o", label: "Open thread" },
    ...((c.kind === "wait" && col === "needs") || sendBack ? [] : [{ id: "reply", key: "r", label: "Reply" }]),
    ...(PR_LANES.has(col) ? [{ id: "note", key: "d", label: NOTE_LABEL }] : []),
    ...(settle ? [{ id: "settle", key: "s", label: "Settle" }] : []),
    ...(info.pr ? [{ id: "pr", key: "p", label: "Open PR" }] : []),
  ];
  const age = ago(g.at, now);
  if (c.kind === "ask") {
    return {
      headline: name,
      primary: { id: "open", key: "o", label: "Open decisions" },
      why: [c.context, `Asked ${age} ago`],
      other: [],
      checks: null,
    };
  }
  if (!DECIDES.has(col)) {
    return {
      headline: g.task ? `${g.task} · ${g.title}` : g.title,
      primary: { id: "open", key: "o", label: "Open thread" },
      why: [`${c.context} · ${g.project} · updated ${age}`],
      other: other.filter((x) => x.id !== "open"),
      checks: null,
    };
  }
  const checks = pr ? checksOf(info.gh, verdict) : null;
  if (col === "cifail" && pr) {
    return { headline: `Fix PR #${pr.number}`, primary: { id: "answer", key: "r", label: "Send back" }, why: [g.task ? `${g.task} · ${g.title}` : g.title, checkWords(info.gh, verdict)], other, checks };
  }
  if ((col === "ready" || col === "review") && pr) {
    const title = g.task ? `${g.task} · ${g.title}` : g.title;
    if (!verdict) return { headline: `Review PR #${pr.number}`, primary: { id: "review", key: "t", label: "Start review", armed: "Confirm review" }, why: [title, "No review yet, so this can't merge."], other, checks };
    if (verdict.state === "loading") return { headline: `PR #${pr.number}`, primary: { id: "wait", key: "", label: "Checking review…" }, why: [title, checkWords(info.gh, verdict)], other, checks };
    if (sendBack) return { headline: `Fix PR #${pr.number}`, primary: { id: "answer", key: "r", label: "Send back" }, why: [title, `Review failed: ${verdict.label.replace(/^rev /, "")}.`], other, checks };
    return { headline: `Merge PR #${pr.number}`, primary: { id: "merge", key: "a", label: "Approve merge", armed: "Confirm relay" }, why: [title, checkWords(info.gh, verdict)], other, checks };
  }
  if (c.kind === "wait") {
    return { headline: `Answer ${name}'s question`, primary: { id: "answer", key: "r", label: "Reply" }, why: [c.context, `${g.project} · waiting ${age}`], other, checks };
  }
  const retry = c.kind === "fail";
  return {
    headline: `${retry ? "Retry" : "Resume"} ${name}`,
    primary: { id: retry ? "retry" : "resume", key: "t", label: retry ? "Retry" : "Resume", armed: retry ? "Confirm retry" : "Confirm resume" },
    why: [c.error ?? c.context, `${g.title} · ${retry ? "failed" : "stopped"} ${age} ago`],
    other,
    checks,
  };
}

export const ABANDON_LABEL = "Abandon reason";

export function issueDecision(g, ticket, replying, abandonArmed) {
  const issue = g.issue;
  const show = ticket?.status === "ok" ? ticket.issue : null;
  const x = show ?? issue;
  const block = ticket?.status === "fail" ? "Could not load the ticket" : startBlock(show);
  const hint = replying ? (abandonArmed ? "Press Enter again to close this issue as not planned. Esc cancels." : "Type the reason, press Enter to arm, then Enter again to close this issue as not planned. Esc cancels.") : block ? `Can't start: ${block}.` : "Press t or Enter to arm, then t or click to confirm.";
  return {
    headline: g.task ? `${g.task} · ${g.title}` : g.title,
    primary: { id: "start", key: "t", label: "Start", armed: "Confirm start", disabled: block },
    why: [issueRef(issue), [x.stage ?? "no stage", x.priority ? `P${x.priority}` : "no priority", x.type ?? "no type"].join(" · ")],
    other: [{ id: "edit", key: "e", label: "Edit on GitHub" }, { id: "abandon", key: "x", label: "Abandon" }],
    checks: null,
    hint,
  };
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function section(t, title, right) {
  return h_flex().w_full().h(22).gap(8).items_center().border_b(1).border_color(t.border)
    .child(div().flex_1().text_size(10.5).font_semibold().text_color(t.muted).child(title))
    .when(Boolean(right), (el) => el.child(div().flex_none().text_size(10.5).text_color(t.dim).child(right)));
}

function checkRows(t, rows) {
  return v_flex().w_full().gap(2)
    .child(section(t, "Checks"))
    .children(rows.map(([name, mark, tone, reason]) => h_flex().w_full().min_h(24).gap(8).items_start().py(3)
      .child(div().w(16).flex_none().text_size(12).font_semibold().text_color(t[tone === "dim" ? "muted" : tone]).child(mark))
      .child(div().w(84).flex_none().text_size(11.5).font_medium().text_color(t.foreground).child(name))
      .child(div().flex_1().min_w(0).text_size(11.5).line_height("17px").text_color(t.muted).child(reason))));
}

function fileRows(t, files) {
  const count = (key) => files.files.reduce((sum, f) => sum + f[key], 0);
  const summary = files.status === "ok" ? `${plural(files.files.length, "file")}  +${count("add")} −${count("del")}` : null;
  const body = files.status === "loading"
    ? [div().w_full().h(24).flex().items_center().text_size(11.5).text_color(t.dim).child("Loading changed files…")]
    : files.status === "fail"
      ? [div().w_full().py(4).text_size(11.5).line_height("17px").text_color(t.blocked).child(`Could not load changed files: ${files.error}`)]
      : files.files.length
        ? [...files.files.map((f, i) => h_flex().id(`dec-file-${i}`).w_full().min_h(22).gap(8).items_start().py(2)
          .child(div().flex_1().min_w(0).text_size(11.5).line_height("17px").text_color(t.foreground).child(f.path))
          .child(div().flex_none().text_size(11).font_medium().text_color(f.add ? t.done : t.dim).child(`+${f.add}`))
          .child(div().flex_none().text_size(11).font_medium().text_color(f.del ? t.blocked : t.dim).child(`−${f.del}`))),
          ...(files.more ? [div().w_full().py(4).text_size(11.5).text_color(t.dim).child(`+${files.more} more files not shown`)] : [])]
        : [div().w_full().h(24).flex().items_center().text_size(11.5).text_color(t.dim).child("No files changed")];
  return v_flex().w_full().gap(2).child(section(t, "Changed files", summary)).children(body);
}

function primaryButton(t, d, armed, outdated, run) {
  const label = outdated ? (d.primary.id === "merge" || d.primary.id === "wait" ? "Re-check" : "Out of date, close") : armed ? d.primary.armed : d.primary.label;
  return h_flex().id("dec-primary").h(30).px(14).gap(8).items_center().flex_none().rounded(6)
    .bg(armed ? t.blocked : t.solid).text_color(armed ? t.background : t.solid_foreground).text_size(12.5).font_semibold()
    .cursor_pointer().hover((s) => s.opacity(0.9)).on_click((e, cx) => e.click_count > 1 || run(cx))
    .when((d.primary.id === "wait" && !outdated) || Boolean(d.primary.disabled), (el) => el.opacity(0.5))
    .child(label)
    .when(!outdated && Boolean(d.primary.key), (el) => el.child(div().text_size(10.5).font_medium().child(d.primary.key)));
}

const VERDICT_TEXT = (verdict) => (verdict.state === "loading" ? "checking" : verdict.label.replace(/^rev /, ""));

function ticketBody(t, ticket) {
  if (!ticket || ticket.status === "loading") return div().text_size(12.5).text_color(t.dim).child("Loading ticket…");
  if (ticket.status === "fail") return div().w_full().text_size(12.5).line_height("18px").text_color(t.blocked).child(`Could not load the ticket: ${ticket.error}`);
  if (ticket.text === null) return div().text_size(12.5).text_color(t.dim).child("This thread has no messages yet.");
  return TextView.markdown("dec-ticket-md", ticket.text).selectable(true).scrollable(true).size_full();
}

function field(t, name, value) {
  return h_flex().w_full().min_h(18).gap(8).items_start()
    .child(div().w(52).flex_none().text_size(11).text_color(t.dim).child(name))
    .child(div().flex_1().min_w(0).text_size(11.5).line_height("17px").text_color(t.foreground).child(value));
}

function ticketLinks(t, ticket, cb) {
  const { origin, changed, fell, issueError } = ticket;
  const gh = origin.ticket;
  return v_flex().w_full().gap(4)
    .child(section(t, "Ticket"))
    .child(h_flex().w_full().gap(6).items_center().flex_wrap()
      .when(Boolean(gh), (el) => el.child(action(t, "dec-gh", "", `${gh.repo.split("/").at(-1)}#${gh.number}`, () => cb.link(gh.url), gh.url, true)))
      .when(Boolean(origin.linear), (el) => el.child(action(t, "dec-linear", "", "Linear", () => cb.link(origin.linear), origin.linear, true)))
      .when(Boolean(changed), (el) => el.child(chip(t, "changed since launch", "working", "The issue body no longer matches what the agent was given")))
      .when(Boolean(fell), (el) => el.child(chip(t, "fell back", "working", `Asked for ${fell}`))))
    .when(Boolean(issueError), (el) => el.child(div().w_full().text_size(11).line_height("16px").text_color(t.blocked).child(`Could not load the ticket: ${issueError}`)));
}

function pickerRow(t, label, family, value, options, open, cb) {
  return v_flex().w_full().gap(3)
    .child(h_flex().w_full().min_h(20).gap(8).items_center()
      .child(div().w(52).flex_none().text_size(11).text_color(t.dim).child(label))
      .child(action(t, `pick-${family}`, "", `${value ?? "none"} ▾`, (cx) => cb.pick(family, cx), `Change ${label.toLowerCase()}`, true)))
    .when(open, (el) => el.child(h_flex().w_full().gap(4).flex_wrap().pl(60)
      .children(options.map((o) => action(t, `set-${family}-${o}`, "", o, (cx) => cb.setField(family, o, cx), undefined, true, String(o) === String(value ?? "none") ? "accent" : undefined)))));
}

const ATTEMPT_DATE = (iso) => iso.slice(0, 16).replace("T", " ");

function issuePanel(t, v, cb) {
  const { ticket, picker } = v;
  const show = ticket?.status === "ok" ? ticket.issue : null;
  const x = show ?? v.issue;
  const cfg = ticket?.config;
  const intents = show?.ledger.filter((e) => e.kind === "intent") ?? [];
  const attempt = (e) => {
    const receipt = show.ledger.some((r) => r.kind === "receipt" && r.attempt === e.attempt);
    return `#${e.attempt} ${e.builder} / ${e.reviewer} · ${ATTEMPT_DATE(e.at)}${receipt ? " · queued" : " · no receipt"}`;
  };
  const missing = show ? Object.entries(show.template).filter(([, status]) => status !== "ok") : [];
  const open = show?.blockers ?? [];
  const abandoned = show?.ledger.filter((e) => e.kind === "abandon") ?? [];
  const row = (name, value) => field(t, name, value);
  return v_flex().id("dec-side").w(DEC_SIDE).h_full().min_h(0).flex_none().overflow_y_scrollbar().border_l(1).border_color(t.border)
    .child(v_flex().w_full().flex_none().px(14).py(12).gap(10)
      .child(v_flex().w_full().gap(4)
        .child(section(t, "Issue"))
        .child(h_flex().w_full().min_h(20).gap(8).items_center()
          .child(div().w(52).flex_none().text_size(11).text_color(t.dim).child("Link"))
          .child(action(t, "dec-issue-link", "", `${x.repo.split("/").at(-1)}#${x.number}`, () => cb.link(x.url), x.url, true)))
        .when(Boolean(show), (el) => el.child(row("State", show.state.toLowerCase())))
        .child(row("Type", x.type ?? "none"))
        .when(Boolean(show && changedSinceLaunch(show)), (el) => el.child(h_flex().w_full().child(chip(t, "changed since launch", "working", "The issue body no longer matches what the agent was given")))))
      .when(Boolean(cfg), (el) => el.child(v_flex().w_full().gap(4)
        .child(section(t, "Fields"))
        .child(pickerRow(t, "Stage", "stage", x.stage, pickerOptions(cfg, "stage"), picker === "stage", cb))
        .child(pickerRow(t, "Priority", "priority", x.priority, pickerOptions(cfg, "priority"), picker === "priority", cb))
        .child(pickerRow(t, "Builder", "builder", x.builder, pickerOptions(cfg, "builder"), picker === "builder", cb))
        .child(pickerRow(t, "Reviewer", "reviewer", x.reviewer, pickerOptions(cfg, "reviewer"), picker === "reviewer", cb))))
      .when(x.problems.length > 0, (el) => el.child(v_flex().w_full().gap(2)
        .child(section(t, "Problems"))
        .children(x.problems.map((p) => div().w_full().text_size(11.5).line_height("16px").text_color(t.blocked).child(p)))))
      .when(Boolean(show), (el) => el.child(v_flex().w_full().gap(2)
        .child(section(t, "Blockers"))
        .children(open.length ? open.map((b) => div().w_full().text_size(11.5).line_height("16px").text_color(b.state === "OPEN" ? t.blocked : t.muted).child(`${b.repo.split("/").at(-1)}#${b.number} ${b.state.toLowerCase()} · ${b.title}`)) : [div().text_size(11.5).text_color(t.dim).child("None")])))
      .when(Boolean(show), (el) => el.child(v_flex().w_full().gap(2)
        .child(section(t, "Template"))
        .children(missing.length ? missing.map(([name, status]) => div().w_full().text_size(11.5).line_height("16px").text_color(t.blocked).child(`${name}: ${status}`)) : [div().text_size(11.5).text_color(t.dim).child("All sections filled")])))
      .when(intents.length + abandoned.length > 0, (el) => el.child(v_flex().w_full().gap(2)
        .child(section(t, "Attempts"))
        .children([...intents.map((e) => div().w_full().text_size(11.5).line_height("16px").text_color(t.muted).child(attempt(e))), ...abandoned.map((e) => div().w_full().text_size(11.5).line_height("16px").text_color(t.muted).child(`abandoned: ${e.reason}`))]))));
}

function ticketPanel(t, v, cb) {
  const { ticket, verdict, d, files } = v;
  const record = ticket?.status === "ok" ? ticket.record : null;
  const details = record ? [["Status", record.status], ["Model", shortModel(record.model)], ["Type", record.taskType], ["Branch", record.branch]].filter(([, value]) => value) : [];
  const verdictLine = verdict ? `${VERDICT_MARK[verdict.state]} ${VERDICT_TEXT(verdict)}` : "No review yet";
  return v_flex().id("dec-side").w(DEC_SIDE).h_full().min_h(0).flex_none().overflow_y_scrollbar().border_l(1).border_color(t.border)
    .child(v_flex().w_full().flex_none().px(14).py(12).gap(10)
      .child(v_flex().w_full().gap(2)
        .child(section(t, "Details"))
        .children(details.map(([name, value]) => field(t, name, value)))
        .child(h_flex().w_full().min_h(18).gap(8).items_start()
          .child(div().w(52).flex_none().text_size(11).text_color(t.dim).child("Review"))
          .child(div().flex_1().min_w(0).text_size(11.5).font_medium().text_color(verdict ? t[VERDICT_TONE[verdict.state]] : t.muted).child(verdictLine))))
      .when(Boolean(record?.pullRequests.length), (el) => el.child(v_flex().w_full().gap(4)
        .child(section(t, "Pull requests"))
        .child(h_flex().w_full().gap(6).flex_wrap()
          .children(record.pullRequests.map((p) => action(t, `dec-pr-${p.number}`, "", `${p.repository.split("/").at(-1)}#${p.number} ${p.state.toLowerCase()}`, () => cb.link(p.url), p.url, true))))))
      .when(Boolean(ticket?.origin?.ticket || ticket?.origin?.linear), (el) => el.child(ticketLinks(t, ticket, cb)))
      .when(Boolean(d.checks), (el) => el.child(checkRows(t, d.checks)))
      .when(Boolean(d.checks && files), (el) => el.child(fileRows(t, files)))
      .when(Boolean(record), (el) => el.child(v_flex().w_full().gap(4)
        .child(section(t, "Latest report"))
        .child(ticket.report === null
          ? div().text_size(11.5).text_color(t.dim).child("No report yet")
          : div().w_full().h(REPORT_HEIGHT).text_size(11.5).text_color(t.foreground).child(TextView.markdown("dec-report-md", ticket.report).selectable(true).scrollable(true).size_full())))));
}

export function decisionView(t, v, input, cb) {
  const { col, d, armed, armedKind, outdated, replying, outcome } = v;
  const [, label, tone] = COLUMNS.find((c) => c[0] === col);
  const hint = d.hint ?? (outdated ? "This view is over a minute old. Nothing happens until it is re-checked." : d.primary.id === "open" ? "Opens the thread in T3 Code." : d.primary.id === "answer" ? "Opens a reply box. Nothing is sent until you press Enter in it." : d.primary.id === "wait" ? "Nothing can be merged until the review check loads." : `Press ${d.primary.key} or Enter to arm, then ${d.primary.key} or click to confirm.`);
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child(label))
      .child(headButton(t, "dec-close", "✕", "Close", () => cb.close())))
    .child(h_flex().flex_1().min_h(0).w_full()
      .child(v_flex().flex_1().min_w(0).min_h(0)
        .child(v_flex().id("dec-strip").w_full().flex_none().max_h(DEC_STRIP).overflow_y_scrollbar().border_b(1).border_color(t.border)
          .child(v_flex().w_full().flex_none().px(16).py(14).gap(12)
            .child(div().w_full().text_size(18).line_height("24px").font_semibold().text_color(t.foreground).child(d.headline))
            .child(v_flex().w_full().gap(4).children(d.why.map((line) => div().w_full().text_size(12.5).line_height("18px").text_color(t.muted).child(line))))
            .child(h_flex().gap(10).items_center().child(primaryButton(t, d, armed, outdated, (cx) => cb.primary(cx))))
            .child(div().w_full().text_size(10.5).text_color(t.dim).child(hint))
            .when(Boolean(outcome), (el) => el.child(div().w_full().p(8).rounded(6).border_1().border_color(t.blocked).text_size(12).line_height("17px").text_color(t.foreground).child(outcome.text)))
            .when(replying, (el) => el.child(h_flex().w_full().h(30).gap(8).items_center()
              .when(Boolean(v.replyLabel), (r) => r.child(div().flex_none().text_size(11).font_medium().text_color(t.accent).child(v.replyLabel)))
              .child(Input.new(input).flex_1().min_w(0).h(30).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_size(12).text_color(t.foreground))))
            .child(h_flex().gap(6).items_center().flex_wrap()
              .child(div().text_size(10.5).text_color(t.dim).child("Other"))
              .children(d.other.map((x) => action(t, `dec-${x.id}`, x.key, x.id === "settle" && armedKind === "settle" ? "Confirm settle" : x.label, (cx) => cb.other(x.id, cx)))))))
        .child(div().id("dec-ticket").flex_1().min_h(0).w_full().px(16).py(12).text_size(12.5).line_height("19px").text_color(t.foreground).child(ticketBody(t, v.ticket))))
      .child(v.issue ? issuePanel(t, v, cb) : ticketPanel(t, v, cb)));
}

export const DECIDES = new Set(["needs", "cifail", "review", "ready"]);
export const KEY_TABLE = [
  { keys: "⏎", group: "Card", all: "Open the card's ticket and decision pop-up" },
  { keys: "a", group: "Card", all: "Approve the merge, press twice (Approved/Ready cards)" },
  { keys: "o", group: "Card", all: "Open the thread (the issue on GitHub for ticket cards)" },
  { keys: "r", group: "Card", all: "Reply to the thread" },
  { keys: "d", group: "Card", all: "Send back with a note: reply to the thread (PR cards; on Needs you cards it is a plain reply)" },
  { keys: "s", group: "Card", all: "Settle the card's finished threads" },
  { keys: "p", group: "Card", all: "Open the pull request" },
  { keys: "u", group: "Card", all: "Send a conflicting PR back to its builder for a rebase, press twice (PR cards)" },
  { keys: "z", group: "Card", all: "Snooze the card until tomorrow, 3 days, next Monday, or until it changes (Needs you, CI failed, Review pending and Approved/Ready cards)" },
  { keys: "q", group: "Card", all: "Queue the task, press twice (Backlog cards without a GitHub issue)" },
  { keys: "n", group: "Move", all: "Jump to the oldest Needs you card, then CI failed, then Approved/Ready, and cycle" },
  { keys: "⌥⌘N", group: "Move", all: "Jump to the next blocked agent in any space, else the next Needs you card (bind cockpit.needs)" },
  { keys: "j k", group: "Move", all: "Next or previous card (the arrow keys work too)" },
  { keys: "h l", group: "Move", all: "Previous or next column (section on a narrow board)" },
  { keys: "g G", group: "Move", all: "First or last card in the column" },
  { keys: "→ ←", group: "Move", all: "Show or hide a task's other threads" },
  { keys: "S", group: "Board", all: "Settle every reviewed card, press twice (Done)" },
  { keys: "A", group: "Board", all: "Settle every finished card, press twice (Done)" },
  { keys: "M", group: "Board", all: "Approve every PR with a passing review, press twice (Approved/Ready)" },
  { keys: "F", group: "Board", all: "Retry failed cards in groups by error kind (Needs you)" },
  { keys: "U", group: "Board", all: "Send every conflicting PR back for a rebase, press twice (every PR lane; the lane head button does one lane)" },
  { keys: "Z", group: "Board", all: "List snoozed cards, wake one or all" },
  { keys: "f", group: "Board", all: "Fold or show this column" },
  { keys: "e", group: "Board", all: "Open this column in a pop-up" },
  { keys: "b", group: "Board", all: "Fold or show Backlog" },
  { keys: "P", group: "Board", all: "Choose one project to show, or all projects" },
  { keys: "/", group: "Board", all: "Search cards by ticket ID or title, with quick filters. Enter returns to the board, Esc clears" },
  { keys: "R", group: "Board", all: "Reload the board now" },
  { keys: "?", group: "Board", all: "Show this list" },
];

const QUICK_FILTERS = [
  ["p1", "P1", "Only priority 1 tickets"],
  ["ci", "CI failing", "Only cards whose pull request has failing CI"],
  ["conflict", "Conflict", "Only cards whose pull request has merge conflicts"],
  ["blocked", "Blocked", "Only tickets with problems and pull requests that can't merge yet"],
];

function quickChip(t, id, label, tip, on, run) {
  return div().id(`qf-${id}`).h(20).px(8).flex().items_center().flex_none().rounded(10).border_1().border_color(on ? t.accent : t.input).bg(on ? t.accent + "33" : t.raised)
    .text_size(10.5).font_medium().text_color(on ? t.foreground : t.muted).cursor_pointer().hover((s) => s.bg(t.selected))
    .on_mouse_down("left", stop).on_click((_e, cx) => run(cx)).tooltip(tip).child(label);
}

export function searchRow(t, v, input, cb) {
  return h_flex().id("ck-search").h(H.search).px(10).gap(6).items_center().flex_none().overflow_hidden().border_b(1).border_color(t.border)
    .child(div().flex_none().text_size(10.5).font_semibold().text_color(t.muted).child("/"))
    .child(div().flex_none().on_mouse_down("left", stop).child(Input.new(input).w(v.compact ? 120 : 220).h(22).px(8).rounded(4).border_1().border_color(v.searching ? t.accent : t.input).bg(t.background).text_size(11).text_color(t.foreground)))
    .children(QUICK_FILTERS.map(([id, label, tip]) => quickChip(t, id, label, tip, v.quick.has(id), (cx) => cb.quick(id, cx))))
    .child(div().flex_1())
    .when(!v.compact, (el) => el.child(div().flex_none().text_size(9.5).text_color(t.muted).child(`${v.shown} of ${v.total} cards`)))
    .child(headButton(t, "search-close", "✕", "Clear the search and filters (Esc)", (cx) => cb.clearSearch(cx)));
}

function keysHint(t, cb) {
  return h_flex().id("keys-help").flex_none().gap(4).items_center().cursor_pointer().hover((s) => s.bg(t.raised)).px(3).rounded(3).on_click((_e, cx) => cb.keys(cx))
    .child(div().text_size(9.5).font_medium().text_color(t.muted).child("?"))
    .child(div().text_size(9.5).text_color(t.dim).child("all keys"));
}

export const SHEET_WIDTH = 640;
export const sheetHeight = () => Math.min(DEC_CAP, 34 + 24 + [...new Set(KEY_TABLE.map((r) => r.group))].length * 30 + KEY_TABLE.length * 24);

export function keySheet(t, cb) {
  const groups = [...new Set(KEY_TABLE.map((r) => r.group))];
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child("Keys"))
      .child(headButton(t, "keys-close", "✕", "Close", () => cb.close())))
    .child(v_flex().id("keys-body").flex_1().min_h(0).overflow_y_scrollbar()
      .child(v_flex().w_full().flex_none().px(16).py(10).gap(10)
        .children(groups.map((group) => v_flex().w_full().gap(2)
          .child(section(t, group))
          .children(KEY_TABLE.filter((r) => r.group === group).map((r) => h_flex().w_full().min_h(22).gap(10).items_start().py(2)
            .child(div().w(54).flex_none().text_size(11.5).font_semibold().text_color(t.foreground).child(r.keys))
            .child(div().flex_1().min_w(0).text_size(11.5).line_height("17px").text_color(t.muted).child(r.all))))))));
}

export const PROJECT_ROW = 30;
export const projectSheetHeight = (rows) => Math.min(DEC_CAP, 34 + 20 + rows * PROJECT_ROW);

export function projectSheet(t, chooser, chosen, cb) {
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child(chooser.title))
      .child(headButton(t, "project-close", "✕", "Close", () => cb.close())))
    .child(v_flex().id("project-body").flex_1().min_h(0).overflow_y_scrollbar()
      .child(v_flex().w_full().flex_none().p(10).children(chooser.list.map((p, i) => h_flex().id(`project-${i}`).w_full().h(PROJECT_ROW).px(8).gap(8).items_center().rounded(4).cursor_pointer()
        .bg(i === chosen ? t.selected : t.chrome).hover((s) => s.bg(t.raised)).on_click(() => cb.pick(p))
        .child(div().w(10).flex_none().text_size(11).text_color(t.done).child(p.name === chooser.current ? "✓" : ""))
        .child(div().flex_1().min_w(0).truncate().text_size(12).font_medium().text_color(t.foreground).child(p.name ?? "All projects"))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(String(p.count)))))));
}

const ROW_SHEET_ROW = 50;
export const rowSheetHeight = (rows) => Math.min(DEC_CAP, 34 + 20 + rows * ROW_SHEET_ROW);

export function rowSheet(t, sheet, chosen, armed, cb) {
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child(sheet.title))
      .child(headButton(t, "rows-close", "✕", "Close", () => cb.close())))
    .child(v_flex().id("rows-body").flex_1().min_h(0).overflow_y_scrollbar()
      .child(v_flex().w_full().flex_none().p(10).children(sheet.rows.map((r, i) => h_flex().id(`rs-${i}`).w_full().h(ROW_SHEET_ROW).px(8).gap(10).items_center().rounded(4)
        .bg(i === chosen ? t.selected : t.chrome)
        .child(div().w(sheet.leadW).flex_none().truncate().text_size(12).font_semibold().text_color(t.foreground).child(r.lead))
        .child(v_flex().id(`rs-text-${i}`).flex_1().min_w(0).gap(2).tooltip(r.sample)
          .child(div().w_full().truncate().text_size(12).font_medium().text_color(t.foreground).child(r.label))
          .child(div().w_full().truncate().text_size(10.5).text_color(t.muted).child(r.sample)))
        .child(action(t, `rs-act-${i}`, "", armed?.kind === sheet.kind && armed.key === r.id ? "Confirm" : r.action, (cx) => cb.act(r, cx), r.tip, true, sheet.kind === "retry" ? "blocked" : undefined))))));
}

export const noticeHeight = (notice) => Math.min(DEC_CAP, 34 + 24 + Math.ceil(notice.text.length / 70) * 18 + notice.items.length * 56);

export function noticeSheet(t, notice, cb) {
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().size(7).flex_none().rounded(4).bg(t[NOTICE_TONE[notice.level]]))
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child("Board message"))
      .child(headButton(t, "notice-close", "✕", "Close", () => cb.close())))
    .child(v_flex().id("notice-body").flex_1().min_h(0).overflow_y_scrollbar()
      .child(v_flex().w_full().flex_none().px(16).py(10).gap(10)
        .child(div().w_full().text_size(12.5).line_height("18px").text_color(t.foreground).child(notice.text))
        .children(notice.items.map((x) => v_flex().w_full().gap(2)
          .child(h_flex().gap(6).items_center()
            .child(div().size(6).flex_none().rounded(3).bg(t[x.ok ? "done" : "blocked"]))
            .child(div().text_size(11.5).font_semibold().text_color(t.foreground).child(x.name)))
          .child(div().w_full().pl(12).text_size(11.5).line_height("17px").text_color(t.muted).child(x.text))))));
}

export function thumb(t, top, view, total) {
  const h = Math.max(24, (view * view) / total);
  return div().absolute().right(2).top(Math.round((view - h) * (top / (total - view)))).w(3).h(Math.round(h)).rounded(2).bg(t.input);
}
