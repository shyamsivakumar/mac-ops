// Elements of the board. Every row has a fixed height, so each column can window itself.

import { div } from "gpui-kit";
import { v_flex, h_flex, Input } from "gpui-base";
import { shortModel } from "./hub.js";

export const H = { head: 42, sub: 16, card: 86, foot: 18, title: 30, child: 24, reply: 34, empty: 50, folded: 44 };
const TONE = { wait: "blocked", fail: "blocked", stop: "working", run: "working", done: "done", idle: "idle" };
const CI_TONE = { pass: "done", fail: "blocked", pending: "working", none: "dim" };
const CI_MARK = { pass: "✓", fail: "✗", pending: "…", none: "—" };
const VERDICT_MARK = { pass: "✓", fail: "✗", unknown: "?" };
const VERDICT_TONE = { pass: "done", fail: "blocked", unknown: "dim" };
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

function action(t, id, hint, label, run, tip, bare) {
  const el = h_flex().id(id).h(18).px(5).gap(4).items_center().flex_none().rounded(4).border_1().border_color(t.input).bg(t.raised)
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
  const [, label, tone] = COLUMNS.find((c) => c[0] === key);
  const capped = key === "run" && state.running >= state.cap;
  const tight = state.colW < 260;
  return v_flex().id(`fold-${key}`).h(H.head).flex_none().border_b(1).border_color(t.border)
    .when(!state.popup, (el) => el.cursor_pointer().on_click((_e, cx) => cb.fold(key, cx)).tooltip(`${state.collapsed ? "Show" : "Hide"} ${label}`))
    .child(h_flex().h(H.head - H.sub).px(10).gap(6).items_center().overflow_hidden()
      .when(!state.popup, (el) => el.child(div().w(10).text_size(9).text_color(t.dim).child(state.collapsed ? "▸" : "▾")))
      .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
      .child(div().min_w(0).text_size(11).font_semibold().text_color(t.foreground).truncate().child(key === "done" && state.colW < 260 ? "Done" : label))
      .child(div().text_size(11).font_semibold().text_color(capped ? t.blocked : col.count ? t[tone] : t.dim).child(key === "run" ? `${state.running}/${state.cap}` : String(col.count)))
      .child(div().flex_1())
      .when(key === "done" && state.reviewed > 0 && state.colW >= 260, (el) => el.child(action(t, "settle-reviewed", "S", state.armed?.kind === "settle" ? `Confirm ${state.reviewed}` : `Settle ${state.reviewed}`, (cx) => cb.settleReviewed(cx))))
      .when(key === "done" && state.done > 0, (el) => el.child(action(t, "settle-all", "A", state.armed?.kind === "settle-all" ? `Confirm ${state.done}` : tight ? `Settle ${state.done}` : `Settle all ${state.done}`, (cx) => cb.settleAll(cx), `Settle all ${state.done} (A)`, tight)))
      .when(key === "ready" && state.approvable > 0, (el) => el.child(action(t, "approve-all", "M", state.armed?.kind === "approve-all" ? `Confirm ${state.approvable}` : tight ? `Approve ${state.approvable}` : `Approve all ${state.approvable}`, (cx) => cb.approveAll(cx), `Approve all ${state.approvable} (M)`, tight)))
      .child(state.popup ? headButton(t, "pop-close", "✕", "Close", () => cb.close()) : headButton(t, `pop-${key}`, "⤢", `Open ${label} in a pop-up`, () => cb.expand(key))))
    .child(h_flex().h(H.sub).px(10).gap(8).items_start().overflow_hidden()
      .children(fitSummary(col.summary, state.colW - 20).map(([text, summaryTone]) => div().flex_none().text_size(9.5).text_color(summaryTone === "dim" ? t.muted : t[summaryTone]).child(text))));
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
  if (c.kind === "run") return c.status === "queued" ? "Queued" : `Running ${elapsed(now - v.since)}`;
  if (c.kind === "done") return v.reviewed ? "Ready to settle" : "Not reviewed yet";
  return c.context;
}

export function card(t, e, v, input, cb) {
  const { c, count, expanded, selected, mark, replying, now, canSettle, variant, opening } = v;
  const ready = variant === "ready";
  const narrow = v.narrow;
  const line = ready ? null : statusLine(v);
  const fit = ready ? readyFit(v, narrow) : null;
  const armedHere = v.armed?.key === e.key ? v.armed.kind : null;
  const readyActions = h_flex().gap(4).h(H.foot).flex_1().min_w(0).items_center().overflow_hidden()
    .child(action(t, `ap-${e.key}`, "a", armedHere === "approve" ? "Confirm" : "Approve", (cx) => cb.approve(cx), armedHere === "approve" ? "Press again to send the merge approval" : "Approve merge (a)", narrow))
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
    .when(!ready || fit.model, (el) => el.child(modelChips(t, c, v.runModel)));
  const status = ready
    ? prChips(t, v, fit).on_mouse_down("left", selectOnly(e.key, cb))
    : h_flex().flex_1().min_w(0).gap(5).items_center()
      .child(div().size(6).flex_none().rounded(3).bg(t[TONE[c.kind]]))
      .child(div().flex_1().min_w(0).truncate().text_size(10).text_color(t.muted).child(line));
  const foot = selected
    ? h_flex().h(H.foot).w_full().flex_none().items_center().child(ready ? readyActions : quick)
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
      .child(opening === e.key ? div().flex_none().text_size(10).font_medium().text_color(t.accent).child("Opening…") : div().flex_none().text_size(10).text_color(t.muted).child(ago(c.at, now))))
    .child(div().w_full().h(H.title).flex_none().overflow_hidden().text_size(11.5).line_height("15px").text_color(t.foreground).child(c.title))
    .child(div().flex_1())
    .child(foot);
  const cardEl = div().h(cardHeight(false)).w_full().flex_none().px(6).pb(4).child(body);
  if (!replying) return cardEl;
  return v_flex().w_full().flex_none().child(cardEl)
    .child(div().h(H.reply).px(6).pt(2).child(Input.new(input).h(28).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_size(11.5).text_color(t.foreground)));
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

const KEYS = [["h l", "column"], ["j k", "card"], ["→ ←", "threads"], ["r", "reply"], ["o", "open"], ["s", "settle"], ["A", "settle all"], ["a", "approve"], ["M", "approve all"], ["q", "queue"], ["f", "fold column"], ["e", "pop-up"], ["b", "backlog"], ["R", "refresh"]];

export function footer(t, width, stale, compact) {
  const fit = [];
  let used = 20;
  for (const [k, hint] of KEYS) {
    const v = compact ? hint.replace("column", "section") : hint;
    used += (k.length + v.length) * 5.2 + 12;
    if (used > width) break;
    fit.push([k, v]);
  }
  return h_flex().h(18).px(10).flex_none().gap(8).items_center().border_t(1).border_color(t.border).overflow_hidden()
    .children(fit.map(([k, v]) => h_flex().gap(4).items_center().flex_none()
      .child(div().text_size(9.5).font_medium().text_color(t.muted).child(k))
      .child(div().text_size(9.5).text_color(t.dim).child(v))))
    .when(stale, (el) => el.child(div().flex_1()).child(div().flex_none().text_size(9.5).text_color(t.working).child("stale")));
}

export function thumb(t, top, view, total) {
  const h = Math.max(24, (view * view) / total);
  return div().absolute().right(2).top(Math.round((view - h) * (top / (total - view)))).w(3).h(Math.round(h)).rounded(2).bg(t.input);
}
