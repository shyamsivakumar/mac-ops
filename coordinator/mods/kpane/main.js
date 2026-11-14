// The diagram popup for kpane: a near full window overlay that shows the
// picture kpane put in ~/.config/herdr-app/kpane/. Esc closes it.
//
// The pointer file says which picture to show, what to call it, how big the
// picture is and how far to zoom in, so the mod does not have to read the
// picture itself.
import { View, div, image } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { appHome, readTextFile, theme } from "herdr";

const POINTER = "/kpane/current.json";
const ZOOMS = [1, 1.5, 2, 3, 4, 6, 8];

export default class Kpane extends View {
  init(_props, cx) {
    this.title = "Diagram";
    this.picture = "kpane/current.png";
    this.natural = null;
    this.box = { width: 0, height: 0 };
    this.zoom = 1;
    this.load(cx);
  }

  load(cx) {
    cx.spawn(async (cx) => {
      try {
        const raw = await readTextFile(`${appHome()}${POINTER}`);
        const data = JSON.parse(raw || "{}");
        if (data.title) this.title = data.title;
        if (data.image) this.picture = data.image;
        if (data.width && data.height) {
          this.natural = { width: data.width, height: data.height };
        }
        if (data.zoom) this.zoom = data.zoom;
      } catch (error) {
        this.title = `Diagram (not found: ${error})`;
      }
      cx.notify();
    });
  }

  // The picture as large as the box allows, with its shape kept.
  fit() {
    const box = this.box;
    const natural = this.natural;
    let size;
    if (!box.width || !box.height) {
      size = natural ? { ...natural } : { width: 0, height: 0 };
    } else if (!natural) {
      size = { width: box.width, height: box.height };
    } else {
      const scale = Math.min(box.width / natural.width, box.height / natural.height);
      size = { width: natural.width * scale, height: natural.height * scale };
    }
    return { width: Math.round(size.width * this.zoom), height: Math.round(size.height * this.zoom) };
  }

  // The zoom steps, up and down, around the current one.
  step(direction) {
    const index = ZOOMS.findIndex((value) => value >= this.zoom - 0.001);
    const at = index === -1 ? ZOOMS.length - 1 : index;
    const next = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, at + direction))];
    this.zoom = next;
  }

  button(label, on_click) {
    const t = theme();
    return div().id(`kpane-${label}`).px(8).h(22).rounded(4).text_size(12)
      .text_color(t.foreground).bg(t.raised).cursor_pointer()
      .on_click((_event, cx) => { on_click(); cx.notify(); })
      .child(label);
  }

  render(cx) {
    const t = theme();
    const size = this.fit();
    const zoomed = this.zoom > 1.001;
    return v_flex().size_full().bg(t.canvas).children([
      h_flex().h(40).px(12).gap(10).items_center().border_b_1().border_color(t.border)
        .child(div().text_size(15).font_semibold().text_color(t.foreground).child(this.title))
        .child(this.button("−", () => this.step(-1)))
        .child(this.button("Fit", () => { this.zoom = 1; }))
        .child(this.button("+", () => this.step(1)))
        .child(div().text_size(12).text_color(t.dim).child(`${Math.round(this.zoom * 100)}%`))
        .child(div().text_size(12).text_color(t.dim).child("Esc closes")),
      div().flex_1().min_h_0().p(12).id("kpane-picture")
        .on_size_change((size, cx) => { this.box = size; cx.notify(); })
        .on_scroll_wheel((event, cx) => {
          this.step(event.delta.y > 0 ? 1 : -1);
          cx.notify();
        })
        .overflow_scroll()
        .when(zoomed, (el) => el.items_start().justify_start(), (el) => el.items_center().justify_center())
        .child(image(this.picture).w(size.width).h(size.height)),
    ]);
  }
}
