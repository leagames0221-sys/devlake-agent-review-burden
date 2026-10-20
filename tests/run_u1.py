#!/usr/bin/env python3
"""Run a metric SQL file against a throw-away MySQL 8 container and compare with an expected json.
(U1 defaults: sql/mysql/agent_review_burden.sql, tests/fixture_u1.sql, tests/expected_u1.json.
U2 passes its own files with --sql / --fixture / --expected / --var, see docs/adr/0002.)

Steps: start a fresh container (public image from Docker Hub, started with the same character set
and collation as DevLake's own compose file: utf8mb4 / utf8mb4_bin) -> load schema_mysql.sql and
fixture_u1.sql -> run each "-- @metric" block of sql/mysql/agent_review_burden.sql (appended to the
"-- @common" block, Grafana macros replaced by fixed values) -> compare -> stop and remove the
container (also when something fails).

Standard library and the docker CLI only. No network access other than pulling the MySQL image
the first time. Nothing contacts GitHub.

Usage: python tests/run_u1.py [--sql PATH] [--fixture PATH] [--expected PATH] [--var NAME=VALUE ...] [--image mysql:8.4]

The first column of every "-- @metric" result is the row key. It must be unique inside one metric
(a repeated key stops the test). U1 uses the agent name as the key; U2 uses composite keys such as
tool:<name>, mode:<name>, week:<YEARWEEK>, pr:<PR id>, check:<name>; a key that combines two parts joins them
with | so that no two rows share a key (tool:<name>|week:<YEARWEEK>, mode:cloud_agent|tool:<name>). Values are compared as numbers
(tolerance 1e-4) when the expected value is a json number, as exact text when it is a json string,
and as NULL when it is json null.
Exit code 0 = every expected value matched; 1 = a mismatch; 2 = an environment problem.
"""
import argparse
import atexit
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = uuid.uuid4().hex  # root password of the throw-away container; new for every run, never stored
DB = "lake"

# Fixed values for the Grafana macros (period 2026-03-01 .. 2026-03-31, one repo).
# U2 adds the merged_date filter and the dashboard variable include_own_markers (0 or 1, default 0).
VARIABLES = {"include_own_markers": "0"}


def macros(variables):
    return [
        ("$__timeFilter(pr.created_date)",
         "pr.created_date BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'"),
        ("$__timeFilter(pr.merged_date)",
         "pr.merged_date BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'"),
        ("${repo_id}", "'github:GithubRepo:1:1'"),
        ("${include_own_markers}", variables["include_own_markers"]),
    ]


def docker(*args, input_bytes=None, check=True, timeout=600):
    r = subprocess.run(["docker", *args], input=input_bytes, capture_output=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("docker %s failed (%d): %s" % (" ".join(args[:3]), r.returncode,
                           r.stderr.decode("utf-8", "replace").strip()))
    return r


def mysql(name, sql_text):
    """Run SQL in the container; return (header, rows) of the last result set, NULL -> None."""
    r = docker("exec", "-i", name, "mysql", "-uroot", "-p" + PASSWORD, "--default-character-set=utf8mb4",
               "--batch", "--raw", DB, input_bytes=sql_text.encode("utf-8"), check=False)
    err = "\n".join(l for l in r.stderr.decode("utf-8", "replace").splitlines()
                    if "Using a password on the command line" not in l).strip()
    if r.returncode != 0:
        raise RuntimeError("mysql error: " + err)
    lines = r.stdout.decode("utf-8").splitlines()
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = [[None if c == "NULL" else c for c in l.split("\t")] for l in lines[1:]]
    return header, rows


def split_sql(path):
    """Return (common_text, {metric_name: text}) from the marker lines."""
    sections, current, buf = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^-- @(common|metric)\b\s*(\S*)\s*$", line)
        if m:
            if current:
                sections[current] = "\n".join(buf)
            current = m.group(2) if m.group(1) == "metric" else "@common"
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf)
    common = sections.pop("@common", None)
    if common is None or not sections:
        raise RuntimeError("SQL file has no @common or no @metric block: %s" % path)
    return common, sections


def apply_macros(text, variables):
    for k, v in macros(variables):
        text = text.replace(k, v)
    if "$__" in text or "${" in text:
        raise RuntimeError("a Grafana macro was not replaced")
    return text


