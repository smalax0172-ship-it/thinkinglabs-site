---
name: handoff
description: Use when context is running low, the session must end mid-task, or the user says handoff, compact this, or new window. Compacts the session into one block a fresh session can continue from.
---

# handoff

A dying context window must never take the work with it.

When triggered:

1. First run the close-ritual skill so all state is banked to files.
2. Then produce ONE fenced code block containing: the goal of the current task, everything done so far with file paths, everything verified working versus written-but-unverified (per verify-progress), the exact next step, and any traps or decisions a fresh session must not re-open.
3. Write facts, not narrative. A fresh agent with zero context must be able to continue from this block alone.
4. Nothing outside the block except one line telling the user to paste it into the new session.
