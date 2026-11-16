import { div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { home, readTextFile, theme, settings } from "herdr";
import { Shipped, loadShipped, since, windowStart } from "./shipped.js";

const FLOW_DAYS = 14, SLOWEST = 5, SITTING = 3, BAR_MAX = 44;
const HOUR = 3600000, DAY = 86400000;
const LANES = [["needs", "Needs you"], ["run", "Working"], ["checks", "Checks running"], ["cifail", "CI failed"], ["review", "Review pending"], ["ready", "Approved/Ready"], ["backlog", "Backlog"]];
const LOG = `${home()}/.local/state/herdr-board/flow.jsonl`;
const WEEKDAY_LETTER = ["S", "M", "T", "W", "T", "F", "S"];

const pad2 = (n) => String(n).padStart(2, "0");
const localDay = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; };

export const duration = (ms) => (ms < HOUR ? `${Math.max(1, Math.round(ms / 60000))}m` : ms < 2 * DAY ? `${(ms / HOUR).toFixed(1)}h` : `${(ms / DAY).toFixed(1)}d`);

export function percentile(sorted, p) {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.ceil(p * sorted.length) - 1)];
}

const spread = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  return { n: sorted.length, median: percentile(sorted, 0.5), p90: percentile(sorted, 0.9) };
};

export function mergedPerDay(merged, now) {
  const first = windowStart(now, FLOW_DAYS), days = [];
  for (let i = 0; i < FLOW_DAYS; i++) {
    const d = new Date(first); d.setDate(d.getDate() + i);
    days.push({ key: localDay(d.getTime()), date: d, count: 0 });
  }
  const byKey = new Map(days.map((d) => [d.key, d]));
  const repos = new Map();
  for (const pr of merged) {
    const day = byKey.get(localDay(pr.at));
    if (day) day.count += 1;
    repos.set(pr.repo, (repos.get(pr.repo) ?? 0) + 1);
  }
  return { days, repos: [...repos].sort((a, b) => b[1] - a[1]) };
}

export function startToMerge(merged) {
  const prs = merged.filter((p) => p.created && p.at >= p.created);
  const byRepo = new Map();
  for (const pr of prs) byRepo.set(pr.repo, [...(byRepo.get(pr.repo) ?? []), pr.at - pr.created]);
  return {
    all: spread(prs.map((p) => p.at - p.created)),
    repos: [...byRepo].map(([repo, ms]) => ({ repo, ...spread(ms) })).sort((a, b) => b.n - a.n),
    slowest: [...prs].sort((a, b) => (b.at - b.created) - (a.at - a.created)).slice(0, SLOWEST),
  };
}

export function laneTimes(lines, now) {
  const byKey = new Map();
  for (const e of lines) byKey.set(e.key, [...(byKey.get(e.key) ?? []), e]);
  const spent = new Map(LANES.map(([id]) => [id, []])), sitting = new Map(LANES.map(([id]) => [id, []]));
  for (const entries of byKey.values()) {
    entries.sort((a, b) => a.t - b.t);
    entries.forEach((e, i) => {
      if (!spent.has(e.to)) return;
      const next = entries[i + 1];
      if (next) { if (e.from !== null) spent.get(e.to).push(next.t - e.t); }
      else sitting.get(e.to).push({ key: e.key, project: e.project, pr: e.pr, ms: now - e.t });
    });
  }
  return LANES.map(([id, name]) => ({ id, name, ...spread(spent.get(id)), sitting: sitting.get(id).sort((a, b) => b.ms - a.ms) }));
}

async function loadLog() {
  const text = await readTextFile(LOG).catch(() => null);
  return (text ?? "").split("\n").filter(Boolean).flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
}

export class Flow extends Shipped {
  async fetch(force) {
    const [shipped, log] = await Promise.all([loadShipped(force), loadLog()]);
    return { ...shipped, log };
  }

  heading(text, t) {
    return div().h(26).flex_none().px(14).flex().items_center().text_size(11).font_semibold().text_color(t.dim).child(text);
  }

