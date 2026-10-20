#!/usr/bin/env python3
"""Run the metric SQL of this repo on a real Apache DevLake database and write each result as a CSV (U4).

The SQL files are read the way tests/run_u1.py reads them ("-- @common" + "-- @metric <name>", the metric is appended to the
common WITH list). The Grafana macros are replaced by fixed values:
  $__timeFilter(pr.created_date) / $__timeFilter(pr.merged_date)   the period (--period-start .. --period-end, UTC, both included)
  ${repo_id}                                                        the DevLake ids of the repos (--repo-id, or all rows of `repos`)
  ${include_own_markers}                                            0 or 1 (--include-own-markers)

It only sends SELECT statements (a statement must start with WITH or SELECT after comments are removed; anything else stops
the run) through `docker compose exec -T mysql sh -c 'mysql ... -p"$MYSQL_PASSWORD" lake'`, run in the folder of DevLake's
compose file (--compose-dir). The password is expanded inside the container; this script never reads it and never reads .env.
A file without "-- @common" (sql/mysql/checks/*.sql) borrows the common block of the file given with --common-from.

Standard library and the docker CLI only.

Usage:
  python tools/run_on_devlake.py --compose-dir DIR --out-dir OUT --sql sql/mysql/ai_impact_parity.sql
  python tools/run_on_devlake.py --compose-dir DIR --out-dir OUT --sql sql/mysql/checks/per_pr.sql --common-from sql/mysql/ai_impact_parity.sql --prefix parity_
"""
import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

DB = "lake"
# Git Bash would rewrite a string that starts with "/" inside the sh -c argument; MSYS_NO_PATHCONV=1 is set for the docker call below.
MYSQL_CMD = 'mysql -umerico -p"$MYSQL_PASSWORD" --default-character-set=utf8mb4 --batch ' + DB


def split_blocks(path):
    """Same marker lines as tests/run_u1.py split_sql. Returns (common_text or None, {metric_name: text})."""
    sections, current, buf = {}, None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
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
    if not sections:
        raise RuntimeError("SQL file has no @metric block: %s" % path)
    return common, sections


def apply_macros(text, period_start, period_end, repo_ids, include_own):
    quoted = ", ".join("'" + r.replace("'", "''") + "'" for r in repo_ids)
    pairs = [
        ("$__timeFilter(pr.created_date)", "pr.created_date BETWEEN '%s' AND '%s'" % (period_start, period_end)),
        ("$__timeFilter(pr.merged_date)", "pr.merged_date BETWEEN '%s' AND '%s'" % (period_start, period_end)),
        ("${repo_id}", quoted),
        ("${include_own_markers}", str(include_own)),
    ]
    for k, v in pairs:
        text = text.replace(k, v)
    if "$__" in text or "${" in text:
        raise RuntimeError("a Grafana macro was not replaced")
    return text


def strip_comments(sql):
    # a "--" comment runs to the end of the line; none of the metric SQL has "--" inside a string
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines()).strip()


def check_select_only(sql):
    body = strip_comments(sql)
    if not re.match(r"(?is)^(with|select)\b", body):
        raise RuntimeError("only a statement that starts with WITH or SELECT is sent")
    if ";" in body.rstrip(";"):
        raise RuntimeError("only one statement is sent")
    return body.rstrip(";") + ";"


_ESC = {"n": "\n", "t": "\t", "\\": "\\", "0": "\0", "b": "\b", "r": "\r", "Z": "\x1a"}


def unescape(cell):
    """mysql --batch writes NULL as the text NULL and escapes \\n \\t \\\\ \\0 in values."""
    if cell == "NULL":
        return ""
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(0)), cell)


def parse_batch(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return [], []
    header = lines[0].split("\t")
    return header, [[unescape(c) for c in l.split("\t")] for l in lines[1:]]


def run_mysql(compose_dir, sql_text):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run(["docker", "compose", "exec", "-T", "mysql", "sh", "-c", MYSQL_CMD], input=sql_text.encode("utf-8"),
                       capture_output=True, cwd=compose_dir, env=env, timeout=1800)
    err = "\n".join(l for l in r.stderr.decode("utf-8", "replace").splitlines()
                    if "Using a password on the command line" not in l and "attribute `version` is obsolete" not in l).strip()
    if r.returncode != 0:
        raise RuntimeError("mysql failed: " + err)
    return parse_batch(r.stdout.decode("utf-8"))


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--compose-dir", required=True, help="the folder of DevLake's docker-compose.yml")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--sql", required=True, help="a SQL file with -- @metric blocks")
    ap.add_argument("--common-from", help="SQL file whose -- @common block is used when --sql has none")
    ap.add_argument("--metrics", nargs="*", help="metric names to run (default: all blocks of --sql)")
    ap.add_argument("--repo-id", nargs="*", help="DevLake repo ids (default: every row of `repos`)")
    ap.add_argument("--include-own-markers", type=int, choices=(0, 1), default=0)
    ap.add_argument("--period-start", default="2026-09-01 00:00:00")
    ap.add_argument("--period-end", default="2026-09-30 23:59:59")
    ap.add_argument("--prefix", default="", help="prefix of the CSV file names")
    a = ap.parse_args(argv)

    common, metrics = split_blocks(a.sql)
    if common is None:
        if not a.common_from:
            raise SystemExit("%s has no @common block: give --common-from" % a.sql)
        common, _ = split_blocks(a.common_from)
    names = a.metrics or list(metrics)
    for n in names:
        if n not in metrics:
            raise SystemExit("metric %s is not in %s" % (n, a.sql))
    repo_ids = a.repo_id
    if not repo_ids:
        _, rows = run_mysql(a.compose_dir, "SELECT id FROM repos ORDER BY id;")
        repo_ids = [r[0] for r in rows]
    if not repo_ids:
        raise SystemExit("no repo in DevLake's `repos` table")
    os.makedirs(a.out_dir, exist_ok=True)
    for n in names:
        sql = apply_macros(common, a.period_start, a.period_end, repo_ids, a.include_own_markers) + "\n" + \
            apply_macros(metrics[n], a.period_start, a.period_end, repo_ids, a.include_own_markers)
        header, rows = run_mysql(a.compose_dir, check_select_only(sql))
        target = Path(a.out_dir) / ("%s%s.csv" % (a.prefix, n))
        write_csv(target, header, rows)
        print("%s: %d rows -> %s" % (n, len(rows), target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
