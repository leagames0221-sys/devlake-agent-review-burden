#!/usr/bin/env python3
"""Read the assignees of GitHub pull requests and write a .sql file that puts them into DevLake's
pull_request_assignees table. (U3, see docs/adr/0003-github-pr-assignee-importer.md and docs/importer.md)

Why: DevLake v1.0.3-beta18 does not write pull_request_assignees for GitHub (ADR 0003, R6 and R9), so the
metric "first human reaction without the assignees" (sql/mysql/agent_review_burden.sql, 1B) has nothing to
exclude. This script only READS from GitHub and WRITES a text file. It never connects to a database; the
person who runs it feeds the .sql to MySQL (docs/importer.md).

What it reads: GitHub REST "List pull requests", GET /repos/{owner}/{repo}/pulls?state=all&per_page=100,
the pages followed by the rel="next" URL of the Link header (only URLs that start with https://api.github.com/).
From each pull request it uses `id` and, from every element of `assignees`, `id` and `login`. Nothing else.

Token: an optional token is read from the environment in one place (read_token, see docs/importer.md). It is
sent as an Authorization header that is NOT forwarded when a request is redirected. It is never printed or written.

Standard library only. Exit code 0 = the .sql was written; 1 = reading from GitHub failed (no .sql is written);
2 = a bad argument or an unusable input file (no .sql is written).

Usage:
  python importer/github_pr_assignees.py --repo OWNER/NAME --connection-id 1 --out assignees.sql
  python importer/github_pr_assignees.py --repo OWNER/NAME --connection-id 1 --out assignees.sql --from-file pages.json
      (--from-file: the pages come from a json file and nothing is sent over the network; used by the tests)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# E2 (ADR 0003): the _raw_data_table value of the rows written by this script.
RAW_DATA_TABLE = "_raw_github_ext_pull_request_assignees"
API_PREFIX = "https://api.github.com/"
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")
MAX_PAGES = 1000  # stops a Link header that never ends (1000 pages = 100,000 pull requests)


class Stop(Exception):
    """A reason to stop without writing the .sql. `code` is the exit code."""

    def __init__(self, message, code):
        Exception.__init__(self, message)
        self.code = code


# ---------------------------------------------------------------- SQL text
def sql_str(value):
    """A SQL string literal. MySQL reads a backslash as an escape character, so the backslash is doubled
    first, then the single quote is doubled."""
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "''")
    return "'" + s + "'"


def pr_domain_id(connection_id, github_id):
    """R1/R2: DevLake's id of a GitHub pull request = github:GithubPullRequest:<connection_id>:<GithubId>,
    where GithubId is the REST `id` of the pull request (not `number`)."""
    return "github:GithubPullRequest:%d:%d" % (int(connection_id), int(github_id))


def account_domain_id(connection_id, user_id):
    """R5: DevLake's id of a GitHub account = github:GithubAccount:<connection_id>:<user id>."""
    return "github:GithubAccount:%d:%d" % (int(connection_id), int(user_id))


def in_list(column, ids):
    if not ids:
        return "1 = 0"  # IN () is not valid SQL; no id, no row
    return "%s IN (%s)" % (column, ", ".join(sql_str(i) for i in ids))


# ---------------------------------------------------------------- reading pages
def read_token():
    """The only place that reads the token from the environment. The value is passed to build_request and nowhere else."""
    return os.environ.get("GITHUB_TOKEN") or None


def build_request(url, token):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "devlake-agent-review-burden-importer",
    })
    if token:
        # unredirected: urllib does not copy this header to the target of a redirect
        req.add_unredirected_header("Authorization", "Bearer " + token)
    return req


def next_url(link_header):
    """The rel="next" URL of a Link header, or None."""
    if not link_header:
        return None
    for m in re.finditer(r'<([^>]*)>\s*;\s*rel="([^"]*)"', link_header):
        if "next" in m.group(2).split():
            return m.group(1)
    return None


