import { div, image, svg } from "gpui-kit";
import { settings } from "herdr";
import { v_flex, h_flex, Textarea, TextView } from "gpui-base";

const TONE = { running: "working", waiting: "blocked", failed: "blocked", stopped: "working", done: "done", idle: "idle" };
const STATUS = { working: ["working", "working"], blocked: ["asking", "blocked"], done: ["idle", "done"], idle: ["idle", "idle"] };
const CONTEXT_WINDOW = 1000000;

export function ago(at, now) {
  const m = Math.floor((now - at) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 1440)}d ago`;
}

export function elapsed(at, now) {
  const s = Math.max(0, Math.round((now - at) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function chip(t, scope, id, task, cb) {
  const tone = t[TONE[task.status]];
  return h_flex().id(`chip-${scope}-${id}`).h(16).px(6).gap(4).flex_none().items_center().rounded(4).border_1().border_color(tone + "66").bg(tone + "18")
    .cursor_pointer().hover((s) => s.bg(t.selected)).tooltip(task.title).on_click((_e, cx) => cb.open(id, task, cx))
    .child(div().size(5).rounded(3).bg(tone))
    .child(div().text_size(10).font_medium().text_color(t.foreground).child(id))
    .child(div().text_size(9.5).text_color(tone).child(cb.opening === id ? "opening…" : task.status));
}

export const liveTasks = (ids, tasks) => ids.filter((id) => tasks[id] && tasks[id].status !== "idle");

const STRIP_MAX_IDS = 8;
const STRIP_MAX_TURNS = 5;
const STRIP_GAP = 4;
const STRIP_MORE_WIDTH = 28;
const chipWidth = (id, task) => 27 + id.length * 6.4 + task.status.length * 5.8;

function recentTasks(view) {
  const ids = new Set();
  const recent = (view?.turns ?? []).filter((m) => m.role === "coordinator").slice(-STRIP_MAX_TURNS).reverse();
  for (const m of recent) for (const id of m.tasks) if (ids.size < STRIP_MAX_IDS) ids.add(id);
  return [...ids];
}

export function taskStrip(t, view, cb, width) {
  const ids = liveTasks(recentTasks(view), cb.tasks);
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
  const rest = ids.slice(fit).map((id) => `${id} ${cb.tasks[id].status}`).join(", ");
  return h_flex().h(24).px(10).gap(STRIP_GAP).flex_none().items_center().overflow_hidden().border_b(1).border_color(t.border)
    .children(ids.slice(0, fit).map((id) => chip(t, "strip", id, cb.tasks[id], cb)))
    .when(hidden > 0, (el) => el.child(div().id("strip-more").flex_none().text_size(10).text_color(t.muted).tooltip(`${hidden} more: ${rest}`).child(`+${hidden}`)));
}

function link(t, id, label, onClick) {
  return div().id(id).flex_none().text_size(10.5).font_medium().text_color(t.accent).cursor_pointer().hover((s) => s.text_color(t.foreground)).on_click(onClick).child(label);
}

export const turnKey = (m) => `${m.role}-${m.at}`;

const monoFont = () => settings().font_family ?? settings().font ?? "JetBrains Mono";
const MONO = 11;
const OUTPUT_SHOWN = 3;
const DIFF_SHOWN = 12;
const CODE_SHOWN = 30;
const TOOLS_SHOWN = 40;
const TABLE_CHAR = 6.1;
const TABLE_PAD = 14;
const GROUPED = new Set(["Read", "Grep", "Glob", "WebFetch", "WebSearch"]);

const sum = (list) => list.reduce((a, b) => a + b, 0);

export function fitColumns(ideal, min, room) {
  const wide = ideal.map((n) => n * TABLE_CHAR + TABLE_PAD);
  const floor = min.map((n, i) => Math.min(n * TABLE_CHAR + TABLE_PAD, wide[i]));
  if (sum(wide) <= room) return wide;
  if (sum(floor) >= room) return floor.map((n) => Math.max(40, (n * room) / sum(floor)));
  const spare = (room - sum(floor)) / (sum(wide) - sum(floor));
  return floor.map((n, i) => n + (wide[i] - n) * spare);
}

function table(t, b, room) {
  const widths = fitColumns(b.ideal, b.min, room);
  const row = (cells, head, last) => h_flex().flex_none().children(cells.map((c, i) => div().w(widths[i]).flex_none().px(6).py(3).border_color(t.border)
    .when(i < cells.length - 1, (el) => el.border_r(1)).when(!last, (el) => el.border_b(1))
    .text_size(11).text_color(head ? t.foreground : t.muted).when(head, (el) => el.font_semibold().bg(t.surface)).when(c.mono, (el) => el.font_family(monoFont()))
    .child(c.text || " ")));
  return v_flex().flex_none().rounded(4).border_1().border_color(t.border).overflow_hidden()
    .child(row(b.head, true, b.rows.length === 0))
    .children(b.rows.map((r, i) => row(r, false, i === b.rows.length - 1)));
}

function codeBlock(t, b, id, cb) {
  const open = cb.isOpen(`code-${id}`);
  const shown = open ? b.lines.length : Math.min(CODE_SHOWN, b.lines.length);
  const hidden = b.lines.length - shown;
  return v_flex().w_full().flex_none().rounded(4).bg(t.surface).px(10).py(7)
    .children(b.lines.slice(0, shown).map((l) => div().w_full().min_w(0).font_family(monoFont()).text_size(MONO).text_color(t.foreground).child(l || " ")))
    .when(hidden > 0 || open && b.lines.length > CODE_SHOWN, (el) => el.child(link(t, `code-more-${id}`, open ? "Show less" : `… +${hidden} lines`, (_e, cx) => cb.toggle(`code-${id}`, cx))))
    .when(open && b.more > 0, (el) => el.child(div().text_size(10).text_color(t.muted).child(`… ${b.more} more lines not kept`)));
}

const AUTOLINK = /^<[a-z][a-z0-9+.-]{1,31}:[^\s<>]*>|^<[^\s<>@]+@[^\s<>@]+>/i;

export function escapeAngles(text) {
  let out = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === "`") {
      const run = /^`+/.exec(text.slice(i))[0];
      const close = text.indexOf(run, i + run.length);
      const end = close < 0 ? i + run.length : close + run.length;
      out += text.slice(i, end);
      i = end;
    } else if (ch === "<" && !AUTOLINK.test(text.slice(i))) {
      out += "\\<";
      i++;
    } else {
      out += ch;
      i++;
    }
  }
  return out;
}

function textBlocks(t, id, blocks, color, room, cb) {
  return blocks.map((b, i) => (b.t === "md"
    ? TextView.markdown(`md-${id}-${i}`, escapeAngles(b.text)).w_full().text_size(12).text_color(color).on_link_click((url) => cb.link(url))
    : b.t === "code" ? codeBlock(t, b, `${id}-${i}`, cb) : table(t, b, room)));
}

const dot = (tone) => div().size(6).flex_none().rounded(3).bg(tone);

function expander(t, id, label, cb) {
  return link(t, `tool-more-${id}`, label, (_e, cx) => cb.toggle(`tool-${id}`, cx));
}

function outputLines(t, item, open, cb) {
  const r = item.result;
  if (!r || r.total === 0) return null;
  const shown = open ? r.lines.length : Math.min(OUTPUT_SHOWN, r.lines.length);
  const hidden = r.total - shown;
  return v_flex().w_full().min_w(0).pl(12).gap(1)
    .children(r.lines.slice(0, shown).map((l, i) => h_flex().w_full().gap(6).items_start()
      .child(div().w(10).flex_none().font_family(monoFont()).text_size(MONO).text_color(t.dim).child(i === 0 ? "⎿" : ""))
      .child(div().flex_1().min_w(0).font_family(monoFont()).text_size(MONO - 0.5).text_color(r.error ? t.blocked : t.muted).child(l || " "))))
    .when(hidden > 0 || open && r.lines.length > OUTPUT_SHOWN, (el) => el.child(h_flex().pl(16).child(expander(t, item.id, open ? "Show less" : `… +${hidden} lines`, cb))))
    .when(open && r.total > r.lines.length, (el) => el.child(div().pl(16).text_size(10).text_color(t.muted).child(`… ${r.total - r.lines.length} more lines not kept`)));
}

function diffLines(t, item, open, cb) {
  const d = item.diff;
  if (d.wrote) return v_flex().pl(12).child(div().text_size(10.5).text_color(t.done).child(`+${d.wrote} lines`));
  const rows = [...d.removed.map((l) => ["-", l]), ...d.added.map((l) => ["+", l])];
  if (!rows.length) return null;
  const shown = open ? rows.length : Math.min(DIFF_SHOWN, rows.length);
  const hidden = rows.length - shown + d.hidden;
  return v_flex().w_full().min_w(0).pl(12).gap(1)
    .children(rows.slice(0, shown).map(([sign, l]) => {
      const tone = sign === "-" ? t.blocked : t.done;
      return h_flex().w_full().gap(6).items_start().rounded(2).bg(tone + "18")
        .child(div().w(10).flex_none().pl(3).font_family(monoFont()).text_size(MONO).text_color(tone).child(sign))
        .child(div().flex_1().min_w(0).font_family(monoFont()).text_size(MONO - 0.5).text_color(t.foreground).child(l || " "));
    }))
    .when(hidden > 0 || open && rows.length > DIFF_SHOWN, (el) => el.child(h_flex().pl(16).child(expander(t, item.id, open ? "Show less" : `… +${hidden} lines`, cb))));
}

function toolBlock(t, item, now, cb) {
  const running = cb.working && !item.result && item.id === cb.pendingId;
  const open = cb.isOpen(`tool-${item.id}`);
  const head = h_flex().w_full().gap(6).items_center()
    .child(dot(running ? t.muted : !item.result ? t.dim : item.result.error ? t.blocked : t.done))
    .child(div().flex_none().font_family(monoFont()).text_size(MONO).font_semibold().text_color(t.foreground).child(item.name))
    .child(div().flex_1().min_w(0).truncate().font_family(monoFont()).text_size(MONO).text_color(t.muted).child(item.detail ? `(${item.detail})` : ""))
    .when(running, (el) => el.child(div().flex_none().text_size(10).text_color(t.working).child(elapsed(item.at, now))));
  const detail = item.diff ? diffLines(t, item, open, cb) : outputLines(t, item, open, cb);
  return v_flex().w_full().min_w(0).gap(2).child(head).when(detail, (el) => el.child(detail));
}

function groupLine(t, items, cb) {
  const count = (names) => items.filter((i) => names.includes(i.name)).length;
  const reads = count(["Read"]);
  const searches = count(["Grep", "Glob"]);
  const pages = count(["WebFetch", "WebSearch"]);
  const parts = [reads && `read ${reads} ${reads === 1 ? "file" : "files"}`, searches && `searched ${searches} ${searches === 1 ? "pattern" : "patterns"}`, pages && `fetched ${pages} ${pages === 1 ? "page" : "pages"}`].filter(Boolean).join(", ");
  const running = cb.working && items.some((i) => !i.result && i.id === cb.pendingId);
  return h_flex().w_full().gap(6).items_center()
    .child(dot(running ? t.muted : t.done))
    .child(div().flex_1().min_w(0).truncate().font_family(monoFont()).text_size(MONO).text_color(t.muted).child(parts.charAt(0).toUpperCase() + parts.slice(1)));
}

function eventLine(t, item) {
  return h_flex().w_full().gap(6).items_start()
    .child(div().flex_none().text_size(MONO).text_color(t.dim).child("◦"))
    .child(div().flex_1().min_w(0).text_size(10.5).text_color(t.muted).child(item.text));
}

const IMAGE_MAX = 220;

function imageTile(t, ref, id, cb) {
  const img = cb.image(ref);
  if (img.state === "ready") {
    const scale = Math.min(1, IMAGE_MAX / img.w, IMAGE_MAX / img.h);
    const w = Math.round(img.w * scale);
    const h = Math.round(img.h * scale);
    return div().id(id).w(w).h(h).flex_none().rounded(6).border_1().border_color(t.border).overflow_hidden()
      .cursor_pointer().hover((s) => s.opacity(0.85)).tooltip("Open in Preview").on_click(() => cb.openImage(ref.path || img.file))
      .child(image(img.rel).w(w).h(h));
  }
  const label = img.state === "missing" ? "image not found" : img.state === "failed" ? "image failed" : "image";
  return div().id(id).w(120).h(60).flex_none().flex().items_center().justify_center().rounded(6).border_1().border_color(t.border).bg(t.surface)
    .text_size(10.5).text_color(t.muted).child(label);
}

function imageStrip(t, images, id, cb) {
  return h_flex().w_full().gap(6).flex_wrap().children(images.map((ref, i) => imageTile(t, ref, `${id}-${i}`, cb)));
}

function groupable(item) {
  return item.k === "tool" && GROUPED.has(item.name) && !item.diff && !item.result?.error && !item.images;
}

function bodyOf(t, m, now, color, room, cb) {
  const out = [];
  const key = turnKey(m);
  const tools = m.items.flatMap((it, at) => (it.k === "tool" ? [at] : []));
  const firstKept = tools.length > TOOLS_SHOWN ? tools[tools.length - TOOLS_SHOWN] : 0;
  const earlier = cb.isOpen(`earlier-${key}`);
  for (let i = 0; i < m.items.length; i++) {
    const item = m.items[i];
    if (earlier && firstKept > 0 && i === tools[0]) out.push(link(t, `earlier-hide-${key}`, "Hide earlier tool calls", (_e, cx) => cb.toggle(`earlier-${key}`, cx)));
    if (item.k === "tool" && i < firstKept && !earlier) {
      let n = 1;
      while (i + 1 < firstKept && m.items[i + 1].k === "tool") {
        i++;
        n++;
      }
      out.push(link(t, `earlier-${key}-${i}`, `${n} earlier tool calls`, (_e, cx) => cb.toggle(`earlier-${key}`, cx)));
    } else if (item.k === "text") out.push(...textBlocks(t, `${key}-${i}`, item.blocks, color, room, cb));
    else if (item.k === "event") out.push(eventLine(t, item));
    else if (item.k === "images") out.push(imageStrip(t, item.images, `img-${key}-${i}`, cb));
    else if (groupable(item) && m.items[i + 1] && groupable(m.items[i + 1])) {
      const run = [item];
      while (groupable(m.items[i + 1] ?? {})) run.push(m.items[++i]);
      out.push(groupLine(t, run, cb));
    } else {
      out.push(toolBlock(t, item, now, cb));
      if (item.images) out.push(imageStrip(t, item.images, `img-${key}-${i}`, cb));
    }
  }
  return out;
}

export function turn(t, m, now, cb) {
  const mine = m.role === "you";
  const session = m.role === "session";
  const live = liveTasks(m.tasks, cb.tasks);
  const others = m.tasks.length - live.length;
  const footnote = others ? `${others} other ${others === 1 ? "task" : "tasks"} mentioned` : "";
  const head = h_flex().w_full().gap(8).items_center()
    .child(div().text_size(11.5).font_semibold().text_color(mine ? t.accent : session ? t.muted : t.foreground).child(mine ? "You" : session ? `From ${cb.sender(m.from)}` : "Coordinator"))
    .child(div().text_size(10).text_color(t.dim).child(ago(m.at, now)));
  const room = cb.width - 24 - (mine || session ? 22 : 0);
  const body = v_flex().flex_1().min_w(0).gap(6).child(head).children(bodyOf(t, m, now, session ? t.muted : t.foreground, room, cb))
    .when(live.length, (el) => el.child(h_flex().gap(4).flex_wrap().children(live.map((id) => chip(t, turnKey(m), id, cb.tasks[id], cb)))))
    .when(footnote, (el) => el.child(div().text_size(10).text_color(t.muted).child(footnote)));
  if (!mine && !session) return h_flex().w_full().flex_none().px(2).py(2).child(body);
  return h_flex().w_full().flex_none().rounded(6).overflow_hidden().bg(mine ? t.accent + "14" : t.background)
    .child(div().w(3).flex_none().bg(mine ? t.accent : t.input))
    .child(v_flex().flex_1().min_w(0).px(10).py(7).child(body));
}

export const TURN_ESTIMATE = 160;

function drawTurns(t, turns, now, cb) {
  const out = [];
  let below = 0;
  const from = cb.fromBottom - cb.viewH;
  const to = cb.fromBottom + 2 * cb.viewH;
  for (let i = turns.length - 1; i >= 0; i--) {
    const m = turns[i];
    const key = turnKey(m);
    const h = cb.heights.get(key) ?? TURN_ESTIMATE;
    const near = below + h >= from && below <= to;
    const above = below >= cb.fromBottom + cb.viewH;
    out.push(near
      ? div().id(`turn-${key}`).w_full().flex_none().px(12).py(4).on_size_change((size, cx) => cb.turnSize(key, size.height, cx, above)).child(turn(t, m, now, cb))
      : div().w_full().flex_none().h(h));
    below += h;
  }
  return out.reverse();
}

const footerLink = (t, id, label, onClick) =>
  div().id(id).w_full().flex_none().py(10).flex().justify_center().text_size(11).font_medium().text_color(t.accent).cursor_pointer().on_click(onClick).child(label);

export const clampFrom = (from, content, view) => Math.min(Math.max(0, from), Math.max(0, content - view));
export const holdFrom = (from, before, after, view, prepended) => clampFrom(from > 0 && !prepended ? from + after - before : from, after, view);

function thumb(t, top, view, total) {
  const h = Math.max(24, (view * view) / total);
  return div().absolute().right(2).top(Math.round((view - h) * (top / (total - view)))).w(3).h(Math.round(h)).rounded(2).bg(t.input);
}

function latestButton(t, cb) {
  return div().id("co-latest").absolute().bottom(8).right(16).h(22).px(10).flex().items_center().rounded(11).bg(t.accent).text_color(t.background)
    .text_size(10.5).font_semibold().cursor_pointer().hover((s) => s.opacity(0.85)).on_click((_e, cx) => cb.latest(cx)).child("Latest ↓");
}

export function conversation(t, view, error, now, cb) {
  const note = (text) => div().w_full().py(20).flex().justify_center().text_size(11).text_color(t.dim).child(text);
  const log = v_flex().id("co-log").flex_1().min_w(0).min_h(0).on_size_change((size, cx) => cb.size(size, cx));
  if (!view || view.turns.length === 0) {
    return log.child(note(!view ? (error ? "Can't read the Coordinator transcript. Retrying." : "Loading…") : "No messages yet. Write one below."));
  }
  const total = view.turns.length;
  const hidden = total - cb.shown;
  const content = v_flex().id("co-content").w_full().flex_none().relative().top(cb.fromBottom).on_size_change((size, cx) => cb.measure(size, cx))
    .when(hidden > 0, (el) => el.child(footerLink(t, "co-show-older", view.unread ? "Show older" : `Show older · ${hidden} more`, (_e, cx) => cb.more(cx))))
    .when(hidden <= 0 && view.unread, (el) => el.child(footerLink(t, "co-older-block", cb.loading ? "Loading…" : "Show older", (_e, cx) => cb.older(cx))))
    .when(hidden <= 0 && !view.unread && view.hasOlder, (el) => el.child(footerLink(t, "co-older", cb.loading ? "Loading…" : "↑ Load previous session", (_e, cx) => cb.older(cx))))
    .children(drawTurns(t, view.turns.slice(-cb.shown), now, cb));
  const column = div().id("co-turns").size_full().relative().overflow_hidden()
    .on_scroll_wheel((e, cx) => cb.wheel(e.delta.y, cx))
    .child(v_flex().size_full().justify_end().child(content))
    .when(cb.contentH > cb.viewH, (el) => el.child(thumb(t, cb.contentH - cb.viewH - cb.fromBottom, cb.viewH, cb.contentH)))
    .when(cb.fromBottom > 0, (el) => el.child(latestButton(t, cb)));
  return log.child(column);
}

export function status(t, info, view, at, width, error) {
  const narrow = width < 440;
  const [word, tone] = STATUS[info?.status] ?? ["not running", "dim"];
  const working = info?.status === "working";
  const doing = error ? "transcript unreadable, showing old data" : working ? (view?.activity ? `${view.activity} · ${elapsed(view.activityAt, at)}` : "Thinking") : view?.lastReplyAt ? `replied ${ago(view.lastReplyAt, at)}` : "";
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

const CHIP_CLIP = 24;
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
    .border_1().border_color(ready ? t.accent : t.input).bg(ready ? t.accent : t.selected).text_color(ready ? t.background : t.muted)
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

export function askRow(t, list, answered, cb) {
  const first = list[0];
  const detail = [first.options.length ? `${first.options.length} options` : "", first.recommended ? recommendedLine(first.recommended) : ""].filter(Boolean).join(" · ");
  return h_flex().id("ask-row").min_h(30).px(10).py(6).gap(8).flex_none().items_start().border_b(1).border_color(t.border)
    .cursor_pointer().hover((s) => s.bg(t.selected)).tooltip("Open the questions").on_click(() => cb.openAsks())
    .child(div().flex_none().pt(2).text_size(10).font_semibold().text_color(t.blocked).child(`Needs you · ${list.length}`))
    .child(v_flex().id("ask-text").flex_1().min_w(0).max_h(96).overflow_y_scrollbar().gap(2)
      .child(div().w_full().text_size(11).line_height("16px").text_color(t.muted).child(first.text))
      .when(Boolean(detail), (el) => el.child(div().w_full().text_size(10.5).line_height("15px").text_color(t.dim).child(detail)))
      .when(list.length > 1, (el) => el.child(div().text_size(10.5).text_color(t.dim).child(`+${list.length - 1} more`))))
    .child(div().flex_none().pt(2).text_size(10).text_color(t.muted).child(`${answered} of ${list.length} answered`));
}

export function popupBar(t, title, cb) {
  return h_flex().h(34).px(12).flex_none().items_center().border_b(1).border_color(t.border)
    .child(div().flex_1().text_size(12).font_semibold().text_color(t.foreground).child(title))
    .child(div().id("ask-pop-close").size(22).flex().items_center().justify_center().rounded(4).text_size(12).text_color(t.dim)
      .cursor_pointer().hover((s) => s.bg(t.selected)).on_click(() => cb.close()).child("✕"));
}

export function choicesOf(a) {
  const rec = a.recommended;
  const base = a.options.length
    ? a.options.map((text) => ({ kind: "option", text, label: text, rec: rec?.kind === "option" && rec.text === text }))
    : [{ kind: "yes", text: "yes", label: "Yes", rec: rec?.kind === "yes" }, { kind: "no", text: "no", label: "No", rec: rec?.kind === "no" }];
  return rec?.kind === "text" ? [...base, { kind: "reply", text: rec.text, label: rec.text, rec: true }] : base;
}

export const answerText = (draft) => (draft.kind === "reply" ? draft.text : draft.kind === "yes" || draft.kind === "no" ? draft.kind[0].toUpperCase() + draft.kind.slice(1) : draft.text);

function choiceRow(t, id, n, c, selected, onClick) {
  return h_flex().id(id).w_full().min_h(30).px(10).py(6).gap(10).items_start().rounded(6).border_1()
    .border_color(selected ? t.accent : c.rec ? t.accent + "88" : t.input).bg(selected ? t.accent : t.raised)
    .cursor_pointer().hover((s) => s.opacity(0.9)).on_click(onClick)
    .child(div().w(14).flex_none().text_size(11).font_semibold().text_color(selected ? t.background : t.dim).child(String(n)))
    .child(div().flex_1().min_w(0).text_size(12).line_height("17px").font_medium().text_color(selected ? t.background : t.foreground).child(c.label))
    .when(c.rec, (el) => el.child(div().flex_none().text_size(10).font_medium().text_color(selected ? t.background : t.accent).child("★ recommended")));
}

function questionBody(t, a, i, view, cb) {
  const draft = view.drafts.get(a.text);
  const open = view.editing.has(a.text);
  const choices = choicesOf(a);
  const replyOn = draft?.kind === "reply" && !choices.some((c) => c.kind === "reply" && c.text === draft.text);
  return v_flex().w_full().px(16).py(14).gap(10)
    .child(div().w_full().text_size(14).line_height("20px").font_medium().text_color(t.foreground).child(a.text))
    .when(Boolean(a.recommended), (el) => el.child(div().w_full().text_size(11.5).line_height("16px").text_color(t.muted).child(recommendedLine(a.recommended))))
    .child(v_flex().w_full().gap(6).children(choices.map((c, j) => choiceRow(t, `ask-${i}-c${j}`, j + 1, c, draft?.kind === c.kind && draft.text === c.text, (_e, cx) => cb.pick(a.text, c, cx)))))
    .child(h_flex().w_full().gap(8).items_start()
      .child(h_flex().id(`ask-${i}-r`).h(24).px(10).flex_none().items_center().gap(6).rounded(5).border_1().border_color(replyOn || open ? t.accent : t.input)
        .bg(replyOn || open ? t.accent + "22" : t.raised).text_size(11).font_medium().text_color(t.foreground)
        .cursor_pointer().hover((s) => s.opacity(0.85)).on_click((_e, cx) => cb.reply(a.text, cx))
        .child(div().text_size(10).text_color(t.dim).child("r")).child("Reply…"))
      .when(replyOn && !open, (el) => el.child(div().flex_1().min_w(0).pt(3).text_size(11.5).line_height("17px").text_color(t.done).child(`✓ ${draft.text}`))))
    .when(open, (el) => el.child(v_flex().w_full().rounded(6).border_1().border_color(t.accent).bg(t.background)
      .child(Textarea.new(view.editor(a.text)).w_full().px(8).py(4).text_size(12).text_color(t.foreground))
      .child(div().px(8).pb(4).text_size(10).text_color(t.dim).child("⏎ save · ⇧⏎ newline"))));
}

function reviewBody(t, list, view, cb) {
  return v_flex().w_full().px(16).py(14).gap(8)
    .when(view.changed, (el) => el.child(div().w_full().text_size(11.5).line_height("16px").text_color(t.blocked).child("The questions changed while you were reviewing. Read the list again before sending.")))
    .children(list.map((a, i) => {
      const draft = view.drafts.get(a.text);
      return h_flex().id(`review-${i}`).w_full().px(10).py(8).gap(10).items_start().rounded(6).border_1().border_color(draft ? t.border : t.blocked + "66").bg(t.surface)
        .cursor_pointer().hover((s) => s.bg(t.raised)).on_click((_e, cx) => cb.go(i, cx))
        .child(div().w(14).flex_none().text_size(11).font_semibold().text_color(draft ? t.done : t.blocked).child(String(i + 1)))
        .child(v_flex().flex_1().min_w(0).gap(3)
          .child(div().w_full().text_size(11.5).line_height("16px").text_color(t.muted).child(a.text))
          .child(div().w_full().text_size(12.5).line_height("17px").font_medium().text_color(draft ? t.foreground : t.dim).child(draft ? answerText(draft) : "No answer, nothing will be sent for this one")));
    }));
}

function footerKey(t, key, label, id, onClick) {
  return h_flex().id(id).h(22).px(8).gap(5).items_center().flex_none().rounded(4).border_1().border_color(t.input).bg(t.raised)
    .text_size(10.5).font_medium().text_color(t.foreground).cursor_pointer().hover((s) => s.bg(t.selected)).on_click(onClick)
    .child(div().text_size(9.5).text_color(t.dim).child(key)).child(label);
}

export function questionPop(t, list, view, cb) {
  const review = view.step >= list.length;
  const k = view.answers.length;
  const acceptable = list.some((a) => a.recommended && !view.drafts.has(a.text));
  const ready = k > 0 && !view.sending;
  return v_flex().size_full().min_h(0)
    .child(popupBar(t, review ? "Review your answers" : `Question ${view.step + 1} of ${list.length}`, cb))
    .child(v_flex().id("ask-body").flex_1().min_h(0).overflow_y_scrollbar().mode("always")
      .child(review ? reviewBody(t, list, view, cb) : questionBody(t, list[view.step], view.step, view, cb)))
    .child(h_flex().h(40).px(12).gap(6).flex_none().items_center().border_t(1).border_color(t.border)
      .child(div().flex_1().min_w(0).text_size(10.5).text_color(t.muted).child(`${k} of ${list.length} answered`))
      .when(view.step > 0, (el) => el.child(footerKey(t, "k", "Back", "ask-back", (_e, cx) => cb.back(cx))))
      .when(!review, (el) => el.child(footerKey(t, "→", "Skip", "ask-skip", (_e, cx) => cb.skip(cx))))
      .when(acceptable, (el) => el.child(acceptButton(t, (_e, cx) => cb.accept(cx))))
      .when(review, (el) => el.child(sendButton(t, "ask-send", k ? `${sendLabel(k)} (s)` : "Send answers (s)", ready, false, (_e, cx) => cb.send(cx)))));
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
      .child(h_flex().h(30).px(8).gap(8).items_center()
        .child(div().flex_1().min_w(0).truncate().text_size(10.5).text_color(t.dim).child(state === "sending" ? "" : "⏎ send · ⇧⏎ new line"))
        .child(button)));
}
