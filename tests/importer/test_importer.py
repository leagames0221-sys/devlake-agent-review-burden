#!/usr/bin/env python3
"""Test of importer/github_pr_assignees.py (U3) against a throw-away MySQL 8.4 container.

Same container handling as tests/run_u1.py (which this file imports for docker(), mysql() and the password): a fresh
container from the public image, started with utf8mb4 / utf8mb4_bin as in DevLake's compose file, removed at the end
(also when something fails). Schema = tests/schema_mysql.sql, then tests/importer/schema_extra.sql.

Nothing here contacts GitHub: the pages come from tests/importer/pages_*.json (--from-file), and the network
code of the script is exercised with a fake open_url. The expected values are written by hand from the inputs
(see tests/importer/pages_README.md); the script's own output is never used to compute an expectation.

Usage:
  python tests/importer/test_importer.py              run every scene (A1..A13 and the network-free checks N1..N6)
  python tests/importer/test_importer.py --mutants    change the script in 6 places, one at a time, and show which scenes fail
Exit code 0 = all passed (--mutants: every mutant was caught); 1 = something failed; 2 = environment problem.
"""
import argparse
import atexit
import contextlib
import email.message
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import run_u1  # noqa: E402  (tests/run_u1.py: docker(), mysql(), PASSWORD, split_sql(), apply_macros(), VARIABLES)

SCRIPT = ROOT / "importer" / "github_pr_assignees.py"
OURS = "_raw_github_ext_pull_request_assignees"  # E2, written here by hand (not read from the script)
DEVLAKE_T = "_raw_github_api_pull_requests"      # R7: the raw table of DevLake's own GitHub PR convertor
PARAMS3 = '{"ConnectionId":3,"Name":"octo-org/demo-repo"}'   # what DevLake writes for connection 3 (R8, Go json of GithubApiParams)
PARAMS9 = '{"ConnectionId":9,"Name":"other-org/other-repo"}'
REPO = "octo-org/demo-repo"
TOKEN = "dummy-token-for-test"


def pid(n, c=3):
    return "github:GithubPullRequest:%d:%d" % (c, n)


def aid(n, c=3):
    return "github:GithubAccount:%d:%d" % (c, n)


class Ctx:
    def __init__(self, script, name, tmp):
        self.script, self.name, self.tmp = script, name, Path(tmp)
        self.results = []   # (label, description, ok, detail)
        self.mod = None

    def check(self, label, desc, ok, detail=""):
        self.results.append((label, desc, bool(ok), "" if ok else str(detail)))

    def sql(self, text):
        return run_u1.mysql(self.name, text)

    def rows(self, text):
        return [tuple(r) for r in self.sql(text)[1]]

    def reset(self):
        self.sql("DELETE FROM pull_request_assignees; DELETE FROM pull_request_comments; "
                 "DELETE FROM pull_requests; DELETE FROM accounts;")

    def add_prs(self, *ids, params=PARAMS3, conn=3):
        vals = ", ".join("('%s', 'github:GithubRepo:%d:1', 'OPEN', '2026-03-01 00:00:00', '%s', '%s')"
                         % (pid(i, conn), conn, params, DEVLAKE_T) for i in ids)
        self.sql("INSERT INTO pull_requests (id, base_repo_id, status, created_date, _raw_data_params, _raw_data_table) VALUES " + vals)

    def run_import(self, pages, repo=REPO, conn=3, out_name="out.sql"):
        out = self.tmp / out_name
        if out.exists():
            out.unlink()
        r = subprocess.run([sys.executable, str(self.script), "--repo", repo, "--connection-id", str(conn),
                            "--out", str(out), "--from-file", str(HERE / pages)], capture_output=True)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"), out

    def apply(self, out):
        """Feed a written .sql to MySQL; return the check SELECT as a dict."""
        header, rows = self.sql(out.read_text(encoding="utf-8"))
        return dict(zip(header, rows[0])) if rows else {}

    def ours(self):
        return self.rows("SELECT pull_request_id, assignee_id, name, user_name FROM pull_request_assignees "
                         "WHERE _raw_data_table = '%s' ORDER BY pull_request_id, assignee_id" % OURS)

    def load_module(self):
        spec = importlib.util.spec_from_file_location("importer_under_test", str(self.script))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def import_ok(c, label, pages, **kw):
    rc, so, se, out = c.run_import(pages, **kw)
    c.check(label, "%s: the script exits 0 and writes the .sql" % pages, rc == 0 and out.exists(), "rc=%s stderr=%s" % (rc, se))
    return rc, so, se, out


