import extension from "../../coordinator/pi/extensions/coordinator.ts";
const handlers: Record<string, Function[]> = {};
extension({on(name: string, fn: Function) {(handlers[name] ||= []).push(fn);}, registerCommand() {}});
const cases = [
  ["bgmon_start", {command: "echo unsafe"}, true],
  ...["stop", "forget", "server_stop", "delete_history"].map(action => ["bgmon_control", {action}, true]),
  ["bgmon_unknown", {}, true],
  ["bgmon_events", {action: "clear"}, true],
  ["bgmon_events", {action: "list"}, false],
  ["bgmon_events", {}, true],
  ["bgmon_inspect", {}, false],
  ...["add", "list", "update", "remove"].map(action => ["bgmon_watch", {action}, false]),
];
for (const [toolName, input, blocked] of cases) {
  const result = await handlers.tool_call[0]({toolName, input}, {cwd: "/tmp"});
  if (Boolean(result?.block) !== blocked) throw new Error(`Unexpected guard result: ${toolName} ${JSON.stringify(input)}`);
}
console.log(`PASS: ${cases.length} tool-call boundary cases; fake pi only, no package or command execution`);
