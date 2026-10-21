#!/usr/bin/env python3
"""Test of tools/run_on_devlake.py without a database: the file reading, the macros, the SELECT-only guard and the
reading of mysql --batch output. The expected values are written by hand.

Usage: python tests/tools/test_run_on_devlake.py     (the last line is "N checks, M failures"; exit code 0 = no failure)
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("run_on_devlake", ROOT / "tools" / "run_on_devlake.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rows, bad = [], []


def check(name, got, want):
    ok = got == want
    rows.append(name)
    if not ok:
        bad.append("%s: got %r, want %r" % (name, got, want))


def raises(name, fn):
    rows.append(name)
    try:
        fn()
    except RuntimeError:
        return
    bad.append("%s: nothing was refused" % name)


# 1. the SQL files are split like tests/run_u1.py splits them
common, metrics = mod.split_blocks(ROOT / "sql" / "mysql" / "ai_impact_parity.sql")
check("u2 has a common block", common is not None and common.lstrip().startswith("WITH identities"), True)
check("u2 metric names", sorted(metrics), sorted(["batch_size", "cloud_agent_outcomes", "diagnostics", "pr_classification",
                                                  "throughput", "time_in_review", "time_to_first_review", "pr_cycle_time"]))
c1, m1 = mod.split_blocks(ROOT / "sql" / "mysql" / "checks" / "per_pr.sql")
check("checks file has no common block", c1, None)
check("checks file metric", sorted(m1), ["per_pr"])
c2, m2 = mod.split_blocks(ROOT / "sql" / "mysql" / "agent_review_burden.sql")
check("u1 metric count", len(m2), 5)

# 2. macros
text = "WHERE $__timeFilter(pr.created_date) OR $__timeFilter(pr.merged_date) AND x IN (${repo_id}) AND ${include_own_markers:sqlstring} = '1'"
out = mod.apply_macros(text, "2026-09-01 00:00:00", "2026-09-30 23:59:59", ["r:1", "r:2"], 1)
check("macros", out, "WHERE pr.created_date BETWEEN '2026-09-01 00:00:00' AND '2026-09-30 23:59:59' OR "
                     "pr.merged_date BETWEEN '2026-09-01 00:00:00' AND '2026-09-30 23:59:59' AND x IN ('r:1', 'r:2') AND '1' = '1'")
raises("unknown macro refused", lambda: mod.apply_macros("$__timeGroup(x)", "a", "b", ["r"], 0))
for f in (ROOT / "sql" / "mysql" / "ai_impact_parity.sql", ROOT / "sql" / "mysql" / "agent_review_burden.sql"):
    cm, mt = mod.split_blocks(f)
    for name, body in mt.items():
        mod.apply_macros(cm + body, "2026-09-01 00:00:00", "2026-09-30 23:59:59", ["r:1"], 0)
rows.append("every metric of both SQL files has all its macros replaced")

# 3. only a single SELECT / WITH statement goes out
check("select ok", mod.check_select_only("-- c\nSELECT 1;"), "SELECT 1;")
check("with ok", mod.check_select_only("WITH a AS (SELECT 1) -- note\nSELECT * FROM a"), "WITH a AS (SELECT 1) \nSELECT * FROM a;")
raises("delete refused", lambda: mod.check_select_only("DELETE FROM pull_requests"))
raises("update refused", lambda: mod.check_select_only("-- SELECT\nUPDATE pull_requests SET status = 'x'"))
raises("two statements refused", lambda: mod.check_select_only("SELECT 1; SELECT 2"))
raises("insert refused", lambda: mod.check_select_only("INSERT INTO t VALUES (1)"))

# 4. mysql --batch output
header, data = mod.parse_batch("a\tb\tc\n1\tNULL\tx\\ty\nz\\\\w\t\\n\t\n")
check("batch header", header, ["a", "b", "c"])
check("batch rows", data, [["1", "", "x\ty"], ["z\\w", "\n", ""]])
check("empty output", mod.parse_batch(""), ([], []))

for b in bad:
    print("FAIL " + b)
print("%d checks, %d failures" % (len(rows), len(bad)))
sys.exit(1 if bad else 0)
