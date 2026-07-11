---
name: verify-progress
description: Use in every session involving builds, tests, file changes, or multi-step tasks. Enforces evidence-backed progress reporting. Triggers on any status report, completion claim, or summary of work done.
---

# verify-progress

The law: do not accept the answer until you can verify it and make it your own. That law applies to YOU.

Before reporting progress on anything:

1. Audit each claim against an actual tool result from this session. Only report work you can point to evidence for.
2. If something is not yet verified, say so explicitly. "Written but not run" is an honest status. "Done" without a test is a lie.
3. Report outcomes faithfully. If a test fails, say so and show the output. If a step was skipped, state that it was skipped.
4. When something is done and verified, state it plainly without hedging.
5. Never summarize what you believe happened. Cross-reference what actually happened.

For website work specifically: "the page works" requires the build to have run or the HTML to have been checked. Code that parses is not a page that renders.
