#!/usr/bin/env python3
"""Test of the dashboard (U5, ADR 0004) on a throw-away MySQL 8 container (the same image and settings as tests/run_u1.py).

V1  The SQL of every panel of the built dashboard (tools/build_dashboard.py) is run with the variables replaced the way Grafana does it
    (${name:sqlstring}; $__timeFilter(col) as `col BETWEEN FROM_UNIXTIME(a) AND FROM_UNIXTIME(b)` with the session time zone +00:00, as in the
    Grafana page on the MySQL query editor and data source), for each of the three comparisons, on fixture_u2.sql (the parity panels) and fixture_u1.sql
    (the three U1 panels). The rows must be exactly the set of keys that SPEC section 4-3 gives for that comparison, and every value must be the
    value of tests/expected_u2_parity.json / expected_u1.json (worked out by hand).
V2  The variable scenes (tests/fixture_u5.sql, tests/expected_u5_vars.json): tools taken out, modes, the marks m5 / x1 / x2, a custom tool and a
    removed built-in row, first_reaction = any, own markers, and two hostile values. And fixture_u2.sql with first_reaction = any.
Also: the SQL of the panels has no Grafana variable syntax other than the ones the dashboard defines (no bare text variable, no [[ ]]).

Expected values are in the json files, worked out by hand from the fixtures; nothing is taken from running the SQL.
Usage: python tests/test_dashboard.py     (the last line is "N checks, M failures"; exit code 0 = no failure, 2 = environment problem)
"""
import atexit
import datetime
import importlib.util
import json
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("run_u1", ROOT / "tests" / "run_u1.py")
run_u1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_u1)
import ai_impact_sql  # noqa: E402
import build_dashboard  # noqa: E402

IMAGE = "mysql:8.4"


def _epoch(text):
    return int(datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp())


def expand_time(sql):
    """Grafana's $__timeFilter(col) for the period 2026-03-01 00:00:00 .. 2026-03-31 23:59:59 UTC: `col BETWEEN FROM_UNIXTIME(a) AND FROM_UNIXTIME(b)`."""
    a, b = _epoch("2026-03-01 00:00:00"), _epoch("2026-03-31 23:59:59")
    for col in ("pr.created_date", "pr.merged_date"):
        sql = sql.replace("$__timeFilter(%s)" % col, "%s BETWEEN FROM_UNIXTIME(%d) AND FROM_UNIXTIME(%d)" % (col, a, b))
    return sql


def apply(sql, variables):
    return run_u1.apply_macros(expand_time(sql), variables)
rows_checked, bad = [], []


def check(name, ok, detail=""):
    rows_checked.append(name)
    if not ok:
        bad.append("%s %s" % (name, detail))


# ------------------------------------------------------------------ the container
class Db:
    def __init__(self):
        self.name = "u5-dash-test-" + uuid.uuid4().hex[:8]
        self.started = False

    def start(self):
        info = run_u1.docker("info", "--format", "{{.ServerVersion}}", check=False)
        if info.returncode != 0:
            raise RuntimeError("Docker is not running. Start Docker Desktop and run again.")
        run_u1.docker("run", "-d", "--name", self.name, "-e", "MYSQL_ROOT_PASSWORD=" + run_u1.PASSWORD, "-e", "MYSQL_DATABASE=lake", IMAGE,
                      "--character-set-server=utf8mb4", "--collation-server=utf8mb4_bin", timeout=1800)
        self.started = True
        for _ in range(120):
            p = run_u1.docker("exec", self.name, "mysqladmin", "-uroot", "-p" + run_u1.PASSWORD, "-h127.0.0.1", "ping", check=False)
            if p.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("MySQL did not become ready in 120 s")
        schema = (ROOT / "tests" / "schema_mysql.sql").read_text(encoding="utf-8")
        for db, fixture in (("lake_u1", "fixture_u1.sql"), ("lake_u2", "fixture_u2.sql"), ("lake_u5", "fixture_u5.sql"), ("lake_u5c", "fixture_u5_coauthor.sql")):
            self.sql("lake", "CREATE DATABASE %s;" % db)
            self.sql(db, schema)
            self.sql(db, (ROOT / "tests" / fixture).read_text(encoding="utf-8"))

    def sql(self, db, text):
        """(header, rows) of the last result set; NULL -> None. A mysql error raises RuntimeError."""
        r = run_u1.docker("exec", "-i", self.name, "mysql", "-uroot", "-p" + run_u1.PASSWORD, "--default-character-set=utf8mb4", "--batch", "--raw",
                          db, input_bytes=("SET time_zone = '+00:00';\n" + text).encode("utf-8"), check=False)
        err = "\n".join(l for l in r.stderr.decode("utf-8", "replace").splitlines() if "Using a password on the command line" not in l).strip()
        if r.returncode != 0:
            raise RuntimeError("mysql error: " + err[:400])
        lines = r.stdout.decode("utf-8").splitlines()
        if not lines:
            return [], []
        return lines[0].split("\t"), [[None if c == "NULL" else c for c in l.split("\t")] for l in lines[1:]]

    def stop(self):
        if self.started:
            run_u1.docker("rm", "-f", self.name, check=False)
            self.started = False


