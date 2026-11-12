import { div, image } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { closeOverlay, exec, props, settings, theme } from "herdr";

const FALLBACK_BOX = { w: 800, h: 520 };

export class Preview {
  init(cx) {
    const { images, index } = props();
    this.images = images; this.at = index; this.box = FALLBACK_BOX; this.note = null;
    this.handle = cx.focus_handle();
    this.handle.focus();
    cx.timer.after(300, () => this.handle.focus());
  }

  step(delta, cx) {
    this.at = (this.at + delta + this.images.length) % this.images.length;
    cx.notify();
  }

  openInPreview(cx) {
    exec("open", ["-a", "Preview", this.images[this.at].path], { timeout: 20000 }).then((r) => {
      if (r.code !== 0) throw new Error(r.stderr.trim() || `open exited ${r.code}`);
    }).catch((e) => {
      this.note = `Cannot open: ${e}`;
      cx.notify();
    });
  }

  key(e, cx) {
    if (e.key === "escape") closeOverlay(props().overlay);
    else if (e.key === "left") this.step(-1, cx);
    else if (e.key === "right") this.step(1, cx);
    else if (e.key === "o" || e.key === "enter") this.openInPreview(cx);
    else return;
    cx.stop_propagation();
  }

  fitted(img) {
    if (!img.w || !img.h) return image(img.src).size_full();
    const scale = Math.min(this.box.w / img.w, this.box.h / img.h, 1);
    return image(img.src).w(Math.round(img.w * scale)).h(Math.round(img.h * scale));
  }

  button(id, label, onClick, t) {
    return div().id(id).h(24).px(9).flex().items_center().rounded(6).text_size(12).cursor_pointer()
      .bg(t.raised).text_color(t.foreground).hover((s) => s.bg(t.hover)).on_click((_e, cx) => onClick(cx)).child(label);
  }

  arrow(id, glyph, delta, t) {
    return div().id(id).w(36).flex_none().flex().items_center().justify_center().rounded(8).text_size(24).cursor_pointer()
      .text_color(t.muted).hover((s) => s.bg(t.hover)).on_click((_e, cx) => this.step(delta, cx)).child(glyph);
  }

  render(cx) {
    const t = theme(), img = this.images[this.at], zoom = settings().zoom;
    return v_flex().id("outputs-preview").track_focus(this.handle).size_full().min_h(0).bg(t.popover).text_color(t.foreground).text_size(13)
      .on_key_down((e, cx) => this.key(e, cx))
      .child(h_flex().h(44).flex_none().px(14).gap(10).items_center().border_b(1).border_color(t.border)
        .child(div().flex_1().min_w(0).truncate().font_semibold().child(img.name))
        .child(div().flex_none().text_size(11).text_color(t.dim).child(`${this.at + 1} / ${this.images.length}`))
        .child(this.button("outputs-preview-open", "Open in Preview", (cx) => this.openInPreview(cx), t))
        .child(div().id("outputs-preview-close").px(6).py(2).rounded(5).text_size(11).text_color(t.dim).cursor_pointer()
          .hover((s) => s.bg(t.hover).text_color(t.foreground)).on_click(() => closeOverlay(props().overlay)).child("Esc")))
      .when(Boolean(this.note), (e) => e.child(div().px(14).py(4).text_size(11).text_color(t.ansi1).child(this.note)))
      .child(h_flex().flex_1().min_h(0).p(8).gap(8)
        .child(this.arrow("outputs-preview-prev", "‹", -1, t))
        .child(div().id("outputs-preview-stage").flex_1().min_w(0).h_full().flex().items_center().justify_center().overflow_hidden()
          .on_size_change((size, cx) => {
            const box = { w: size.width / zoom, h: size.height / zoom };
            if (Math.abs(box.w - this.box.w) > 1 || Math.abs(box.h - this.box.h) > 1) { this.box = box; cx.notify(); }
          })
          .child(this.fitted(img)))
        .child(this.arrow("outputs-preview-next", "›", 1, t)))
      .child(div().h(26).flex_none().px(14).flex().items_center().text_size(11).text_color(t.dim).child("Left and right step through this group. O opens in Preview. Esc closes."));
  }
}
