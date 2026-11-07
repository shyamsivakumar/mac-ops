// Elements of the board. Every row has a fixed height, so each column can window itself.

import { div } from "gpui-kit";
import { v_flex, h_flex, Input } from "gpui-base";
import { shortModel } from "./hub.js";

export const H = { bar: 26, head: 42, sub: 16, card: 86, foot: 18, title: 30, child: 24, reply: 34, empty: 50, folded: 44 };
const TONE = { wait: "blocked", fail: "blocked", stop: "working", run: "working", done: "done", idle: "idle" };
const CI_TONE = { pass: "done", fail: "blocked", pending: "working", none: "dim" };
const CI_MARK = { pass: "✓", fail: "✗", pending: "…", none: "—" };
const VERDICT_MARK = { pass: "✓", fail: "✗", unknown: "?", loading: "…" };
const VERDICT_TONE = { pass: "done", fail: "blocked", unknown: "dim", loading: "working" };
export const LOADING_VERDICT = { state: "loading", label: "rev …" };
export const canMerge = (verdict) => verdict?.state === "pass" || verdict?.state === "unknown";
const MERGE = { MERGEABLE: ["merge ✓", "done", "Mergeable"], CONFLICTING: ["merge ✗", "blocked", "Merge conflict"], UNKNOWN: ["merge ?", "dim", "Merge status unknown"] };
export const COLUMNS = [["backlog", "Backlog", "idle", "Backlog"], ["needs", "Needs you", "blocked", "Needs"], ["run", "Running", "working", "Running"], ["ready", "Ready to merge", "accent", "Ready"], ["done", "Done · not settled", "done", "Done"]];
const stop = (_e, cx) => cx.stop_propagation();
const selectOnly = (key, cb) => (e, cx) => {
  cb.press(key, e, cx);
  cx.stop_propagation();
};

export const cardHeight = (replying) => H.card + (replying ? H.reply : 0);

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
    used += part[0].length * 5.2 + 10;
    if (used > room) break;
    fit.push(part);
  }
  return fit;
}

function headButton(t, id, glyph, tip, run) {
  return div().id(id).size(18).flex_none().flex().items_center().justify_center().rounded(4).text_size(12).text_color(t.muted)
    .cursor_pointer().hover((s) => s.bg(t.selected).text_color(t.foreground)).on_mouse_down("left", stop).on_click((_e, cx) => run(cx)).tooltip(tip).child(glyph);
}

export function columnHead(t, key, col, state, cb) {
  const [, label, tone, short] = COLUMNS.find((c) => c[0] === key);
  const capped = key === "run" && state.running >= state.cap;
  const tight = state.colW < 260;
  return v_flex().id(`fold-${key}`).h(H.head).flex_none().border_b(1).border_color(t.border)
    .when(!state.popup, (el) => el.cursor_pointer().on_click((_e, cx) => cb.fold(key, cx)).tooltip(`${state.collapsed ? "Show" : "Hide"} ${label}`))
    .child(h_flex().h(H.head - H.sub).px(10).gap(6).items_center().overflow_hidden()
      .when(!state.popup, (el) => el.child(div().w(10).text_size(9).text_color(t.dim).child(state.collapsed ? "▸" : "▾")))
      .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
      .child(div().min_w(0).text_size(11).font_semibold().text_color(t.foreground).truncate().child(tight && (key === "done" || key === "ready") ? short : label))
      .child(div().text_size(11).font_semibold().text_color(capped ? t.blocked : col.count ? t[tone] : t.dim).child(key === "run" ? `${state.running}/${state.cap}` : String(col.count)))
      .child(div().flex_1())
      .when(key === "done" && state.reviewed > 0 && state.colW >= 260, (el) => el.child(action(t, "settle-reviewed", "S", state.armed?.kind === "settle" ? `Confirm ${state.reviewed}` : `Settle ${state.reviewed}`, (cx) => cb.settleReviewed(cx))))
      .when(key === "done" && state.done > 0, (el) => el.child(action(t, "settle-all", "A", state.armed?.kind === "settle-all" ? `Confirm ${state.done}` : tight ? `Settle ${state.done}` : `Settle all ${state.done}`, (cx) => cb.settleAll(cx), `Settle all ${state.done} (A)`, tight)))
      .when(key === "ready" && state.approvable > 0, (el) => el.child(action(t, "approve-all", "M", state.armed?.kind === "approve-all" ? `Confirm ${state.approvable}` : tight ? `Approve ${state.approvable}` : `Approve all ${state.approvable}`, (cx) => cb.approveAll(cx), `Approve all ${state.approvable} (M)`, tight)))
      .child(state.popup ? headButton(t, "pop-close", "✕", "Close", () => cb.close()) : headButton(t, `pop-${key}`, "⤢", `Open ${label} in a pop-up`, () => cb.expand(key))))
    .child(h_flex().h(H.sub).px(10).gap(8).items_start().overflow_hidden()
      .children(fitSummary(col.summary, state.colW - 20).map(([text, summaryTone]) => div().flex_none().text_size(9.5).text_color(summaryTone === "dim" ? t.muted : t[summaryTone]).child(text))));
}