def by_key(header, rows):
    out = {}
    for r in rows:
        if r[0] in out:
            raise RuntimeError("duplicate key %s" % r[0])
        out[r[0]] = dict(zip(header[1:], r[1:]))
    return out


def compare(name, got, want_by_key, exact_keys=True):
    """got: {key: {field: text}}, want_by_key: {key: {field: expected}}. Checks the key set (when exact_keys) and every listed value."""
    if exact_keys:
        check(name + ": the rows are exactly the expected keys", set(got) == set(want_by_key),
              "extra=%s missing=%s" % (sorted(set(got) - set(want_by_key)), sorted(set(want_by_key) - set(got))))
    for key, fields in want_by_key.items():
        for f, ev in fields.items():
            gv = got.get(key, {}).get(f, "<missing>")
            check("%s: %s %s" % (name, key, f), gv != "<missing>" and run_u1.same(ev, gv), "expected %r got %r" % (ev, gv))


# ------------------------------------------------------------------ the panels
def flatten(panels):
    for p in panels:
        yield p
        for q in flatten(p.get("panels", [])):
            yield q


def variables_for(common, **over):
    v = dict(run_u1.VARIABLES)
    v["tools"] = ai_impact_sql.all_tools(common)
    v.update(over)
    return v


# the rows of each comparison, SPEC section 4-3, written here from the SPEC table (not from the build script)
MODE_ROWS = ["mode:cloud_agent", "mode:ai_assisted", "mode:review_agent", "mode:everything_else"]


def want_keys(kind, comparison, expected_keys):
    if kind == "period":
        if comparison == "tools":
            return {k for k in expected_keys if k.startswith("tool:") and "|" not in k}
        return set(MODE_ROWS) if comparison == "modes" else {"mode:ai_used", "mode:everything_else"}
    if kind == "week":
        if comparison == "tools":
            return {k for k in expected_keys if re.fullmatch(r"tool:[a-z_]+\|week:\d+", k)}
        return {k for k in expected_keys if re.fullmatch(r"week:\d+", k)}
    if kind == "outcome":
        if comparison == "tools":
            return {k for k in expected_keys if k.startswith("mode:cloud_agent|tool:")}
        return {"mode:cloud_agent"}
    return set(expected_keys)   # diagnostics: all


# panel id -> (metric, kind)
PARITY_IDS = {11: ("throughput", "period"), 12: ("pr_cycle_time", "period"), 13: ("time_to_first_review", "period"), 14: ("time_in_review", "period"),
              15: ("batch_size", "period"), 16: ("throughput", "week"), 17: ("cloud_agent_outcomes", "outcome"), 31: ("diagnostics", "all")}
U1_IDS = {21: "m2_review_burden", 22: "m3_changes_requested", 23: "m1_first_human_reaction"}


