# Revision 3 decisions

Run: `ticket:shyamsivakumar/mac-ops#153:a3`. Refs #153.

## Sound

### Bound the secret exception to one complete command

- When: revision 3.
- The decision: Only a single cat command with a quoted delimiter and one output redirection qualifies. For example, prose naming auth.json inside a quoted heredoc is ignored for secret matching, while a command after its closing delimiter remains checked. All DENY rules still inspect the entire text.
- The gap: The brief did not define handling of compound commands or unusual heredoc delimiter spellings. Those retain the existing blocks.
- The reach: Additional shell forms need separate evidence before gaining an exception. No shell command parser is introduced.
- Verdict: sound. A narrow exception preserves fail-closed behavior.
- Confidence: high.

### Preserve unused protected-path declarations

- When: revision 3.
- The decision: Remove only the two checkBash checks and retain their declarations, because the brief requires other content unchanged. Writes through write/edit keep their existing path rule; shell writes rely on the unchanged kernel sandbox.
- The gap: The brief did not request declaration cleanup.
- The reach: Sandbox installation is required for shell write protection.
- Verdict: sound. This keeps the requested change bounded.
- Confidence: high.

## Final coordinator decision

- When: after Opus rejected ad605711 for a second redirection escaping the truncation temp exception.
- The decision: Drop stated change 2 entirely and restore main's truncation rule byte for byte. For example, both `: > /tmp/a` and `: > /tmp/a > ~/x` block. The coordinator uses its write tool to create temp files instead. Protected-path bash checks remain removed, and the quoted cat heredoc secret exception remains.
- The gap: None. This is the coordinator's explicit scope revision, superseding both earlier truncation fixes.
- The reach: Shell truncation has no temp exception. Future work must not infer one from the heredoc output exception.
- Verdict: sound. Restoring the existing rule avoids reasoning about multiple shell redirections.
- Confidence: high.

## Verification

The entire DENY array is byte-identical to origin/main. The one-off temporary proof imports both exported checkBash implementations: all 28 must-block cases block on both, and all five must-allow cases pass on the revised guard. Temp truncation moved from must-allow to must-block; the second-redirection reproduction is also must-block. No credential files were read. The PR contains the script and output. Fast check runs on the final head. Sandbox unchanged; the earlier sandbox write probe failed with Operation not permitted.

## Review history and remaining gate

One Luna reviewer round found a heredoc output traversal issue, fixed by normalizing its target before granting the secret prose exception. Two subsequent coordinator Opus gates rejected truncation exceptions. Those exceptions are now removed entirely. The pre-existing deployment wrapper limitations remain unchanged, as required. Coordinator Opus re-gate remains pending. After merge rerun the installer, then ask Shyam to run /reload.