# ------------------------------------------------------------------ scenes
def scene_basic(c):
    """A1 A2 A3 A6 A11 A12 and (on the same data) A9 A10."""
    c.reset()
    c.add_prs(4000001, 4000002, 4000004)      # 4000003 is not in DevLake
    rc, so, se, out = import_ok(c, "A2", "pages_basic.json")
    text = out.read_text(encoding="utf-8")
    c.check("A12", "the .sql starts with START TRANSACTION; and ends with COMMIT;",
            text.startswith("START TRANSACTION;") and text.rstrip().endswith("COMMIT;"), text[:40] + " ... " + text[-20:])
    chk = c.apply(out)
    want = [(pid(4000002), aid(7001), "octocat", "octocat"),
            (pid(4000002), aid(7002), "hubot", "hubot"),
            (pid(4000004), aid(7002), "hubot", "hubot")]
    got = c.ours()
    c.check("A1", "a PR with 0 assignees (4000001) gets no row", not [r for r in got if r[0] == pid(4000001)], got)
    c.check("A2", "PR 4000002 gets 2 rows with ids built from the PR id (not number) and the user ids; "
                  "the PR that lists hubot twice gets 1 row", got == want, got)
    c.check("A3", "PR 4000003 (not in DevLake) gets no row and is counted as not in DevLake",
            not [r for r in got if r[0] == pid(4000003)] and chk.get("prs_not_in_devlake") == "1"
            and chk.get("rows_in_table") == "3" and chk.get("rows_expected_if_all_prs_in_devlake") == "4"
            and chk.get("prs_read") == "4" and chk.get("pages_read") == "1" and chk.get("prs_skipped_invalid") == "0",
            chk)
    meta = c.rows("SELECT COUNT(*), SUM(_raw_data_params = '%s'), SUM(_raw_data_table = '%s'), "
                  "SUM(created_at IS NOT NULL), SUM(updated_at IS NOT NULL) FROM pull_request_assignees" % (PARAMS3, OURS))[0]
    c.check("A6", "every row has the params of its PR, the E2 table name, created_at and updated_at",
            meta == ("3", "3", "3", "3", "3"), meta)
    c.check("A11", "name and user_name are the login", all(r[2] == r[3] and r[2] in ("octocat", "hubot") for r in got), got)

    # A9 / A10 on the rows just written, plus one row of another repo
    c.sql("INSERT INTO pull_request_assignees (pull_request_id, assignee_id, name, user_name, _raw_data_table, _raw_data_params, created_at, updated_at) "
          "VALUES ('%s', '%s', 'x', 'x', '%s', '%s', NOW(3), NOW(3))" % (pid(5000001, 9), aid(1, 9), OURS, PARAMS9))
    cnt = "SELECT COUNT(*) FROM pull_request_assignees WHERE _raw_data_table = '%s' AND _raw_data_params = '%s'"
    c.sql("DELETE FROM pull_request_assignees WHERE _raw_data_table = '%s' AND _raw_data_params = '%s'" % (DEVLAKE_T, PARAMS3))
    n9 = c.rows(cnt % (OURS, PARAMS3))[0][0]
    c.check("A9", "a full re-import of DevLake (delete by its raw table + params) keeps our 3 rows", n9 == "3", n9)
    by_params = "SELECT COUNT(*) FROM pull_request_assignees WHERE _raw_data_params = '%s'"   # any _raw_data_table
    pre10 = c.rows(by_params % PARAMS3)[0][0]
    c.sql("DELETE FROM pull_request_assignees WHERE _raw_data_table LIKE '_raw_github%%' AND _raw_data_params = '%s'" % PARAMS3)
    n10 = c.rows(by_params % PARAMS3)[0][0]
    other = c.rows(by_params % PARAMS9)[0][0]
    c.check("A10", "a scope deletion (LIKE '_raw_github%' + params) removes the 3 rows of that repo (whatever their table name is "
                   "in the script) and not another repo's row", (pre10, n10, other) == ("3", "0", "1"), (pre10, n10, other))


