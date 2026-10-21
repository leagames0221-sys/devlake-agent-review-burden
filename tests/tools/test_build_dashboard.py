#!/usr/bin/env python3
"""Test of tools/build_dashboard.py and tools/ai_impact_sql.py without a database (U5, ADR 0004): the built json (variables, no textbox, allowCustomValue,
time zone, titles, no person on the screen), --check, the rule of Grafana's `sqlstring`, and the checks and the rewriting of custom AI tools.
The expected values are written by hand.

Usage: python tests/tools/test_build_dashboard.py     (the last line is "N checks, M failures"; exit code 0 = no failure)
"""
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ai_impact_sql as S  # noqa: E402
import build_dashboard as B  # noqa: E402
import run_on_devlake as R  # noqa: E402

rows, bad = [], []


def check(name, got, want=True):
    rows.append(name)
    if got != want:
        bad.append("%s: got %r, want %r" % (name, got, want))


def refused(name, fn, needle=None):
    rows.append(name)
    try:
        fn()
    except (B.ConfigError, RuntimeError) as e:
        if needle and needle not in str(e):
            bad.append("%s: refused with another text: %s" % (name, e))
        return
    bad.append("%s: nothing was refused" % name)


def walk(panels):
    for p in panels:
        yield p
        yield from walk(p.get("panels", []))


dash = B.build()
text = B.to_text(dash)
parity_common, parity_metrics = R.split_blocks(ROOT / "sql" / "mysql" / "ai_impact_parity.sql")
u1_common, u1_metrics = R.split_blocks(ROOT / "sql" / "mysql" / "agent_review_burden.sql")

# ---------------------------------------------------------------- the json in the repo (V5) and the build
repo_text = (ROOT / "dashboards" / "json" / "ai-impact.json").read_bytes().decode("utf-8").replace("\r\n", "\n")
check("V5 the json in the repo is what the SQL files give now", repo_text, text)
check("the same input gives the same bytes", B.to_text(B.build()), text)
check("the json is valid utf-8 without a BOM", text.encode("utf-8")[:3] != b"\xef\xbb\xbf", True)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "d.json"
    buf = io.StringIO()
    with redirect_stdout(buf):
        check("--check: a missing file is a difference (exit 1)", B.main(["--check", "--out", str(out)]), 1)
        check("build writes the file (exit 0)", B.main(["--out", str(out)]), 0)
        check("--check: the file just built is equal (exit 0)", B.main(["--check", "--out", str(out)]), 0)
        old = json.loads(out.read_text(encoding="utf-8"))
        old["panels"][3]["targets"][0]["rawSql"] += "\n-- an older SQL"
        out.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        check("--check: an old json (one SQL differs) is a difference (exit 1)", B.main(["--check", "--out", str(out)]), 1)
        out.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        check("--check: the same text with CRLF line ends (a checkout on Windows) is equal", B.main(["--check", "--out", str(out)]), 0)
    err = io.StringIO()
    with redirect_stderr(err), redirect_stdout(buf):
        check("a custom tools file that does not exist is refused (exit 2)", B.main(["--custom-tools", str(Path(tmp) / "none.json"), "--out", str(out)]), 2)

# ---------------------------------------------------------------- the dashboard itself (V8 and the screen rules)
check("uid", dash["uid"], "ai-impact-pr")
check("time zone is utc (W14)", dash["timezone"], "utc")
check("default time range", dash["time"], {"from": "now-90d", "to": "now"})
variables = dash["templating"]["list"]
check("variable names", [v["name"] for v in variables], ["repo_id", "comparison", "tools", "modes", "include_own_markers", "first_reaction"])
check("V8 no textbox variable", [v for v in variables if v["type"] == "textbox"], [])
check("V8 every custom variable has allowCustomValue false", [v["name"] for v in variables if v["type"] == "custom" and v.get("allowCustomValue") is not False], [])
check("every variable has allowCustomValue false (the query variable too)", [v["name"] for v in variables if v.get("allowCustomValue") is not False], [])
check("no 'Custom all value' (allValue) on tools and modes", [v["name"] for v in variables if v["name"] in ("tools", "modes") and v.get("allValue")], [])
check("tools and modes are multi with All", [(v["multi"], v["includeAll"]) for v in variables if v["name"] in ("tools", "modes")], [(True, True), (True, True)])
by_name = {v["name"]: v for v in variables}
check("tools are the tools of the identities list", [o["value"] for o in by_name["tools"]["options"][1:]], S.all_tools(parity_common))
check("comparison values", [o["value"] for o in by_name["comparison"]["options"]], ["tools", "modes", "ai_used"])
check("modes values", [o["value"] for o in by_name["modes"]["options"][1:]], ["cloud", "assist", "review"])
check("include_own_markers values and default", ([o["value"] for o in by_name["include_own_markers"]["options"]], by_name["include_own_markers"]["current"]["value"]), (["0", "1"], "0"))
check("first_reaction values and default", ([o["value"] for o in by_name["first_reaction"]["options"]], by_name["first_reaction"]["current"]["value"]), (["review", "any"], "review"))
check("repo_id is DevLake's query (W13)", (by_name["repo_id"]["query"], by_name["repo_id"]["regex"], by_name["repo_id"]["multi"], by_name["repo_id"]["includeAll"]),
      ("select concat(name, '--', id) as text from repos where id like 'github%'", "/^(?<text>.*)--(?<value>.*)$/", True, True))