def test_panels(db, dash):
    common, metrics = run_u1.split_sql(ROOT / "sql" / "mysql" / "ai_impact_parity.sql")
    u1_common, u1_metrics = run_u1.split_sql(ROOT / "sql" / "mysql" / "agent_review_burden.sql")
    expected = json.loads((ROOT / "tests" / "expected_u2_parity.json").read_text(encoding="utf-8"))["metrics"]
    expected_u1 = json.loads((ROOT / "tests" / "expected_u1.json").read_text(encoding="utf-8"))["metrics"]
    panels = {p["id"]: p for p in flatten(dash["panels"]) if p["type"] == "table"}
    check("the dashboard has the 8 parity panels and the 3 U1 panels", set(panels) == set(PARITY_IDS) | set(U1_IDS), sorted(panels))
    for pid, (metric, kind) in PARITY_IDS.items():
        sql = panels[pid]["targets"][0]["rawSql"]
        check("panel %d embeds the metric %s" % (pid, metric), (", metric AS (\n" + metrics[metric].strip() + "\n)\nSELECT * FROM metric") in sql)
        check("panel %d starts with the @common block" % pid, sql.startswith(common.rstrip()))
        for comparison in ("tools", "modes", "ai_used"):
            name = "V1 panel %d (%s) comparison=%s" % (pid, metric, comparison)
            header, data = db.sql("lake_u2", apply(sql, variables_for(common, comparison=comparison)))
            got = by_key(header, data)
            keys = want_keys(kind, comparison, expected[metric])
            compare(name, got, {k: expected[metric][k] for k in keys})
    for pid, metric in U1_IDS.items():
        sql = panels[pid]["targets"][0]["rawSql"]
        for comparison in ("tools", "modes", "ai_used"):
            name = "V1 panel %d (%s) comparison=%s" % (pid, metric, comparison)
            header, data = db.sql("lake_u1", apply(sql, dict(run_u1.VARIABLES, comparison=comparison)))
            got = by_key(header, data)
            compare(name, got, expected_u1[metric])
            sort_no = [int(r[header.index("sort_no")]) for r in data]
            check(name + ": rows are in the order of sort_no", sort_no == sorted(sort_no) and len(sort_no) == 7, sort_no)


def test_syntax(dash):
    """No Grafana variable syntax in the SQL of the panels other than the macros and variables that the dashboard defines."""
    names = {v["name"] for v in dash["templating"]["list"]}
    for p in flatten(dash["panels"]):
        for t in p.get("targets", []):
            sql = t.get("rawSql")
            if not sql:
                continue
            text = sql.replace("$__timeFilter(pr.created_date)", "").replace("$__timeFilter(pr.merged_date)", "")
            found = re.findall(r"\$\{(\w+)(:\w+)?\}", text)
            check("panel %s: every variable is defined by the dashboard" % p["id"], all(n in names for n, _ in found), found)
            check("panel %s: no bare text variable (only ${repo_id} may be bare)" % p["id"], all(f == ":sqlstring" or n == "repo_id" for n, f in found), found)
            rest = re.sub(r"\$\{\w+(:\w+)?\}", "", text)
            check("panel %s: no other $name, $[ or [[ ]] in the SQL" % p["id"], not re.search(r"\$[A-Za-z_{(\[]", rest) and "[[" not in rest, "")


# ------------------------------------------------------------------ the variable scenes
def run_scene(db, fixture_db, common, metrics, variables, names):
    out = {}
    for n in names:
        header, data = db.sql(fixture_db, apply(common, variables) + "\n" + apply(metrics[n], variables))
        out[n] = by_key(header, data)
    return out