def scene_rerun(c):
    """A4 A4z A5 A5o."""
    c.reset()
    c.add_prs(4000012, 4000013)
    c.sql("INSERT INTO pull_request_assignees (pull_request_id, assignee_id, name, user_name, _raw_data_table, _raw_data_params, created_at, updated_at) "
          "VALUES ('%s', '%s', 'dev-owned', 'dev-owned', '%s', '%s', NOW(3), NOW(3))" % (pid(4000012), aid(7009), DEVLAKE_T, PARAMS3))
    dev = "SELECT COUNT(*) FROM pull_request_assignees WHERE _raw_data_table = '%s' AND pull_request_id = '%s'" % (DEVLAKE_T, pid(4000012))
    _, _, _, out = import_ok(c, "A4", "pages_a4_first.json")
    c.apply(out)
    first = c.ours()
    c.check("A4", "first import: 2 rows on PR 4000012 and 1 on PR 4000013",
            first == [(pid(4000012), aid(7001), "octocat", "octocat"), (pid(4000012), aid(7002), "hubot", "hubot"),
                      (pid(4000013), aid(7001), "octocat", "octocat")], first)
    _, _, _, out = import_ok(c, "A4", "pages_a4_second.json")
    c.apply(out)
    c.apply(out)    # the same .sql twice must give the same rows
    second = c.ours()
    c.check("A4", "second import (1 assignee left): 1 row on PR 4000012 after it (run twice, same result)",
            [r for r in second if r[0] == pid(4000012)] == [(pid(4000012), aid(7001), "octocat", "octocat")], second)
    c.check("A5o", "our row of PR 4000013, which is not in the second input, stays",
            [r for r in second if r[0] == pid(4000013)] == [(pid(4000013), aid(7001), "octocat", "octocat")], second)
    d = c.rows(dev)[0][0]
    c.check("A5", "DevLake's own row (another _raw_data_table) on the same PR stays after the import", d == "1", d)
    _, _, _, out = import_ok(c, "A4z", "pages_a4_zero.json")
    c.apply(out)
    zero = c.ours()
    c.check("A4z", "third import (0 assignees): 0 rows on PR 4000012, PR 4000013 untouched",
            zero == [(pid(4000013), aid(7001), "octocat", "octocat")], zero)
    c.check("A5", "DevLake's own row stays after the third import too", c.rows(dev)[0][0] == "1", c.rows(dev))


def scene_pages(c):
    """A7 and the stops on a bad Link."""
    c.reset()
    c.add_prs(4000021, 4000022)
    _, so, _, out = import_ok(c, "A7", "pages_two_pages.json")
    chk = c.apply(out)
    got = c.ours()
    c.check("A7", "two pages: the PRs of both pages get their rows and pages_read is 2",
            got == [(pid(4000021), aid(7001), "octocat", "octocat"), (pid(4000022), aid(7002), "hubot", "hubot")]
            and chk.get("pages_read") == "2", (got, chk))
    rc, _, se, out = c.run_import("pages_bad_host.json")
    c.check("A7", "a next URL that is not on https://api.github.com/ stops the script, exit code is not 0, no .sql",
            rc != 0 and not out.exists() and "api.github.com" in se, (rc, se))
    rc, _, se, out = c.run_import("pages_truncated.json")
    c.check("A7", "an input that ends while the last page still has a next link stops with no .sql",
            rc != 0 and not out.exists(), (rc, se))


def scene_escape(c):
    """A8."""
    c.reset()
    c.add_prs(4000031, 4000032, 4000033, 4000034)
    rc, so, se, out = import_ok(c, "A8", "pages_escape.json")
    c.check("A8", "the number of skipped PRs is printed", "did not pass the checks: 3" in so, so)
    chk = c.apply(out) if out.exists() else {}
    url = "https://api.github.com/repos/octo-org/demo-repo/pulls?note=a'b\\c'; DELETE FROM pull_requests WHERE 1 = 1; --\\"
    c.check("A8", "a page url with a quote and a backslash is stored in the check SELECT exactly as it is",
            chk.get("page_urls") == url, chk)
    got = c.ours()
    c.check("A8", "the valid PR gets its row; the PR with a bad login, the one with a 40-character login and the one "
                  "with a text id are skipped (3 counted)",
            got == [(pid(4000031), aid(7001), "octocat", "octocat")] and chk.get("prs_skipped_invalid") == "3"
            and chk.get("prs_read") == "4", (got, chk))
    n = c.rows("SELECT COUNT(*) FROM pull_requests")[0][0]
    c.check("A8", "the text in the page url did not run as SQL (pull_requests still has 4 rows)", n == "4", n)
    for bad in ("octo'org/demo", "octo\\org/demo", "a/b'; SELECT 1; --", "../x", "x/..", "noslash", "a/b/c"):
        rc, _, se, out = c.run_import("pages_basic.json", repo=bad)
        c.check("A8", "--repo %r is refused, exit code 2, no .sql" % bad, rc == 2 and not out.exists(), (rc, se))