const BAR_GAP = 6;
const NOTICE_MIN = 140;
const HINT_ROOM = 64;
const NOTICE_TONE = { success: "done", error: "blocked", info: "muted" };
const barCost = (item) => (item.label.length + (item.more?.length ?? 0)) * 6.2 + 12;
function barItems(v) {
  const { worktrees: w, hub, ops, running, cap } = v;
  const circuits = hub?.circuits ? Object.entries(hub.circuits) : null;
  const out = circuits?.filter(([, c]) => c.state === "open").map(([name]) => name);
  const retrying = circuits?.filter(([, c]) => c.state === "half-open").map(([name]) => name);
  const modelsLabel = !circuits ? "Models" : out.length ? `Models · ${out.length} out` : retrying.length ? `Models · ${retrying.length} retrying` : "Models · all up";
  const modelsTone = out?.length ? "blocked" : retrying?.length ? "muted" : undefined;
  const modelsTip = out?.length ? `Out: ${out.join(", ")}. Click for the retry times and fallback order.` : retrying?.length ? `Waiting to retry: ${retrying.join(", ")}. The next task will try ${retrying.length === 1 ? "it" : "them"}. Click for details.` : "Model providers and the fallback order. Click to open.";
  const health = ops?.health;
  const issues = health && !health.stale ? health.problems.length + health.warnings.length : 0;
  const hubLabel = !health ? "Hub" : hub?.draining ? "Hub · draining" : health.stale ? "Hub · no check" : health.problems.length ? `Hub · ${plural(health.problems.length, "problem")}` : health.warnings.length ? `Hub · ${plural(health.warnings.length, "warning")}` : "Hub · ok";
  const hubTone = !health ? undefined : health.problems.length ? "blocked" : hub?.draining || health.stale || issues ? "working" : undefined;
  return [
    { id: "wt", prio: 0, label: w ? `Worktrees · ${w.stale} stale` : "Worktrees", more: w?.look ? ` · ${w.look} need a look` : "", tone: w?.stale ? "working" : undefined, tip: w ? `${w.stale} safe to clean or prune · ${w.look} need a look. Click to review and clean.` : "Linked Git worktrees. Click to review and clean them." },
    { id: "models", prio: 2, label: modelsLabel, tone: modelsTone, tip: modelsTip },
    { id: "queue", prio: 4, label: v.hasBoard ? `Queue · ${running}/${cap}` : "Queue", tone: v.hasBoard && running >= cap ? "working" : undefined, tip: "Running tasks against the cap, and what is waiting. Click to open." },
    { id: "hub", prio: 1, label: hubLabel, tone: hubTone, tip: "Hub health, Coordinator context, uptime. Click to open." },
  ];
}

