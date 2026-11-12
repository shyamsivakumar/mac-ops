import { exec, home } from "herdr";

async function hubRoots() {
  const r = await exec(`${home()}/.local/bin/t3mcp`, ["call", "t3_project_list", JSON.stringify({ limit: 100 })]);
  const projects = JSON.parse(r.stdout).projects ?? [];
  return projects.filter((p) => !p.archivedAt && !p.deletedAt && p.workspaceRoot).map((p) => ({ name: p.title, path: p.workspaceRoot }));
}

async function underFolder(folder) {
  const r = await exec("find", [folder, "-maxdepth", "2", "-name", ".git", "-prune"]);
  return r.stdout.split("\n").filter(Boolean).map((p) => p.replace(/\/\.git$/, "")).sort().map((path) => ({ name: path.split("/").pop(), path }));
}

export async function loadRepos(folder) {
  const [hub, local] = await Promise.all([hubRoots().catch(() => []), folder ? underFolder(folder).catch(() => []) : []]);
  const seen = new Set();
  return [...local.map((r) => ({ ...r, source: "space" })), ...hub.map((r) => ({ ...r, source: "hub" }))]
    .filter((r) => !seen.has(r.path) && seen.add(r.path));
}
