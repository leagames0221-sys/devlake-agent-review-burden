# The Grafana screen: `tools/build_dashboard.py` and `tools/grafana_install.py` (U5)

The SQL of this repo (ADR 0002) gives AI-impact numbers per AI tool and per way of use. This page is about the screen that shows them in the
Grafana of a local DevLake, how it is built from the SQL, how it is put into Grafana, and how a company changes it. The decisions and the sources are
in `docs/adr/0004-grafana-dashboard.md`.

## What the screen shows

One dashboard, uid `ai-impact-pr`, title "AI 利用別の PR 指標（レビュー負荷）", in a folder `AI impact`. The time zone is UTC and the default range is the
last 90 days. Panel titles and column names are in Japanese, the English name of a metric is in brackets.

| Row | Panels |
|---|---|
| AI 利用別の PR 指標 (open, the first thing on the screen) | PRs merged, Time to first review, Cycle time side by side; then Time in review, Batch size, PRs merged per week, Cloud agent outcomes |
| この repo 独自の指標 | the three review-burden metrics of U1 (review count, changes-requested share, first human reaction) |
| データの確かめ (closed) | the check values of the SQL (`diagnostics`) |
| この画面の読み方 (closed, last) | the text: what the screen is, how to read the selections, the cautions. Every table also has a one-line description (the i icon) |

The selections at the top (Grafana variables):

| Variable | Values | Does |
|---|---|---|
| Repo (`repo_id`) | the repos of DevLake (`id like 'github%'`), several, All | as in DevLake's own dashboards |
| 比べ方 (`comparison`) | AI ツール別 / 使い方別 / AI を使ったか | which rows the tables show: each tool vs everything else; cloud agent, AI-assisted, review agent vs everything else; AI used vs everything else. The layout is the same for all three |
| 含めるツール (`tools`) | the tools of the identities list, several, All | the tools that are in the comparison. A PR whose only marks are of a tool that is out falls to "everything else" (ADR 0002 D17) |
| 含める使い方 (`modes`) | cloud agent / AI-assisted / review agent, several, All | the modes that are in the comparison (the mode comes from the mark: ADR 0004) |
| 独自の印 (`include_own_markers`) | 標準の見分け方だけ (0) / この repo 独自の見分け方も使う (1) | also use the two markers of this repo: the branch prefix and `Co-Authored-By: Claude` in the PR body |
| 最初の反応の数え方 (`first_reaction`) | レビューだけ (`review`) / コメントも (`any`) | what ends Time to first review: the first review of a person, or the first review, comment or line comment of a person (ADR 0002 D16) |

The three review-burden panels of U1 do not change with these selections (only with Repo and the time range). With a non-default selection, `pr_classification` and the `diagnostics` check `tool_group_total_minus_pr_total` follow the selection too; the rows of a tool that is taken out are not shown, but the rows of the modes stay (with 0 PRs) in the "使い方別" comparison (ADR 0002 D17).

Only the marks of high confidence are used; there is no switch for the low-confidence marks. A PR can be in several tools and several modes. The screen shows no
login and no name of a person. No variable lets a person type text (ADR 0004).

## Build the json: `tools/build_dashboard.py`

```
python tools/build_dashboard.py                  # writes dashboards/json/ai-impact.json
python tools/build_dashboard.py --check          # exit 1 when the file is not what the SQL files give now
```

The SQL of every panel is `@common` of a SQL file, `, metric AS (` and one `@metric` block, `)`, and `SELECT * FROM metric WHERE <the rows of the comparison> ORDER BY ...`.
Nothing is typed by hand, so a panel runs the SQL that the tests ran. The same input gives the same bytes. After a change in `sql/mysql/*.sql` run the build, commit the json,
and `--check` (and `tests/tools/test_build_dashboard.py`) stay green. The file in the repo is built without custom tools.

### Rows of the comparisons

| Table | tools | modes | ai_used |
|---|---|---|---|
| the five period tables | `tool:<name>` (without `|`) | `mode:cloud_agent`, `mode:ai_assisted`, `mode:review_agent`, `mode:everything_else` | `mode:ai_used`, `mode:everything_else` |
| PRs merged per week | `tool:<name>\|week:<yw>` | `week:<yw>` (with the columns of the modes) | the same |
| Cloud agent outcomes | `mode:cloud_agent\|tool:<name>` | `mode:cloud_agent` | `mode:cloud_agent` |
| U1's three, diagnostics | all rows | all rows | all rows |