export function fitBar(width, v) {
  if (v.compact) return [];
  const room = width - 20 - HINT_ROOM - (v.notice ? NOTICE_MIN + BAR_GAP : 0);
  const fits = (list) => list.reduce((sum, x) => sum + barCost(x), 0) + (list.length - 1) * BAR_GAP <= room;
  let shown = barItems(v);
  const wt = shown[0];
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
    .children(fitBar(width, v).map((x) => action(t, `bar-${x.id}`, "", x.label + (x.more ?? ""), (cx) => cb.panel(x.id, cx), x.tip, true, x.tone)))
    .when(Boolean(v.notice), (el) => el.child(noticeLine(t, v.notice, cb)))
    .when(!v.notice, (el) => el.child(div().flex_1()))
    .when(v.stale, (el) => el.child(div().flex_none().text_size(9.5).text_color(t.working).child("stale")))
    .child(keysHint(t, cb));
}

export function foldedColumn(t, key, col, state, cb) {
  const [, label, tone, short] = COLUMNS.find((c) => c[0] === key);
  const capped = key === "run" && state.running >= state.cap;
  return v_flex().id(`col-${key}`).w(H.folded).flex_none().h_full().items_center().pt(8).gap(4).border_r(1).border_color(t.border)
    .cursor_pointer().hover((s) => s.bg(t.raised)).on_click((_e, cx) => cb.fold(key, cx)).tooltip(`Show ${label}`)
    .child(div().text_size(9).text_color(t.dim).child("▸"))
    .child(div().text_size(11).font_semibold().text_color(capped ? t.blocked : col.count ? t[tone] : t.dim).child(key === "run" ? `${state.running}/${state.cap}` : String(col.count)))
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

const chipWidth = (text) => 8 + text.length * 5.5;

function readyFit(v, narrow) {
  const [mergeLabel] = MERGE[v.gh?.mergeable] ?? MERGE.UNKNOWN;
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
  const [mergeLabel, mergeTone, mergeTip] = MERGE[gh?.mergeable] ?? MERGE.UNKNOWN;
  const ci = gh ? gh.ci : "none";
  const { label, used } = modelParts(v.c, v.runModel);
  const dropped = [!fit.rev && `Review ${verdict?.label ?? "none yet"}`, !fit.model && label && `Model ${label}`, !fit.model && used && `Ran on ${used}`].filter(Boolean);
  const prTip = [`PR #${v.pr.number}${gh?.draft ? " (draft)" : ""}`, ...dropped].join(" · ");
  return h_flex().h(H.foot).flex_1().min_w(0).gap(3).items_center().overflow_hidden()
    .child(chip(t, `#${v.pr.number}${gh?.draft && fit.rev ? " draft" : ""}`, "accent", prTip))
    .child(chip(t, `CI ${gh ? CI_MARK[ci] ?? "?" : "…"}`, CI_TONE[ci] ?? "dim", gh ? `CI ${ci}` : "CI loading"))
    .when(fit.rev, (el) => el.child(chip(t, `rev ${verdict ? VERDICT_MARK[verdict.state] ?? "?" : "—"}`, verdict ? VERDICT_TONE[verdict.state] ?? "dim" : "dim", verdict?.label ?? "No review yet")))
    .child(chip(t, fit.short ? mergeLabel.slice(-1) : mergeLabel, mergeTone, mergeTip));
}

function statusLine(v) {
  const { c, variant, now } = v;
  if (variant === "backlog") {
    const age = ago(c.created, now);
    return `Created ${age === "now" ? "just now" : `${age} ago`}`;
  }
  if (c.kind === "run") return c.status === "queued" ? "Queued" : `Running ${elapsed(now - v.since)}${v.quiet ? ` · quiet ${elapsed(now - c.at)}` : ""}`;
  if (c.kind === "done") return v.reviewed ? "Ready to settle" : "Not reviewed yet";
  return c.context;
}

export function card(t, e, v, input, cb) {
  const { c, count, expanded, selected, mark, replying, now, canSettle, variant, opening } = v;
  const ready = variant === "ready";
  const narrow = v.narrow;
  const line = ready ? null : statusLine(v);
  const fit = ready ? readyFit(v, narrow) : null;
  const refused = ready && Boolean(v.refusal);
  const armedHere = v.armed?.key === e.key ? v.armed.kind : null;
  const readyActions = h_flex().gap(4).h(H.foot).min_w(0).when(!refused, (el) => el.flex_1()).items_center().overflow_hidden()
    .child(action(t, `ap-${e.key}`, "a", armedHere === "approve" ? "Confirm" : "Approve", (cx) => cb.approve(cx), armedHere === "approve" ? "Press again to send the merge approval" : v.blocked ? v.refusal : "Approve merge (a)", narrow).when(v.blocked, (el) => el.opacity(0.5)))
    .child(action(t, `pr-${e.key}`, "p", "PR", () => cb.openPr(), "Open the PR (p)", narrow))
    .child(action(t, `op-${e.key}`, "o", narrow ? "Open" : "Thread", (cx) => cb.open(cx), "Open the thread (o)", narrow))
    .when(canSettle && !narrow, (el) => el.child(action(t, `se-${e.key}`, "s", "Settle", (cx) => cb.settle(cx))));
  const quick = variant === "backlog"
    ? h_flex().gap(4).flex_none()
      .child(action(t, `qu-${e.key}`, "q", armedHere === "queue" ? "Confirm" : "Queue", (cx) => cb.queue(cx), armedHere === "queue" ? "Press again to queue" : "Queue this task"))
      .child(action(t, `op-${e.key}`, "o", "Open", (cx) => cb.open(cx), "Open the thread (o)", narrow))
    : actions(t, e.key, canSettle, cb, narrow);
  const meta = h_flex().gap(6).flex_none().items_center().on_mouse_down("left", selectOnly(e.key, cb))
    .when(count > 1, (el) => el.child(fold(t, e.key, count, expanded, cb)))
    .when(variant === "backlog" && v.state, (el) => el.child(chip(t, v.state, "idle")))
    .when(v.merged, (el) => el.child(chip(t, "merged", "done")))
    .when(!refused && (!ready || fit.model), (el) => el.child(modelChips(t, c, v.runModel)));
  const status = refused
    ? h_flex().id(`why-${e.key}`).flex_1().min_w(0).gap(5).items_center().tooltip(v.refusal).on_mouse_down("left", selectOnly(e.key, cb))
      .child(div().size(6).flex_none().rounded(3).bg(t.blocked))
      .child(div().flex_1().min_w(0).truncate().text_size(10).text_color(t.blocked).child(v.refusal))
    : ready
    ? prChips(t, v, fit).on_mouse_down("left", selectOnly(e.key, cb))
    : h_flex().flex_1().min_w(0).gap(5).items_center()
      .child(div().size(6).flex_none().rounded(3).bg(v.quiet ? t.muted : t[TONE[c.kind]]))
      .child(div().flex_1().min_w(0).truncate().text_size(10).text_color(t.muted).child(line));
  const foot = selected
    ? h_flex().h(H.foot).w_full().flex_none().gap(6).items_center().child(ready ? readyActions : quick)
      .when(refused, (el) => el.child(div().id(`why-${e.key}`).flex_1().min_w(0).truncate().text_size(10).text_color(t.blocked).tooltip(v.refusal).child(v.refusal)))
    : h_flex().h(H.foot).w_full().flex_none().gap(6).items_center().child(status).child(meta);
  const body = v_flex().id(`card-${e.key}`).w_full().h(cardHeight(false) - 4).overflow_hidden().rounded(6).bg(selected ? t.raised : t.surface).border_1()
    .when(!selected, (el) => el.cursor_pointer().hover((s) => s.bg(t.raised)))
    .border_color(selected ? (mark === "focus" ? t.accent : t.input) : t.border).px(8).py(5).gap(2)
    .on_mouse_down("left", (ev, cx) => cb.press(e.key, ev, cx))
    .on_mouse_move((ev) => cb.drag(ev))
    .on_click((_e, cx) => cb.click(e.key, cx))
    .child(h_flex().h(18).flex_none().gap(6).items_center()
      .when(Boolean(c.task), (el) => el.child(div().flex_none().text_size(11.5).font_semibold().text_color(t.foreground).child(c.task)))
      .when(!c.task, (el) => el.child(div().min_w(0).truncate().text_size(11).font_medium().text_color(t.muted).child(c.project ?? "thread")))
      .child(div().flex_1())
      .when(v.window, (el) => el.child(action(t, `win-${e.key}`, "", armedHere === "close-window" ? "Close it?" : narrow ? "Empryo" : "open in Empryo", (cx) => cb.closeWindow(e.key, cx), armedHere === "close-window" ? "Press again to close the Empryo window" : "An Empryo window is open on this task, so the hub can't send to it. Click to close it.", true, "working")))
      .child(opening === e.key ? div().flex_none().text_size(10).font_medium().text_color(t.accent).child("Opening…") : div().flex_none().text_size(10).text_color(t.muted).child(ago(c.at, now))))
    .child(div().w_full().h(H.title).flex_none().overflow_hidden().text_size(11.5).line_height("15px").text_color(t.foreground).child(c.title))
    .child(div().flex_1())
    .child(foot);
  const cardEl = div().h(cardHeight(false)).w_full().flex_none().px(6).pb(4).child(body);
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

export const DEC_WIDTH = 640;
const DEC_CAP = 640;
const DEC_COLUMN = { needs: ["Needs you", "blocked"], ready: ["Ready to merge", "accent"] };
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
  const agent = verdict ? { pass: "agent review found nothing blocking", fail: `agent review ${verdict.label.replace(/^rev /, "")}`, unknown: "agent review unclear", loading: "checking the agent review" }[verdict.state] : "no agent review yet";
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
  const settle = g.threads.some((x) => SETTLEABLE.includes(x.kind));
  const sendBack = col === "ready" && pr && verdict?.state === "fail";
  const other = [
    { id: "open", key: "o", label: "Open thread" },
    ...((c.kind === "wait" && col === "needs") || sendBack ? [] : [{ id: "reply", key: "r", label: "Reply" }]),
    ...(col === "ready" ? [{ id: "note", key: "d", label: NOTE_LABEL }] : []),
    ...(settle ? [{ id: "settle", key: "s", label: "Settle" }] : []),
    ...(info.pr ? [{ id: "pr", key: "p", label: "Open PR" }] : []),
  ];
  const age = ago(g.at, now);
  const checks = pr ? checksOf(info.gh, verdict) : null;
  if (col === "ready" && pr) {
    const title = g.task ? `${g.task} · ${g.title}` : g.title;
    if (!verdict) return { headline: `Review PR #${pr.number}`, primary: { id: "review", key: "t", label: "Start review", armed: "Confirm review" }, why: [title, "No review yet, so this can't merge."], other, checks };
    if (verdict.state === "loading") return { headline: `PR #${pr.number}`, primary: { id: "wait", key: "", label: "Checking review…" }, why: [title, checkWords(info.gh, verdict)], other, checks };
    if (sendBack) return { headline: `Fix PR #${pr.number}`, primary: { id: "answer", key: "r", label: "Send back" }, why: [title, `Review failed: ${verdict.label.replace(/^rev /, "")}.`], other, checks };
    return { headline: `Merge PR #${pr.number}`, primary: { id: "merge", key: "a", label: "Merge", armed: "Confirm merge" }, why: [title, checkWords(info.gh, verdict)], other, checks };
  }
  if (c.kind === "wait") {
    return { headline: `Answer ${name}'s question`, primary: { id: "answer", key: "r", label: "Reply" }, why: [c.context, `${g.project} · waiting ${age}`], other, checks };
  }
  const retry = c.kind === "fail";
  return {
    headline: `${retry ? "Retry" : "Resume"} ${name}`,
    primary: { id: retry ? "retry" : "resume", key: "t", label: retry ? "Retry" : "Resume", armed: retry ? "Confirm retry" : "Confirm resume" },
    why: [c.context, `${g.title} · ${retry ? "failed" : "stopped"} ${age} ago`],
    other,
    checks,
  };
}

export function decisionHeight(d, fileCount) {
  const lines = (text, size) => Math.ceil((text.length * size * 0.6) / (DEC_WIDTH - 40));
  const body = lines(d.headline, 18) * 24 + d.why.reduce((sum, w) => sum + lines(w, 12.5) * 18, 0) + 150;
  const review = d.checks ? 40 + d.checks.length * 26 + 40 + Math.min(fileCount ?? 3, 10) * 24 : 0;
  return Math.min(DEC_CAP, H.head - 8 + 32 + body + review);
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
    .when(d.primary.id === "wait" && !outdated, (el) => el.opacity(0.5))
    .child(label)
    .when(!outdated && Boolean(d.primary.key), (el) => el.child(div().text_size(10.5).font_medium().child(d.primary.key)));
}

export function decisionView(t, v, input, cb) {
  const { col, d, armed, armedKind, outdated, replying, outcome, files } = v;
  const [label, tone] = DEC_COLUMN[col];
  const hint = outdated ? "This view is over a minute old. Nothing happens until it is re-checked." : d.primary.id === "answer" ? "Opens a reply box. Nothing is sent until you press Enter in it." : d.primary.id === "wait" ? "Nothing can be merged until the review check loads." : `Press ${d.primary.key} or Enter to arm, then ${d.primary.key} or click to confirm.`;
  return v_flex().size_full().min_h(0)
    .child(h_flex().h(34).px(12).gap(6).items_center().flex_none().border_b(1).border_color(t.border)
      .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
      .child(div().flex_1().text_size(11).font_semibold().text_color(t.foreground).child(label))
      .child(headButton(t, "dec-close", "✕", "Close", () => cb.close())))
    .child(v_flex().id("dec-body").flex_1().min_h(0).overflow_y_scrollbar()
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
          .children(d.other.map((x) => action(t, `dec-${x.id}`, x.key, x.id === "settle" && armedKind === "settle" ? "Confirm settle" : x.label, (cx) => cb.other(x.id, cx)))))
        .when(Boolean(d.checks), (el) => el.child(checkRows(t, d.checks)))
        .when(Boolean(d.checks && files), (el) => el.child(fileRows(t, files)))));
}

