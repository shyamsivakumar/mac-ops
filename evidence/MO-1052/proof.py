import importlib.machinery
import importlib.util
import sys

path = sys.argv[1]
loader = importlib.machinery.SourceFileLoader("ticket_under_proof", path)
spec = importlib.util.spec_from_loader(loader.name, loader)
ticket = importlib.util.module_from_spec(spec)
loader.exec_module(ticket)

cfg = ticket.load_config()
old_sections = [s for s in cfg["template"] if s != "Failure behavior"]
old = "\n\n".join(f"## {s}\n\ntext" for s in old_sections) + "\n\nProof command: true\n"
new = old + "\n## Failure behavior\n\nMissing data: exit 2.\n"

print("open, body without the section:", ticket.check_body(cfg, old, []))
print("open, body with the section:", ticket.check_body(cfg, new, []))

ticket.pull_guard_reasons = lambda *_: []
ticket.text_blocker_reasons = lambda *_, **__: []
repo = next(r for r, c in cfg["repos"].items() if c.get("key"))
key = cfg["repos"][repo]["key"]


def start(body):
    issue = {
        "id": "I",
        "number": 9,
        "title": f"{key}-9 · fixture",
        "body": body,
        "state": "OPEN",
        "url": "https://example.invalid/9",
        "comments": [],
        "blockedBy": {"totalCount": 0, "nodes": []},
        "labels": [{"name": n} for n in ("type:standard", "stage:backlog")],
    }
    try:
        ticket.validate_start(cfg, repo, issue, check_text=False)
        return "start accepted"
    except ticket.Refuse as e:
        return f"start refused: {e}"


print("start, existing ticket without the section:", start(old))
print("start, ticket missing Rollback:", start(old.replace("## Rollback", "## Other")))

t = {"url": "u", "reviewerAlias": "r", "body": new, "arm": None}
brief = ticket.assemble_brief(cfg, t, "ticket:a/b#9:a1", {"number": 9, "comments": []})
print("brief has failure instruction:", "Prove each listed case" in brief)
print(
    "prefix before body:",
    brief.index("Prove each listed case") < brief.index("Failure behavior\n"),
)
print("prefix sha:", ticket.brief_prefix_sha())