panels = list(walk(dash["panels"]))
# the layout: the values at once (the owner's rule); the explanation is the last row, closed. Shape of rows: DevLake's own dashboards (dl_beta18_Gitlab.json and
# dl_beta18_engineering-throughput-and-cycle-time.json: "panels" of the file, a row with "collapsed": false and "panels": [] and the panels after it at the top level, by gridPos.y;
# the type RowPanel of grafana_v13.2.2_dashboard_types.gen.ts.txt L1172-L1205: a collapsed row holds its panels in "panels")
by_y = sorted(dash["panels"], key=lambda p: (p["gridPos"]["y"], p["gridPos"]["x"]))
check("(a) the first thing in gridPos order is the row 'AI 利用別の PR 指標' and it is not collapsed", (by_y[0]["type"], by_y[0]["title"], by_y[0].get("collapsed")),
      ("row", "AI 利用別の PR 指標", False))
check("(b) no text panel is on the top level above it (the text panel is inside a closed row)", [p["title"] for p in dash["panels"] if p["type"] == "text"], [])
rows_in_order = [p for p in by_y if p["type"] == "row"]
check("the rows, in order of gridPos", [(p["title"], p["collapsed"]) for p in rows_in_order],
      [("AI 利用別の PR 指標", False), ("この repo 独自の指標", False), ("データの確かめ", True), ("この画面の読み方", True)])
check("(c) the reading-guide row is closed, is the last row and holds the text panel", (rows_in_order[-1]["title"], rows_in_order[-1]["collapsed"],
      [q["type"] for q in rows_in_order[-1]["panels"]], by_y[-1] is rows_in_order[-1]), ("この画面の読み方", True, ["text"], True))
check("the diagnostics row is closed and holds its panel", [(p["collapsed"], len(p["panels"])) for p in dash["panels"] if p["title"] == "データの確かめ"], [(True, 1)])
open_rows = [p for p in dash["panels"] if p["type"] == "row" and not p["collapsed"]]
check("an open row has no panels inside (its panels follow at the top level)", [len(p["panels"]) for p in open_rows], [0, 0])
first_tables = [p for p in dash["panels"] if p["type"] == "table" and p["gridPos"]["y"] == 1]
check("three tables side by side right under the first row, each at most 9 units high (the first screen)",
      (len(first_tables), sorted(p["gridPos"]["x"] for p in first_tables), max(p["gridPos"]["h"] for p in first_tables) <= 9), (3, [0, 8, 16], True))
check("panel ids are unique", len({p["id"] for p in panels}), len(panels))
check("panel titles are unique", len({p["title"] for p in panels}), len(panels))
check("every table panel reads DevLake's data source uid", {p["datasource"]["uid"] for p in panels if p["type"] == "table"}, {"devlake-mysql-api"})
check("the first reaction is in the title of Time to first review", ["${first_reaction}" in p["title"] for p in panels if "Time to first review" in p["title"]], [True])
check("11 table panels", sum(1 for p in panels if p["type"] == "table"), 11)
check("the dashboard and every table panel have a one-line description", (bool(dash.get("description")), [p["title"] for p in panels if p["type"] == "table" and not p.get("description")]), (True, []))
vendors = ("swarmia", "jellyfish", "linearb", "faros", "haystack", "gitclear", "waydev")
screen = json.dumps([dash["title"], dash.get("description", ""), [p["description"] for p in panels if p.get("description")], dash["panels"][-1]["panels"][0]["options"]["content"], [p["title"] for p in panels], [v["label"] for v in variables],
                     [v.get("description", "") for v in variables]], ensure_ascii=False).lower()
