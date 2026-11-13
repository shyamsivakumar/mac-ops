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

## Verification

The temporary proof imports both exported checkBash implementations. All 21 must-block cases block on both; all six must-allow cases pass on revision 3. No credential files are read. The sandbox touch probe fails with Operation not permitted. The PR body contains the one-off proof and check results. Installation remains a post-merge action; Shyam must then run /reload.

## Reviewer round

One Luna Max read-only round found that a temp prefix could hide a parent-directory escape. Output paths are now normalized before granting the heredoc exception. Focused regression probes verify that /tmp/../Desktop/out does not qualify, and that an early delimiter followed by a secret read still blocks.

The reviewer also identified deployment wrappers already allowed by main (for example exec railway up). The brief requires the existing deployment DENY rule unchanged, so this pre-existing limitation remains for coordinator review. The reviewer returned FAIL on the pre-fix tree; no second reviewer round was run. The final correction is verified by deterministic probes.
