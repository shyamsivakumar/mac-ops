import { View } from "gpui-kit";
import { props } from "herdr";
import { Board } from "./board.js";
import { Preview } from "./preview.js";

export default class Outputs extends View {
  init(_props, cx) {
    this.part = props()?.role === "preview" ? new Preview() : new Board();
    this.part.init(cx);
  }

  render(cx) { return this.part.render(cx); }
}