def open_url(req):
    return urllib.request.urlopen(req, timeout=60)


def pages_from_github(repo, token):
    """Yield (url, link_header, body) for each page. HTTP errors become Stop; nothing is retried."""
    owner, name = repo.split("/")
    url = "%srepos/%s/%s/pulls?state=all&per_page=100" % (
        API_PREFIX, urllib.parse.quote(owner, safe=""), urllib.parse.quote(name, safe=""))
    seen, n = set(), 0
    while url:
        if url in seen:
            raise Stop("the Link header repeats a URL after %d page(s); stopped" % n, 1)
        seen.add(url)
        try:
            with open_url(build_request(url, token)) as resp:
                link = resp.headers.get("Link")
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            extra = ""
            if e.headers is not None:
                remaining = e.headers.get("X-RateLimit-Remaining")
                reset = e.headers.get("X-RateLimit-Reset")
                if remaining is not None:
                    extra = " (X-RateLimit-Remaining: %s, X-RateLimit-Reset: %s)" % (remaining, reset)
            raise Stop("GitHub answered HTTP %s after %d page(s) were read%s; nothing was written, and "
                       "nothing is retried. Wait, or use a token (docs/importer.md)." % (e.code, n, extra), 1)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise Stop("reading page %d failed (%s) after %d page(s); nothing was written"
                       % (n + 1, type(e).__name__, n), 1)
        if not isinstance(body, list):
            raise Stop("page %d is not a json array; nothing was written" % (n + 1), 1)
        n += 1
        yield url, link, body
        url = next_url(link)
        if url is not None and not url.startswith(API_PREFIX):
            raise Stop("the next page URL does not start with %s; stopped after %d page(s)" % (API_PREFIX, n), 1)
        if n >= MAX_PAGES and url:
            raise Stop("more than %d pages; stopped" % MAX_PAGES, 1)