def same(expected, got):
    if expected is None or got is None:
        return expected is None and got is None
    if isinstance(expected, str):  # text value: exact match
        return expected == got
    # 1e-4: MySQL AVG() returns 4 decimals (2/3 -> 0.6667).
    try:
        return abs(float(expected) - float(got)) < 1e-4
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", default=str(ROOT / "sql" / "mysql" / "agent_review_burden.sql"))
    ap.add_argument("--fixture", default=str(ROOT / "tests" / "fixture_u1.sql"))
    ap.add_argument("--expected", default=str(ROOT / "tests" / "expected_u1.json"))
    ap.add_argument("--var", action="append", default=[], metavar="NAME=VALUE",
                    help="dashboard variable, for example include_own_markers=1")
    ap.add_argument("--image", default="mysql:8.4")
    a = ap.parse_args()

    variables = dict(VARIABLES)
    for item in a.var:
        k, _, v = item.partition("=")
        if k not in VARIABLES or v not in ("0", "1"):
            print("unknown variable or value (only include_own_markers=0|1): %s" % item, file=sys.stderr)
            return 2
        variables[k] = v
    print("variables: " + ", ".join("%s=%s" % kv for kv in sorted(variables.items())))

    expected = json.loads(Path(a.expected).read_text(encoding="utf-8"))["metrics"]
    common, metrics = split_sql(Path(a.sql))

    name = "u1-arb-test-" + uuid.uuid4().hex[:8]
    state = {"started": False}

    def cleanup():
        if state["started"]:
            docker("rm", "-f", name, check=False)
            state["started"] = False
            print("container %s removed" % name)

    atexit.register(cleanup)
    try:
        info = docker("info", "--format", "{{.ServerVersion}}", check=False)
        if info.returncode != 0:
            print("Docker is not running. Start Docker Desktop and run again.", file=sys.stderr)
            return 2
        print("docker server %s, image %s" % (info.stdout.decode().strip(), a.image))
        docker("run", "-d", "--name", name, "-e", "MYSQL_ROOT_PASSWORD=" + PASSWORD,
               "-e", "MYSQL_DATABASE=" + DB, a.image,
               # DevLake's docker-compose-dev-mysql.yml (tag v1.0.3-beta18, line 33)
               "--character-set-server=utf8mb4", "--collation-server=utf8mb4_bin", timeout=1800)
        state["started"] = True
        # The official image first runs a temporary server without TCP; a TCP ping succeeds only on the real one.
        for _ in range(120):
            p = docker("exec", name, "mysqladmin", "-uroot", "-p" + PASSWORD, "-h127.0.0.1", "ping", check=False)
            if p.returncode == 0:
                break
            time.sleep(1)
        else:
            print("MySQL did not become ready in 120 s", file=sys.stderr)
            return 2
        ver = mysql(name, "SELECT VERSION() AS v")[1][0][0]
        print("mysql %s ready in container %s" % (ver, name))

        mysql(name, (ROOT / "tests" / "schema_mysql.sql").read_text(encoding="utf-8"))
        mysql(name, Path(a.fixture).read_text(encoding="utf-8"))
        coll = mysql(name, "SELECT @@character_set_server AS character_set_server, @@collation_server AS collation_server, "
                           "@@collation_database AS collation_database, "
                           "(SELECT table_collation FROM information_schema.tables WHERE table_schema = 'lake' "
                           "AND table_name = 'pull_requests') AS pull_requests_table_collation")
        print("collation: " + ", ".join("%s=%s" % (k, v) for k, v in zip(coll[0], coll[1][0])))
        cnt = mysql(name, "SELECT (SELECT COUNT(*) FROM pull_requests) AS prs, "
                          "(SELECT COUNT(*) FROM pull_request_comments) AS comments, "
                          "(SELECT COUNT(*) FROM accounts) AS accounts, "
                          "(SELECT COUNT(*) FROM pull_request_assignees) AS assignees")[1][0]
        print("loaded: prs=%s comments=%s accounts=%s assignees=%s" % tuple(cnt))

        checks, bad = 0, []
        for metric, exp_by_agent in expected.items():
            if metric not in metrics:
                bad.append("metric %s is missing in the SQL file" % metric)
                continue
            header, rows = mysql(name, apply_macros(common, variables) + "\n" + apply_macros(metrics[metric], variables))
            got = {}
            for r in rows:
                if r[0] in got:  # never overwrite silently
                    bad.append("DUPLICATE KEY in %s: %s" % (metric, r[0]))
                got[r[0]] = dict(zip(header[1:], r[1:]))
            print("-- %s" % metric)
            print("   " + "\t".join(header))
            for r in rows:
                print("   " + "\t".join("NULL" if c is None else c for c in r))
            for agent, fields in exp_by_agent.items():
                for f, ev in fields.items():
                    checks += 1
                    gv = got.get(agent, {}).get(f, "<missing>")
                    if gv == "<missing>" or not same(ev, gv):
                        bad.append("MISMATCH %s %s %s: expected %s got %s" % (metric, agent, f, ev, gv))
            extra = set(got) - set(exp_by_agent)
            if extra:
                bad.append("unexpected agents in %s: %s" % (metric, sorted(extra)))
        print()
        for b in bad:
            print(b)
        print("%d values compared, %d mismatches" % (checks, len(bad)))
        return 1 if bad else 0
    except Exception as e:  # environment or SQL error
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
