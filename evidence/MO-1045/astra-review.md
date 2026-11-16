# Astra review

The single in-session Astra High review returned FAIL on the intermediate diff.

- High: current PR heads were fetched but not compared with recorded heads.
- High: only the first newer dispatch receipt was checked for an active replacement.
- High: live thread listing did not follow pagination.

The reviewer demonstrated these defects with mocked probes. It confirmed closed-ticket suppression, model fallback branches, daily cap, duplicate submission suppression after settlement failure, and existing_worktree preservation on that intermediate diff. No second reviewer round was requested. Final fixes require builder verification; the original review verdict remains FAIL.