def pages_from_file(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Stop("cannot read the input file: %s" % type(e).__name__, 2)
    if not isinstance(data, list):
        raise Stop("the input file must be a json array of pages", 2)
    for i, page in enumerate(data):
        if not isinstance(page, dict) or not isinstance(page.get("body"), list):
            raise Stop("page %d of the input file has no `body` array" % (i + 1), 2)
        link = page.get("link")
        nxt = next_url(link) if isinstance(link, str) else None
        if nxt is not None and not nxt.startswith(API_PREFIX):
            raise Stop("the next page URL does not start with %s; stopped after %d page(s)" % (API_PREFIX, i + 1), 1)
        if nxt is not None and i == len(data) - 1:
            raise Stop("the last page of the input file points to a next page; stopped after %d page(s)" % (i + 1), 1)
        yield str(page.get("url", "")), link, page["body"]


# ---------------------------------------------------------------- reading the pull requests
def collect(pages, connection_id):
    """Return (pr_ids, pairs, stats). pr_ids: DevLake ids of every pull request read, in order, without
    repeats. pairs: (pr_id, assignee_id, login), each (pr, assignee) once. A pull request with a value that
    does not pass the checks is skipped as a whole (it is in neither list) and counted."""
    pr_ids, pairs, done, order = [], [], set(), set()
    stats = {"pages": 0, "prs_read": 0, "prs_skipped_invalid": 0, "page_urls": []}
    for url, _link, body in pages:
        stats["pages"] += 1
        stats["page_urls"].append(url)
        for pr in body:
            stats["prs_read"] += 1
            try:
                gid = pr["id"]
                if isinstance(gid, bool) or not isinstance(gid, int):
                    raise ValueError("pull request id")
                pid = pr_domain_id(connection_id, gid)
                found = []
                if not isinstance(pr["assignees"], list):
                    raise ValueError("assignees")
                for a in pr["assignees"]:
                    uid, login = a["id"], a["login"]
                    if isinstance(uid, bool) or not isinstance(uid, int):
                        raise ValueError("assignee id")
                    if not isinstance(login, str) or not LOGIN_RE.match(login):
                        raise ValueError("login")
                    found.append((account_domain_id(connection_id, uid), login))
            except (KeyError, TypeError, ValueError):
                stats["prs_skipped_invalid"] += 1
                continue
            if pid not in order:
                order.add(pid)
                pr_ids.append(pid)
            for aid, login in found:
                if (pid, aid) in done:
                    continue
                done.add((pid, aid))
                pairs.append((pid, aid, login))
    return pr_ids, pairs, stats


# ---------------------------------------------------------------- the .sql
def build_sql(repo, pr_ids, pairs, stats):
    table = sql_str(RAW_DATA_TABLE)
    lines = ["START TRANSACTION;"]
    # E5/E6: delete only this script's own rows, only for the pull requests that were read
    delete_where = "_raw_data_table = %s AND %s" % (table, in_list("pull_request_id", pr_ids))
    lines.append("DELETE FROM pull_request_assignees WHERE " + delete_where + ";")
    # E1/E3/E4: one row per (pull request, assignee); a pull request that DevLake does not have gets no row
    for pid, aid, login in pairs:
        lines.append(
            "INSERT INTO pull_request_assignees "
            "(pull_request_id, assignee_id, name, user_name, _raw_data_table, _raw_data_params, created_at, updated_at) "
            "SELECT pr.id, %s, %s, %s, %s, pr._raw_data_params, NOW(3), NOW(3) "
            "FROM pull_requests pr WHERE pr.id = %s;" % (sql_str(aid), sql_str(login), sql_str(login), table, sql_str(pid)))
    lines.append(
        "SELECT %s AS repo, %d AS pages_read, %s AS page_urls, %d AS prs_read, %d AS prs_skipped_invalid, "
        "%d AS rows_expected_if_all_prs_in_devlake, "
        "(SELECT COUNT(*) FROM pull_request_assignees WHERE _raw_data_table = %s AND %s) AS rows_in_table, "
        "%d - (SELECT COUNT(*) FROM pull_requests WHERE %s) AS prs_not_in_devlake;"
        % (sql_str(repo), stats["pages"], sql_str(" | ".join(stats["page_urls"])), stats["prs_read"],
           stats["prs_skipped_invalid"], len(pairs), table, in_list("pull_request_id", pr_ids),
           len(pr_ids), in_list("id", pr_ids)))
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Write a .sql that puts GitHub PR assignees into DevLake's pull_request_assignees.")
    ap.add_argument("--repo", required=True, metavar="OWNER/NAME")
    ap.add_argument("--connection-id", required=True, type=int, metavar="N",
                    help="the number of the GitHub connection in DevLake")
    ap.add_argument("--out", required=True, metavar="PATH", help="the .sql file to write")
    ap.add_argument("--from-file", metavar="JSON", help="read the pages from this json file instead of GitHub (tests)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:  # argparse exits with 2 by itself
        return e.code if isinstance(e.code, int) else 2
    try:
        if not REPO_RE.match(a.repo) or any(part in (".", "..") for part in a.repo.split("/")):
            raise Stop("--repo must look like OWNER/NAME (letters, digits, . _ -)", 2)
        if a.connection_id < 1:
            raise Stop("--connection-id must be 1 or more", 2)
        pages = pages_from_file(a.from_file) if a.from_file else pages_from_github(a.repo, read_token())
        pr_ids, pairs, stats = collect(pages, a.connection_id)
        text = build_sql(a.repo, pr_ids, pairs, stats)
    except Stop as e:
        print("stopped: %s" % e, file=sys.stderr)
        return e.code
    Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print("pages read: %d, pull requests read: %d, skipped because a value did not pass the checks: %d, "
          "assignee rows in the .sql: %d" % (stats["pages"], stats["prs_read"], stats["prs_skipped_invalid"], len(pairs)))
    print("written: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