  perDay(t, now, fortnight) {
    const { days, repos } = mergedPerDay(fortnight, now), top = Math.max(1, ...days.map((d) => d.count));
    const column = (d) => v_flex().flex_1().min_w(0).items_center().justify_end().gap(3)
      .child(div().text_size(11).text_color(d.count ? t.foreground : t.dim).child(String(d.count)))
      .child(div().w(12).h(Math.max(2, Math.round((d.count / top) * BAR_MAX))).rounded(2).bg(d.count ? t.accent : t.border))
      .child(div().text_size(10).text_color(t.dim).child(`${WEEKDAY_LETTER[d.date.getDay()]}${d.date.getDate()}`));
    return v_flex().flex_none().child(this.heading(`Cards finished per day · ${fortnight.length} in ${FLOW_DAYS} days`, t))
      .child(h_flex().px(14).h(BAR_MAX + 38).items_end().gap(2).children(days.map(column)))
      .child(div().px(14).py(4).text_size(11).text_color(t.muted).child(repos.map(([name, n]) => `${name} ${n}`).join(" · ")));
  }

  statRow(label, s, t, mono) {
    return h_flex().h(22).flex_none().px(14).gap(8).items_center().text_size(11.5)
      .child(div().w(170).flex_none().truncate().font_family(mono).text_color(t.muted).child(label))
      .child(div().w(50).flex_none().text_color(t.dim).child(s.n ? `${s.n}` : "none"))
      .child(div().w(80).flex_none().child(s.n ? `median ${duration(s.median)}` : ""))
      .child(div().w(80).flex_none().child(s.n ? `p90 ${duration(s.p90)}` : ""));
  }

  startToMergeSection(t, mono, fortnight) {
    const s = startToMerge(fortnight);
    return v_flex().flex_none().child(this.heading("Start to merge · PR opened to merged", t))
      .child(this.statRow("All repos", s.all, t, mono))
      .children(s.repos.map((r) => this.statRow(r.repo, r, t, mono)))
      .child(div().h(22).flex_none().px(14).flex().items_center().text_size(11).text_color(t.dim).child("Slowest"))
      .children(s.slowest.map((pr) => h_flex().id(`fl-slow-${pr.nameWithOwner}#${pr.number}`).h(24).flex_none().px(14).gap(8).items_center().cursor_pointer()
        .hover((x) => x.bg(t.hover)).on_click((_e, cx) => cx.open_url(pr.url))
        .child(div().w(170).flex_none().truncate().font_family(mono).text_size(11.5).text_color(t.muted).child(`${pr.repo} #${pr.number}`))
        .child(div().w(50).flex_none().text_size(11.5).text_color(t.blocked).child(duration(pr.at - pr.created)))
        .child(div().flex_1().min_w(0).truncate().text_size(12).child(pr.title))));
  }

  lanesSection(t, mono, log, now) {
    const head = this.heading("Time in lanes", t);
    if (!log.length) return v_flex().flex_none().child(head)
      .child(div().px(14).py(6).text_size(12).text_color(t.dim).child("Lane times start recording once the board logs lane changes."));
    return v_flex().flex_none().child(head).children(laneTimes(log, now).map((lane) => v_flex().flex_none()
      .child(this.statRow(lane.name, lane, t, mono))
      .when(lane.sitting.length > 0, (e) => e.child(h_flex().h(20).flex_none().pl(28).pr(14).gap(10).items_center().text_size(11).text_color(t.dim)
        .child("sitting")
        .children(lane.sitting.slice(0, SITTING).map((c) => div().flex_none().text_color(t.muted).child(`${c.pr ? `${c.project} #${c.pr}` : c.key} ${duration(c.ms)}`)))
        .when(lane.sitting.length > SITTING, (x) => x.child(`+${lane.sitting.length - SITTING}`))))));
  }

  render(cx) {
    this.lastRender = Date.now();
    this.wake(cx);
    const t = theme(), mono = settings().font_family ?? "JetBrains Mono", now = Date.now(), d = this.data;
    const body = v_flex().flex_1().min_h(0).size_full();
    if (!d) return body.child(div().flex_1().flex().items_center().justify_center().text_size(12).text_color(t.dim).child("Loading flow numbers…"));
    return body
      .child(h_flex().h(30).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border).text_size(12)
        .child(div().font_semibold().child("Flow numbers"))
        .child(div().flex_1())
        .child(div().text_size(11).text_color(t.dim).child(this.loading ? "Refreshing…" : `Updated ${since(d.at)}`)))
      .when(d.errors.length > 0, (e) => e.child(v_flex().flex_none().px(14).py(4).gap(2).border_b(1).border_color(t.border).text_size(11).text_color(t.ansi1)
        .children(d.errors.slice(0, 3).map((m) => div().truncate().child(m)))))
      .child(v_flex().id("fl-feed").flex_1().min_h(0).overflow_y_scrollbar().pb(8)
        .child(this.perDay(t, now, d.fortnight))
        .child(this.startToMergeSection(t, mono, d.fortnight))
        .child(this.lanesSection(t, mono, d.log, now)));
  }
}
