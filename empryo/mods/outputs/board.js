import { div, svg, image } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, home, layout, openOverlay, theme } from "herdr";
import { collect, groupItems, newCache, OTHER } from "./data.js";

const ICON = (name) => `mods/outputs/${name}.svg`;
const CHIPS = [["all", "All"], ["image", "Images"], ["page", "Pages"], ["wiki", "Wiki"], ["artifact", "Artifacts"]];
const TIMEOUT = 20000;
const THUMB_BOX = { w: 150, h: 84 };
const THUMB_CAP = 12;
const LAST_OPEN = "outputs.lastOpen";
const OPENED = "outputs.opened";
const OPENED_KEEP_SECONDS = 8 * 86400;

const store = {
  read(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  },
  write(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { return; }
  },
};

function hidden() {
  const find = (node) => node?.id === "outputs-col" ? node : (node?.children ?? []).map(find).find(Boolean);
  return Boolean(find(layout())?.hidden);
}

const ago = (t, now) => {
  const s = Math.max(0, now - t);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
};

export class Board {
  init(cx) {
    this.cache = newCache();
    this.items = []; this.titles = new Map(); this.filter = "all";
    this.loading = false; this.loaded = false; this.error = null; this.warnings = []; this.note = null;
    this.away = true; this.since = Infinity;
    this.opened = store.read(OPENED) ?? {};
    this.refresh(cx);
    cx.timer.every(60000, (cx) => {
      if (hidden()) this.away = true;
      else this.refresh(cx);
    });
  }

  visit() {
    this.away = false;
    this.since = store.read(LAST_OPEN) ?? Infinity;
    store.write(LAST_OPEN, Date.now() / 1000);
  }

  markSeen(cx) {
    this.since = Infinity;
    store.write(LAST_OPEN, Date.now() / 1000);
    cx.notify();
  }

  isNew(item) { return item.t > this.since && !this.opened[item.target]; }

  remember(item) {
    const now = Date.now() / 1000;
    this.opened[item.target] = now;
    for (const [target, at] of Object.entries(this.opened)) if (now - at > OPENED_KEEP_SECONDS) delete this.opened[target];
    store.write(OPENED, this.opened);
  }

