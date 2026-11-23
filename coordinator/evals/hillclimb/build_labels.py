#!/usr/bin/env python3
"""Build the cold-start label set for the coordinator hill climb (MO-1199 a).

Reads only:
  ~/.pi/agent-coordinator/sessions/--Users-shyamsivakumar-Code-coordinator--/*.jsonl
  ~/Code/coordinator/decisions.json snapshots (backups, tmp files)
  ~/Code/mac-ops/coordinator/overnight/lane_driver.py and ~/.local/bin/coordq
    (only to read the recommended option each generator records)

Writes only under ~/Code/coordinator/evals/hillclimb/.

A label is kept only when the coordinator's recommendation is recorded
somewhere: a decisions-board item's `recommended` option, a
"(Recommended: ...)" line in the ask, or the generator code that raises the
card. Nothing is invented. Action cards (kind "action") carry no options and
no recommendation, so they are not labels.
"""

import ast
import glob
import hashlib
import json
import os
import re

HOME = os.path.expanduser("~")
SESS = f"{HOME}/.pi/agent-coordinator/sessions/--Users-shyamsivakumar-Code-coordinator--"
OUT = f"{HOME}/Code/coordinator/evals/hillclimb"
TMP = os.environ.get("TMPDIR", "/tmp")

# ---------------------------------------------------------------- sources


def message_text(m):
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(
            str(x.get("text", "")) for x in c if isinstance(x, dict) and x.get("type") == "text"
        )
    return str(c or "")


def tool_calls(m):
    c = m.get("content")
    if not isinstance(c, list):
        return []
    return [x for x in c if isinstance(x, dict) and x.get("type") == "toolCall"]


def load_messages():
    recs = []
    for f in sorted(glob.glob(f"{SESS}/*.jsonl")):
        base = os.path.basename(f)
        with open(f) as fh:
            for i, line in enumerate(fh):
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "message":
                    continue
                m = o["message"]
                recs.append(
                    dict(
                        f=base,
                        i=i,
                        ts=o.get("timestamp"),
                        role=m.get("role"),
                        text=message_text(m),
                        tcs=tool_calls(m),
                    )
                )
    return recs


# ------------------------------------------------- decisions board items