def test_scenes(db):
    doc = json.loads((ROOT / "tests" / "expected_u5_vars.json").read_text(encoding="utf-8"))
    common0, metrics = run_u1.split_sql(ROOT / "sql" / "mysql" / "ai_impact_parity.sql")

    def regex_checker(patterns):
        errors = []
        for p in patterns:
            try:
                db.sql("lake_u5", "SELECT REGEXP_LIKE('', '%s');" % p)
            except RuntimeError as e:
                errors.append("%r: %s" % (p, str(e)[:100]))
        return errors

    # a coauthor pattern with a top-level | (acme|acme-bot) is put into a group after `co-authored-by:` (ADR 0002 m4): a body that names acme-bot
    # outside a Co-authored-by line is not a hit
    cs = doc["coauthor_scene"]
    common_c = build_dashboard.apply_custom_tools(common0, cs["custom_tools"], regex_checker)
    got = run_scene(db, "lake_u5c", common_c, metrics, variables_for(common_c), ["time_to_first_review", "pr_classification"])
    compare("V2 coauthor pattern with | time_to_first_review", got["time_to_first_review"], cs["time_to_first_review"])
    compare("V2 coauthor pattern with | pr_classification", got["pr_classification"],
            {"pr:github:GithubPullRequest:1:" + k: v for k, v in cs["pr_classification"].items()}, exact_keys=False)

    done = {}
    for sc in doc["scenarios"]:
        name = sc["name"].split(" ")[0] + " " + sc["name"].split(" ", 1)[1][:60]
        common = build_dashboard.apply_custom_tools(common0, sc.get("custom_tools"), regex_checker)
        over = dict(sc["vars"])
        if "tools_except" in over:
            gone = over.pop("tools_except")
            over["tools"] = [t for t in ai_impact_sql.all_tools(common) if t not in gone]
        v = variables_for(common, **over)
        got = run_scene(db, "lake_u5", common, metrics, v, ["time_to_first_review", "pr_classification", "cloud_agent_outcomes"])
        want = doc["scenarios"][0]["time_to_first_review"] if sc.get("same_as") == "S0" else sc.get("time_to_first_review")
        compare("V2 " + name + " time_to_first_review", got["time_to_first_review"], want)
        pc = {"pr:github:GithubPullRequest:1:" + k: val for k, val in sc.get("pr_classification", {}).items()}
        if sc.get("same_as") == "S0":
            pc = {"pr:github:GithubPullRequest:1:" + k: val for k, val in doc["scenarios"][0]["pr_classification"].items()}
        compare("V2 " + name + " pr_classification", got["pr_classification"], pc, exact_keys=False)
        if "cloud_agent_outcomes" in sc:
            compare("V2 " + name + " cloud_agent_outcomes", got["cloud_agent_outcomes"], sc["cloud_agent_outcomes"], exact_keys=False)
        done[sc["name"].split(" ")[0]] = True
    check("all scenes were run", len(done) == len(doc["scenarios"]), done)

    # fixture_u2.sql with first_reaction = any: only Q20 changes (90 -> 30 minutes)
    base = json.loads((ROOT / "tests" / "expected_u2_parity.json").read_text(encoding="utf-8"))["metrics"]["time_to_first_review"]
    want = {k: dict(v) for k, v in base.items()}
    want.update(doc["u2_any"]["override"])
    v = variables_for(common0, first_reaction="any")
    got = run_scene(db, "lake_u2", common0, metrics, v, ["time_to_first_review"])["time_to_first_review"]
    compare("V2 fixture_u2 first_reaction=any time_to_first_review", got, want)
    # per PR (a SELECT of this test on the same WITH list; checks/per_pr.sql reads pull_requests.pull_request_key, a column of a real DevLake that the test schema does not have)
    per_pr = "SELECT CONCAT('pr:', f.id) AS grp, f.ttfr_min FROM pr_facts f ORDER BY f.id"
    header, data = db.sql("lake_u2", apply(common0, v) + chr(10) + per_pr)
    q20 = by_key(header, data)["pr:github:GithubPullRequest:1:220"]
    check("V2 fixture_u2 first_reaction=any: Q20 ends at 30 minutes", q20["ttfr_min"] == str(doc["u2_any"]["q20_first_reaction_minutes"]), q20)
    # that is U1's first human reaction of Q20, and the value of expected_u2_u1_cross.json (P-R2: 30 minutes)
    u1_common, _ = run_u1.split_sql(ROOT / "sql" / "mysql" / "agent_review_burden.sql")
    u1_per = "SELECT CONCAT('pr:', f.id) AS grp, f.first_human_min FROM pr_facts f ORDER BY f.id"
    header, data = db.sql("lake_u2", apply(u1_common, run_u1.VARIABLES) + chr(10) + u1_per)
    check("V2 fixture_u2: U1's first human reaction of Q20 is the same 30 minutes",
          by_key(header, data)["pr:github:GithubPullRequest:1:220"]["first_human_min"] == str(doc["u2_any"]["q20_first_reaction_minutes"]))


def main():
    db = Db()
    atexit.register(db.stop)
    try:
        db.start()
        dash = build_dashboard.build()
        test_syntax(dash)
        test_panels(db, dash)
        test_scenes(db)
    except Exception as e:   # environment or SQL error
        print("ERROR: %s" % e, file=sys.stderr)
        for b in bad:
            print("FAIL " + b)
        return 2
    finally:
        db.stop()
    for b in bad:
        print("FAIL " + b)
    print("%d checks, %d failures" % (len(rows_checked), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
