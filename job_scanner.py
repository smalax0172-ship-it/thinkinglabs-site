#!/usr/bin/env python3
"""Daily job scanner.

Pulls open roles from public job-board APIs (Greenhouse, Lever, Ashby),
filters them by location and title without any AI call, scores the survivors
against resume.md with Claude, drafts cover letters for the best fits, and
writes one ranked Markdown report to reports/YYYY-MM-DD.md.

Dependencies: Python 3.11 standard library, requests, anthropic.

Usage:
    python job_scanner.py                 # full run, needs ANTHROPIC_API_KEY
    python job_scanner.py --dry-run       # fetch + filter only, no AI calls
    python job_scanner.py --dry-run --fixtures scanner_fixtures
                                          # read board JSON from disk instead
                                          # of the network (for testing)
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

MODEL = "claude-haiku-4-5-20251001"
MAX_SCORED_JOBS = 60
COVER_LETTER_COUNT = 3
COVER_LETTER_MIN_SCORE = 70
COVER_LETTER_MAX_WORDS = 250
REQUEST_TIMEOUT = 30
USER_AGENT = "thinkinglabs-job-scanner/1.0 (+https://github.com/smalax0172-ship-it/thinkinglabs-site)"

TITLE_KEYWORDS = [
    "training",
    "trainer",
    "learning",
    "curriculum",
    "instructional",
    "education",
    "educator",
    "application scientist",
    "scientific",
    "enablement",
    "content",
    "evaluation",
]

# Substrings that mark a Massachusetts or Boston-area location.
MA_MARKERS = [
    "massachusetts",
    "boston",
    "cambridge, ma",
    "cambridge ma",
    "waltham",
    "lexington, ma",
    "bedford, ma",
    "burlington, ma",
    "woburn",
    "somerville",
    "watertown",
    "marlborough",
    "framingham",
    "norwood",
    "andover, ma",
    "billerica",
    "worcester",
    "acton, ma",
    "milford, ma",
    "natick",
    "quincy, ma",
    "needham",
    "newton, ma",
]

# Markers that say a remote role is US-based.
US_MARKERS = [
    "united states",
    "usa",
    " us",
    "u.s.",
    "us-",
    "us remote",
    "remote - us",
    "remote, us",
    "remote (us)",
    "north america",
    "americas",
]

# If a remote listing names one of these and no US marker, it is not US remote.
NON_US_MARKERS = [
    "canada",
    "united kingdom",
    " uk",
    "london",
    "ireland",
    "dublin",
    "germany",
    "berlin",
    "france",
    "paris",
    "netherlands",
    "amsterdam",
    "spain",
    "portugal",
    "poland",
    "india",
    "bangalore",
    "bengaluru",
    "singapore",
    "japan",
    "tokyo",
    "australia",
    "sydney",
    "brazil",
    "mexico",
    "emea",
    "apac",
    "latam",
    "europe",
    "switzerland",
    "zurich",
    "israel",
    "tel aviv",
    "china",
    "shanghai",
    "korea",
    "seoul",
]

BOARDS = ("greenhouse", "lever", "ashby")


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------


@dataclass
class Job:
    company: str
    board: str
    title: str
    location: str
    url: str
    description: str
    job_id: str
    score: int | None = None
    requirements_met: list[str] = field(default_factory=list)
    requirements_missing: list[str] = field(default_factory=list)
    why: str = ""
    cover_letter: str = ""
    score_error: str = ""


@dataclass
class Company:
    name: str
    board: str
    slugs: list[str]


@dataclass
class Skipped:
    name: str
    reason: str


# --------------------------------------------------------------------------
# Minimal YAML reader for companies.yaml
# --------------------------------------------------------------------------


def load_companies(path: Path) -> list[Company]:
    """Read the small YAML subset used by companies.yaml.

    Supports a top-level "companies:" list whose items are "- key: value"
    mappings. Values for "slugs" may be a comma list or a [a, b] list.
    """
    companies: list[Company] = []
    current: dict[str, str] | None = None
    in_list = False

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        name = current.get("name", "").strip()
        board = current.get("board", "auto").strip().lower() or "auto"
        raw = current.get("slugs") or current.get("slug") or ""
        raw = raw.strip().strip("[]")
        slugs = [s.strip().strip("'\"") for s in raw.split(",") if s.strip()]
        if name and slugs:
            companies.append(Company(name=name, board=board, slugs=slugs))
        current = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if not in_list:
            if stripped.startswith("companies:"):
                in_list = True
            continue
        if stripped.startswith("- "):
            flush()
            current = {}
            stripped = stripped[2:].strip()
        if current is None:
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = value.strip().strip("'\"")
    flush()
    return companies


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def _get_json(url: str) -> Any:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.json()


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _join_locations(parts: list[str]) -> str:
    """Join location fragments, dropping blanks and case-insensitive repeats."""
    seen: set[str] = set()
    out = []
    for p in parts:
        p = (p or "").strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return ", ".join(out)


def _load_fixture(fixtures: Path | None, board: str, slug: str) -> Any:
    """Return on-disk JSON for board/slug, or raise if none exists."""
    if fixtures is None:
        raise RuntimeError("no fixtures")
    path = fixtures / f"{board}_{slug}.json"
    if not path.exists():
        raise RuntimeError("no fixture")
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_greenhouse(company: str, slug: str, fixtures: Path | None) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = _load_fixture(fixtures, "greenhouse", slug) if fixtures else _get_json(url)
    if not isinstance(data, dict) or "jobs" not in data:
        raise RuntimeError("not a Greenhouse board")
    jobs = []
    for j in data["jobs"]:
        loc = (j.get("location") or {}).get("name", "") or ""
        offices = ", ".join(o.get("name", "") for o in j.get("offices", []) if o.get("name"))
        location = loc if loc else offices
        if offices and offices.lower() not in location.lower():
            location = f"{location} ({offices})" if location else offices
        jobs.append(
            Job(
                company=company,
                board="greenhouse",
                title=j.get("title", "").strip(),
                location=location.strip(),
                url=j.get("absolute_url", ""),
                description=_strip_html(j.get("content", "")),
                job_id=str(j.get("id", "")),
            )
        )
    return jobs


def fetch_lever(company: str, slug: str, fixtures: Path | None) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = _load_fixture(fixtures, "lever", slug) if fixtures else _get_json(url)
    if not isinstance(data, list):
        raise RuntimeError("not a Lever board")
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        parts = [cats.get("location", "")]
        parts += list(j.get("allLocations") or [])
        if j.get("workplaceType"):
            parts.append(j["workplaceType"])
        if j.get("country"):
            parts.append(j["country"])
        location = _join_locations(parts)
        desc = j.get("descriptionPlain") or _strip_html(j.get("description", ""))
        for block in j.get("lists") or []:
            desc += "\n" + block.get("text", "") + "\n" + _strip_html(block.get("content", ""))
        jobs.append(
            Job(
                company=company,
                board="lever",
                title=j.get("text", "").strip(),
                location=location,
                url=j.get("hostedUrl") or j.get("applyUrl", ""),
                description=desc.strip(),
                job_id=str(j.get("id", "")),
            )
        )
    return jobs


def fetch_ashby(company: str, slug: str, fixtures: Path | None) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false"
    data = _load_fixture(fixtures, "ashby", slug) if fixtures else _get_json(url)
    if not isinstance(data, dict) or "jobs" not in data:
        raise RuntimeError("not an Ashby board")
    jobs = []
    for j in data["jobs"]:
        parts = [j.get("location", "")]
        for sec in j.get("secondaryLocations") or []:
            parts.append(sec.get("location", ""))
        addr = ((j.get("address") or {}).get("postalAddress") or {})
        for key in ("addressLocality", "addressRegion", "addressCountry"):
            if addr.get(key):
                parts.append(addr[key])
        if j.get("isRemote"):
            parts.append("Remote")
        location = _join_locations(parts)
        desc = j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml", ""))
        jobs.append(
            Job(
                company=company,
                board="ashby",
                title=j.get("title", "").strip(),
                location=location,
                url=j.get("jobUrl") or j.get("applyUrl", ""),
                description=desc.strip(),
                job_id=str(j.get("id", "")),
            )
        )
    return jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def fetch_company(company: Company, fixtures: Path | None) -> tuple[list[Job], str | None, str]:
    """Try every board/slug pair. Return (jobs, board_used, note)."""
    boards = BOARDS if company.board == "auto" else (company.board,)
    failures: list[str] = []
    for slug in company.slugs:
        for board in boards:
            try:
                jobs = FETCHERS[board](company.name, slug, fixtures)
            except Exception as exc:  # noqa: BLE001 - we want to keep going
                failures.append(f"{board}/{slug}: {exc}")
                continue
            return jobs, board, f"{board}/{slug}"
    return [], None, "; ".join(failures)


# --------------------------------------------------------------------------
# Filtering (no AI)
# --------------------------------------------------------------------------


def location_ok(location: str) -> bool:
    loc = " " + location.lower().replace("\n", " ") + " "
    if any(m in loc for m in MA_MARKERS):
        return True
    # A bare state code: ", MA" or " MA " or "MA, USA".
    if re.search(r"[,(\s]ma[\s,)]", loc):
        return True
    if "remote" in loc:
        if any(m in loc for m in US_MARKERS):
            return True
        if not any(m in loc for m in NON_US_MARKERS):
            return True
    return False


def title_ok(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in TITLE_KEYWORDS)


def filter_jobs(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    kept = []
    for job in jobs:
        key = job.url or f"{job.company}|{job.title}|{job.location}"
        if key in seen:
            continue
        seen.add(key)
        if location_ok(job.location) and title_ok(job.title):
            kept.append(job)
    return kept


# --------------------------------------------------------------------------
# Scoring and cover letters (Claude)
# --------------------------------------------------------------------------

SCORE_SYSTEM = (
    "You are a careful hiring analyst. You compare one job posting against a "
    "candidate resume and answer only with a single JSON object, no prose, no "
    "code fences. Keys: fit_score (integer 0 to 100), requirements_met (list of "
    "short strings), requirements_missing (list of short strings), why (one "
    "sentence). Be honest. A teacher with deep chemistry and physics background "
    "fits training, curriculum, learning, and application scientist roles well, "
    "and fits pure software or sales roles poorly."
)

LETTER_SYSTEM = (
    "You write short, plain, confident cover letters. Rules you must follow: "
    "under 250 words. The first two sentences must explain why a chemist with 22 "
    "years of teaching is applying for this role. No em dashes. No semicolons. "
    "No emojis. No bullet points. No headers. Plain confident sentences. Do not "
    "invent facts that are not in the resume. Sign off as Syd Malaxos. Output "
    "only the letter text."
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _message_text(response: Any) -> str:
    return "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")


def make_client() -> Any:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it or run with --dry-run.")
    import anthropic  # imported here so --dry-run works without the package

    return anthropic.Anthropic()


def score_job(client: Any, job: Job, resume: str) -> None:
    desc = job.description[:12000]
    user = (
        f"RESUME:\n{resume}\n\n"
        f"JOB POSTING:\nCompany: {job.company}\nTitle: {job.title}\n"
        f"Location: {job.location}\n\n{desc}\n\n"
        "Return the JSON object now."
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SCORE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        data = _extract_json(_message_text(response))
        job.score = max(0, min(100, int(round(float(data.get("fit_score", 0))))))
        job.requirements_met = [str(x) for x in data.get("requirements_met", [])][:8]
        job.requirements_missing = [str(x) for x in data.get("requirements_missing", [])][:8]
        job.why = str(data.get("why", "")).strip()
    except Exception as exc:  # noqa: BLE001
        job.score = 0
        job.score_error = f"{type(exc).__name__}: {exc}"


def clean_letter(text: str) -> str:
    text = re.sub(r"\s*(?:\u2014|\u2013|--)\s*", ", ", text)
    text = re.sub(r";\s*(\w)", lambda m: ". " + m.group(1).upper(), text)
    text = text.replace(";", ".")
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def draft_cover_letter(client: Any, job: Job, resume: str) -> str:
    user = (
        f"RESUME:\n{resume}\n\n"
        f"JOB POSTING:\nCompany: {job.company}\nTitle: {job.title}\n"
        f"Location: {job.location}\n\n{job.description[:10000]}\n\n"
        "Write the cover letter now."
    )
    letter = ""
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=LETTER_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001
            return f"(cover letter failed: {type(exc).__name__}: {exc})"
        letter = clean_letter(_message_text(response))
        if word_count(letter) <= COVER_LETTER_MAX_WORDS:
            break
        user += f"\n\nThat draft was {word_count(letter)} words. Cut it to under {COVER_LETTER_MAX_WORDS}."
    if word_count(letter) > COVER_LETTER_MAX_WORDS:
        words = letter.split()
        letter = " ".join(words[: COVER_LETTER_MAX_WORDS - 5]).rstrip(",.") + ".\n\nSyd Malaxos"
    return letter


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def build_report(
    date: dt.date,
    jobs: list[Job],
    skipped: list[Skipped],
    sources: list[str],
    total_fetched: int,
    total_filtered: int,
    dry_run: bool,
    unscored_overflow: list[Job],
) -> str:
    lines: list[str] = []
    lines.append(f"# Job scan for {date.isoformat()}")
    lines.append("")
    mode = "Dry run, no AI scoring." if dry_run else f"Scored with {MODEL}."
    lines.append(
        f"{mode} Pulled {total_fetched} openings from {len(sources)} boards, "
        f"{total_filtered} passed the location and title filter, "
        f"{len(jobs)} {'listed' if dry_run else 'scored'} below."
    )
    lines.append("")

    lines.append("## Ranked jobs")
    lines.append("")
    if not jobs:
        lines.append("No jobs passed the filter today.")
    else:
        lines.append("| Score | Title | Company | Location | Link |")
        lines.append("|---|---|---|---|---|")
        for job in jobs:
            score = "n/a" if job.score is None else str(job.score)
            lines.append(
                f"| {score} | {_md(job.title)} | {_md(job.company)} | "
                f"{_md(job.location)} | [apply]({job.url}) |"
            )
    lines.append("")

    lines.append("## Details")
    lines.append("")
    for i, job in enumerate(jobs, 1):
        score = "not scored" if job.score is None else f"{job.score}/100"
        lines.append(f"### {i}. {job.title} at {job.company}")
        lines.append("")
        lines.append(f"Score: {score}  ")
        lines.append(f"Location: {job.location or 'not listed'}  ")
        lines.append(f"Board: {job.board}  ")
        lines.append(f"Link: {job.url}")
        lines.append("")
        if job.score_error:
            lines.append(f"Scoring failed: {job.score_error}")
            lines.append("")
        if job.why:
            lines.append(f"Why: {job.why}")
            lines.append("")
        if job.requirements_met:
            lines.append("Requirements met:")
            lines.append("")
            for r in job.requirements_met:
                lines.append(f"- {r}")
            lines.append("")
        if job.requirements_missing:
            lines.append("Requirements missing:")
            lines.append("")
            for r in job.requirements_missing:
                lines.append(f"- {r}")
            lines.append("")
    if unscored_overflow:
        lines.append(f"### Not scored (over the {MAX_SCORED_JOBS} job cap)")
        lines.append("")
        for job in unscored_overflow:
            lines.append(f"- {job.title} at {job.company}, {job.location}. {job.url}")
        lines.append("")

    lines.append("## Cover letters")
    lines.append("")
    letters = [j for j in jobs if j.cover_letter]
    if dry_run:
        lines.append("Skipped in dry run.")
    elif not letters:
        lines.append(f"No job scored {COVER_LETTER_MIN_SCORE} or higher, so no letters were drafted.")
    else:
        for job in letters:
            lines.append(f"### {job.title} at {job.company} (score {job.score})")
            lines.append("")
            lines.append(job.cover_letter)
            lines.append("")
    lines.append("")

    lines.append("## Skipped companies")
    lines.append("")
    if not skipped:
        lines.append("Every company in companies.yaml answered.")
    else:
        for s in skipped:
            lines.append(f"- {s.name}: {s.reason}")
    lines.append("")

    lines.append("## Sources checked")
    lines.append("")
    for s in sources:
        lines.append(f"- {s}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _short_reason(note: str) -> str:
    """Collapse a list of per-board failures into a phone-sized reason."""
    if "HTTP 404" in note and "CONNECT" not in note and "Connection" not in note:
        return "no public Greenhouse, Lever, or Ashby board found (likely Workday or similar)"
    if "no fixture" in note:
        return "no fixture file for this company"
    if "Connection" in note or "CONNECT" in note or "Max retries" in note:
        return "network error reaching the job boards"
    return note[:200]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily job scanner")
    parser.add_argument("--dry-run", action="store_true", help="fetch and filter only, no AI calls")
    parser.add_argument("--fixtures", type=Path, help="directory of board JSON files to use instead of the network")
    parser.add_argument("--companies", type=Path, default=Path("companies.yaml"))
    parser.add_argument("--resume", type=Path, default=Path("resume.md"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports"))
    parser.add_argument("--date", help="report date as YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    companies = load_companies(args.companies)
    if not companies:
        sys.exit(f"No companies found in {args.companies}")
    resume = args.resume.read_text(encoding="utf-8")

    all_jobs: list[Job] = []
    skipped: list[Skipped] = []
    sources: list[str] = []
    for company in companies:
        jobs, board, note = fetch_company(company, args.fixtures)
        if board is None:
            skipped.append(Skipped(company.name, _short_reason(note)))
            print(f"[skip] {company.name}: {note}", file=sys.stderr)
            continue
        sources.append(f"{company.name}: {note} ({len(jobs)} openings)")
        print(f"[ok]   {company.name}: {note}, {len(jobs)} openings", file=sys.stderr)
        all_jobs.extend(jobs)
        if not args.fixtures:
            time.sleep(0.5)

    filtered = filter_jobs(all_jobs)
    filtered.sort(key=lambda j: (j.company.lower(), j.title.lower()))
    print(f"[filter] {len(all_jobs)} fetched, {len(filtered)} kept", file=sys.stderr)
    for job in filtered:
        print(f"  - {job.company}: {job.title} ({job.location})", file=sys.stderr)

    to_score = filtered[:MAX_SCORED_JOBS]
    overflow = filtered[MAX_SCORED_JOBS:]

    if not args.dry_run:
        client = make_client()
        for i, job in enumerate(to_score, 1):
            score_job(client, job, resume)
            print(f"[score] {i}/{len(to_score)} {job.company}: {job.title} -> {job.score}", file=sys.stderr)
        to_score.sort(key=lambda j: (-(j.score or 0), j.company.lower(), j.title.lower()))
        top = [j for j in to_score if (j.score or 0) >= COVER_LETTER_MIN_SCORE][:COVER_LETTER_COUNT]
        for job in top:
            job.cover_letter = draft_cover_letter(client, job, resume)
            print(f"[letter] {job.company}: {job.title} ({word_count(job.cover_letter)} words)", file=sys.stderr)

    report = build_report(
        date=date,
        jobs=to_score,
        skipped=skipped,
        sources=sources,
        total_fetched=len(all_jobs),
        total_filtered=len(filtered),
        dry_run=args.dry_run,
        unscored_overflow=overflow,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{date.isoformat()}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"[done] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
