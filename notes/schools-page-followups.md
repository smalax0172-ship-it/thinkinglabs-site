# Schools page — follow-ups after the public/independent broadening

Shipped: commit 9154b97 on main. schools.html only, six lines changed.
Title tag, meta description, og:description, h1, hero-sub, and the opening body
paragraph now speak to public districts and independent schools alike.
"Title I" is kept as an eligibility note, not the frame. The Title I Eligible
badge in the Investment section is untouched.

## Open items

1. Verify the live page.
   Hard refresh thinkinglabs.academy/schools.html.
   Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows.
   The headline should read "An AI critical thinking curriculum for your school."
   Not verified from the build environment — egress to the domain is blocked there.

2. Purge Cloudflare cache if the old headline persists.
   The site sits behind Cloudflare (CNAME + Cloudflare analytics beacon).
   Dashboard, then Caching, then Configuration, then purge the single URL
   https://thinkinglabs.academy/schools.html
   A stale headline after a hard refresh is an edge-cache problem, not a code problem.

3. Homepage still leads with Title I. NOT CHANGED — out of scope, needs a decision.
   index.html line 368: "Bring Thinking Labs to your school. Title I eligible.
   Curriculum, assessment infrastructure, and instructor training included."
   That card is the doorway to schools.html. The landing page is now broad but the
   door into it is still narrow. Independent schools reading the homepage may
   self-select out before they ever reach the page.

4. schools.html is missing from sitemap.xml entirely. NOT CHANGED — out of scope.
   sitemap.xml lists only /, research.html, and stem-landing.html.
   The page just optimized for search is not in the sitemap at all.
   Also stale: every lastmod still reads 2026-04-18.

5. Resubmit the sitemap and request reindex.
   After item 4 is fixed, resubmit in Google Search Console and request indexing
   for schools.html so the new title and description get picked up rather than
   waiting on an organic recrawl.

## Note on the preferred path

The corrected 276-line schools.html in Downloads was never used. The build runs in
a remote container with no access to the local Downloads folder. The six
replacements were applied by hand instead. Result is 276 lines, six lines changed.
If the Downloads copy differs from this in any wording, that difference is still
unmerged and worth a diff.
