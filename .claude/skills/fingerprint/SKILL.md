---
name: fingerprint
description: Use UNPROMPTED on any public-facing text drafted or edited in a session, including website copy, Substack posts, LinkedIn posts, comments, replies, emails to prospects, and product descriptions. Also use when the user says fingerprint, scan this, or voice check. Enforces the user's public voice rules before the text is presented.
---

# fingerprint

This user's public voice is a brand asset with hard mechanical rules. Any public-facing text must pass this scan BEFORE being shown as finished. Run it unprompted and report the result in one short line.

STRIP ON SIGHT, zero tolerance:

1. Em-dashes. Zero allowed in anything Claude writes. Replace with a period, a comma, or a rewrite.
2. Semicolons. Zero allowed.
3. Emojis. Zero allowed.
4. The words: delve, leverage (as a verb), moat, robust, seamless, elevate. The phrase: navigate the landscape.
5. Engagement filler: this hits, this resonates, resonates deeply, going to stay with me, spot on, so well put, couldn't agree more, love this, this is gold.
6. Soft intensifiers: genuinely, truly, deeply, incredibly, absolutely (unless quoting someone).
7. Announce-openers (sentences that describe the reply instead of being it) and verdict-closers (grand summary praise at the end).
8. Listy bold-headers and forced rule-of-three constructions in prose meant to be read as prose.

VOICE TARGETS, check and adjust:

9. Short declarative sentences. Teacher authority. Observation to insight to implication.
10. Credential is always "over 20 years," never a specific number of years.
11. No hedging chains (I think maybe it could possibly). One qualifier maximum per claim.
12. Story before concept where a story exists. End with the point or the next move, never a summary of what was just said.

REPORTING: after any public text, output one line: "Fingerprint: clean" or "Fingerprint: fixed N issues (list them in a few words)." Do not lecture about the rules. Fix and report.

SCOPE: applies to public-facing text only. Code, commit messages, internal notes, and docs/lessons files are exempt.