check("no vendor or company name in the title, the intro text, the panel titles and the variable labels", [v for v in vendors if v in screen], [])
check("no vendor or company name in the SQL of any panel (the comments of the SQL files are in it)", [v for v in vendors if v in " ".join(
    p["targets"][0]["rawSql"] for p in panels if p["type"] == "table").lower()], [])
check("the intro says the U1 panels do not change with the selections", "変わりません" in dash["panels"][-1]["panels"][0]["options"]["content"], True)
check("include_own_markers is named in words a first-time reader understands", [o["text"] for o in {v["name"]: v for v in variables}["include_own_markers"]["options"]],
      ["標準の見分け方だけ", "この repo 独自の見分け方も使う"])
intro = dash["panels"][-1]["panels"][0]["options"]["content"]
check("the intro says: high confidence only, a tool taken out, the first reaction, one PR in several groups, the ADRs",
      [w in intro for w in ("確度の高い", "含めないツール", "first_reaction", "複数のツール", "ADR 0002", "ADR 0004")], [True] * 6)
sql_all = [p["targets"][0]["rawSql"] for p in panels if p["type"] == "table"]
metric_part = [s.split(", metric AS (", 1)[1] for s in sql_all]
check("no panel selects a login or a name (the metric part of every panel)", [s[:30] for s in metric_part if re.search(r"user_name|author_name|author_login|commit_author", s)], [])
check("no panel reads the per-PR metric pr_classification", [s[:30] for s in sql_all if "One row per PR: the marks that hit" in s], [])
check("every panel SQL ends with ORDER BY grp or ORDER BY sort_no", sorted({s.rsplit("\n", 1)[1] for s in sql_all}), ["ORDER BY grp", "ORDER BY sort_no"])
check("the three U1 panels add sort_no once", [p["targets"][0]["rawSql"].count("g.sort_no AS sort_no") for p in panels if p.get("id") in (21, 22, 23)], [1, 1, 1])
check("the three U1 panels hide sort_no", [p["transformations"][0]["options"]["excludeByName"] for p in panels if p.get("id") in (21, 22, 23)], [{"sort_no": True}] * 3)
for name, mt in list(parity_metrics.items()) + list(u1_metrics.items()):
    check("the metric %s has no WITH of its own (it is put into metric AS (...))" % name, re.search(r"(?im)^\s*WITH\b", mt), None)
check("13 metric blocks in the two SQL files", len(parity_metrics) + len(u1_metrics), 13)
check("every text variable in the SQL files is ${name:sqlstring} (only ${repo_id} is bare)",
      sorted(set(re.findall(r"\$\{(?!repo_id\})(\w+)\}", (ROOT / "sql/mysql/ai_impact_parity.sql").read_text(encoding="utf-8") +
                            (ROOT / "sql/mysql/agent_review_burden.sql").read_text(encoding="utf-8")))), [])

# ---------------------------------------------------------------- Grafana's sqlstring (W15) and the bare form (W16)
check("sqlstring: the example of the Grafana page", S.sqlstring(["test'1", "test2"]), "'test''1','test2'")
check("sqlstring: one value", S.sqlstring("review"), "'review'")
check("sqlstring: only the quote is changed (W15)", S.sqlstring("a\\b"), "'a\\b'")
check("bare, one value: the quote is doubled, no quotes are added (W16 L82)", S.bare_value("a'b", multi=False), "a''b")
check("bare, multi: quoted like sqlstring (W16 L79-L80)", S.bare_value("a'b", multi=True), "'a''b'")
check("apply_variables fills sqlstring and bare", S.apply_variables("x IN (${tools:sqlstring}) AND ${include_own_markers} = 1 AND y = ${first_reaction:sqlstring}",
                                                                     {"tools": ["a", "b"], "include_own_markers": "0", "first_reaction": "any"}),
      "x IN ('a','b') AND 0 = 1 AND y = 'any'")
refused("apply_variables stops on a variable that was not given", lambda: S.apply_variables("${unknown:sqlstring}", {"tools": ["a"]}), "not replaced")

# ---------------------------------------------------------------- run_on_devlake: --var and the defaults
vs = R.parse_vars([], parity_common)
check("run_on_devlake defaults: all tools, all modes, review, tools comparison", (vs["tools"], vs["modes"], vs["first_reaction"], vs["comparison"]),
      (S.all_tools(parity_common), ["cloud", "assist", "review"], "review", "tools"))
