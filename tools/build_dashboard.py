#!/usr/bin/env python3
"""Builds the Grafana dashboard dashboards/json/ai-impact.json from the tested SQL files (U5, ADR 0004, docs/dashboard.md).

The SQL of every panel is not typed: it is the `-- @common` WITH list of a SQL file, a comma, `metric AS (` + one `-- @metric` block + `)`,
and a closing SELECT that picks the rows of the chosen comparison:

  <@common of sql/mysql/ai_impact_parity.sql>, metric AS (<@metric>) SELECT * FROM metric WHERE <rows of the comparison> ORDER BY <order>

Inputs : sql/mysql/ai_impact_parity.sql, sql/mysql/agent_review_burden.sql, optional --custom-tools FILE (json, see docs/dashboard.md).
Output : dashboards/json/ai-impact.json (uid ai-impact-pr, "timezone": "utc", time range now-90d .. now). The same input gives the same bytes.
         The file in the repo is built WITHOUT --custom-tools.
--check: builds in memory and compares with the file; exit 1 when they differ (give the same --custom-tools that the file was built with).

The dashboard variables: repo_id (query, as in DevLake's own dashboards), comparison, tools, modes, include_own_markers, first_reaction (custom,
every one with "allowCustomValue": false). There is no variable in which a person types text (ADR 0004). The text variables are used in the
SQL only as ${name:sqlstring}.

Custom AI tools (--custom-tools FILE):
  {"tools": [{"name": "acme", "rows": [{"field": "pr_author", "pattern": "^acme-agent\\\\[bot\\\\]$"}]}],
   "remove": [{"tool": "cursor", "field": "commit_author_email"}]}
  field is one of pr_author, commit_author_name, commit_author_email (-> cloud agent), coauthor (-> AI-assisted), review_author (-> review agent):
  the mode is decided by the field, not written. `remove` takes a built-in row out by (tool, field). The checks are in check_custom_tools().

Standard library only (the docker CLI too, but only to check the regular expressions of --custom-tools on a throw-away MySQL).
Exit code 0 = done / equal; 1 = --check found a difference; 2 = a bad input.

Usage:
  python tools/build_dashboard.py                      write dashboards/json/ai-impact.json
  python tools/build_dashboard.py --check              compare it with the SQL files
  python tools/build_dashboard.py --custom-tools my.json --out my-dashboard.json
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ai_impact_sql  # noqa: E402
from run_on_devlake import split_blocks  # noqa: E402  (the same marker lines as tests/run_u1.py)

UID = "ai-impact-pr"
TITLE = "AI 利用別の PR 指標（レビュー負荷）"
DATASOURCE = {"type": "mysql", "uid": "devlake-mysql-api"}   # https://github.com/apache/devlake/blob/v1.0.3-beta18/grafana/scripts/entrypoint.sh, line 176
DEFAULT_OUT = ROOT / "dashboards" / "json" / "ai-impact.json"
PARITY_SQL = ROOT / "sql" / "mysql" / "ai_impact_parity.sql"
U1_SQL = ROOT / "sql" / "mysql" / "agent_review_burden.sql"
MYSQL_IMAGE = "mysql:8.4"

# ------------------------------------------------------------------ the rows of each comparison (SPEC section 4-3, ADR 0004)
Q = "${comparison:sqlstring}"
MODE_KEYS = "'mode:cloud_agent', 'mode:ai_assisted', 'mode:review_agent', 'mode:everything_else'"
# a table of periods (Time to first review, Time in review, Cycle time, Batch size, PRs merged)
COND_PERIOD = (
    "(%s = 'tools' AND grp LIKE 'tool:%%' AND grp NOT LIKE '%%|%%')\n"
    "   OR (%s = 'modes' AND grp IN (%s))\n"
    "   OR (%s = 'ai_used' AND grp IN ('mode:ai_used', 'mode:everything_else'))" % (Q, Q, MODE_KEYS, Q))
# PRs merged per week: the rows tool:<name>|week:<yw> by tool; the rows week:<yw> (with the columns of the modes) by mode and by ai_used
COND_WEEK = (
    "(%s = 'tools' AND grp LIKE 'tool:%%|week:%%')\n"
    "   OR (%s IN ('modes', 'ai_used') AND grp LIKE 'week:%%')" % (Q, Q))
# the outcome of the cloud agent PRs: one row per tool, or the one row of the mode
COND_OUTCOME = (
    "(%s = 'tools' AND grp LIKE 'mode:cloud_agent|tool:%%')\n"
    "   OR (%s IN ('modes', 'ai_used') AND grp = 'mode:cloud_agent')" % (Q, Q))

MIN = {"unit": "m", "decimals": 1}
INT = {"decimals": 0}
RATIO = {"unit": "percentunit", "decimals": 1}
NUM = {"decimals": 1}

# (panel id, title, SQL file key, metric, rows condition, order, columns [(field, display name, format)], hidden fields, width, height)
PARITY_PANELS = [
    (11, "PR のマージ数（PRs merged）", "parity", "throughput", COND_PERIOD, "grp",
     [("grp", "群", {}), ("merged", "マージした PR 数", INT)],
     ["merged_cloud_agent", "merged_ai_assisted", "merged_review_agent", "merged_ai_used", "merged_everything_else"], 12, 9),
    (12, "サイクルタイム（Cycle time）", "parity", "pr_cycle_time", COND_PERIOD, "grp",
     [("grp", "群", {}), ("n", "PR 数", INT), ("mean_minutes", "平均", MIN), ("median_minutes", "中央値", MIN)], [], 12, 9),
    (13, "最初のレビューまでの時間（Time to first review）　最初の反応の数え方: ${first_reaction}", "parity", "time_to_first_review",
     COND_PERIOD, "grp",
     [("grp", "群", {}), ("prs", "開いた PR 数", INT), ("n_defined", "値のある PR 数", INT), ("mean_minutes", "平均", MIN),
      ("median_minutes", "中央値", MIN)], [], 12, 9),
    (14, "レビューの時間（Time in review）", "parity", "time_in_review", COND_PERIOD, "grp",
     [("grp", "群", {}), ("n", "PR 数", INT), ("mean_minutes", "平均", MIN), ("median_minutes", "中央値", MIN)], [], 12, 9),
    (15, "PR の大きさ（Batch size）", "parity", "batch_size", COND_PERIOD, "grp",
     [("grp", "群", {}), ("prs", "PR 数", INT), ("mean_size", "平均（行）", NUM), ("median_size", "中央値（行）", NUM),
      ("share_lt200", "200 行未満", RATIO), ("share_200_499", "200〜499 行", RATIO), ("share_ge500", "500 行以上", RATIO)], [], 12, 9),
    (16, "週ごとの PR のマージ数（PRs merged per week）", "parity", "throughput", COND_WEEK, "grp",
     [("grp", "群（週は ISO 週、月曜始まり）", {}), ("merged", "マージした PR 数", INT),
      ("merged_cloud_agent", "cloud agent", INT), ("merged_ai_assisted", "AI-assisted", INT), ("merged_review_agent", "review agent", INT),
      ("merged_ai_used", "AI を使った", INT), ("merged_everything_else", "それ以外", INT)], [], 12, 9),
    (17, "cloud agent の PR の結末（Cloud agent outcomes）", "parity", "cloud_agent_outcomes", COND_OUTCOME, "grp",
     [("grp", "群", {}), ("prs", "開いた PR 数", INT), ("merged", "マージ", INT), ("closed", "閉じた", INT), ("open", "開いたまま", INT)],
     [], 12, 9),
]
U1_PANELS = [
    (21, "レビューの件数（U1 ② review burden）", "u1", "m2_review_burden", None, "sort_no",
     [("agent", "群", {}), ("pr_count", "PR 数", INT), ("median_comments", "コメント数の中央値", NUM),
      ("median_comments_excl_bots", "bot を除いた中央値", NUM)], ["sort_no"], 8, 9),
    (22, "差し戻しの割合（U1 ③ changes requested）", "u1", "m3_changes_requested", None, "sort_no",
     [("agent", "群", {}), ("pr_count", "PR 数", INT), ("changes_requested_prs", "差し戻しの PR 数", INT),
      ("changes_requested_ratio", "割合", RATIO)], ["sort_no"], 8, 9),
    (23, "最初の人の反応（U1 ① first human reaction）", "u1", "m1_first_human_reaction", None, "sort_no",
     [("agent", "群", {}), ("pr_count", "PR 数", INT), ("reacted", "反応のあった PR 数", INT), ("median_minutes", "中央値", MIN),
      ("reacted_excl_assignee", "担当者を除く PR 数", INT), ("median_minutes_excl_assignee", "担当者を除く中央値", MIN)],
     ["sort_no"], 8, 9),
]
DIAG_PANEL = (31, "データの確かめ（diagnostics）", "parity", "diagnostics", None, "grp",
              [("grp", "確かめる項目", {}), ("value", "値", INT)], [], 24, 6)

# The screen shows the values at once: the first row is the tables, open; the explanation is the last row, closed (the owner's rule).
# Order and size of the tables of the first row: the three most used side by side in the first screen (a 1280 x 800 window shows about 16 grid
# units under the variables), then the others. (width, height) in Grafana grid units, 24 units wide.
AI_ORDER = [11, 13, 12, 14, 15, 16, 17]
SIZE = {11: (8, 8), 13: (8, 8), 12: (8, 8), 14: (8, 8), 15: (16, 8), 16: (12, 9), 17: (12, 9)}
DESCRIPTIONS = {
    11: "期間内にマージした PR の数。1 本の PR が複数の群に数えられることがあります。",
    12: "最初の commit か PR を開いた時の早い方から、マージまでの時間（分）。マージした PR だけ。",
    13: "PR を開いてから、最初の人の反応までの時間（分）。何を反応と数えるかは上の「最初の反応の数え方」で選びます。bot と PR の作者は数えません。",
    14: "PR を開いてから、最後の承認（承認が無ければマージ）までの時間（分）。マージした PR だけ。",
    15: "PR の大きさ（追加した行 + 消した行）の平均と中央値、200 行未満・200〜499 行・500 行以上の割合。",
    16: "マージした PR の数を ISO 週（月曜始まり）ごとに。AI ツール別は群ごと、使い方別は使い方の列。",
    17: "cloud agent が作った PR の結末（マージ・閉じた・開いたまま）。AI ツール別はツールごと。",
    21: "群ごとの、PR 1 本あたりのコメント数の中央値（全部と bot を除いた分）。上の選択では変わりません。",
    22: "群ごとの、差し戻し（changes requested）のレビューがあった PR の割合。上の選択では変わりません。",
    23: "PR を開いてから最初の人の反応（コメントを含む）までの分。上の選択では変わりません。",
    31: "データの穴の確かめ: commit の本文が読めなかった PR の数、本文を GitHub の表から読んだ PR の数、ツールの群の重なりの数。",
}
ROW_AI = "AI 利用別の PR 指標"
ROW_OWN = "この repo 独自の指標"
ROW_DIAG = "データの確かめ"
ROW_GUIDE = "この画面の読み方"

INTRO = """**この画面で見られるもの**
DevLake に取り込んだ GitHub の PR を、AI ツール別・使い方別に比べます。指標は 5 つです: PR のマージ数（PRs merged）、サイクルタイム（Cycle time）、最初のレビューまでの時間（Time to first review）、レビューの時間（Time in review）、PR の大きさ（Batch size）。時間は分で、時刻は UTC です。