def scene_u1_chain(c):
    """A13: the ordering 1B of the U1 SQL, on one PR, before and after the import."""
    c.reset()
    c.sql("INSERT INTO accounts (id, user_name, is_bot) VALUES ('github:GithubAccount:1:1', 'alice', 0), "
          "('github:GithubAccount:1:3', 'carol', 0), ('github:GithubAccount:1:5', 'Copilot', 0);")
    c.sql("INSERT INTO pull_requests (id, base_repo_id, status, description, author_name, author_id, created_date, merged_date, closed_date, "
          "head_ref, additions, deletions, is_draft, _raw_data_params, _raw_data_table) VALUES "
          "('github:GithubPullRequest:1:5000001', 'github:GithubRepo:1:1', 'MERGED', '', 'Copilot', 'github:GithubAccount:1:5', "
          "'2026-03-05 00:00:00', '2026-03-06 00:00:00', '2026-03-06 00:00:00', 'copilot/x', 10, 2, 0, "
          "'{\"ConnectionId\":1,\"Name\":\"octo-org/demo-repo\"}', '%s');" % DEVLAKE_T)
    c.sql("INSERT INTO pull_request_comments (id, pull_request_id, body, account_id, created_date, type, review_id, status) VALUES "
          "('c:51:1', 'github:GithubPullRequest:1:5000001', 'please fix', 'github:GithubAccount:1:1', '2026-03-05 00:10:00', 'NORMAL', '', ''), "
          "('c:51:2', 'github:GithubPullRequest:1:5000001', 'ok', 'github:GithubAccount:1:3', '2026-03-05 01:00:00', 'REVIEW', 'rv:51:1', 'APPROVED');")
    common, metrics = run_u1.split_sql(ROOT / "sql" / "mysql" / "agent_review_burden.sql")
    q = (run_u1.apply_macros(common, run_u1.VARIABLES) + "\n"
         + run_u1.apply_macros(metrics["m1_first_human_reaction"], run_u1.VARIABLES))

    def copilot_row():
        header, rows = c.sql(q)
        return {r[0]: dict(zip(header[1:], r[1:])) for r in rows}["copilot"]

    before = copilot_row()
    c.check("A13", "before the import: reaction 1 and 1B are both 10 minutes (alice, the assignee-to-be, commented first)",
            (before["pr_count"], before["median_minutes"], before["median_minutes_excl_assignee"]) == ("1", "10", "10"), before)
    _, _, _, out = import_ok(c, "A13", "pages_a13.json", conn=1)
    c.apply(out)
    after = copilot_row()
    c.check("A13", "after the import: reaction 1 stays 10, 1B becomes 60 (carol's review; alice is the assignee)",
            (after["pr_count"], after["reacted"], after["median_minutes"], after["reacted_excl_assignee"],
             after["median_minutes_excl_assignee"]) == ("1", "1", "10", "1", "60"), after)


# ------------------------------------------------------------------ network-free checks of the script's own network code
class FakeResp:
    def __init__(self, body, link=None):
        self.headers = {"Link": link} if link else {}
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(url, code):
    h = email.message.Message()
    h["X-RateLimit-Remaining"] = "0"
    h["X-RateLimit-Reset"] = "1"
    return urllib.error.HTTPError(url, code, "x", h, None)


def run_main(mod, tmp, answers):
    """Run mod.main() against fake answers (a list of FakeResp or an Exception to raise); return (rc, text, requests, out)."""
    out = Path(tmp) / "net.sql"
    if out.exists():
        out.unlink()
    seen = []

    def fake_open(req):
        seen.append(req)
        a = answers[len(seen) - 1]
        if isinstance(a, Exception):
            raise a
        return a

    mod.open_url, mod.read_token = fake_open, (lambda: TOKEN)
    buf_o, buf_e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
        rc = mod.main(["--repo", REPO, "--connection-id", "3", "--out", str(out)])
    return rc, buf_o.getvalue() + buf_e.getvalue(), seen, out