  refresh(cx) {
    if (this.loading) return;
    this.loading = true;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        const result = await collect({ exec, home }, this.cache);
        this.items = result.items; this.titles = result.titles; this.warnings = result.warnings;
        this.error = null;
      } catch (e) { this.error = String(e); }
      finally { this.loaded = true; this.loading = false; cx.notify(); }
    });
  }

  fail(prefix, e, cx) {
    this.note = `${prefix}: ${e}`;
    cx.notify();
    cx.timer.after(5000, (cx) => { this.note = null; cx.notify(); });
  }

  open(item, cx) {
    this.remember(item);
    cx.notify();
    exec("open", [item.target], { timeout: TIMEOUT }).then((r) => {
      if (r.code !== 0) throw new Error(r.stderr.trim() || `open exited ${r.code}`);
    }).catch((e) => this.fail("Cannot open", e, cx));
  }

  preview(images, index, cx) {
    this.remember(images[index]);
    cx.notify();
    openOverlay({
      mod: "outputs", kind: "dialog", width: 0.8, height: 0.85,
      props: { role: "preview", index, images: images.map(({ path, name, w, h }) => ({ path, name, w, h })) },
    });
  }

  chip(id, label, t) {
    const on = this.filter === id;
    return div().id(`outputs-chip-${id}`).h(22).px(9).flex().items_center().rounded(11).text_size(11).cursor_pointer()
      .bg(on ? t.selected : t.raised).text_color(on ? t.foreground : t.muted).hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => { this.filter = id; cx.notify(); }).child(label);
  }

  dot(t) { return div().size(6).flex_none().rounded(3).bg(t.accent); }

  row(item, key, t, now) {
    return h_flex().id(`outputs-row-${key}`).h(28).flex_none().px(8).gap(8).items_center().rounded(7).cursor_pointer()
      .hover((s) => s.bg(t.hover)).on_click((_e, cx) => this.open(item, cx))
      .child(this.isNew(item) ? this.dot(t) : div().size(6).flex_none())
      .child(svg(ICON(item.kind)).size(14).flex_none().text_color(t.muted))
      .child(div().flex_1().min_w(0).truncate().child(item.name))
      .child(div().max_w(120).min_w(0).truncate().text_size(11).text_color(t.dim).child(item.src))
      .child(div().w(28).flex_none().text_right().text_size(11).text_color(t.dim).child(ago(item.t, now)));
  }

  thumb(pic, index, images, key, t) {
    const scale = pic.w && pic.h ? Math.min(THUMB_BOX.w / pic.w, THUMB_BOX.h / pic.h) : null;
    const w = scale ? Math.max(24, Math.round(pic.w * scale)) : THUMB_BOX.h;
    const h = scale ? Math.max(24, Math.round(pic.h * scale)) : THUMB_BOX.h;
    return v_flex().id(`outputs-thumb-${key}-${index}`).flex_none().w(w).gap(3).cursor_pointer()
      .on_click((_e, cx) => this.preview(images, index, cx))
      .child(div().relative().w(w).h(h).rounded(5).overflow_hidden().border_1().border_color(t.border)
        .child(image(pic.path).w(w).h(h))
        .when(this.isNew(pic), (e) => e.child(this.dot(t).absolute().top(4).right(4))))
      .child(div().text_size(10).text_color(t.dim).truncate().child(pic.name));
  }

  strip(images, key, t) {
    const shown = images.slice(0, THUMB_CAP);
    return h_flex().flex_wrap().gap(8).px(8).py(2)
      .children(shown.map((img, i) => this.thumb(img, i, images, key, t)))
      .when(images.length > THUMB_CAP, (e) => e.child(
        div().id(`outputs-more-${key}`).flex_none().w(56).h(THUMB_BOX.h).flex().items_center().justify_center().rounded(5).bg(t.raised)
          .text_size(12).text_color(t.muted).cursor_pointer().hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => this.preview(images, THUMB_CAP, cx)).child(`+${images.length - THUMB_CAP}`)));
  }

  group(g, gi, t, now) {
    const images = g.items.filter((i) => i.kind === "image"), rest = g.items.filter((i) => i.kind !== "image");
    const fresh = g.items.filter((i) => this.isNew(i)).length;
    return v_flex().id(`outputs-group-${gi}`).flex_none().gap(2).pt(8).pb(6)
      .child(h_flex().h(24).px(8).gap(8).items_center()
        .child(div().flex_none().font_semibold().text_color(g.key === OTHER ? t.muted : t.foreground).child(g.label))
        .child(div().flex_1().min_w(0).truncate().text_color(t.muted).child(g.title))
        .when(fresh > 0, (e) => e.child(div().flex_none().px(5).rounded(4).bg(t.accent).text_size(10).text_color(t.accent_foreground).child(`${fresh} new`)))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(`${g.items.length} · ${ago(g.t, now)}`)))
      .when(images.length > 0, (e) => e.child(this.strip(images, gi, t)))
      .children(rest.map((item, i) => this.row(item, `${gi}-${i}`, t, now)));
  }

  render(cx) {
    if (this.away && !hidden()) { this.visit(); this.refresh(cx); }
    const t = theme(), now = Date.now() / 1000;
    const visible = this.items.filter((i) => this.filter === "all" || i.kind === this.filter);
    const groups = groupItems(visible, this.titles);
    const fresh = visible.filter((i) => this.isNew(i)).length;
    return v_flex().id("outputs").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .child(h_flex().h(42).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().child("Outputs"))
        .child(div().px(5).py(1).rounded(4).border_1().border_color(t.border).text_size(10).text_color(t.muted).child(`${visible.length}`))
        .when(fresh > 0, (e) => e.child(div().id("outputs-new").px(6).py(1).rounded(4).bg(t.accent).text_size(10).text_color(t.accent_foreground).cursor_pointer()
          .on_click((_e, cx) => this.markSeen(cx)).child(`${fresh} new`)))
        .child(div().flex_1())
        .child(div().id("outputs-refresh").size(24).flex().items_center().justify_center().rounded(6).cursor_pointer().hover((s) => s.bg(t.hover))
          .text_color(this.loading ? t.accent : t.muted).on_click((_e, cx) => this.refresh(cx)).child(svg(ICON("refresh")).size(14))))
      .child(h_flex().flex_none().px(10).py(8).gap(6).children(CHIPS.map(([id, label]) => this.chip(id, label, t))))
      .when(Boolean(this.note), (e) => e.child(div().px(14).pb(6).text_size(11).text_color(t.ansi1).child(this.note)))
      .when(this.warnings.length > 0, (e) => e.child(div().px(14).pb(6).text_size(11).text_color(t.dim).child(this.warnings.join(" "))))
      .child(v_flex().id("outputs-list").flex_1().min_h(0).overflow_y_scroll().px(6).pb(6)
        .children(groups.map((g, gi) => this.group(g, gi, t, now)))
        .when(!groups.length, (e) => e.child(div().p(8).text_color(this.error ? t.ansi1 : t.dim).child(this.error ?? (this.loaded ? "Nothing in the last 7 days" : "Loading outputs…"))))
        .when(Boolean(this.error) && groups.length > 0, (e) => e.child(div().p(8).text_size(11).text_color(t.ansi1).child(this.error))));
  }
}