vs = R.parse_vars(["tools=claude,cursor", "modes=assist", "first_reaction=any", "comparison=modes"], parity_common)
check("run_on_devlake --var", (vs["tools"], vs["modes"], vs["first_reaction"], vs["comparison"]), (["claude", "cursor"], ["assist"], "any", "modes"))
for bad_item in ("first_reaction=x", "tools=a'b", "modes=cloud,other", "nope=1", "tools=", "comparison=Tools"):
    try:
        R.parse_vars([bad_item], parity_common)
        bad.append("run_on_devlake --var %s was not refused" % bad_item)
    except SystemExit:
        pass
    rows.append("run_on_devlake refuses --var %s" % bad_item)
sql = R.apply_macros(parity_common, "2026-09-01 00:00:00", "2026-09-30 23:59:59", ["r:1"], 0, R.parse_vars(["tools=claude", "first_reaction=any"], parity_common))
check("run_on_devlake puts the tools and first_reaction in", ("IN ('claude')" in sql, "<> 'any'" in sql, "= 'any'" in sql, "${" in sql), (True, True, True, False))

# ---------------------------------------------------------------- custom tools: the checks (the regular expression check is made on MySQL in tests/test_dashboard.py)
ok_checker = lambda patterns: []   # noqa: E731
good = {"tools": [{"name": "acme", "rows": [{"field": "pr_author", "pattern": "^acme-agent\\[bot\\]$"},
                                              {"field": "coauthor", "pattern": "acme\\b"}]}], "remove": [{"tool": "cursor", "field": "commit_author_email"}]}
removed, added = B.check_custom_tools(good, parity_common, ok_checker)
check("good config: removed", removed, [("cursor", "commit_author_email")])
check("good config: rows, the mode comes from the field, a backslash is doubled for the SQL",
      added, [("acme", "cloud", "pr_author", "^acme-agent\\\\[bot\\\\]$"), ("acme", "assist", "coauthor", "acme\\\\b")])
new_common = B.apply_custom_tools(parity_common, good, ok_checker)
check("the rows are put after the insert point", "-- CUSTOM-TOOLS-INSERT-POINT" in new_common and
      new_common.split("CUSTOM-TOOLS-INSERT-POINT")[1].split("\n")[1:3] ==
      ["  UNION ALL SELECT 'acme', 'cloud', 'pr_author', '^acme-agent\\\\[bot\\\\]$'", "  UNION ALL SELECT 'acme', 'assist', 'coauthor', 'acme\\\\b'"], True)
check("the removed row is gone, the others stay", ("cursoragent@cursor" in new_common, "^cursor agent$" in new_common), (False, True))
check("the tools of the new list", S.all_tools(new_common), S.all_tools(parity_common) + ["acme"])
check("without a config the common text is returned unchanged", B.apply_custom_tools(parity_common, None, ok_checker), parity_common)
check("an empty config changes nothing", B.apply_custom_tools(parity_common, {"tools": [], "remove": []}, ok_checker), parity_common)
first_gone = B.apply_custom_tools(parity_common, {"remove": [{"tool": "copilot", "field": "pr_author"}]}, ok_checker)
check("removing the first row: the next row starts the list with SELECT", "AS (\n  -- tool, mode" in first_gone and
      re.search(r"\n  SELECT 'copilot', 'review', 'review_author'", first_gone) is not None and first_gone.count("UNION ALL SELECT 'copilot'") == 0, True)
check("the rest of the SQL is not touched", first_gone.split("all_groups AS (", 1)[1], parity_common.split("all_groups AS (", 1)[1])
check("the dashboard of a config has the new tool in the variable tools", [o["value"] for o in
      {v["name"]: v for v in B.build(custom=good, regex_checker=ok_checker)["templating"]["list"]}["tools"]["options"]][-1], "acme")