export const DECIDES = new Set(["needs", "ready"]);
export const KEY_TABLE = [
  { keys: "⏎", group: "Card", all: "Decide on a Needs you or Ready card, open the thread on any other" },
  { keys: "a", group: "Card", all: "Approve the merge, press twice (Ready cards)" },
  { keys: "o", group: "Card", all: "Open the thread" },
  { keys: "r", group: "Card", all: "Reply to the thread" },
  { keys: "d", group: "Card", all: "Send back with a note: reply to the thread (Ready cards; on Needs you cards it is a plain reply)" },
  { keys: "s", group: "Card", all: "Settle the card's finished threads" },
  { keys: "p", group: "Card", all: "Open the pull request" },
  { keys: "q", group: "Card", all: "Queue the task, press twice (Backlog cards)" },
  { keys: "n", group: "Move", all: "Jump to the oldest Needs you card, then Ready, and cycle" },
  { keys: "j k", group: "Move", all: "Next or previous card (the arrow keys work too)" },
  { keys: "h l", group: "Move", all: "Previous or next column (section on a narrow board)" },
  { keys: "g G", group: "Move", all: "First or last card in the column" },
  { keys: "→ ←", group: "Move", all: "Show or hide a task's other threads" },
  { keys: "S", group: "Board", all: "Settle every reviewed card, press twice (Done)" },
  { keys: "A", group: "Board", all: "Settle every finished card, press twice (Done)" },
  { keys: "M", group: "Board", all: "Approve every PR with a passing review, press twice (Ready)" },
  { keys: "f", group: "Board", all: "Fold or show this column" },
  { keys: "e", group: "Board", all: "Open this column in a pop-up" },
  { keys: "b", group: "Board", all: "Fold or show Backlog" },
  { keys: "R", group: "Board", all: "Reload the board now" },
  { keys: "?", group: "Board", all: "Show this list" },
];

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
