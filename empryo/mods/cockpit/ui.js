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

export const DEC_WIDTH = 640;
const DEC_CAP = 640;
const DEC_COLUMN = { needs: ["Needs you", "blocked"], ready: ["Ready to merge", "accent"] };
const SETTLEABLE = ["done", "fail", "stop"];

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
  const agent = verdict ? { pass: "agent review found nothing blocking", fail: `agent review ${verdict.label.replace(/^rev /, "")}`, unknown: "agent review unclear" }[verdict.state] : "no agent review yet";
  const human = HUMAN_REVIEW[gh?.review] ?? "no GitHub verdict";
  const reviewMark = verdict?.state === "fail" || gh?.review === "CHANGES_REQUESTED" ? BAD : verdict?.state === "pass" ? OK : UNKNOWN;
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
  const other = [
    { id: "open", key: "o", label: "Open thread" },
    ...(c.kind === "wait" && col === "needs" ? [] : [{ id: "reply", key: "r", label: "Reply" }]),
    ...(settle ? [{ id: "settle", key: "s", label: "Settle" }] : []),
    ...(info.pr ? [{ id: "pr", key: "p", label: "Open PR" }] : []),
  ];
  const age = ago(g.at, now);
  const checks = pr ? checksOf(info.gh, verdict) : null;
  if (col === "ready" && pr) {
    return { headline: `Merge PR #${pr.number}`, primary: { id: "merge", key: "a", label: "Merge", armed: "Confirm merge" }, why: [g.task ? `${g.task} · ${g.title}` : g.title, checkWords(info.gh, verdict)], other, checks };
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
  const label = outdated ? (d.primary.id === "merge" ? "Re-check" : "Out of date, close") : armed ? d.primary.armed : d.primary.label;
  return h_flex().id("dec-primary").h(30).px(14).gap(8).items_center().flex_none().rounded(6)
    .bg(armed ? t.blocked : t.solid).text_color(armed ? t.background : t.solid_foreground).text_size(12.5).font_semibold()
    .cursor_pointer().hover((s) => s.opacity(0.9)).on_click((e, cx) => e.click_count > 1 || run(cx))
    .child(label)
    .when(!outdated, (el) => el.child(div().text_size(10.5).font_medium().child(d.primary.key)));
}

export function decisionView(t, v, input, cb) {
  const { col, d, armed, armedKind, outdated, replying, outcome, files } = v;
  const [label, tone] = DEC_COLUMN[col];
  const hint = outdated ? "This view is over a minute old. Nothing happens until it is re-checked." : d.primary.id === "answer" ? "Opens a reply box. Nothing is sent until you press Enter in it." : `Press ${d.primary.key} or Enter to arm, then ${d.primary.key} or click to confirm.`;
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
        .when(replying, (el) => el.child(div().w_full().h(30).child(Input.new(input).h(30).px(8).rounded(6).border_1().border_color(t.accent).bg(t.background).text_size(12).text_color(t.foreground))))
        .child(h_flex().gap(6).items_center().flex_wrap()
          .child(div().text_size(10.5).text_color(t.dim).child("Other"))
          .children(d.other.map((x) => action(t, `dec-${x.id}`, x.key, x.id === "settle" && armedKind === "settle" ? "Confirm settle" : x.label, (cx) => cb.other(x.id, cx)))))
        .when(Boolean(d.checks), (el) => el.child(checkRows(t, d.checks)))
        .when(Boolean(d.checks && files), (el) => el.child(fileRows(t, files)))));
}

export const DECIDES = new Set(["needs", "ready"]);
const settleable = (c) => (c.entry.thread ? [c.entry.thread] : c.entry.group.threads).some((x) => SETTLEABLE.includes(x.kind));
const FOOT_HELP = 64;