### Add or remove AI tools of a company (`--custom-tools`)

The list of tools and the way they are recognised is one CTE, `identities(tool, mode, field, pattern)`, at the start of `sql/mysql/ai_impact_parity.sql` (`docs/agent_identities.md`).
A company does not edit the SQL file: it writes a json file and builds its own dashboard.

```json
{"tools": [{"name": "acme", "rows": [{"field": "pr_author", "pattern": "^acme-agent\\[bot\\]$"},
                                       {"field": "coauthor", "pattern": "acme\\b"}]}],
 "remove": [{"tool": "cursor", "field": "commit_author_email"}]}
```

```
python tools/build_dashboard.py --custom-tools acme.json --out acme-dashboard.json
python tools/build_dashboard.py --custom-tools acme.json --out acme-dashboard.json --check
```

- `field` is `pr_author`, `commit_author_name`, `commit_author_email` (these give the mode **cloud agent**), `coauthor` (**AI-assisted**) or `review_author` (**review agent**).
  The mode is not written: the field decides, as for the built-in rows.
- `pattern` is a regular expression for MySQL (`REGEXP_LIKE`), written in lower case (so escapes such as `\S`, `\W`, `\D`, `\B` are refused; use the lower-case forms `\s`, `\w`, `\d`, `\b`): every match is made on `LOWER(text)`. Logins and names are anchored with `^...$`;
  a literal `[bot]` is `\\[bot\\]` in the json (one backslash in the pattern, as in the example).
- `name`: `a-z`, `0-9`, `_`, `-`, 1 to 32 characters; not the name of a built-in tool and not `everything_else`.
- Refused with a message: a pattern that is not lower case, or has `'`, `--`, `[[`, `;`, a control character, or a `$` followed by a letter, `_` or `{` (Grafana would take it for a variable);
  a `(field, pattern)` that another tool already has (an author belongs to one tool, as in the source); a `remove` that matches no built-in row; a `remove` that takes the last row of
  `claude`, `codex`, `copilot`, `cursor` or `devin` (the marks `m5`, `x1`, `x2` name them in the SQL).
- A `coauthor` pattern is only the name after `Co-authored-by:` (the SQL puts `^co-authored-by:[ \t]*(?:` before it and `)` after it): write `claude\\b` or `acme|acme-bot`; a pattern that starts with `^` is refused.
- A pattern is checked with `REGEXP_LIKE('', pattern)` on a throw-away MySQL container, so Docker must run when `--custom-tools` is used.
- `remove` takes a built-in row out by `(tool, field)`. It does not touch the marks `m5`, `x1`, `x2`.
- A difference to the paid service: it links an author by GitHub username; here a row is a regular expression on the login, the git name, the git e-mail or the trailer (ADR 0004).

## Put it into Grafana: `tools/grafana_install.py`

Needs: DevLake running from its compose file (`docker-compose.yml` with the service `grafana`), Docker, nothing else. No password is typed or read.

```
python tools/grafana_install.py plan   --compose-dir <compose-folder>   [--custom-tools acme.json]
python tools/grafana_install.py apply  --compose-dir <compose-folder>
python tools/grafana_install.py status --compose-dir <compose-folder> --wait 120
```

- **plan** changes nothing. It checks the folder, the repo files and the override file, and prints the override file that `apply` would write and what recreating the container does.
- **apply** writes `docker-compose.override.yml` next to `docker-compose.yml` (two read-only bind mounts of the `grafana` service, long syntax, `create_host_path: false`) and runs
  `docker compose up -d --no-deps --force-recreate grafana` (since U6 with `--force-recreate`, so that the container reads the files again every time). An override file that already has other content is not overwritten (the command stops).
- **status** changes nothing and passes only if all five checks are true: both mounts are in the container, as bind mounts, read-only (2 checks); the sha256 of `/etc/grafana/ai-impact/ai-impact.json` in the container is the sha256 of the repo file (this proves the mount only);
  since the container was started the log has `finished to provision dashboards` from logger `provisioning.dashboard` (one line for all providers); and the log has no line of logger `provisioning` at level `warn` or `error` that contains `ai-impact`
  (this covers `ai-impact-pr` and a duplicates warning that names the provider `ai-impact`). **It does not prove that the uid is in Grafana's database**; the screen shows that.
  If a mount is missing, Docker Compose did not read the override file; the script says so and stops. It does not try another file name.

