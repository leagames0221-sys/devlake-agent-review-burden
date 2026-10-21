#!/usr/bin/env python3
"""Helpers for the text variables of sql/mysql/ai_impact_parity.sql and for the identities list (U5, ADR 0004).
Used by tools/build_dashboard.py, tools/run_on_devlake.py, tests/run_u1.py and the tests. Standard library only.

Text variables
  The dashboard variables tools, modes, first_reaction, comparison and include_own_markers are written in the SQL as ${name:sqlstring}.
  Grafana's format option `sqlstring` "escapes ' in each value by '' and quotes each value with '" and joins several values with a
  comma (https://grafana.com/docs/grafana/latest/dashboards/variables/variable-syntax/). sqlstring() does the same, nothing more. It is a quoting rule, not a check of the value,
  which is why no variable lets a person type text (ADR 0004).
  A bare ${name} is what Grafana's MySQL data source would fill in without a format option (https://github.com/grafana/grafana/blob/v13.2.2/
  packages/grafana-sql/src/datasource/SqlDatasource.ts, lines 77-93): a multi value is quoted like sqlstring, a single value only has ' doubled and gets
  no quotes. The SQL of this repo never uses a bare text variable; bare_value() exists so that a test can show what a bare one would do.

The identities list
  The SQL file has one CTE `identities(tool, mode, field, pattern)` whose rows are one line each. rewrite_identities() removes rows
  by (tool, field) and adds rows of custom tools after the line CUSTOM-TOOLS-INSERT-POINT. Nothing else of the SQL is touched.
"""
import re

MODES = ("cloud", "assist", "review")                 # values of the dashboard variable `modes`
FIELD_MODE = {                                          # the mode a custom row gets from its field (as the built-in rows)
    "pr_author": "cloud", "commit_author_name": "cloud", "commit_author_email": "cloud",
    "coauthor": "assist", "review_author": "review",
}
# The tools that marks m5, x1 and x2 name in the SQL itself (not in identities). A built-in row removal must leave each of them at
# least one row of identities, otherwise a PR would carry a tool that has no row on the dashboard.
MARK_TOOLS = ("claude", "codex", "copilot", "cursor", "devin")
INSERT_POINT = "CUSTOM-TOOLS-INSERT-POINT"
NAME_RE = re.compile(r"[a-z0-9_-]{1,32}")

IDENTITIES_START = "WITH identities(tool, mode, field, pattern) AS (\n"
IDENTITIES_END = "\n),\nall_groups AS ("
ROW_RE = re.compile(r"^  (?:UNION ALL )?SELECT '([^']*)', '([^']*)', '([^']*)', '(.*?)'(\s*(?:--.*)?)$")


def sqlstring(value):
    """Grafana's `sqlstring` format of a value or a list of values."""
    values = [value] if isinstance(value, str) else list(value)
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


def bare_value(value, multi):
    """What the MySQL data source puts in for a variable without a format option (see the module text)."""
    if multi or not isinstance(value, str):
        return sqlstring(value)
    return value.replace("'", "''")


def apply_variables(text, variables, multi=("tools", "modes", "repo_id")):
    """Replaces ${name:sqlstring} and a bare ${name} for every name in `variables` (value: a string or a list of strings).
    Raises RuntimeError when a ${...} is left."""
    def fill(m):
        name, fmt = m.group(1), m.group(2) or ""
        if name not in variables or variables[name] is None:
            return m.group(0)
        if fmt == ":sqlstring":
            return sqlstring(variables[name])
        if fmt == "":
            return bare_value(variables[name], name in multi)
        return m.group(0)
    text = re.sub(r"\$\{(\w+)(:\w+)?\}", fill, text)
    if "${" in text:
        raise RuntimeError("a Grafana variable was not replaced: " + text[text.index("${"):][:40])
    return text


def split_list(value):
    """'a,b' -> ['a', 'b'] (the form of --var tools=a,b)."""
    return [v for v in value.split(",") if v != ""]


# ------------------------------------------------------------------ the identities list
def _block(common):
    i = common.find(IDENTITIES_START)
    j = common.find(IDENTITIES_END)
    if i < 0 or j < 0 or j < i:
        raise RuntimeError("the @common block has no identities list in the expected form")
    return i + len(IDENTITIES_START), j


def identity_rows(common):
    """[(tool, mode, field, pattern)] in the order of the file (the pattern as written in the SQL: a backslash is doubled)."""
    a, b = _block(common)
    rows = []
    for line in common[a:b].split("\n"):
        m = ROW_RE.match(line)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return rows


def all_tools(common):
    """The tools of the identities list, each once, in the order of the file."""
    seen = []
    for tool, _m, _f, _p in identity_rows(common):
        if tool not in seen:
            seen.append(tool)
    return seen


def sql_pattern(pattern):
    """The text of a pattern as it is written in the SQL file: a backslash is doubled (the first level is MySQL's string escape)."""
    return pattern.replace("\\", "\\\\")


def rewrite_identities(common, remove=(), add_rows=()):
    """Returns the common text with the rows (tool, field) of `remove` taken out and the rows `add_rows` (tool, mode, field, sql_pattern)
    put after the insert-point line. Raises RuntimeError when a removal matches no row, or when the result has no row at all."""
    a, b = _block(common)
    lines = common[a:b].split("\n")
    point = [k for k, line in enumerate(lines) if INSERT_POINT in line]
    if len(point) != 1:
        raise RuntimeError("the identities list must have exactly one line with %s" % INSERT_POINT)
    left = {(t, f) for t, f in remove}
    hit = set()
    out = []
    for k, line in enumerate(lines):
        m = ROW_RE.match(line)
        if m:
            key = (m.group(1), m.group(3))
            if key in left:
                hit.add(key)
                continue
            out.append(("row", m.groups()))
        else:
            out.append(("text", line))
        if k == point[0]:
            for t, mode, f, pat in add_rows:
                out.append(("row", (t, mode, f, pat, "")))
    if hit != left:
        raise RuntimeError("remove: no built-in row for %s" % ", ".join("%s/%s" % x for x in sorted(left - hit)))
    rebuilt, first = [], True
    for kind, v in out:
        if kind == "text":
            rebuilt.append(v)
        else:
            lead = "  SELECT " if first else "  UNION ALL SELECT "
            first = False
            rebuilt.append("%s'%s', '%s', '%s', '%s'%s" % (lead, v[0], v[1], v[2], v[3], v[4]))
    if first:
        raise RuntimeError("the identities list would have no row")
    return common[:a] + "\n".join(rebuilt) + common[b:]