export const KEY_TABLE = [
  { keys: "⏎", group: "Card", label: (c) => (!c.entry.thread && DECIDES.has(c.entry.col) ? "decide" : "open"), all: "Decide on a Needs you or Ready card, open the thread on any other", when: (c) => c.entry },
  { keys: "a", group: "Card", label: "approve", all: "Approve the merge, press twice (Ready cards)", when: (c) => c.entry?.col === "ready" && c.entry.group.info?.status === "open" },
  { keys: "o", group: "Card", label: "thread", all: "Open the thread", when: (c) => c.entry },
  { keys: "r", group: "Card", label: "reply", all: "Reply to the thread", when: (c) => c.entry },
  { keys: "s", group: "Card", label: "settle", all: "Settle the card's finished threads", when: (c) => c.entry && settleable(c) },
  { keys: "p", group: "Card", label: "PR", all: "Open the pull request", when: (c) => c.entry?.group.info?.pr },
  { keys: "q", group: "Card", label: "queue", all: "Queue the task, press twice (Backlog cards)", when: (c) => c.entry?.col === "backlog" },
  { keys: "n", group: "Move", label: "next urgent", all: "Jump to the oldest Needs you card, then Ready, and cycle", when: (c) => c.urgent > 0 },
  { keys: "j k", group: "Move", label: "card", all: "Next or previous card (the arrow keys work too)", when: () => true },
  { keys: "h l", group: "Move", label: (c) => (c.compact ? "section" : "column"), all: "Previous or next column (section on a narrow board)", when: (c) => !c.pop },
  { keys: "g G", group: "Move", label: "top, end", all: "First or last card in the column", when: (c) => c.entry },
  { keys: "→ ←", group: "Move", label: "threads", all: "Show or hide a task's other threads", when: (c) => c.entry?.group.threads.length > 1 },
  { keys: "S", group: "Board", label: "settle reviewed", all: "Settle every reviewed card, press twice (Done)", when: (c) => c.entry?.col === "done" && c.reviewed > 0 },
  { keys: "A", group: "Board", label: "settle all", all: "Settle every finished card, press twice (Done)", when: (c) => c.entry?.col === "done" && c.done > 0 },
  { keys: "M", group: "Board", label: "approve all", all: "Approve every open PR, press twice (Ready)", when: (c) => c.entry?.col === "ready" && c.approvable > 0 },
  { keys: "f", group: "Board", label: "fold", all: "Fold or show this column", when: (c) => !c.pop && c.entry },
  { keys: "e", group: "Board", label: "pop-up", all: "Open this column in a pop-up", when: (c) => !c.pop && c.entry },
  { keys: "b", group: "Board", label: "backlog", all: "Fold or show Backlog", when: (c) => !c.pop },
  { keys: "R", group: "Board", label: "refresh", all: "Reload the board now", when: () => true },
  { keys: "?", group: "Board", label: "all keys", all: "Show this list", when: () => true },
];

const labelOf = (row, ctx) => (typeof row.label === "function" ? row.label(ctx) : row.label);

export function footer(t, width, stale, ctx, cb) {
  const fit = [];
  let used = 0;
  const room = width - 20 - FOOT_HELP - (stale ? 40 : 0);
  for (const row of KEY_TABLE) {
    if (row.keys === "?" || !row.when(ctx)) continue;
    const label = labelOf(row, ctx);
    used += (row.keys.length + label.length) * 5.8 + 14;
    if (used > room) break;
    fit.push([row.keys, label]);
  }
  return h_flex().h(18).px(10).flex_none().gap(8).items_center().border_t(1).border_color(t.border).overflow_hidden()
    .child(h_flex().flex_1().min_w(0).gap(8).items_center().overflow_hidden()
      .children(fit.map(([k, v]) => h_flex().gap(4).items_center().flex_none()
        .child(div().text_size(9.5).font_medium().text_color(t.muted).child(k))
        .child(div().text_size(9.5).text_color(t.dim).child(v)))))
    .when(stale, (el) => el.child(div().flex_none().text_size(9.5).text_color(t.working).child("stale")))
    .child(h_flex().id("keys-help").flex_none().gap(4).items_center().cursor_pointer().hover((s) => s.bg(t.raised)).px(3).rounded(3).on_click((_e, cx) => cb.keys(cx))
      .child(div().text_size(9.5).font_medium().text_color(t.muted).child("?"))
      .child(div().text_size(9.5).text_color(t.dim).child("all keys")));
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

export function thumb(t, top, view, total) {
  const h = Math.max(24, (view * view) / total);
  return div().absolute().right(2).top(Math.round((view - h) * (top / (total - view)))).w(3).h(Math.round(h)).rounded(2).bg(t.input);
}