def match_brace(s, start):
    depth = 0
    i = start
    instr = None
    esc = False
    while i < len(s):
        ch = s[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == instr:
                instr = None
        else:
            if ch in "\"'":
                instr = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def match_paren(s, start):
    depth = 0
    i = start
    instr = None
    esc = False
    while i < len(s):
        ch = s[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == instr:
                instr = None
        else:
            if ch in "\"'":
                instr = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def add_panel_item(panel, it, ts, f, i):
    if not isinstance(it, dict) or not it.get("id"):
        return
    opts = [x.get("label") for x in it.get("options", []) if isinstance(x, dict) and x.get("label")]
    rec = [
        x.get("label")
        for x in it.get("options", [])
        if isinstance(x, dict) and x.get("recommended")
    ]
    panel.setdefault(it["id"], []).append(
        dict(ts=ts, f=f, i=i, title=it.get("title", ""), options=opts, rec=rec, kind=it.get("kind", ""))
    )


def scan_panel_blob(blob, panel, ts, f, i):
    dec = json.JSONDecoder()
    for mt in re.finditer(r'\{\s*"(?:updated|items)"', blob):
        try:
            obj, _ = dec.raw_decode(blob[mt.start() :])
        except Exception:
            continue
        if isinstance(obj, dict):
            for it in obj.get("items", []) or []:
                add_panel_item(panel, it, ts, f, i)
    for mt in re.finditer(r'\{\s*[\'"]id[\'"]\s*:', blob):
        en = match_brace(blob, mt.start())
        if en < 0:
            continue
        try:
            it = ast.literal_eval(blob[mt.start() : en + 1])
        except Exception:
            continue
        add_panel_item(panel, it, ts, f, i)
    for mt in re.finditer(r"(?<![\w.])it\(", blob):
        st = mt.end() - 1
        en = match_paren(blob, st)
        if en < 0:
            continue
        try:
            node = ast.parse("f" + blob[st : en + 1], mode="eval").body
        except Exception:
            continue
        if not isinstance(node, ast.Call):
            continue
        try:
            args = [ast.literal_eval(a) for a in node.args]
        except Exception:
            continue
        if len(args) < 3:
            continue
        kw = {}
        for k in node.keywords:
            try:
                kw[k.arg] = ast.literal_eval(k.value)
            except Exception:
                pass
        opts = args[4] if len(args) > 4 else None
        it = {
            "id": args[0],
            "group": args[1],
            "title": args[2],
            "kind": kw.get("kind", ""),
            "options": (
                [{"label": opts[0], "recommended": True}] + [{"label": o} for o in opts[1:]]
                if isinstance(opts, list) and opts
                else []
            ),
        }
        add_panel_item(panel, it, ts, f, i)


def load_panel(recs):
    panel = {}
    for r in recs:
        for tc in r["tcs"]:
            a = tc.get("arguments") or {}
            blobs = []
            if tc.get("name") == "write":
                p = str(a.get("path", ""))
                if p.endswith((".json", ".py")) and ("dec" in p or "decision" in p):
                    blobs.append(a.get("content") or "")
            elif tc.get("name") == "bash":
                cmd = a.get("command") or ""
                if "recommended" in cmd or '"items"' in cmd or "'items'" in cmd:
                    blobs.append(cmd)
            elif tc.get("name") == "edit":
                if "decision" in str(a.get("path", "")):
                    for e in a.get("edits", []) or []:
                        blobs.append(str(e.get("newText", "")))
            for blob in blobs:
                scan_panel_blob(blob, panel, r["ts"], r["f"], r["i"])
    # on-disk snapshots
    snaps = (
        glob.glob(f"{HOME}/Code/coordinator/decisions.json*")
        + glob.glob(f"{HOME}/Code/coordinator/backups/**/decisions.json*", recursive=True)
        + glob.glob(f"{HOME}/Code/coordinator/backups/tmp-decisions.json")
    )
    for p in snaps:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        for it in (d.get("items") if isinstance(d, dict) else None) or []:
            add_panel_item(panel, it, None, os.path.relpath(p, HOME), -1)
    return panel


# ------------------------------------------------------- board answers

BOARD_LINE = re.compile(r"^\s*-\s+(\S+)\s+\((.*)\):\s*(.*)$")


def load_board(recs):
    rows = []
    for r in recs:
        if r["role"] != "user":
            continue
        t = r["text"].strip()
        if not t.startswith("Decisions:"):
            continue
        for ln in t.splitlines():
            m = BOARD_LINE.match(ln)
            if m:
                rows.append(
                    dict(
                        id=m.group(1),
                        title=m.group(2).strip(),
                        answer=m.group(3).strip(),
                        ts=r["ts"],
                        f=r["f"],
                        i=r["i"],
                    )
                )
    return rows


# generator-recorded recommendations (read from the code that raises the card)
GEN = {
    "recut": dict(
        options=["Re-cut it into smaller pull requests"],
        rec="Re-cut it into smaller pull requests",
        kind="size_exception",
        source="~/.local/bin/coordq:2053 recut_item()",
    ),
    "lane-gate-rounds": dict(
        options=[
            "Re-cut it into smaller pull requests",
            "Take it over",
            "Keep fixing (adds the gate:keep-fixing label)",
        ],
        rec="Re-cut it into smaller pull requests",
        kind="recut",
        source="~/Code/mac-ops/coordinator/overnight/lane_driver.py:840 gate_round_item()",
    ),
}
ACTION_PREFIXES = (
    "lane-close-failed-",
    "herdr-build-",
    "lane-gate-split-",
)
ACTION_IDS = {
    "factory-watchdog",
    "factory-zero-merge",
    "factory-overnight-stall",
    "overnight-selftest",
}


def gen_rule(iid):
    if iid.startswith("recut-"):
        return GEN["recut"]
    if iid.startswith("lane-gate-rounds-"):
        return GEN["lane-gate-rounds"]
    return None


def is_action(iid):
    return iid in ACTION_IDS or any(iid.startswith(p) for p in ACTION_PREFIXES)


def proximity_rec(recs, iid, before_ts=None):
    """The (Recommended: ...) that sits next to this id in the same message."""
    best = None
    for r in recs:
        t = r["text"]
        if iid not in t:
            continue
        if before_ts and r["ts"] and r["ts"] > before_ts:
            continue
        for mt in re.finditer(re.escape(iid), t):
            tail = t[mt.end() : mt.end() + 700]
            # stop at the next board id mention
            nxt = re.search(r"\n-\s+\S+\s+\(", tail)
            if nxt:
                tail = tail[: nxt.start()]
            rm = re.search(r"\(Recommended:\s*(.*?)\)", tail, re.S)
            if rm:
                best = dict(rec=rm.group(1).strip(), f=r["f"], i=r["i"], ts=r["ts"], text=t)
    return best


# ------------------------------------------------------- typed answers

AUTO_PREFIX = (
    "Status tick:",
    "Tick alert:",
    "Tick (auto-wake)",
    "Retry thread",
    "Rebase thread",
    "Separate note from Shyam's coding bot",
    "From Coder, approved by Shyam",
    "Guard test",
    "Sandbox test",
    "panel test",
    "Reply with",
    "Reply OK",
    "01a1d24a-",
    "Decisions:",
)


def is_auto(t):
    t = t.strip()
    if any(t.startswith(a) for a in AUTO_PREFIX):
        return True
    if t.startswith('<hc from="t1j">'):
        return True
    return False


def unwrap(t):
    t = t.strip()
    m = re.match(r'^<hc from="[^"]*">From Shyam \(phone\):\s*(.*?)</hc>$', t, re.S)
    return m.group(1).strip() if m else t


def load_typed(recs):
    cands = []
    for k, r in enumerate(recs):
        if r["role"] != "assistant":
            continue
        t = r["text"]
        if t.count("(Recommended:") != 1:
            continue
        idx = t.find("(Recommended:")
        pre = t[:idx].rstrip()
        if not pre.endswith("?"):
            continue
        mrec = re.match(r"\(Recommended:\s*(.*?)\)", t[idx:])
        if not mrec:
            continue
        mstart = max(
            pre.rfind("\n\n"), pre.rfind(". "), pre.rfind("? "), pre.rfind("! "), pre.rfind("\n- ")
        )
        cands.append(
            dict(
                k=k,
                rec=mrec.group(1).strip(),
                q=pre[mstart + 1 :].strip(),
                ts=r["ts"],
                f=r["f"],
                i=r["i"],
            )
        )
    out = []
    for c in cands:
        k = c["k"]
        nxt = None
        for j in range(k + 1, min(k + 6, len(recs))):
            if recs[j]["role"] == "user":
                nxt = recs[j]
                break
            if recs[j]["role"] == "assistant" and recs[j]["text"].strip():
                break
        if not nxt or is_auto(nxt["text"]):
            continue
        ans = unwrap(nxt["text"])
        if not ans or len(ans) > 400:
            continue
        out.append(dict(c, ans=ans, ansf=nxt["f"], ansi=nxt["i"], ansts=nxt["ts"]))
    return out


# ------------------------------------------------------------- options

YESNO = ["yes", "no"]


def split_alternatives(q):
    """Split an ask into the alternatives it offers, verbatim-ish."""
    body = q.strip().rstrip("?").strip()
    # "A, or B, or C" / "A or B"
    parts = re.split(r",?\s+or\s+", body)
    if len(parts) < 2:
        return None
    cleaned = []
    for p in parts:
        p = p.strip().strip(",").strip()
        p = re.sub(r"^(?:Should I|Should we|Should|Shall I|Do you want me to|Do you want)\s+", "", p, flags=re.I)
        p = p.strip()
        if p:
            cleaned.append(p)
    return cleaned if len(cleaned) >= 2 else None


MODAL = re.compile(
    r"^(should|can|will|do|does|is|are|would|could|have|has|may|shall|did|am|want)\b", re.I
)
IMPERATIVE = re.compile(
    r"^(close|keep|add|remove|merge|release|promote|run|start|file|open|build|delete|move|"
    r"send|give|create|approve|install|let|make|set|use|grant|join|pause|prune|rewrite|top|"
    r"do|fix|gate|re-cut|recut|ship|land|clear|kill|revive|archive|relabel|update|change|"
    r"check|verify|enable|disable|turn|wire|cut|split|bump|drop|raise|lower|cap|lift|restore|"
    r"revert|roll|deploy|stage|tag|go|allow|require|bring|put|take|try|apply|adopt|extend|"
    r"extend|hand|hold|ignore|include|exclude|limit|mark|move|pick|push|rebase|refresh|"
    r"reinstall|reload|rename|replace|reset|resume|retire|review|schedule|settle|skip|stop|"
    r"switch|sync|trim|unblock|unpause|wait|write)\b",
    re.I,
)


def _strip_parens(q):
    out = []
    depth = 0
    for ch in q:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _strip_prefix(q):
    q = re.sub(r"^[\s\-]+", "", q)
    q = re.sub(r"^\*\*[^*]{1,80}\*\*[:.\s]*", "", q)
    q = re.sub(r"^[\s\-*_]+", "", q)
    q = re.sub(r"^Shyam,\s*", "", q, flags=re.I)
    q = re.sub(r"^After [^,]{1,80},\s*", "", q, flags=re.I)
    q = re.sub(r"^[A-Z][^:?]{0,70}:\s*", "", q)
    return q.strip()


def options_for_question(q):
    """The choices the ask offered, or [] when it is a free-text ask."""
    bare = _strip_parens(_strip_prefix(q)).strip()
    n_or = len(re.findall(r"\bor\b", bare, re.I))
    if n_or >= 2:
        alts = split_alternatives(bare)
        if alts and len(alts) <= 3 and all(len(a) < 150 for a in alts):
            return alts
    if MODAL.match(bare) or IMPERATIVE.match(bare):
        return list(YESNO)
    if n_or == 1:
        alts = split_alternatives(bare)
        if alts and len(alts) <= 3 and all(len(a) < 150 for a in alts):
            return alts
    return []


# --------------------------------------------------------- answer match

AFFIRM = {
    "yes", "yeah", "yep", "yup", "ya", "yea", "ok", "okay", "sure", "correct", "right",
    "approved", "approve", "do it", "go", "go ahead", "go for it", "proceed", "confirmed",
    "confirm", "done", "restarted", "reloaded", "lgtm", "sgtm", "definitely", "absolutely",
    "of course", "true", "fine", "good", "sounds good", "ship it", "merge it", "close it",
    "keep going", "continue", "make it so", "run it", "start it", "file it", "open it",
    "add it", "send it", "fix it", "build it", "take it", "use it", "try it", "do that",
    "do all", "lets do it", "let's do it", "lets do that", "let's do that", "yes please",
    "yes do it", "please do", "y",
}
NEGATE = {
    "no", "nope", "nah", "dont", "don't", "do not", "not", "stop", "hold", "wait", "later",
    "skip", "cancel", "never", "no thanks", "negative", "n",
}


def norm(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pick_option(answer, options):
    """Return the option string Shyam picked, or None when it is free text."""
    if not options:
        return None
    a = norm(answer)
    if not a:
        return None
    for o in options:
        if a == norm(o):
            return o
    # a single letter / digit naming an option
    if len(a) <= 3:
        for o in options:
            if norm(o) == a:
                return o
    # "lets do b" / "option 2" / "do 1"
    last = a.split()[-1] if a.split() else ""
    for o in options:
        if norm(o) == last:
            return o
    m = re.search(r"\b(?:do|option|go with|pick|choose)\s+(\d)\b", a)
    if m:
        k = int(m.group(1)) - 1
        if 0 <= k < len(options):
            return options[k]
    # answer contains the option
    for o in options:
        no = norm(o)
        if len(no) >= 4 and no in a:
            return o
    # yes/no questions
    if [norm(x) for x in options] == ["yes", "no"]:
        first = a.split()[0] if a.split() else ""
        if a in AFFIRM or first in AFFIRM:
            return options[0]
        if a in NEGATE or first in NEGATE:
            return options[1]
    return None


# ------------------------------------------------------------- kinds

KIND_RULES = [
    ("size_exception", r"gate it whole|gated whole|code lines|size exception|as one pr|keep it as one"),
    ("recut", r"\bre-?cut\b"),
    ("access", r"\baccess\b|\btoken\b|\bpermission|\bsecret|\bkey\b|\blogin\b|\bsign in\b|\bsigned\b|\bteam id\b|\bcertificate|\bvercel\b|\bgithub app\b|\borg\b|deny rules"),
    ("model_choice", r"\bopus\b|\bsol\b|\bastra\b|\bdeepseek\b|\bminimax\b|\bglm\b|\bterra\b|\bmodel\b|\breviewer\b|\bbuilder\b|\bsonnet\b|\bkimi\b|\bmorph\b"),
    ("release", r"\brelease\b|\bpromote\b|production|staging|testflight|deploy"),
    ("money", r"\bspend\b|\bcredit|\bplan\b|\btop up\b|\bexpire|\bposition|\btrade\b|\bsell\b|\bsndk\b|\bth-0|\baccount\b"),
    ("merge", r"\bmerge\b|squash-merge"),
    ("ticketing", r"\bticket|\bissue|\bbacklog\b|\bboard\b|\blabel|\bclose (?:it|the issue|#)|\bfile\b"),
]


def classify(text, options):
    t = text.lower()
    if options and len(options) == 2 and {norm(o) for o in options} == {"yes", "no"}:
        pass
    for kind, pat in KIND_RULES:
        if re.search(pat, t):
            return kind
    return "other"


STOP = {
    "the", "a", "an", "it", "is", "to", "and", "or", "of", "for", "in", "on", "that", "this",
    "so", "we", "i", "you", "me", "my", "be", "as", "at", "by", "with", "then", "now", "if",
    "not", "no", "yes", "do", "does", "should", "can", "will", "would", "could", "have",
}


def agreement(rec, ans, options):
    """true / false / partial, comparing Shyam's answer to the recommendation."""
    r, a = norm(rec), norm(ans)
    if not r or not a:
        return None
    if a == r or a in r or r in a:
        return True
    if [norm(x) for x in options] == ["yes", "no"]:
        ra = r.split()[0] if r.split() else ""
        aa = a.split()[0] if a.split() else ""
        if ra in AFFIRM and aa in AFFIRM:
            return True
        if ra in NEGATE and aa in NEGATE:
            return True
        if (ra in AFFIRM and aa in NEGATE) or (ra in NEGATE and aa in AFFIRM):
            return False
    rt = {w for w in r.split() if w not in STOP and len(w) > 2}
    at = {w for w in a.split() if w not in STOP and len(w) > 2}
    if not rt:
        return None
    overlap = len(rt & at) / len(rt)
    if overlap >= 0.6:
        return True
    if overlap <= 0.2:
        return False
    return "partial"


# ------------------------------------------------------------- splits

def bucket(iid):
    h = int(hashlib.sha256(iid.encode()).hexdigest(), 16)
    return h % 100, (h // 100) % 100


def split_of(iid):
    b1, b2 = bucket(iid)
    if b1 < 15:
        return "FINAL"
    return "DEV" if b2 < 80 else "HELDOUT"


# ------------------------------------------------------------- build

def write_atomic(path, text):
    with open(path + ".tmp", "w") as fh:
        fh.write(text)
    os.replace(path + ".tmp", path)


def prior_rows(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for n, ln in enumerate(fh, 1):
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: unparsable line: {e}")
            if not isinstance(row, dict) or not row.get("id"):
                raise ValueError(f"{path}:{n}: row has no id")
            if row["id"] in out:
                raise ValueError(f"{path}:{n}: duplicate id {row['id']}")
            out[row["id"]] = row
    return out


def recorded(row):
    return str(row.get("source", "")).startswith("daily3 record")


def main():
    recs = load_messages()
    panel = load_panel(recs)
    board = load_board(recs)
    typed = load_typed(recs)

    labels = {}
    repeats = []
    dropped = []

    # ---- board answers
    latest = {}
    for b in board:
        if b["id"] in latest:
            repeats.append((b["id"], latest[b["id"]]["ts"], b["ts"]))
        latest[b["id"]] = b

    for iid, b in latest.items():
        if is_action(iid):
            dropped.append((iid, "action card: no options, no recommendation"))
            continue
        rule = gen_rule(iid)
        gen_kind = None
        if rule:
            options, rec, src = rule["options"], rule["rec"], rule["source"]
            gen_kind = rule["kind"]
        else:
            p = panel.get(iid)
            if p and p[-1]["rec"]:
                options, rec = p[-1]["options"], p[-1]["rec"][0]
                where = f"{p[-1]['f']}:{p[-1]['i']}" if p[-1]["i"] >= 0 else f"{p[-1]['f']} (snapshot)"
                src = f"{where} (decisions board item)"
            else:
                pr = proximity_rec(recs, iid, b["ts"])
                if not pr:
                    dropped.append((iid, "no recorded recommendation"))
                    continue
                rec = pr["rec"]
                options = options_for_question(b["title"])
                src = f"{pr['f']}:{pr['i']} (ask with Recommended)"
        picked = pick_option(b["answer"], options)
        labels[iid] = dict(
            id=iid,
            kind=gen_kind if rule else classify(b["title"], options),
            item_text=b["title"][:300],
            recommended=rec,
            answer=picked if picked else b["answer"],
            agree=None,
            ts=b["ts"],
            source=f"{b['f']}:{b['i']} (board answer) <- {src}",
            options=options,
        )

    # ---- typed answers (curated: only unambiguous pairs)
    for n, t in enumerate(typed):
        if n not in TYPED_KEEP:
            continue
        agree, kind, opts_override = TYPED_KEEP[n]
        if agree is None:
            agree = "partial"
        options = opts_override if opts_override is not None else options_for_question(t["q"])
        picked = pick_option(t["ans"], options)
        if picked is None and re.search(r"go with your recommendation|your recommendation", t["ans"], re.I):
            for o in options:
                if norm(o) and norm(o) in norm(t["rec"]):
                    picked = o
                    break
        iid = "typed-" + re.sub(r"[^a-z0-9]+", "-", t["q"].lower())[:60].strip("-")
        if iid in labels:
            repeats.append((iid, labels[iid]["ts"], t["ansts"]))
        labels[iid] = dict(
            id=iid,
            kind=kind,
            item_text=t["q"][:300],
            recommended=t["rec"],
            answer=picked if picked else t["ans"],
            agree=agree,
            ts=t["ansts"],
            source=f"{t['f']}:{t['i']} (ask) <- {t['ansf']}:{t['ansi']} (reply)",
            options=options,
        )

    # ---- agree: compare the answer to the recommendation
    for lab in labels.values():
        if lab["agree"] is not None:
            continue
        lab["agree"] = agreement(lab["recommended"], lab["answer"], lab["options"])

    labels_path = f"{OUT}/labels.jsonl"
    prior = prior_rows(labels_path)
    kept = [r for i, r in prior.items() if i not in labels or recorded(r)]
    for iid in [i for i in labels if i in prior and recorded(prior[i])]:
        del labels[iid]
    for iid, lab in labels.items():
        old = prior.get(iid, {})
        for k in ("reason", "recommended_option"):
            if k in old:
                lab[k] = old[k]
        lab.setdefault("recommended_option", pick_option(lab["recommended"], lab["options"]))

    rows = sorted(
        list(labels.values()) + kept, key=lambda x: (x.get("ts") or "", x.get("id") or "")
    )
    os.makedirs(OUT, exist_ok=True)
    write_atomic(labels_path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    split = {"FINAL": [], "DEV": [], "HELDOUT": []}
    for r in rows:
        split[split_of(r["id"])].append(r["id"])
    write_atomic(
        f"{OUT}/split.json",
        json.dumps(
            {
                "rule": "sha256(id) -> h; FINAL if h%100<15; else DEV if (h//100)%100<80 else HELDOUT",
                "counts": {k: len(v) for k, v in split.items()},
                "splits": split,
                "final": split["FINAL"],
                "dev": split["DEV"],
                "heldout": split["HELDOUT"],
            },
            indent=1,
        ),
    )

    json.dump(
        {"repeats": repeats, "dropped": dropped},
        open(f"{TMP}/hc/build_notes.json", "w"),
        indent=1,
    )
    print("labels:", len(rows))
    print("with options:", sum(1 for r in rows if r["options"]))
    print("counts:", {k: len(v) for k, v in split.items()})
    print("repeats:", len(repeats), "dropped:", len(dropped))


# Curated typed pairs: index -> (agree, kind, options override or None).
# Only pairs where one question was asked and the reply clearly answers it.
TYPED_KEEP = {
    0: (True, "other", None),
    1: (True, "other", None),
    2: (True, "ticketing", None),
    4: (True, "model_choice", ["B", "A"]),
    5: (None, "ticketing", ["close it as not needed", "keep it open for a design"]),
    6: (True, "other", None),
    7: (True, "ticketing", None),
    9: (True, "ticketing", None),
    10: (True, "other", None),
    14: (True, "other", None),
    15: (True, "ticketing", None),
    17: (True, "other", None),
    20: (False, "model_choice", None),
    23: (False, "other", None),
    24: (True, "other", None),
    28: (True, "ticketing", None),
    29: (True, "ticketing", None),
    30: (True, "model_choice", ["Keep them", "drop them"]),
    31: (True, "ticketing", None),
    32: (True, "other", None),
    34: (True, "other", None),
    38: (True, "other", None),
    40: (False, "other", ["Monitor first", "all three now", "no"]),
    44: (True, "release", None),
    45: (True, "release", None),
    47: (True, "release", None),
    49: (True, "other", None),
    50: (True, "release", None),
    53: (True, "release", None),
    54: (True, "access", None),
    56: (True, "other", None),
    59: (True, "model_choice", None),
    64: (True, "model_choice", None),
    67: (False, "money", None),
    68: (True, "release", None),
    69: (False, "other", None),
    73: (False, "other", None),
    74: (True, "access", None),
    77: (None, "other", None),
    78: (True, "other", ["approve", "leave the learner off for now"]),
    79: (True, "access", None),
    83: (None, "other", None),
    84: (True, "other", None),
    86: (None, "other", None),
    92: (True, "other", None),
    93: (True, "money", ["Add credits to the Anthropic and OpenAI API accounts", "run reviews on the subscriptions only for now"]),
    94: (True, "other", None),
    96: (True, "access", None),
    97: (False, "access", ["Create a GitHub App for the factory", "keep cutting calls only"]),
    98: (True, "money", ["close both now", "wait for the investigation"]),
    99: (True, "other", None),
    100: (True, "release", None),
    102: (True, "release", ["promote now", "hold until the drain is fixed"]),
    103: (True, "release", ["promote tonight and close SNDK at the open", "close SNDK first and then promote"]),
    108: (True, "model_choice", ["top it up", "let builds fall back to DeepSeek"]),
    109: (True, "other", None),
    110: (True, "other", None),
    112: (True, "other", ["bot path first and defer broker-direct", "build both now", "hold"]),
    113: (True, "recut", ["Opus redesign pass", "keep re-cutting it smaller"]),
    116: (None, "access", None),
    119: (True, "release", None),
    120: (False, "model_choice", None),
    121: (False, "model_choice", ["cap Morph at 2 threads at once", "raise the Morph plan limit"]),
    122: (False, "other", ["me (the coordinator)", "another session you name"]),
    126: (True, "model_choice", None),
    128: (False, "other", ["wait and alarm", "keep the market fallback"]),
    129: (True, "other", None),
    133: (False, "model_choice", ["keep Opus for every risky parity ticket today", "switch to Opus only after a DeepSeek build fails its first gate"]),
    136: (True, "other", None),
    137: (True, "merge", None),
    138: (True, "size_exception", ["gate it whole", "re-cut it"]),
    139: (True, "size_exception", ["gate it whole", "re-cut it"]),
    140: (True, "recut", ["re-cut #1575", "keep fixing it"]),
}


if __name__ == "__main__":
    main()