bad_cases = [
    ("a key that is not known", {"tool": []}, "keys"),
    ("tools is not a list", {"tools": {}}, "lists"),
    ("a built-in tool name", {"tools": [{"name": "cursor", "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "built-in"),
    ("the reserved name everything_else", {"tools": [{"name": "everything_else", "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "built-in"),
    ("a name with a capital", {"tools": [{"name": "Acme", "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "only a-z"),
    ("a name with a quote", {"tools": [{"name": "a'b", "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "only a-z"),
    ("a name of 33 characters", {"tools": [{"name": "a" * 33, "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "only a-z"),
    ("an empty name", {"tools": [{"name": "", "rows": [{"field": "pr_author", "pattern": "x"}]}]}, "only a-z"),
    ("two tools with one name", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "x"}]}, {"name": "t1", "rows": [{"field": "pr_author", "pattern": "y"}]}]}, "twice"),
    ("a tool without rows", {"tools": [{"name": "t1", "rows": []}]}, "no rows"),
    ("a field that is not known", {"tools": [{"name": "t1", "rows": [{"field": "mode", "pattern": "x"}]}]}, "field"),
    ("a mode written in a row", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "x", "mode": "cloud"}]}]}, "each row"),
    ("an upper case pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "^Acme$"}]}]}, "lower case"),
    ("an empty pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": ""}]}]}, "lower case"),
    ("a quote in the pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a'b"}]}]}, "must not contain"),
    ("two dashes in the pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a--b"}]}]}, "must not contain"),
    ("[[ in the pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "[[:alpha:]]"}]}]}, "must not contain"),
    ("a semicolon in the pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a;b"}]}]}, "must not contain"),
    ("$ and a letter (a Grafana variable)", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a$tools"}]}]}, "$<letter>"),
    ("$ and a brace (a Grafana variable)", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a${tools}"}]}]}, "$<letter>"),
    ("$ and an underscore", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a$_x"}]}]}, "$<letter>"),
    ("a line break in the pattern", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a\nb"}]}]}, "control"),
    ("the same (field, pattern) in two tools", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "x1"}]},
                                                        {"name": "t2", "rows": [{"field": "pr_author", "pattern": "x1"}]}]}, "already used"),
    ("the same (field, pattern) as a built-in row", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "^cursor\\[bot\\]$"}]}]}, "already used"),
    ("a coauthor pattern that starts with ^", {"tools": [{"name": "t1", "rows": [{"field": "coauthor", "pattern": "^acme"}]}]}, "must not start with"),
    ("an upper case escape such as \\S (the lower-case rule)", {"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "^a\\S$"}]}]}, "lower case"),
    ("remove of a row that does not exist", {"remove": [{"tool": "cursor", "field": "review_author"}]}, "no row"),
    ("remove written with other keys", {"remove": [{"tool": "cursor"}]}, "remove"),
    ("remove twice", {"remove": [{"tool": "devin", "field": "pr_author"}, {"tool": "devin", "field": "pr_author"}]}, "twice"),
    ("remove of every row of a tool that a mark names", {"remove": [{"tool": "cursor", "field": "pr_author"}, {"tool": "cursor", "field": "commit_author_name"},
                                                                  {"tool": "cursor", "field": "commit_author_email"}]}, "no row left"),
]
for label, cfg, needle in bad_cases:
    refused("custom tools refused: " + label, lambda cfg=cfg: B.check_custom_tools(cfg, parity_common, ok_checker), needle)
removed_ok = B.check_custom_tools({"remove": [{"tool": "coderabbit", "field": "pr_author"}, {"tool": "coderabbit", "field": "review_author"}]}, parity_common, ok_checker)
check("a tool that no mark names may lose all its rows", removed_ok[0], [("coderabbit", "pr_author"), ("coderabbit", "review_author")])
refused("the regular expression check of MySQL is asked and its error stops the build",
        lambda: B.check_custom_tools({"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "^("}]}]}, parity_common,
                                     lambda ps: ["%r: bad" % p for p in ps]), "not a regular expression")
asked = []
B.check_custom_tools({"tools": [{"name": "t1", "rows": [{"field": "pr_author", "pattern": "a\\.b"}]}]}, parity_common, lambda ps: asked.append(ps) or [])
check("the checker gets the pattern as it is written in the SQL (a backslash doubled)", asked, [["a\\\\.b"]])
check("every MARK_TOOLS tool has a row in the identities list", [t for t in S.MARK_TOOLS if t not in S.all_tools(parity_common)], [])
for tool in S.MARK_TOOLS:   # the tools that m5, x1 and x2 name in the SQL text
    check("the SQL names the tool %s in m5 / x1 / x2" % tool, ("'%s'" % tool) in parity_common.split("marks AS (", 1)[1].split("marks_sel AS (", 1)[0], True)

for b in bad:
    print("FAIL " + b)
print("%d checks, %d failures" % (len(rows), len(bad)))
sys.exit(1 if bad else 0)