def scene_network_free(c):
    mod = c.load_module()
    req = mod.build_request("https://api.github.com/repos/o/r/pulls", TOKEN)
    c.check("N1", "the token is an unredirected header (urllib does not copy it to a redirect target) and not an ordinary header",
            req.unredirected_hdrs.get("Authorization") == "Bearer " + TOKEN
            and "Authorization" not in req.headers and TOKEN not in str(sorted(req.headers.items())), (req.unredirected_hdrs, req.headers))
    c.check("N1", "without a token no Authorization header is made",
            "Authorization" not in mod.build_request("https://api.github.com/x", None).unredirected_hdrs, "")
    first = "https://api.github.com/repos/octo-org/demo-repo/pulls?state=all&per_page=100"
    body = [{"id": 4000001, "number": 1, "assignees": [{"login": "octocat", "id": 7001}]}]
    for code in (403, 429):
        rc, text, seen, out = run_main(mod, c.tmp, [FakeResp(body, '<https://api.github.com/p2>; rel="next"'), http_error(first, code)])
        c.check("N2", "HTTP %d on page 2: exit code 1, no .sql, 'after 1 page', the token is not printed, one request per page (no retry)" % code,
                rc == 1 and not out.exists() and "HTTP %d after 1 page" % code in text and TOKEN not in text and len(seen) == 2,
                (rc, text, len(seen)))
    rc, text, seen, out = run_main(mod, c.tmp, [http_error(first, 403)])
    c.check("N2", "HTTP 403 on page 1: 'after 0 page', no .sql, requested URL is the documented one",
            rc == 1 and not out.exists() and "after 0 page" in text and seen[0].full_url == first, (rc, text))
    rc, text, seen, out = run_main(mod, c.tmp, [FakeResp(body, '<http://api.github.com/p2>; rel="next"')])
    c.check("N3", "a next URL with http:// (not https://api.github.com/) stops the script; only 1 request is made, no .sql",
            rc == 1 and not out.exists() and len(seen) == 1, (rc, text))
    rc, text, seen, out = run_main(mod, c.tmp, [FakeResp(body, '<%s>; rel="next"' % first)])
    c.check("N4", "a Link that points back to a URL already read stops the script, no .sql", rc == 1 and not out.exists(), (rc, text))
    p2 = "https://api.github.com/repositories/9/pulls?state=all&per_page=100&page=2"
    rc, text, seen, out = run_main(mod, c.tmp, [FakeResp(body, '<%s>; rel="next", <%s>; rel="last"' % (p2, p2)),
                                                 FakeResp([{"id": 4000002, "number": 2, "assignees": []}])])
    sql = out.read_text(encoding="utf-8") if out.exists() else ""
    c.check("N5", "two fake pages are read by following rel=next; the .sql has the PR ids of both pages",
            rc == 0 and [s.full_url for s in seen] == [first, p2] and pid(4000001) in sql and pid(4000002) in sql,
            (rc, text, [s.full_url for s in seen]))
    c.check("N6", "the token is in neither the printed text nor the .sql, and was sent as an unredirected header on both requests",
            TOKEN not in text and TOKEN not in sql and all(s.unredirected_hdrs.get("Authorization") == "Bearer " + TOKEN for s in seen), text)


SCENES = [
    (["A1", "A2", "A3", "A6", "A9", "A10", "A11", "A12"], scene_basic),
    (["A4", "A4z", "A5", "A5o"], scene_rerun),
    (["A7"], scene_pages),
    (["A8"], scene_escape),
    (["A13"], scene_u1_chain),
    (["N1", "N2", "N3", "N4", "N5", "N6"], scene_network_free),
]


def run_suite(script, name):
    with tempfile.TemporaryDirectory() as tmp:
        c = Ctx(script, name, tmp)
        for labels, fn in SCENES:
            try:
                fn(c)
            except Exception as e:  # a SQL error or a crash counts as a failure of the labels of that scene
                for lab in labels:
                    c.check(lab, "%s raised %s: %s" % (fn.__name__, type(e).__name__, str(e)[:300]), False, str(e)[:300])
        return c.results


