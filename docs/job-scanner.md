# Daily job scanner

What it is, how to run it, and the decisions behind it.

## Files

- `job_scanner.py` is the whole program. Standard library plus `requests` and `anthropic`.
- `companies.yaml` is the company list. Edit it freely. Each entry has a name, a board (`greenhouse`, `lever`, `ashby`, or `auto`), and one or more slugs to try.
- `resume.md` is what each job gets compared against.
- `reports/YYYY-MM-DD.md` is the daily output.
- `scanner_fixtures/` holds synthetic board JSON for offline testing. Not real jobs.
- `.github/workflows/job-scanner.yml` runs it every day at 6 AM Eastern and commits the report.

## Running it

Full run (needs the key in the environment):

    export ANTHROPIC_API_KEY=...
    python job_scanner.py

Dry run, no AI calls, real network:

    python job_scanner.py --dry-run

Dry run against the fixtures, no network:

    python job_scanner.py --dry-run --fixtures scanner_fixtures

Other flags: `--date YYYY-MM-DD`, `--out-dir`, `--companies`, `--resume`.

## Pipeline

1. Fetch. For every company, try each slug on each board until one answers with a job list. Companies with no answer go to the Skipped section of the report with a short reason.
2. Filter, free. Keep jobs whose location reads as Massachusetts, Boston area, or Remote US, and whose title contains one of the keywords listed at the top of the script.
3. Score. Up to 60 surviving jobs go to `claude-haiku-4-5-20251001` with the resume. Each returns a fit score, requirements met, requirements missing, and one sentence. Jobs past the cap are listed unscored.
4. Cover letters. Top 3 jobs at 70 or higher get a letter under 250 words. Dashes, semicolons, and emoji are stripped after the fact as a safety net.
5. Report. Ranked table, per-job details, letters, skipped companies, sources checked.

## Decisions banked

- Slugs are unverified. The Claude Code cloud container blocks `boards-api.greenhouse.io`, `api.lever.co`, and `api.ashbyhq.com`, so board discovery could not be done live. The script tries every candidate slug on every board at runtime and reports what answered. After the first GitHub Actions run, set `board:` explicitly for the companies that worked to cut requests.
- Expect most of the biotech and instrument companies (Vertex, Takeda, Biogen, Alnylam, Insulet, Hologic, Waters, Thermo Fisher, Bruker, Agilent, Boston Scientific) to land in Skipped. They use Workday or similar, which has no public JSON board.
- `companies.yaml` is parsed by a tiny reader inside the script, not PyYAML, to keep the dependency list to what was asked. Keep the file in the simple `- name / board / slugs` shape shown in its header comment.
- The 6 AM Eastern schedule uses two UTC cron entries (10:00 and 11:00) and a first step that checks the New York hour, so it runs once a day year round.
- The repo is a GitHub Pages site. Anything committed here, including `resume.md` and the reports, is reachable on the public site URL.
- No report is committed from the build session, because the container had no board access. The first real report comes from the first Actions run.

## Adding a company

Add a block to `companies.yaml`:

    - name: New Company
      board: auto
      slugs: newcompany, new-company

Find the slug in the company's careers page URL. Greenhouse looks like `boards.greenhouse.io/<slug>` or `job-boards.greenhouse.io/<slug>`, Lever like `jobs.lever.co/<slug>`, Ashby like `jobs.ashbyhq.com/<slug>`.
