# MO: heavy jobs get a 45-minute wall-clock ceiling

A Tunerise xcodebuild held one of the two heavy slots for 10 hours (49 CPU-seconds) and every builder check queued behind it. Every heavy job needs a hard wall-clock ceiling that frees its slot.

The repository is at `/app`. Make the change there. Do not edit test files.
