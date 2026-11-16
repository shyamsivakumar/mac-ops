import { div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, home, layout, readTextFile, theme, settings } from "herdr";

const OWNERS = ["shyamsivakumar", "slash-eureka"];
const MINE = "shyamsivakumar";
const DAYS = 7, FLOW_DAYS = 14, STALE_DAYS = 2, LIMIT = 200, TIMEOUT = 60000, JOBS = 3, DAY_ROWS = 40, STALE_CHIPS = 8;
export const EVERY = 300000;
const DAY = 86400000;
const MERGED_FIELDS = "repository,number,title,url,closedAt,createdAt";
const OPEN_FIELDS = "repository,number,title,url,createdAt";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const pad2 = (n) => String(n).padStart(2, "0");
const utcDay = (ms) => new Date(ms).toISOString().slice(0, 10);
const localDay = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; };
const clock = (ms) => { const d = new Date(ms); return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`; };
const NOT_TICKETS = new Set(["UTF", "GPT", "SHA", "ISO", "AES", "RSA", "TLS", "SSL", "CVE", "RFC", "PEP", "CRC", "MD"]);
const KNOWN_PREFIXES = ["SRW", "MO", "SLA", "AUH", "LMW"];

async function coordinatorPrefixes() {
  const text = await readTextFile(`${home()}/.coordinator/tickets.json`);
  return text ? Object.values(JSON.parse(text).repos).map((repo) => repo.key) : [];
}

// Prefixes are the known ones plus any that appear as an uppercase PREFIX-123 in this load's titles.
function withTickets(merged, coordinator) {
  const prefixes = new Set([...KNOWN_PREFIXES, ...coordinator]);
  for (const pr of merged) for (const m of pr.title.matchAll(/\b([A-Z]{2,4})-\d+\b/g)) if (!NOT_TICKETS.has(m[1])) prefixes.add(m[1]);
  const pattern = new RegExp(`\\b(${[...prefixes].sort((a, b) => b.length - a.length).join("|")})-?(\\d+)\\b`, "i");
  return merged.map((pr) => {
    const m = pr.title.match(pattern);
    return { ...pr, ticket: m ? `${m[1].toUpperCase()}-${m[2]}` : null };
  });
}
const count = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function windowStart(now, days = DAYS) {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - (days - 1));
  return d.getTime();
}

async function gh(args) {
  const r = await exec("gh", args, { timeout: TIMEOUT });
  if (r.code !== 0) throw new Error(`gh ${args.slice(0, 2).join(" ")}: ${r.stderr.trim().split("\n")[0] || `exit ${r.code}`}`);
  return JSON.parse(r.stdout);
}

async function pool(jobs, errors) {
  const queue = jobs;
  const worker = async () => { for (let job; (job = queue.shift());) await job().catch((e) => errors.push(String(e?.message ?? e).split(". ")[0])); };
  await Promise.all(Array.from({ length: JOBS }, worker));
}

const basics = (r) => ({ repo: r.repository.name, nameWithOwner: r.repository.nameWithOwner, number: r.number, title: r.title, url: r.url });

// One search per owner for the whole window. An owner whose week fills that search
// (200 results) is split into one search per UTC day; past days are kept and only
// today's and yesterday's UTC days are read again.
const mergedWeeks = new Map();
const splitOwners = new Set();
const mergedDays = new Map();
const openByOwner = new Map();

// Every copy of the mod shares this module: one fetch at a time, and a result younger than EVERY is reused.
let pending = null, cached = null;
export function loadShipped(force = false) {
  if (pending) return pending;
  if (!force && cached && Date.now() - cached.at < EVERY) return Promise.resolve(cached);
  pending = fetchShipped().then((r) => (cached = r)).finally(() => { pending = null; });
  return pending;
}

async function fetchShipped(now = Date.now()) {
  const start = windowStart(now, FLOW_DAYS), week = windowStart(now), errors = [];
  const dates = [];
  for (let ms = Date.parse(utcDay(start)); ms <= now; ms += DAY) dates.push(utcDay(ms));
  const recent = utcDay(now - DAY);
  for (const key of mergedDays.keys()) if (!dates.includes(key.split("|")[1])) mergedDays.delete(key);

  const jobs = [];
  const mergedSearch = (owner, range) => gh(["search", "prs", "--owner", owner, "--author", MINE, "--merged-at", range, "--json", MERGED_FIELDS, "--limit", String(LIMIT)]);
  const mergedPr = (r) => ({ ...basics(r), at: Date.parse(r.closedAt), created: Date.parse(r.createdAt) });
  const dayJobs = (owner) => dates.filter((date) => !mergedDays.has(`${owner}|${date}`) || date >= recent).map((date) => async () => {
    const rows = await mergedSearch(owner, `${date}..${date}`);
    mergedDays.set(`${owner}|${date}`, { prs: rows.map(mergedPr), capped: rows.length >= LIMIT });
  });
  for (const owner of OWNERS) {
    if (splitOwners.has(owner)) jobs.push(...dayJobs(owner));
    else jobs.push(async () => {
      const rows = await mergedSearch(owner, `>=${dates[0]}`);
      if (rows.length < LIMIT) return void mergedWeeks.set(owner, rows.map(mergedPr));
      splitOwners.add(owner); mergedWeeks.delete(owner);
      jobs.push(...dayJobs(owner));
    });
    jobs.push(async () => {
      const rows = await gh(["search", "prs", "--owner", owner, "--state", "open", "--author", MINE, "--sort", "created", "--order", "asc", "--json", OPEN_FIELDS, "--limit", String(LIMIT)]);
      openByOwner.set(owner, rows.map((r) => ({ ...basics(r), at: Date.parse(r.createdAt) })));
    });
  }
  await pool(jobs, errors);
  const coordinator = await coordinatorPrefixes();

  const days = [...mergedDays.values()];
  const fortnight = withTickets([...mergedWeeks.values(), ...days.map((d) => d.prs)].flat().filter((p) => p.at >= start), coordinator).sort((a, b) => b.at - a.at);
  return {
    merged: fortnight.filter((p) => p.at >= week), fortnight,
    capped: [...mergedDays].some(([key, d]) => d.capped && key.split("|")[1] >= utcDay(week)),
    open: [...openByOwner.values()].flat(),
    errors: [...new Set(errors)], at: Date.now(),
  };
}

export function dayGroups(merged, now) {
  const today = localDay(now), yesterday = localDay(now - DAY), groups = [];
  for (const pr of merged) {
    const key = localDay(pr.at);
    if (groups.at(-1)?.key !== key) {
      const d = new Date(pr.at);
      const label = key === today ? "Today" : key === yesterday ? "Yesterday" : `${WEEKDAYS[d.getDay()]} ${MONTHS[d.getMonth()]} ${d.getDate()}`;
      groups.push({ key, label, prs: [] });
    }
    groups.at(-1).prs.push(pr);
  }
  for (const g of groups) {
    const repos = new Map(), tickets = new Map(), untracked = new Map();
    for (const pr of g.prs) {
      repos.set(pr.repo, (repos.get(pr.repo) ?? 0) + 1);
      const into = pr.ticket ? tickets : untracked, id = pr.ticket ?? pr.repo;
      if (into.has(id)) into.get(id).prs.push(pr);
      else into.set(id, { key: `${g.key}|${id}`, ticket: pr.ticket, repo: pr.repo, noTicket: !pr.ticket, prs: [pr] });
    }
    g.repos = [...repos].sort((a, b) => b[1] - a[1]);
    g.entries = [...tickets.values(), ...[...untracked.values()].map((e) => (e.prs.length === 1 ? { ...e, key: detailKey(e.prs[0]), noTicket: false } : e))];
  }
  return groups;
}

export function summary(merged, now) {
  const today = merged.filter((p) => localDay(p.at) === localDay(now));
  return { today: today.length, repos: new Set(today.map((p) => p.nameWithOwner)).size, week: merged.length };
}

export function staleByRepo(open, now) {
  const by = new Map();
  for (const pr of open.filter((p) => now - p.at > STALE_DAYS * DAY).sort((a, b) => a.at - b.at)) {
    if (!by.has(pr.nameWithOwner)) by.set(pr.nameWithOwner, { repo: pr.repo, prs: [] });
    by.get(pr.nameWithOwner).prs.push(pr);
  }
  return [...by.values()].sort((a, b) => b.prs.length - a.prs.length);
}

const details = new Map();
const detailKey = (pr) => `${pr.nameWithOwner}#${pr.number}`;
export const detailOf = (pr) => details.get(detailKey(pr));

const firstParagraph = (body) => {
  const paragraph = body.split(/\n\s*\n/).map((p) => p.replace(/^#+\s.*$/gm, "").trim()).find(Boolean) ?? "No description.";
  return paragraph.length > 400 ? paragraph.slice(0, 399) + "…" : paragraph;
};

export async function loadDetail(pr) {
  const key = detailKey(pr);
  if (details.has(key) && details.get(key).state !== "error") return;
  details.set(key, { state: "loading" });
  try {
    const d = await gh(["pr", "view", String(pr.number), "-R", pr.nameWithOwner, "--json", "body,additions,deletions,changedFiles"]);
    details.set(key, { state: "ready", text: firstParagraph(d.body), additions: d.additions, deletions: d.deletions, files: d.changedFiles });
  } catch (e) {
    details.set(key, { state: "error", message: String(e?.message ?? e) });
  }
}

const graphHidden = () => {
  const find = (node) => (node?.id === "graph-col" ? node : (node?.children ?? []).map(find).find(Boolean));
  return Boolean(find(layout())?.hidden);
};

export const since = (ms) => {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`;
};
const ageDays = (ms) => `${Math.floor((Date.now() - ms) / DAY)}d`;

export class Shipped {
  constructor() {
    this.data = null; this.loading = false; this.stale = true; this.lastRender = 0;
    this.open = new Set(); this.fullDays = new Set(); this.days = new Map();
  }

  fetch(force) { return loadShipped(force); }

  refresh(cx, force = false) {
    if (this.loading) return;
    this.loading = true; this.stale = false;
    cx.notify();
    cx.spawn(async (cx) => {
      try {
        this.data = await this.fetch(force);
      } finally {
        this.loading = false; cx.notify();
      }
    });
  }

  tick(cx, active) {
    if (!active || graphHidden() || Date.now() - this.lastRender > EVERY * 1.5) this.stale = true;
    else this.refresh(cx);
  }

  wake(cx) {
    if (!this.stale || graphHidden()) return;
    this.stale = false;
    cx.timer.after(0, (cx) => this.refresh(cx));
  }

  toggle(entry, cx) {
    if (this.open.delete(entry.key)) return cx.notify();
    this.open.add(entry.key);
    if (entry.prs.length === 1) cx.spawn(async (cx) => { await loadDetail(entry.prs[0]); cx.notify(); });
    cx.notify();
  }

  toggleDay(key, shown, cx) {
    this.days.set(key, !shown);
    cx.notify();
  }

  expanded(pr, t) {
    const d = detailOf(pr);
    const body = v_flex().pl(40).pr(14).pb(6).gap(3).text_size(11.5);
    if (!d || d.state === "loading") return body.child(div().text_color(t.dim).child("Loading…"));
    if (d.state === "error") return body.child(div().text_color(t.ansi1).child(d.message));
    return body.child(div().text_color(t.muted).child(d.text))
      .child(h_flex().gap(8).text_size(11).child(div().text_color(t.ansi2).child(`+${d.additions}`)).child(div().text_color(t.ansi1).child(`−${d.deletions}`))
        .child(div().text_color(t.dim).child(count(d.files, "file"))));
  }

  entryRow(entry, t, mono) {
    const pr = entry.prs[0], group = entry.prs.length > 1, open = this.open.has(entry.key);
    const repos = [...new Set(entry.prs.map((x) => x.repo))].join(", ");
    const row = h_flex().id(`sh-${entry.key}`).h(26).flex_none().pr(14).gap(8).items_center().cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => (group ? this.toggle(entry, cx) : cx.open_url(pr.url)))
      .child(h_flex().id(`sh-chev-${entry.key}`).w(32).h_full().flex_none().items_center().justify_center().text_color(t.dim).hover((s) => s.text_color(t.foreground))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => { cx.stop_propagation(); this.toggle(entry, cx); }).child(open ? "▾" : "▸"))
      .child(div().w(130).flex_none().truncate().font_family(mono).text_size(11.5).text_color(t.muted).child(repos))
      .child(div().w(70).flex_none().truncate().font_family(mono).text_size(11).text_color(t.accent).child(pr.ticket ?? ""))
      .child(div().flex_1().min_w(0).truncate().text_size(12).child(entry.noTicket ? `${pr.repo} · ${entry.prs.length} PRs without a ticket` : pr.title))
      .when(group && !entry.noTicket, (e) => e.child(div().flex_none().text_size(11).text_color(t.muted).child(`${entry.prs.length} PRs`)))
      .child(div().w(38).flex_none().text_right().text_size(11).text_color(t.dim).child(clock(pr.at)));
    return v_flex().flex_none().child(row).when(open, (e) => e.children(group ? entry.prs.map((x) => this.groupedPr(x, t, mono)) : [this.expanded(pr, t)]));
  }

  groupedPr(pr, t, mono) {
    return h_flex().id(`sh-pr-${detailKey(pr)}`).h(24).flex_none().pl(40).pr(14).gap(8).items_center().cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => cx.open_url(pr.url))
      .child(div().w(130).flex_none().truncate().font_family(mono).text_size(11.5).text_color(t.muted).child(pr.repo))
      .child(div().flex_1().min_w(0).truncate().text_size(11.5).child(pr.title))
      .child(div().flex_none().text_size(11).text_color(t.dim).child(`#${pr.number}`))
      .child(div().w(38).flex_none().text_right().text_size(11).text_color(t.dim).child(clock(pr.at)));
  }

  staleSection(groups, t, mono) {
    const chip = (pr) => h_flex().id(`sh-stale-${detailKey(pr)}`).h(20).px(6).gap(5).flex_none().items_center().rounded(4).cursor_pointer().text_size(11).text_color(t.blocked)
      .hover((s) => s.bg(t.raised)).on_click((_e, cx) => cx.open_url(pr.url)).child(`#${pr.number}`).child(div().text_color(t.dim).child(ageDays(pr.at)));
    return v_flex().flex_none().border_b(1).border_color(t.border)
      .child(div().h(24).flex_none().px(14).flex().items_center().text_size(11).text_color(t.dim).child(`Still open after ${STALE_DAYS} days`))
      .child(v_flex().id("sh-stale").max_h(26 * 5).overflow_y_scrollbar().pb(4)
        .children(groups.map((g) => h_flex().h(26).flex_none().px(14).gap(8).items_center().overflow_hidden()
          .child(div().w(130).flex_none().truncate().font_family(mono).text_size(11.5).text_color(t.muted).child(g.repo))
          .children(g.prs.slice(0, STALE_CHIPS).map(chip))
          .when(g.prs.length > STALE_CHIPS, (e) => e.child(div().flex_none().text_size(11).text_color(t.dim).child(`+${g.prs.length - STALE_CHIPS} more`))))));
  }

  render(cx) {
    this.lastRender = Date.now();
    this.wake(cx);
    const t = theme(), mono = settings().font_family ?? "JetBrains Mono", now = Date.now(), d = this.data;
    const body = v_flex().flex_1().min_h(0).size_full();
    if (!d) return body.child(div().flex_1().flex().items_center().justify_center().text_size(12).text_color(t.dim).child("Loading merged pull requests…"));
    const s = summary(d.merged, now), plus = d.capped ? "+" : "";
    const days = dayGroups(d.merged, now), stale = staleByRepo(d.open, now);
    return body
      .child(h_flex().h(30).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border).text_size(12)
        .child(div().font_semibold().child(`Today: ${s.today}${plus} merged across ${count(s.repos, "repo")}`))
        .child(div().text_color(t.dim).child(`· this week: ${s.week}${plus}`))
        .child(div().flex_1())
        .child(div().text_size(11).text_color(t.dim).child(this.loading ? "Refreshing…" : `Updated ${since(d.at)}`)))
      .when(d.errors.length > 0, (e) => e.child(v_flex().flex_none().px(14).py(4).gap(2).border_b(1).border_color(t.border).text_size(11).text_color(t.ansi1)
        .children(d.errors.slice(0, 3).map((m) => div().truncate().child(m)))
        .when(d.errors.length > 3, (el) => el.child(div().child(`and ${d.errors.length - 3} more errors`)))))
      .when(stale.length > 0, (e) => e.child(this.staleSection(stale, t, mono)))
      .child(v_flex().id("sh-feed").flex_1().min_h(0).overflow_y_scrollbar().pb(8)
        .when(days.length === 0 && d.errors.length === 0, (e) => e.child(div().p(14).text_size(12).text_color(t.dim).child("Nothing merged in the last 7 days.")))
        .children(days.flatMap((g) => {
          const shown = this.days.get(g.key) ?? (g.label === "Today" || (g.label === "Yesterday" && s.today === 0));
          const all = this.fullDays.has(g.key), entries = all ? g.entries : g.entries.slice(0, DAY_ROWS);
          return [
            h_flex().id(`sh-day-${g.key}`).h(28).flex_none().px(14).gap(8).items_center().text_size(11).cursor_pointer().hover((s) => s.bg(t.hover))
              .on_click((_e, cx) => this.toggleDay(g.key, shown, cx))
              .child(div().w(10).flex_none().text_color(t.dim).child(shown ? "▾" : "▸"))
              .child(div().flex_none().text_color(t.dim).font_semibold().child(`${g.label} · ${g.prs.length}`))
              .child(div().flex_1().min_w(0).truncate().text_color(t.dim).child(g.repos.map(([name, n]) => `${name} ${n}`).join(" · "))),
            ...(shown ? entries.map((entry) => this.entryRow(entry, t, mono)) : []),
            ...(shown && g.entries.length > entries.length ? [div().id(`sh-more-${g.key}`).h(24).flex_none().px(14).flex().items_center().text_size(11).text_color(t.accent).cursor_pointer()
              .hover((s) => s.bg(t.hover)).on_click((_e, cx) => { this.fullDays.add(g.key); cx.notify(); }).child(`Show ${g.entries.length - entries.length} more`)] : []),
          ];
        })));
  }
}