What recreating the `grafana` container does: only that container is recreated (`--no-deps`; mysql, devlake and config-ui keep running; the volumes stay). When it starts, the start script of DevLake's Grafana image **tries** to delete the data sources
of Grafana and to create its own (uid `devlake-mysql-api`). On the Grafana 13.2.2 of this DevLake the delete by id answered 404 and the create answered 409 (log lines of 2026-10-21; ADR 0004, Appendix B, V6),
so the data source that is already there is kept.

The dashboard comes from a provider file of its own (`dashboards/provisioning/ai-impact.yml`), not from DevLake's: DevLake's file is not touched, and the path is outside DevLake's
`/etc/grafana/dashboards`, so the two never read the same json (a dashboard uid must be unique).

**A custom version** (built with `--custom-tools`) replaces `dashboards/json/ai-impact.json`; do not put a second file in `dashboards/json/` (the folder is mounted as it is and `plan` fails when another file there has the uid `ai-impact-pr`). Give the same `--custom-tools FILE` to `plan` and `apply`: the freshness check builds with it.

**Change the json later:** build it again, then force the container to read it: `docker compose up -d --no-deps --force-recreate grafana` in the compose folder
(the provider looks at the files every 5 seconds, but do not rely on it), and run `status`.
`apply` replaces an existing `docker-compose.override.yml` only when its first line is the header line that this script writes (plan shows the old and the new content as a diff); any other override stops it.

**Take it away:** delete `docker-compose.override.yml` in the compose folder and run `docker compose up -d --no-deps --force-recreate grafana`.

## Let Grafana read with a user who cannot write: `tools/grafana_readonly_user.py` and `--readonly-db`

Why: dashboard variable values can also come from the page URL and reach the query. Grafana's documentation says that it does not validate the safety of queries and that the database user of a data source should have only `SELECT` permissions (https://grafana.com/docs/grafana/latest/datasources/mysql/configure/). The default data source user of DevLake's Grafana (`merico`) has write rights. This part makes the user `grafana_ro`
(`SELECT` on `lake.*` and nothing else) and points the data source of Grafana at it. Why it was built this way, what was rejected, and what stays readable: ADR 0004, "A read-only database user for Grafana".