**上の選択**
- **比べ方（comparison）**: 「AI ツール別」は各ツールとそれ以外、「使い方別」は cloud agent・AI-assisted・review agent とそれ以外、「AI を使ったか」は AI を使った PR とそれ以外を並べます。どの比べ方でも画面の作りは同じです。
- **含めるツール（tools）・含める使い方（modes）**: 比べる対象を選びます。
- **独自の印（include_own_markers）**: 「標準の見分け方だけ」は commit の作者・共作者・Made-with の行・cloud agent の作者・review agent のレビューだけを見ます。「この repo 独自の見分け方も使う」は、この repo 独自の 2 つの印（branch 名の先頭、PR の本文の Co-Authored-By）も足します。
- **最初の反応の数え方（first_reaction）**: 「レビューだけ」は最初の人のレビュー、「コメントも」は最初の人のレビュー・コメント・行コメントで、Time to first review の終わりを決めます。Time in review と Cycle time は変わりません。

**読み方の注意**
- 1 本の PR は、複数のツール・複数の使い方に数えられることがあります。群の合計は PR の数より多くなることがあります。
- 判定は確度の高い物だけです。確度の低い判定は入れていません。
- 含めないツールの PR は、他に含めたツールの印が無ければ「それ以外」に入ります（母数から除きません）。
- 「この repo 独自の指標」の 3 つの表（U1）は、上の選択（比べ方・ツール・使い方・独自の印・最初の反応の数え方）では変わりません。Repo と時間の範囲だけで変わります。
- 人の名前や login はこの画面に出しません。
- 定義と、原文で決まらない所の決め方は ADR 0002（D16・D17 が最初の反応と外したツールの PR）、画面の作りは ADR 0004 に書いてあります。"""


# ------------------------------------------------------------------ custom tools
class ConfigError(Exception):
    """The custom tools file is wrong (exit code 2)."""


BAD_PATTERN_PARTS = ("'", "--", "[[", ";")
VAR_LIKE = re.compile(r"\$[A-Za-z_{]")


def check_custom_tools(cfg, common, regex_checker):
    """Checks the custom tools config against the identities list of `common`. Returns (remove, add_rows):
    remove = [(tool, field)], add_rows = [(tool, mode, field, pattern as written in the SQL)]. Raises ConfigError.
    regex_checker(list of patterns as written in the SQL) returns a list of error texts (empty = every pattern is a regular expression)."""
    if not isinstance(cfg, dict) or set(cfg) - {"tools", "remove"}:
        raise ConfigError('the file must be a json object with the keys "tools" and "remove" only')
    tools, remove = cfg.get("tools", []), cfg.get("remove", [])
    if not isinstance(tools, list) or not isinstance(remove, list):
        raise ConfigError('"tools" and "remove" must be lists')
    built_in = ai_impact_sql.identity_rows(common)
    builtin_names = set(t for t, _m, _f, _p in built_in) | set(ai_impact_sql.MARK_TOOLS) | {"everything_else"}

    removed = []
    for r in remove:
        if not isinstance(r, dict) or set(r) != {"tool", "field"} or not all(isinstance(v, str) for v in r.values()):
            raise ConfigError('each "remove" entry must be {"tool": "...", "field": "..."}')
        key = (r["tool"], r["field"])
        if not any((t, f) == key for t, _m, f, _p in built_in):
            raise ConfigError("remove: the identities list has no row %s / %s" % key)
        if key in removed:
            raise ConfigError("remove: %s / %s is listed twice" % key)
        removed.append(key)
    kept = [row for row in built_in if (row[0], row[2]) not in removed]
    for tool in ai_impact_sql.MARK_TOOLS:
        if not any(t == tool for t, _m, _f, _p in kept) and any(t == tool for t, _m, _f, _p in built_in):
            raise ConfigError("remove: the tool %s would have no row left, but the marks m5, x1 and x2 name it in the SQL" % tool)

    add, seen_names, seen_pairs = [], set(), {(f, p) for _t, _m, f, p in kept}
    for t in tools:
        if not isinstance(t, dict) or set(t) != {"name", "rows"} or not isinstance(t["name"], str) or not isinstance(t["rows"], list):
            raise ConfigError('each tool must be {"name": "...", "rows": [{"field": "...", "pattern": "..."}]}')
        name = t["name"]
        if not ai_impact_sql.NAME_RE.fullmatch(name):
            raise ConfigError("tool name %r: only a-z, 0-9, _ and - are allowed, 1 to 32 characters" % name[:40])
        if name in builtin_names:
            raise ConfigError("tool name %r is the name of a built-in tool (or reserved)" % name)
        if name in seen_names:
            raise ConfigError("tool name %r is listed twice" % name)
        seen_names.add(name)
        if not t["rows"]:
            raise ConfigError("tool %r has no rows" % name)
        for row in t["rows"]:
            if not isinstance(row, dict) or set(row) != {"field", "pattern"} or not all(isinstance(v, str) for v in row.values()):
                raise ConfigError('each row of %r must be {"field": "...", "pattern": "..."}' % name)
            field, pattern = row["field"], row["pattern"]
            if field not in ai_impact_sql.FIELD_MODE:
                raise ConfigError("tool %r: field %r is not one of %s" % (name, field, ", ".join(sorted(ai_impact_sql.FIELD_MODE))))
            if pattern == "" or pattern != pattern.lower():
                raise ConfigError("tool %r: the pattern must not be empty and must be lower case (every match is made on LOWER(text))" % name)
            if any(ord(c) < 32 or ord(c) == 127 for c in pattern):
                raise ConfigError("tool %r: the pattern has a control character" % name)
            bad = [p for p in BAD_PATTERN_PARTS if p in pattern]
            if bad or VAR_LIKE.search(pattern):
                raise ConfigError("tool %r: the pattern must not contain %s (the pattern is written inside a SQL string, on one line; a $ followed by a "
                                  "letter, _ or { is taken for a Grafana variable)" % (name, " ".join(bad + (["$<letter>"] if VAR_LIKE.search(pattern) else []))))
            if field == "coauthor" and pattern.startswith("^"):
                raise ConfigError("tool %r: a coauthor pattern must not start with ^ (the SQL puts it after `^co-authored-by:` and wraps it in a group, "
                                  "so write only the name, for example claude\\b or acme|acme-bot)" % name)
            sql_pat = ai_impact_sql.sql_pattern(pattern)
            if (field, sql_pat) in seen_pairs:
                raise ConfigError("tool %r: the row %s / %r is already used by another tool (or twice): an author belongs to one tool" % (name, field, pattern))
            seen_pairs.add((field, sql_pat))
            add.append((name, ai_impact_sql.FIELD_MODE[field], field, sql_pat))
    errors = regex_checker([r[3] for r in add]) if add else []
    if errors:
        raise ConfigError("not a regular expression for MySQL: " + "; ".join(errors))
    return removed, add


def apply_custom_tools(common, cfg, regex_checker):
    """The @common text with the config applied (the text is returned unchanged when the config changes nothing)."""
    if not cfg or (not cfg.get("tools") and not cfg.get("remove")):
        return common
    removed, add = check_custom_tools(cfg, common, regex_checker)
    return ai_impact_sql.rewrite_identities(common, removed, add)


def mysql_regex_checker(image=MYSQL_IMAGE):
    """A regex_checker that asks a throw-away MySQL container: SELECT REGEXP_LIKE('', pattern) for every pattern."""
    def check(patterns):
        name = "u5-regex-" + uuid.uuid4().hex[:8]
        password = uuid.uuid4().hex

        def docker(*args, stdin=None):
            return subprocess.run(["docker", *args], input=stdin, capture_output=True, timeout=600)
        if docker("info").returncode != 0:
            raise ConfigError("Docker is not running: the patterns cannot be checked (they are checked on a throw-away MySQL container)")
        try:
            r = docker("run", "-d", "--name", name, "-e", "MYSQL_ROOT_PASSWORD=" + password, image,
                       "--character-set-server=utf8mb4", "--collation-server=utf8mb4_bin")
            if r.returncode != 0:
                raise ConfigError("cannot start %s: %s" % (image, r.stderr.decode("utf-8", "replace").strip()[:200]))
            for _ in range(120):
                if docker("exec", name, "mysqladmin", "-uroot", "-p" + password, "-h127.0.0.1", "ping").returncode == 0:
                    break
                time.sleep(1)
            else:
                raise ConfigError("MySQL did not become ready in 120 s")
            errors = []
            for p in patterns:
                sql = "SELECT REGEXP_LIKE('', '%s');" % p
                r = docker("exec", "-i", name, "mysql", "-uroot", "-p" + password, "--batch", "--raw", stdin=sql.encode("utf-8"))
                if r.returncode != 0:
                    msg = [l for l in r.stderr.decode("utf-8", "replace").splitlines() if "Using a password" not in l]
                    errors.append("%r: %s" % (p, (msg[0] if msg else "error")[:160]))
            return errors
        finally:
            docker("rm", "-f", name)
    return check


# ------------------------------------------------------------------ the dashboard
def panel_sql(common, metric, where, order, sort_column=False):
    """@common + ", metric AS (" + @metric + ") SELECT * FROM metric WHERE ... ORDER BY ..." (the SPEC rule). U1's metrics get the column
    sort_no (their ORDER BY is on a column that they do not output)."""
    text = metric.strip()
    if sort_column:
        text, n = re.subn(r"(?m)^SELECT\n  g\.agent,\n", "SELECT\n  g.agent,\n  g.sort_no AS sort_no,\n", text, count=1)
        if n != 1:
            raise RuntimeError("a U1 metric does not start with SELECT g.agent: sort_no cannot be added")
    sql = common.rstrip() + ", metric AS (\n" + text + "\n)\nSELECT * FROM metric"
    if where:
        sql += "\nWHERE " + where
    return sql + "\nORDER BY " + order


def table_panel(spec, sqls, x, y):
    pid, title, _src, _metric, _cond, _order, columns, hidden, w, h = spec
    w, h = SIZE.get(pid, (w, h))
    overrides = []
    for field, display, fmt in columns:
        props = [{"id": "displayName", "value": display}]
        if "unit" in fmt:
            props.append({"id": "unit", "value": fmt["unit"]})
        if "decimals" in fmt:
            props.append({"id": "decimals", "value": fmt["decimals"]})
        overrides.append({"matcher": {"id": "byName", "options": field}, "properties": props})
    panel = {
        "datasource": dict(DATASOURCE),
        "fieldConfig": {
            "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "inspect": False}, "mappings": [],
                         "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}},
            "overrides": overrides,
        },
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": pid,
        "options": {"cellHeight": "sm", "footer": {"countRows": False, "fields": "", "reducer": ["sum"], "show": False}, "showHeader": True},
        "targets": [{"datasource": dict(DATASOURCE), "editorMode": "code", "format": "table", "rawQuery": True,
                     "rawSql": sqls[pid], "refId": "A"}],
        "title": title,
        "type": "table",
    }
    if pid in DESCRIPTIONS:
        panel["description"] = DESCRIPTIONS[pid]
    if hidden:
        panel["transformations"] = [{"id": "organize", "options": {"excludeByName": {f: True for f in hidden}, "indexByName": {}, "renameByName": {}}}]
    return panel


def layout(specs, sqls, y):
    """Places the panels left to right, 24 columns wide. Returns (panels, next y)."""
    panels, x, row_h = [], 0, 0
    for spec in specs:
        w, h = SIZE.get(spec[0], (spec[8], spec[9]))
        if x + w > 24:
            y, x, row_h = y + row_h, 0, 0
        panels.append(table_panel(spec, sqls, x, y))
        x += w
        row_h = max(row_h, h)
    return panels, y + row_h


def row_panel(pid, title, y, collapsed=False, panels=None):
    return {"collapsed": collapsed, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": pid, "panels": panels or [], "title": title, "type": "row"}


def custom_variable(name, label, pairs, current, multi_all=False, description=""):
    """pairs = [(text, value)]. A custom variable; allowCustomValue is false (a person cannot add a value)."""
    options = []
    if multi_all:
        options.append({"selected": True, "text": "All", "value": "$__all"})
    for text, value in pairs:
        options.append({"selected": (not multi_all) and value == current, "text": text, "value": value})
    var = {
        "allowCustomValue": False,
        "current": ({"selected": True, "text": ["All"], "value": ["$__all"]} if multi_all
                    else {"selected": False, "text": [t for t, v in pairs if v == current][0], "value": current}),
        "description": description,
        "hide": 0,
        "includeAll": multi_all,
        "label": label,
        "multi": multi_all,
        "name": name,
        "options": options,
        "query": ", ".join(("%s : %s" % (t, v)) if t != v else v for t, v in pairs),
        "queryValue": "",
        "skipUrlSync": False,
        "type": "custom",
    }
    return var


def variables(tools):
    repo = {
        "allowCustomValue": False,
        "allValue": "",
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        "datasource": dict(DATASOURCE),
        "definition": "select concat(name, '--', id) as text from repos where id like 'github%'",
        "hide": 0,
        "includeAll": True,
        "label": "Repo",
        "multi": True,
        "name": "repo_id",
        "options": [],
        "query": "select concat(name, '--', id) as text from repos where id like 'github%'",
        "refresh": 1,
        "regex": "/^(?<text>.*)--(?<value>.*)$/",
        "skipUrlSync": False,
        "sort": 0,
        "type": "query",
    }
    return [
        repo,
        custom_variable("comparison", "比べ方", [("AI ツール別", "tools"), ("使い方別", "modes"), ("AI を使ったか", "ai_used")], "tools"),
        custom_variable("tools", "含めるツール", [(t, t) for t in tools], None, multi_all=True),
        custom_variable("modes", "含める使い方", [("cloud agent", "cloud"), ("AI-assisted", "assist"), ("review agent", "review")], None,
                        multi_all=True),
        custom_variable("include_own_markers", "独自の印", [("標準の見分け方だけ", "0"), ("この repo 独自の見分け方も使う", "1")], "0"),
        custom_variable("first_reaction", "最初の反応の数え方", [("レビューだけ", "review"), ("コメントも", "any")], "review"),
    ]


def build(parity_path=PARITY_SQL, u1_path=U1_SQL, custom=None, regex_checker=None):
    """The dashboard as a dict."""
    common, metrics = split_blocks(parity_path)
    common = apply_custom_tools(common, custom, regex_checker or mysql_regex_checker())
    u1_common, u1_metrics = split_blocks(u1_path)
    sources = {"parity": (common, metrics), "u1": (u1_common, u1_metrics)}
    sqls = {}
    for spec in PARITY_PANELS + U1_PANELS + [DIAG_PANEL]:
        pid, _t, src, metric, cond, order = spec[:6]
        c, m = sources[src]
        sqls[pid] = panel_sql(c, m[metric], cond, order, sort_column=(src == "u1"))
    intro = {
        "datasource": {"type": "datasource", "uid": "grafana"},
        "id": 1,
        "options": {"code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False}, "content": INTRO, "mode": "markdown"},
        "title": "この画面について",
        "type": "text",
    }
    ai = sorted(PARITY_PANELS, key=lambda s: AI_ORDER.index(s[0]))
    panels = [row_panel(2, ROW_AI, 0)]
    block, y = layout(ai, sqls, 1)
    panels += block
    panels.append(row_panel(3, ROW_OWN, y))
    block, y = layout(U1_PANELS, sqls, y + 1)
    panels += block
    diag = table_panel(DIAG_PANEL, sqls, 0, y + 1)
    panels.append(row_panel(4, ROW_DIAG, y, collapsed=True, panels=[diag]))
    intro["gridPos"] = {"h": 14, "w": 24, "x": 0, "y": y + 2}
    panels.append(row_panel(5, ROW_GUIDE, y + 1, collapsed=True, panels=[intro]))
    return {
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "datasource", "uid": "grafana"}, "enable": True, "hide": True,
                                  "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"}]},
        "description": "AI ツール別・使い方別の PR の指標。上の選択で比べ方・ツール・使い方・数え方を変えます。読み方は一番下の「この画面の読み方」。",
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": panels,
        "refresh": "",
        "schemaVersion": 39,
        "tags": ["AI impact"],
        "templating": {"list": variables(ai_impact_sql.all_tools(common))},
        "time": {"from": "now-90d", "to": "now"},
        "timepicker": {},
        "timezone": "utc",
        "title": TITLE,
        "uid": UID,
        "version": 1,
        "weekStart": "",
    }


def to_text(dashboard):
    return json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="the dashboard json (default dashboards/json/ai-impact.json)")
    ap.add_argument("--check", action="store_true", help="build in memory and compare with --out; exit 1 when they differ")
    ap.add_argument("--custom-tools", help="json file with custom AI tools (see the top of this file); give the same one to --check")
    ap.add_argument("--parity-sql", default=str(PARITY_SQL))
    ap.add_argument("--u1-sql", default=str(U1_SQL))
    a = ap.parse_args(argv)
    custom = None
    try:
        if a.custom_tools:
            try:
                custom = json.loads(Path(a.custom_tools).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise ConfigError("cannot read %s as json (%s)" % (a.custom_tools, type(e).__name__))
        text = to_text(build(Path(a.parity_sql), Path(a.u1_sql), custom))
    except ConfigError as e:
        print("STOP: %s" % e, file=sys.stderr)
        return 2
    out = Path(a.out)
    if a.check:
        try:
            have = out.read_bytes().decode("utf-8").replace("\r\n", "\n")
        except OSError:
            print("DIFFERENT: %s cannot be read" % out)
            return 1
        if have != text:
            print("DIFFERENT: %s is not what the SQL files give now (run tools/build_dashboard.py to write it again)" % out)
            return 1
        print("equal: %s is what the SQL files give now (sha256 %s)" % (out, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote %s (sha256 %s)" % (out, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
