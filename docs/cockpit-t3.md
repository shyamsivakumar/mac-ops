# Cockpit on T3 Code

The Herdr Cockpit reads T3 Code through `~/.local/bin/t3mcp`. The transport
is `empryo/mods/cockpit/hub.js`; the historical directory name is retained.
All five board columns remain. Pending requests, failed runs and interrupted
runs take priority over PR readiness in Needs you. Open follows the T3 thread
link. Reply and Settle use T3 send and organize; they were not exercised in
read-only acceptance.

The Hub chip checks T3 project-list reachability. Queue reads `empq status`
for cap, live and queued counts. Provider health and run timing are not
available on T3. Approve merge queues a relay only after fresh PR and exact-head Opus review
checks. The review must end with `VERDICT: PASS` and include exactly one
`CHECK: PASS <40-character SHA>` line. The separate Opus review
remains required before a relay merge.

After checks pass, back up the installed directory to
`~/.config/herdr-app/mods/cockpit.empryo-bak`, then copy the source mod into
`~/.config/herdr-app/mods/cockpit`. Herdr hot reloads the directory. Verify
`herdr-app check` and `herdr-app status`, then compare the visible Running
column with `t3mcp call t3_thread_list '{"allProjects":true,"statuses":["running"]}'`.
Queue counts can change between polls. Roll back by restoring the backup.

See [MO-185 evidence](../evidence/MO-185/verification.md) for the bounded
acceptance results and remaining gate.