Who runs what (the compose folder is the folder of DevLake's `docker-compose.yml`; the commands are run in this repository):

1. Anyone: `python tools/grafana_readonly_user.py plan --compose-dir <compose-folder>`. It changes nothing: it shows the user, the right, the SQL (with `<password>` in place of the value) and the name of the line that is added to `.env`.
2. **The owner of DevLake** (only this step changes the database): `python tools/grafana_readonly_user.py apply --compose-dir <compose-folder>`. It uses the line `GRAFANA_DB_RO_PASSWORD` of the `.env` in the compose folder; if there is none, it makes a value (hex digits) and adds the line (a missing newline at the end of `.env` is added first),
   then creates or updates `grafana_ro` through the `mysql` container, as root (the root password is expanded inside the container). The value is never printed; a mysql error prints only `ERROR nnnn`. It can be run again: `.env` and the database keep the same password.
   **The line in `.env` is also read by the `devlake` and `config-ui` containers** (both have `env_file: ./.env`) the next time they are created. They do not use it. `.env` is not part of this repository and must not be committed.
3. Anyone: `python tools/grafana_install.py plan --compose-dir <compose-folder> --readonly-db` (changes nothing; shows the override with the third mount `dashboards/provisioning/datasources/ai-impact-ro.yml` and the `environment` lines, and the difference to the override that is there).
4. **The owner**: `python tools/grafana_install.py apply --compose-dir <compose-folder> --readonly-db`. It writes the override and runs `docker compose up -d --no-deps --force-recreate grafana`. If Docker Compose stops because the `.env` line is missing (step 2 not done), the old override is put back and the script says so.
5. Anyone: `python tools/grafana_install.py status --compose-dir <compose-folder> --wait 120 --readonly-db` (six checks: three read-only mounts, the sha256, the two log checks).
6. Open the Grafana screen once so that every panel is loaded, then: `python tools/grafana_readonly_user.py status --compose-dir <compose-folder>`. It passes only if `SHOW GRANTS FOR 'grafana_ro'@'%'` is exactly the two lines
   ``GRANT USAGE ON *.* TO `grafana_ro`@`%` `` and ``GRANT SELECT ON `lake`.* TO `grafana_ro`@`%` ``, and the processlist has, from the IP of the grafana container, one connection or more of `grafana_ro` and none of `merico`. It also prints, as a record, how many times the log of the container has the lines of DevLake's start script (`Datasource created successfully`, `already exists`, `status=409`).

- **An override that has the read-only lines is not replaced by one without them** (`plan` and `apply` both stop) unless `--drop-readonly-db` is given. So "build the json again and install again" ("Change the json later", above) needs `--readonly-db` too, and a forgotten flag cannot silently remove the read-only lines (a Grafana that is set up again, with a new volume, would then get the data source of `merico` again).
- **For a recording**, `--readonly-db --anonymous-viewer` (only together) adds `GF_AUTH_ANONYMOUS_ENABLED: "true"` and `GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer`: the screen can then be seen without a login (role Viewer). `plan` and `apply` first check that every port of the services `grafana` and `config-ui` in the compose file of the folder is published on `127.0.0.1` only, and stop otherwise
  (DevLake's own compose file publishes `3002:3000` and `4000:4000` on all interfaces, and `config-ui` proxies `/grafana`; the compose file used for U4 binds both to `127.0.0.1`). `plan` prints the warning. Afterwards run `apply` with `--readonly-db` only and check that the override has no `GF_AUTH_ANONYMOUS`,
  that the container started after the override was updated, and that a browser without a login gets the login page.
- **Take it away:** `apply` without `--readonly-db` and with `--drop-readonly-db` only removes the lines from the override; deleting the override as above removes the mounts. **Neither puts the data source back.** The data source stays `grafana_ro` with `editable: false` in Grafana's database:
  a provisioned data source is removed only by `deleteDatasources`, or by `prune: true`, in a provisioning file (the Grafana page "Provision Grafana", https://grafana.com/docs/grafana/latest/administration/provisioning/; the file of this repository sets neither), and DevLake's start script keeps an existing data source (404/409). How to put `merico` back is not covered by this repository
  and not described in the docs that were read: a person has to change the data source first, and only then drop the database user `grafana_ro`.

## Limits

- **Variable values can also come from the page URL and reach the query.** Grafana's documentation says that it does not validate the safety of queries and that the database user of a data source should have only `SELECT` permissions (https://grafana.com/docs/grafana/latest/datasources/mysql/configure/). DevLake's default data source user (`merico`) has write rights, so this repository makes Grafana use a read-only user (`grafana_readonly_user.py apply`, then `grafana_install.py apply --readonly-db`; ADR 0004, "A read-only database user for Grafana"). With `grafana_ro` (`SELECT` on `lake.*`) nothing can be written through the screen.
- **`grafana_ro` can still read every table of `lake`** (the tables of the connections, whose tokens are stored encrypted, the raw tables of the GitHub data, and the tables that hold people's logins and names). So keep the screen local, and use it only where everyone who can open it may read all of `lake`; while `--anonymous-viewer` is on (a recording), that includes people without a login. DevLake's own dashboards (`repo_id`) work the same way.
- Only the MySQL version of DevLake. PostgreSQL is not built.
- "Teams" as a way of comparing, and the low-confidence marks, are not built.

## Tests

```
python tests/tools/test_build_dashboard.py     # no database: the json, the variables, --check, custom tools, sqlstring
python tests/tools/test_grafana_install.py     # a fake docker: the override file, plan, apply, status, --readonly-db, --anonymous-viewer
python tests/tools/test_grafana_readonly_user.py   # a fake docker and fake mysql: the password never shown, the SQL, the .env line, status
python tests/test_dashboard.py                 # a throw-away MySQL: every panel on the fixtures (V1) and the variable scenes (V2)
```

Each prints `N checks, M failures` as its last line. The mutation tests are listed in ADR 0004, Appendix A.
