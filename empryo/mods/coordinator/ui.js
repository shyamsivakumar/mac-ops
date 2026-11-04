import { div, svg } from "gpui-kit";
import { v_flex, h_flex, Textarea, TextView } from "gpui-base";

const TONE = { running: "working", waiting: "blocked", failed: "blocked", stopped: "working", done: "done", idle: "idle" };
const STATUS = { working: ["working", "working"], blocked: ["asking", "blocked"], done: ["idle", "done"], idle: ["idle", "idle"] };
const COLLAPSED_LINES = 6;
const CONTEXT_WINDOW = 1000000;

export const READ_WIDTH = 720;

export function ago(at, now) {
  const m = Math.floor((now - at) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 1440)}d ago`;
}

export function elapsed(at, now) {
  const s = Math.max(0, Math.round((now - at) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function chip(t, id, task, open) {
  const tone = task ? t[TONE[task.status]] : t.dim;
  const el = h_flex().h(16).px(6).gap(4).flex_none().items_center().rounded(4).border_1().border_color(task ? tone + "66" : t.border)
    .bg(task ? tone + "18" : t.surface)
    .child(div().size(5).rounded(3).bg(tone))
    .child(div().text_size(10).font_medium().text_color(task ? t.foreground : t.dim).child(id))
    .child(div().text_size(9.5).text_color(tone).child(task?.status ?? "no live thread"));
  return task && open ? el.id(`strip-chip-${id}`).cursor_pointer().hover((s) => s.bg(t.selected)).tooltip(task.title).on_click(() => open(id, task)) : el;
}

const STRIP_MAX_IDS = 8;
const STRIP_MAX_TURNS = 5;
const STRIP_GAP = 4;
const STRIP_MORE_WIDTH = 28;
const chipWidth = (id, task) => 25 + id.length * 6 + (task?.status ?? "no live thread").length * 5.5;

function recentTasks(view) {
  const ids = new Set();
  const recent = (view?.turns ?? []).filter((m) => m.role !== "you").slice(-STRIP_MAX_TURNS).reverse();
  for (const m of recent) for (const id of m.tasks) if (ids.size < STRIP_MAX_IDS) ids.add(id);
  return [...ids];
}

export function taskStrip(t, view, cb, width) {
  const ids = recentTasks(view);
  if (!ids.length) return null;
  const room = width - 20;
  let used = 0;
  let fit = 0;
  for (const id of ids) {
    used += chipWidth(id, cb.tasks[id]) + STRIP_GAP;
    if (used > room - (fit + 1 < ids.length ? STRIP_MORE_WIDTH : 0)) break;
    fit++;
  }
  const hidden = ids.length - fit;
  return h_flex().h(24).px(10).gap(STRIP_GAP).flex_none().items_center().overflow_hidden().border_b(1).border_color(t.border)
    .children(ids.slice(0, fit).map((id) => chip(t, id, cb.tasks[id], cb.open)))
    .when(hidden > 0, (el) => el.child(div().flex_none().text_size(10).text_color(t.dim).child(`+${hidden}`)));
}

function link(t, id, label, onClick) {
  return div().id(id).text_size(10.5).font_medium().text_color(t.accent).cursor_pointer().hover((s) => s.text_color(t.foreground)).on_click(onClick).child(label);
}

export const turnKey = (m) => `${m.role}-${m.at}`;

export function turn(t, m, now, cb) {
  const mine = m.role === "you";
  const all = m.text.split("\n").filter((l) => l.trim());
  const long = all.length > COLLAPSED_LINES;
  const open = cb.isOpen(turnKey(m));
  const shown = long && !open ? all.slice(0, COLLAPSED_LINES) : all;
  const lines = all.length;
  const body = TextView.markdown(`md-${turnKey(m)}`, shown.join("\n")).w_full().text_size(12).text_color(mine ? t.foreground : t.muted).on_link_click((url) => cb.open(url));
  const head = h_flex().w_full().gap(8).items_center()
    .child(div().text_size(11.5).font_semibold().text_color(mine ? t.accent : t.foreground).child(mine ? "You" : "Coordinator"))
    .child(div().text_size(10).text_color(t.dim).child(ago(m.at, now)))
    .child(div().flex_1())
    .when(long, (el) => el.child(link(t, `more-${turnKey(m)}`, open ? "Show less" : `Show more · ${lines} lines`, (_e, cx) => cb.toggle(turnKey(m), cx))));
  return h_flex().w_full().max_w(READ_WIDTH).flex_none().rounded(6).overflow_hidden().bg(mine ? t.accent + "14" : t.surface).border_1().border_color(mine ? t.accent + "55" : t.border)
    .child(div().w(3).flex_none().bg(mine ? t.accent : t.border))
    .child(v_flex().flex_1().min_w(0).px(10).py(7).gap(5).child(head).child(body)
      .when(m.tasks.length, (el) => el.child(h_flex().gap(4).flex_wrap().children(m.tasks.map((id) => chip(t, id, cb.tasks[id], cb.open)))))
      .when(m.tools, (el) => el.child(div().text_size(10).text_color(t.dim).child(m.tools))));
}

const footerLink = (t, id, label, onClick) =>
  div().id(id).w_full().flex_none().py(10).flex().justify_center().text_size(11).font_medium().text_color(t.accent).cursor_pointer().on_click(onClick).child(label);

export function conversation(t, view, error, now, cb) {
  const note = (text) => div().w_full().py(20).flex().justify_center().text_size(11).text_color(t.dim).child(text);
  const log = v_flex().id("co-log").flex_1().min_w(0).min_h(0).on_size_change((size, cx) => cb.size(size, cx));
  if (!view || view.turns.length === 0) {
    return log.child(note(!view ? (error ? "Can't read the Coordinator transcript. Retrying." : "Loading…") : "No messages yet. Write one below."));
  }
  const total = view.turns.length;
  const hidden = total - cb.shown;
  const column = v_flex().id("co-turns").size_full().overflow_y_scrollbar()
    .children(view.turns.slice(-cb.shown).reverse().map((m) => div().w_full().flex_none().px(12).py(4).child(turn(t, m, now, cb))))
    .when(hidden > 0, (el) => el.child(footerLink(t, "co-show-older", view.unread ? "Show older" : `Show older · ${hidden} more`, (_e, cx) => cb.more(cx))))
    .when(hidden <= 0 && view.unread, (el) => el.child(footerLink(t, "co-older-block", "Show older", (_e, cx) => cb.older(cx))))
    .when(hidden <= 0 && !view.unread && view.hasOlder, (el) => el.child(footerLink(t, "co-older", "↑ Load previous session", (_e, cx) => cb.older(cx))));
  return log.child(column);
}

export function status(t, info, view, at, width) {
  const narrow = width < 440;
  const [word, tone] = STATUS[info?.status] ?? ["not running", "dim"];
  const working = info?.status === "working";
  const doing = working ? (view?.activity ? `${view.activity} · ${elapsed(view.activityAt, at)}` : "Thinking") : view?.lastReplyAt ? `replied ${ago(view.lastReplyAt, at)}` : "";
  const tokens = view?.tokens ?? 0;
  const fraction = Math.min(1, tokens / CONTEXT_WINDOW);
  return h_flex().h(26).px(10).gap(6).flex_none().items_center().border_b(1).border_color(t.border)
    .child(div().size(7).flex_none().rounded(4).bg(t[tone]))
    .child(div().flex_none().text_size(11.5).font_semibold().text_color(t.foreground).child("Coordinator"))
    .child(div().flex_none().text_size(10.5).font_medium().text_color(t[tone]).child(word))
    .child(div().flex_1().min_w(0).truncate().text_size(10.5).text_color(t.muted).child(doing))
    .when(working && view?.lastReplyAt && !narrow, (el) => el.child(div().flex_none().text_size(10).text_color(t.dim).child(`replied ${ago(view.lastReplyAt, at)}`)))
    .when(tokens, (el) => el.child(h_flex().gap(6).items_center().flex_none()
      .when(!narrow, (b) => b.child(div().w(48).h(4).rounded(2).bg(t.background).child(div().h(4).rounded(2).w(Math.max(2, Math.round(48 * fraction))).bg(fraction > 0.8 ? t.blocked : t.accent))))
      .child(div().text_size(10).text_color(fraction > 0.8 ? t.blocked : t.dim).child(`${Math.round(tokens / 1000)}k/1M`))))
    .when(Boolean(info?.address), (el) => el.child(div().flex_none().text_size(10).text_color(t.dim).child(info.address)));
}

const ASK_CLIP = 200;
const CHIP_CLIP = 24;
const OPTION_CLIP = 40;
const ASKS_MAX_HEIGHT = 260;
const ASK_ROW_HEIGHT = 116;

const clip = (text, max) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);
const recommendedLine = (rec) => `Recommended: ${rec.answer}${rec.reason ? ` · ${rec.reason}` : ""}`;
const sendLabel = (k) => (k === 0 ? "Send" : `Send ${k} ${k === 1 ? "answer" : "answers"}`);

function sendButton(t, id, label, ready, done, onClick) {
  return h_flex().id(id).h(22).px(10).flex_none().items_center().rounded(5).text_size(11).font_semibold()
    .bg(ready ? t.accent : t.surface).text_color(ready ? t.background : t.dim)
    .when(done, (el) => el.bg(t.done + "22").text_color(t.done))
    .when(ready, (el) => el.cursor_pointer().hover((s) => s.opacity(0.85)).on_click(onClick))
    .when(!ready, (el) => el.cursor_not_allowed())
    .child(label);
}

function sendIconButton(t, ready, state, k, onClick) {
  const icon = state === "sending" ? "loader" : state === "sent" ? "check" : "arrow-up";
  return h_flex().id("co-send").size(24).flex_none().relative().items_center().justify_center().rounded(12)
    .accessibility_label(k > 0 ? sendLabel(k) : "Send")
    .tooltip(k > 0 ? sendLabel(k) : "Send (⏎) · ⇧⏎ for a new line")
    .bg(ready ? t.accent : t.surface).text_color(ready ? t.background : t.dim)
    .when(state === "sent", (el) => el.bg(t.done + "22").text_color(t.done))
    .when(ready, (el) => el.cursor_pointer().hover((s) => s.opacity(0.85)).on_click(onClick))
    .when(!ready, (el) => el.cursor_not_allowed())
    .child(svg(`mods/coordinator/${icon}.svg`).size(14))
    .when(k > 0 && !state, (el) => el.child(div().absolute().top(-4).right(-4).min_w(14).h(14).px(3).flex().items_center().justify_center().rounded(7).bg(t.blocked).text_color(t.background).text_size(9).font_semibold().child(String(k))));
}

function acceptButton(t, onClick) {
  return h_flex().id("ask-accept").h(22).px(10).flex_none().items_center().rounded(5).border_1().border_color(t.accent).text_size(11).font_medium().text_color(t.accent)
    .cursor_pointer().hover((s) => s.bg(t.selected)).on_click(onClick).child("Accept recommended");
}

function segment(t, id, label, selected, recommended, onClick) {
  return div().id(id).h(20).px(10).flex().items_center().text_size(10.5).font_medium()
    .bg(selected ? t.accent : t.raised).text_color(selected ? t.background : recommended ? t.accent : t.foreground)
    .cursor_pointer().hover((s) => s.opacity(0.85)).on_click(onClick).child(recommended ? `★ ${label}` : label);
}

function option(t, id, label, selected, recommended, onClick) {
  return div().id(id).h(20).px(8).flex().items_center().rounded(4).border_1().border_color(selected || recommended ? t.accent : t.input)
    .bg(selected ? t.accent : t.raised).text_size(10.5).font_medium().text_color(selected ? t.background : recommended ? t.accent : t.foreground)
    .cursor_pointer().hover((s) => s.opacity(0.85)).tooltip(label).on_click(onClick).child(clip(recommended ? `★ ${label}` : label, OPTION_CLIP));
}

function ask(t, { text: q, options, recommended: rec }, i, view, cb) {
  const draft = view.drafts.get(q);
  const open = view.editing.has(q);
  const tone = draft ? t.done : t.blocked;
  const choice = (kind) => segment(t, `ask-${i}-${kind}`, kind === "yes" ? "Yes" : "No", draft?.kind === kind, rec?.kind === kind, (_e, cx) => cb.choose(q, kind, kind, cx));
  const suggestion = rec?.kind === "text"
    ? option(t, `ask-${i}-s`, rec.text, draft?.kind === "reply" && draft.text === rec.text, true, (_e, cx) => cb.choose(q, "reply", rec.text, cx))
    : null;
  const choices = options.length
    ? h_flex().flex_wrap().gap(4).children(options.map((o, j) => option(t, `ask-${i}-o${j}`, o, draft?.kind === "option" && draft.text === o, rec?.kind === "option" && rec.text === o, (_e, cx) => cb.choose(q, "option", o, cx))))
    : h_flex().h(20).flex_none().rounded(4).border_1().border_color(t.input).overflow_hidden()
      .child(choice("yes"))
      .child(div().w(1).h(20).bg(t.input))
      .child(choice("no"));
  const replyButton = h_flex().id(`ask-${i}-r`).h(20).px(8).flex_none().items_center().rounded(4).border_1().border_color(draft?.kind === "reply" || open ? t.accent : t.input)
    .bg(draft?.kind === "reply" || open ? t.accent + "22" : t.raised).text_size(10.5).font_medium().text_color(t.foreground)
    .cursor_pointer().hover((s) => s.opacity(0.85)).on_click((_e, cx) => cb.reply(q, cx)).child("Reply…");
  const shown = draft?.kind === "reply" && !open
    ? div().id(`ask-${i}-shown`).flex_1().min_w(0).truncate().text_size(10.5).text_color(t.muted).cursor_pointer().on_click((_e, cx) => cb.reply(q, cx)).child(`✓ ${draft.text}`)
    : draft && draft.kind !== "reply"
      ? div().flex_1().min_w(0).truncate().text_size(10.5).font_medium().text_color(t.done).child(`✓ ${draft.text}`)
      : div().flex_1();
  return h_flex().flex_none().rounded(6).overflow_hidden().bg(t.surface).border_1().border_color(t.border)
    .child(div().w(3).flex_none().bg(tone))
    .child(v_flex().flex_1().min_w(0).px(8).py(6).gap(5)
      .child(h_flex().gap(6).items_start()
        .child(div().flex_none().text_size(11).font_semibold().text_color(tone).child(`${i + 1}`))
        .child(div().flex_1().min_w(0).text_size(11.5).text_color(t.foreground).child(clip(q, ASK_CLIP))))
      .when(rec, (el) => el.child(div().id(`ask-${i}-rec`).w_full().truncate().text_size(10.5).text_color(t.dim).tooltip(recommendedLine(rec)).child(recommendedLine(rec))))
      .when(options.length > 0, (el) => el.child(choices))
      .child(h_flex().gap(6).items_center()
        .when(options.length === 0, (el) => el.child(choices))
        .when(suggestion, (el) => el.child(suggestion))
        .child(replyButton)
        .child(shown))
      .when(open, (el) => el.child(v_flex().rounded(6).border_1().border_color(t.accent).bg(t.background)
        .child(Textarea.new(view.editor(q)).w_full().px(8).py(4).text_size(11.5).text_color(t.foreground))
        .child(div().px(8).pb(4).text_size(10).text_color(t.dim).child("⏎ save · ⇧⏎ newline")))));
}

export function asks(t, list, view, cb) {
  const k = view.answers.length;
  const ready = k > 0 && !view.sending;
  const acceptable = list.some((a) => a.recommended && !view.drafts.has(a.text));
  return v_flex().flex_none().px(10).py(6).gap(6).border_b(1).border_color(t.border)
    .child(h_flex().h(22).gap(8).items_center()
      .child(div().text_size(10).font_semibold().text_color(t.blocked).child(`Needs you · ${list.length}`))
      .child(div().flex_1().min_w(0).truncate().text_right().text_size(10).text_color(t.dim).child(`${k}/${list.length}`))
      .when(acceptable, (el) => el.child(acceptButton(t, (_e, cx) => cb.accept(cx))))
      .child(sendButton(t, "ask-send", k ? sendLabel(k) : "Send answers", ready, false, (_e, cx) => cb.send(cx))))
    .child(v_flex().id("ask-list").w_full().h(Math.min(list.length * ASK_ROW_HEIGHT, ASKS_MAX_HEIGHT)).overflow_y_scrollbar().mode("always")
      .children(list.map((a, i) => div().w_full().flex_none().pb(4).child(ask(t, a, i, view, cb)))));
}

function answerChip(t, a, cb) {
  const label = a.kind === "reply" ? `"${clip(a.text, CHIP_CLIP)}"` : clip(a.text, CHIP_CLIP);
  return h_flex().h(18).pl(6).pr(2).gap(4).flex_none().items_center().rounded(4).border_1().border_color(t.border).bg(t.surface)
    .child(div().text_size(10.5).text_color(t.foreground).child(`${a.n} · ${label}`))
    .child(div().id(`chip-x-${a.n}`).size(14).flex().items_center().justify_center().rounded(3).text_size(10).text_color(t.dim)
      .cursor_pointer().hover((s) => s.bg(t.selected)).on_click((_e, cx) => cb.clear(a.q, cx)).child("✕"));
}

export function composer(t, info, input, state, focused, answers, cb) {
  const text = input.value();
  const k = answers.length;
  const ready = (Boolean(text.trim()) || k > 0) && Boolean(info) && state !== "sending";
  const button = sendIconButton(t, ready, state, k, (_e, cx) => cb.send(cx));
  return v_flex().flex_none().px(10).py(8).border_t(1).border_color(t.border)
    .child(v_flex().rounded(8).border_1().border_color(focused ? t.accent : t.input).bg(t.background)
      .when(k > 0, (el) => el.child(h_flex().px(8).pt(8).gap(4).flex_wrap().children(answers.map((a) => answerChip(t, a, cb)))))
      .child(Textarea.new(input).w_full().px(10).pt(8).pb(4).text_size(12).text_color(t.foreground))
      .child(h_flex().h(30).px(8).items_center().justify_end().child(button)));
}
