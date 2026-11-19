// Runs an installed pi deny-guard against a list of tool_call events.
//
// Usage: bun pi-guard-probe.ts <guard.ts> <events.json>
//
// The guard is the installed artifact (for example
// ~/.pi/agent-deepseek/extensions/deny-guard.ts), loaded exactly as pi loads
// it: default-exported function called with a pi object, then the registered
// tool_call handler invoked with the event and ctx pi passes.
// @ts-nocheck
const [guardPath, eventsPath] = process.argv.slice(2);
const guard = await import(guardPath);
const events: Array<{ label: string; cwd: string; event: unknown; env?: Record<string, string> }> = JSON.parse(
  await Bun.file(eventsPath).text(),
);
const baseEnv = { ...process.env };

let handler: ((event: unknown, ctx: unknown) => Promise<unknown>) | undefined;
const pi = {
  on: (name: string, fn: (event: unknown, ctx: unknown) => Promise<unknown>) => {
    if (name === "tool_call") handler = fn;
  },
};
guard.default(pi);
if (!handler) {
  console.log(JSON.stringify({ error: "guard registered no tool_call handler" }));
  process.exit(1);
}

const results = [];
for (const item of events) {
  // The role is read from the environment the agent was launched with, so
  // each case gets its own environment, not one carved into the command.
  for (const key of Object.keys(process.env)) if (!(key in baseEnv)) delete process.env[key];
  Object.assign(process.env, baseEnv, item.env || {});
  const decision = await handler(item.event, { cwd: item.cwd, mode: "print" });
  results.push({ label: item.label, decision: decision ?? null });
}
console.log(JSON.stringify(results, null, 2));