# ------------------------------------------------------------------ mutants: one change at a time
SRC_DELETE = '    delete_where = "_raw_data_table = %s AND %s" % (table, in_list("pull_request_id", pr_ids))\n'
MUTANTS = [
    ("DELETE without the _raw_data_table condition", "A5",
     SRC_DELETE, '    delete_where = "%s" % (in_list("pull_request_id", pr_ids),)\n'),
    ("PR id built from `number` instead of `id`", "A2",
     '                gid = pr["id"]\n', '                gid = pr["number"]\n'),
    ("backslash not escaped in SQL strings", "A8",
     '    s = s.replace("\\\\", "\\\\\\\\")\n', '    pass\n'),
    ("E2 name does not start with _raw_github", "A10",
     'RAW_DATA_TABLE = "_raw_github_ext_pull_request_assignees"', 'RAW_DATA_TABLE = "_raw_ext_github_pull_request_assignees"'),
    ("DELETE without the IN (...) condition", "A5o",
     SRC_DELETE, '    delete_where = "_raw_data_table = %s" % (table,)\n'),
    ("duplicates (same PR, same assignee) not merged", "A2",
     '                if (pid, aid) in done:\n', '                if False:\n'),
]


def start_container():
    name = "u3-asg-test-" + uuid.uuid4().hex[:8]
    state = {"started": False}

    def cleanup(say=False):
        if state["started"]:
            run_u1.docker("rm", "-f", name, check=False)
            state["started"] = False
            if say:
                print("container %s removed" % name)

    atexit.register(cleanup)
    info = run_u1.docker("info", "--format", "{{.ServerVersion}}", check=False)
    if info.returncode != 0:
        raise RuntimeError("Docker is not running. Start Docker Desktop and run again.")
    print("docker server %s, image mysql:8.4" % info.stdout.decode().strip())
    run_u1.docker("run", "-d", "--name", name, "-e", "MYSQL_ROOT_PASSWORD=" + run_u1.PASSWORD, "-e", "MYSQL_DATABASE=" + run_u1.DB,
                  "mysql:8.4", "--character-set-server=utf8mb4", "--collation-server=utf8mb4_bin", timeout=1800)
    state["started"] = True
    for _ in range(120):
        p = run_u1.docker("exec", name, "mysqladmin", "-uroot", "-p" + run_u1.PASSWORD, "-h127.0.0.1", "ping", check=False)
        if p.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("MySQL did not become ready in 120 s")
    print("mysql %s ready in container %s" % (run_u1.mysql(name, "SELECT VERSION() AS v")[1][0][0], name))
    run_u1.mysql(name, (ROOT / "tests" / "schema_mysql.sql").read_text(encoding="utf-8"))
    run_u1.mysql(name, (HERE / "schema_extra.sql").read_text(encoding="utf-8"))
    coll = run_u1.mysql(name, "SELECT @@collation_server AS s, (SELECT table_collation FROM information_schema.tables WHERE "
                              "table_schema = 'lake' AND table_name = 'pull_request_assignees') AS t")[1][0]
    print("collation: server=%s, pull_request_assignees=%s" % tuple(coll))
    return name, cleanup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="with --mutants: print every failed check")
    a = ap.parse_args()
    cleanup = lambda say=False: None  # noqa: E731
    try:
        name, cleanup = start_container()
        if not a.mutants:
            results = run_suite(SCRIPT, name)
            for label, desc, ok, detail in results:
                print("%s %-4s %s%s" % ("PASS" if ok else "FAIL", label, desc, "" if ok else "\n       got: " + detail))
            bad = [r for r in results if not r[2]]
            cleanup(True)
            print("%d checks, %d failures" % (len(results), len(bad)))   # the last line of the output
            return 1 if bad else 0
        src = SCRIPT.read_text(encoding="utf-8")
        caught = 0
        with tempfile.TemporaryDirectory() as mdir:
            for i, (desc, expected, old, new) in enumerate(MUTANTS, 1):
                if src.count(old) != 1:
                    print("ERROR: mutant %d: the text to change is found %d times (must be 1): %r" % (i, src.count(old), old))
                    return 2
                path = Path(mdir) / ("mutant_%d.py" % i)
                path.write_text(src.replace(old, new), encoding="utf-8")
                results = run_suite(path, name)
                failed = sorted({r[0] for r in results if not r[2]})
                if a.verbose:
                    for r in results:
                        if not r[2]:
                            print("    FAIL %s %s | %s" % (r[0], r[1][:90], r[3][:300]))
                ok = expected in failed
                caught += ok
                print("mutant %d: %-52s expected to fail %-4s -> failed scenes: %s -> %s"
                      % (i, desc, expected, ", ".join(failed) or "(none)", "CAUGHT" if ok else "NOT CAUGHT"))
        cleanup(True)
        print("%d mutants, %d caught" % (len(MUTANTS), caught))   # the last line of the output
        return 0 if caught == len(MUTANTS) else 1
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
