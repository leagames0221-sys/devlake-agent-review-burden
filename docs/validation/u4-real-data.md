# U4: the metrics on a real DevLake, against GitHub's raw data

Record of the U4 check (SPEC U4). Two public repositories were imported into a local Apache DevLake; the SQL of this repo was run on it; the same per-PR values were computed a second time, from GitHub's raw API answers, by a separate script that does not read the SQL, the tests or the DevLake database. Every number below is counted from the saved result files (the raw data stays outside the repository because it contains people's logins; no login, name, e-mail or per-PR time is written here).

## 1. Result in short

- **297 PRs compared, 253 of them with every item equal** (6988 of 7062 items equal). Times, sizes, outcomes, the period flags, U1's agent group, (1) and (1B) are equal on every PR. The 288 / 291 group values (parity / own markers) and 63 U1 group values equal too, once the 5 PRs whose group differs (section 5) are given the group DevLake gave them (section 6).
- **Two defects of the SQL were found on the real DevLake (class (a)). They are not fixed here (SPEC U4 5: stop and report).** The synthetic tests could not show them because the test data does not have the shape of the real tables:
  - **A1 (m1):** DevLake's GraphQL path stores the author of a bot's PR without `[bot]` (`pull_requests.author_name` is `cursor`, `claude`, `copilot-swe-agent`), so the pattern `^cursor\[bot\]$` of m1 never matches. 43 PRs lost the m1 mark. Where no other mark exists (4 PRs) the PR left its tool and mode group.
  - **A2 (m4, m5):** in the real DevLake `commits.message` is a `longblob` (the test schema has `LONGTEXT`). `LOWER()` does nothing on a binary string and `REGEXP_LIKE` is then case-sensitive, so the usual `Co-Authored-By: Claude` line is not found: 0 of the 9 PRs that have an m4 mark in GitHub's data are found by the SQL (5 of the 9 have no commit message in DevLake at all, class (c); 4 have the message and the SQL still misses the line).
- (a) = 43 PRs (43 with A1, 4 of these also A2), (b) = 0, (c) = 5 PRs (all on m4: no commit message in DevLake), (d) = 0. Mutant M3 (section 7) is caught: 28 PRs differ on time to first review.
- The seven checks of ADR 0003 on a real DevLake are in section 8; the importer works on the real tables (102 rows written).

## 2. Repositories and how they were chosen

| repo | license | owner | PRs opened or merged in 2026-09 (compared) | of them opened in the period | merged in the period | PRs of the repo in GitHub (selection time) | PRs in DevLake |
|---|---|---|---|---|---|---|---|
| Launchframe/alliance-hq | MIT | Organization | 150 | 140 | 128 | 772 | 772 |
| sanity-io/cli | MIT | Organization | 147 | 135 | 117 | 1929 | 832 |

Period: 2026-09-01 00:00:00 to 2026-09-30 23:59:59 UTC, both ends included. Agent PRs (m1, Swarmia-aligned: the PR author is an agent bot): alliance-hq 33 (cursor), sanity-io/cli 10 (claude 8, copilot 2). Three agent tools in the two repos.

The rule list was fixed before looking at results (SPEC U4 3-1). Number of repositories left after each rule (from a discovery sample of 16,441 public repositories with at least one m1 hit):

| step | rule | repos left |
|---|---|---|
| 1 | owner is an Organization | 3,816 |
| 2 | license MIT or Apache-2.0 | 1,849 |
| 3 | not a fork, not archived | 1,657 |
| 5 | repo total PRs <= 2,500 (so the importer runs without a token) | 1,442 |
| 4 | PRs opened or merged in the period: 20 to 150 | 532 |
| 6 | m1 PRs in the period >= 5 | 169 |
| 7 | >= 5 PRs with a review by a human who is neither the author nor a bot (evaluated in rank order until two were found) | 2 passed of 2 evaluated |

Step 8 ranked the 169 by the number of PRs in the period; these two are the first two (150 and 147 PRs). Rule 7 was evaluated for these two only; the other 167 were not evaluated for it.

Two departures from the specification, found before this trip and kept as they are:

1. **The search was a sample for the biggest tools.** The GitHub search API returns at most 1,000 hits per query; for tools with more hits in a month, the search was split by day and only the first pages of each day were read (copilot-swe-agent 24.8% of the created hits, devin 37.7%, cursor 46.5%, claude 68.1%). The candidate list is therefore not complete for these tools; the PR counts of the chosen repositories were counted per repository and are not a sample.
2. **The import took only three Data Entities.** The first import (all entities) was stopped: the CI part of sanity-io/cli has 82,245 workflow runs (DevLake asks for the jobs of a run one run at a time), more than 16 hours at 5,000 calls an hour. The Scope Config `u4-code-review-only` selects `CODE`, `CODEREVIEW`, `CROSS` (Source Code Management, Code Review, Cross Domain). The metrics use no CI or issue table. The second import (pipeline #2, 7 min 43 s) is the one compared.

## 3. Environment and times

| item | value |
|---|---|
| DevLake | v1.0.3-beta18 (the compose file of the release, local, ports on 127.0.0.1) |
| MySQL | 8.4.11 (the compose image is `mysql:8`, not pinned) |
| GitHub path | GraphQL (a classic token; the REST list of PRs does not return additions and deletions) |
| Data Time Range | from 2026-05-31T15:00:00Z (2026-06-01 00:00 Japan time); frequency Manual |
| Data Entities | `CODE`, `CODEREVIEW`, `CROSS` (deviation 2 above) |
| import finished (pipeline #2, `TASK_COMPLETED`) | 2026-10-20 17:14:00 UTC |
| raw data fetched | 2026-10-20 17:17:36 to 17:29:37 UTC, 1,485 REST calls (every list was one page) |
| `GITHUB_PR_EXCLUDELIST` in the DevLake container | not set |
| rule for class (d) | a PR whose `updated_at` in the raw data is later than 17:14:00 UTC: **0** PRs |

## 4. How the comparison was made

- **Independent calculation:** a separate script reads GitHub's answers for `pulls/{n}`, `pulls/{n}/reviews`, `pulls/{n}/comments`, `issues/{n}/comments`, `pulls/{n}/commits` and computes, per PR, the marks m1 to m6 (and x1, x2), the tool and mode groups, time to first review, time in review, cycle time, size, outcome, (1), (1B) and U1's agent group, from the definitions of ADR 0002 (D1 to D14) and ADR 0001. Minutes are cut toward zero; the median is the highest value with `percent_rank() <= 0.5`. sha256 of the script: `a341e6f00fa81ad5054b315b793d90968019960656304d359a9d852d51766914` at the start of the check and `a341e6f00fa81ad5054b315b793d90968019960656304d359a9d852d51766914` at the end (unchanged, no change was needed).
- **SQL side:** `tools/run_on_devlake.py` runs the `@common` WITH list of `ai_impact_parity.sql` (or `agent_review_burden.sql`) on the real DevLake with the period and the two repo ids, and `sql/mysql/checks/per_pr.sql` / `per_pr_u1.sql` add one SELECT per PR on the same list, unchanged. `pr_classification` gives the marks, tools and modes.
- **Items compared per PR:** m1 to m6; tools, modes, ai_used; x1, x2; tools, modes, ai_used with the own markers; time to first review, time in review, cycle time (whole minutes); size; outcome; the two period flags; and for PRs opened in the period U1's agent group, (1), (1B). 21 items, 24 for the 275 PRs opened in the period.
- **Identity of a PR:** all 297 DevLake ids end with the REST `id` of the PR (`github:GithubPullRequest:1:<id>`), so the GraphQL `databaseId` and the REST `id` are the same number (R4 of ADR 0003); the DevLake set of PRs (opened or merged in the period) is exactly the 297 PRs of the GitHub list.

- **Two readings where the specification does not decide** (kept as written before the run): a trailer line (m4, m5) counts when it starts a line and the colon is followed by zero or more spaces or tabs (git-interpret-trailers accepts any number); spaces before the colon and the rule that git reads trailers only from the last paragraph are not followed. For the choice of repositories (rule 7), a person is any account that is not the author and is not of type `Bot` or named `...[bot]`, and reviews were not restricted to the period.

Classes of a difference (SPEC U4 3-3 and 4-3): (a) the SQL is wrong; (b) the independent script is wrong; (c) DevLake lacks the data, only for the causes listed before the run (PR created before the start of the Data Time Range; more than 100 commits or reviews; m4/m5 on a PR without a commit message in DevLake; PRs dropped by `GITHUB_PR_EXCLUDELIST`; comments deleted later); (d) the PR changed between the DevLake import and the raw fetch.

## 5. Result per item

| item | differing PRs | compared PRs |
|---|---|---|
| m1 | 43 | 297 |
| m2 | 0 | 297 |
| m3 | 0 | 297 |
| m4 | 9 | 297 |
| m5 | 0 | 297 |
| m6 | 0 | 297 |
| tools | 5 | 297 |
| modes | 5 | 297 |
| ai_used | 5 | 297 |
| x1 | 0 | 297 |
| x2 | 0 | 297 |
| tools_own | 1 | 297 |
| modes_own | 5 | 297 |
| ai_used_own | 1 | 297 |
| time_to_first_review | 0 | 297 |
| time_in_review | 0 | 297 |
| pr_cycle_time | 0 | 297 |
| batch_size | 0 | 297 |
| outcome | 0 | 297 |
| in_created | 0 | 297 |
| in_merged | 0 | 297 |
| u1_agent | 0 | 275 |
| u1_first_reaction | 0 | 275 |
| u1b_first_reaction | 0 | 275 |

| class | PRs | items |
|---|---|---|
| every item equal | 253 | |
| (a) SQL is wrong | 43 | m1: 43, m4: 4 |
| (b) independent script is wrong | 0 | |
| (c) DevLake lacks the data | 5 (all on m4, no commit message in DevLake; 4 of them are also in (a)) | m4: 5 |
| (d) changed after the import | 0 | |

The tools, modes and ai_used items that differ (5, 5, 5; own markers 1, 5, 1) are consequences of m1 and m4 on the same PRs (nothing else differs).

**A1 in detail.** For the 43 PRs, GitHub's REST login of the author is the bot's login with `[bot]` (type `Bot`), and DevLake's `pull_requests.author_name` is the login without it (`cursor` 33, `claude` 8, `copilot-swe-agent` 2). The `accounts` table has the `[bot]` forms (`cursor[bot]`, `claude[bot]`, `is_bot = 1`). The review-agent mark m6 reads `accounts` and agrees with GitHub on all 297 PRs (2 PRs have it). The m1 patterns of the identities list are written for the REST form. Effect on the groups here: 4 PRs (2 `copilot`, 2 `cursor`; no other mark) are in `everything_else` instead of their tool.

**A2 in detail.** `information_schema` says `commits.message` is `longblob` with no collation. On the commit of PR sanity-io/cli #1863, `LOCATE('Co-Authored-By', message)` finds the line and `LOCATE('co-authored-by', LOWER(message))` does not. On all 2,766 rows of `commits`, the m4 pattern finds 0. m5 (`Made-with: Cursor`) has the same form; there is no PR with an m5 line in this data, so it is not measured. Of the 9 PRs with an m4 line in GitHub's data, 5 have no commit message in DevLake (class (c)) and 4 have it and are missed.

**The commit message in DevLake.** `check:prs_without_commit_message` = **230** of the 275 PRs opened in the period, so the message could be read for **45** PRs (16.4%). In GitHub's raw data, 8 PRs of the period have no commit message at all. DevLake's `commits` table (filled by the git clone, not by the GraphQL collector) has 2,766 rows for 5,214 rows of `pull_request_commits`.

**Not triggered in this data:** PRs created before the Data Time Range start: 0; PRs with more than 100 commits or more than 100 reviews: 0; PRs dropped by `GITHUB_PR_EXCLUDELIST`: the variable is not set; PRs changed after the import (class (d)): 0.

## 6. Group values

Group means, medians and counts from the SQL on the real DevLake, both repositories together (minutes, whole minutes cut toward zero; TTFR = time to first review; size = additions + deletions). **These values contain the effect of A1 and A2 (5 PRs are in the wrong group); they are to be taken again after the SQL is corrected.**

Swarmia-aligned markers (`include_own_markers = 0`), tool groups:

| group | PRs opened | TTFR n | TTFR mean | TTFR median | PRs merged | time in review mean | median | cycle time mean | median | size median |
|---|---|---|---|---|---|---|---|---|---|---|
| tool:claude | 8 | 4 | 5106.8 | 7 | 4 | 5106.8 | 7 | 5291.2 | 44 | 83 |
| tool:copilot | 0 | 0 | - | - | 2 | 62236.5 | 62144 | 62237.5 | 62144 | - |
| tool:cursor | 68 | 28 | 560.8 | 543 | 55 | 4115.1 | 549 | 4534.0 | 550 | 468 |
| tool:everything_else | 199 | 90 | 1598.0 | 171 | 184 | 4695.6 | 805 | 5433.9 | 993 | 219 |

groups without any PR: tool:coderabbit, tool:codex, tool:cubic, tool:devin, tool:graphite, tool:macroscope, tool:qodo.

Mode groups:

| group | PRs opened | TTFR n | TTFR mean | TTFR median | PRs merged | time in review mean | median | cycle time mean | median | size median |
|---|---|---|---|---|---|---|---|---|---|---|
| mode:ai_assisted | 76 | 32 | 1129.0 | 490 | 59 | 4182.3 | 543 | 4585.3 | 543 | 413 |
| mode:ai_used | 76 | 32 | 1129.0 | 490 | 61 | 6085.7 | 549 | 6475.6 | 550 | 413 |
| mode:cloud_agent | 49 | 32 | 1129.0 | 490 | 39 | 5440.4 | 254 | 6000.5 | 256 | 202 |
| mode:everything_else | 199 | 90 | 1598.0 | 171 | 184 | 4695.6 | 805 | 5433.9 | 993 | 219 |
| mode:review_agent | 0 | 0 | - | - | 2 | 62236.5 | 62144 | 62237.5 | 62144 | - |

With this repo's own markers added (`include_own_markers = 1`), tool groups:

| group | PRs opened | TTFR n | TTFR mean | TTFR median | PRs merged | time in review mean | median | cycle time mean | median | size median |
|---|---|---|---|---|---|---|---|---|---|---|
| tool:claude | 8 | 4 | 5106.8 | 7 | 4 | 5106.8 | 7 | 5291.2 | 44 | 83 |
| tool:codex | 6 | 4 | 46.0 | 17 | 4 | 46.0 | 17 | 295.8 | 32 | 64 |
| tool:copilot | 2 | 0 | - | - | 3 | 41517.0 | 62144 | 41517.7 | 62144 | 689 |
| tool:cursor | 70 | 29 | 570.7 | 549 | 56 | 4056.8 | 549 | 4468.2 | 550 | 466 |
| tool:everything_else | 189 | 85 | 1679.9 | 186 | 178 | 4847.6 | 912 | 5605.2 | 1063 | 218 |

U1 (agents of U1, PRs opened in the period; (1) = first human reaction, (1B) = the same without assignees; minutes):

| agent | PRs | with a reaction | median (1) | with a reaction not by an assignee | median (1B) |
|---|---|---|---|---|---|
| copilot | 2 | 2 | 0 | 0 | - |
| devin | 0 | 0 | - | 0 | - |
| codex | 6 | 4 | 17 | 4 | 17 |
| claude | 0 | 0 | - | 0 | - |
| cursor | 41 | 29 | 490 | 29 | 490 |
| other_bot | 68 | 52 | 81 | 52 | 81 |
| no_marker | 158 | 46 | 640 | 46 | 640 |

Checks of these tables. The independent calculation was run again with the tool and mode group of every PR taken from DevLake's `pr_classification` (only the 5 PRs whose group differs change). Then every group value of the SQL (counts, means, medians, size shares, weekly counts, outcomes) equals the independent one: both repositories together 288 of 288 (parity markers) and 291 of 291 (own markers); alliance-hq alone 284 of 284 and 284 of 284; sanity-io/cli alone 286 of 286 and 289 of 289; all 63 U1 group values of each of the three sets. So the means, medians, counts and weekly counts of the SQL are right given the marks. Without that replacement, 127 of 288 (parity) and 98 of 291 (own) group values differ; all of them come from the 5 PRs.

## 7. The comparison can catch a wrong SQL (mutant M3)

M3 of ADR 0002 (D2: the first review is only an APPROVED or CHANGES_REQUESTED review) was put into a copy of `ai_impact_parity.sql` (one added line in the `first_review` list; the repo file was not touched) and the same per-PR and group comparison was run on the real DevLake. Result: 28 PRs differ on time to first review (0 without the mutation); 226 PRs have every item equal (253 without the mutation); 14 of the 288 group values differ (14 of them time-to-first-review values; 0 without the mutation). The comparison catches it.

## 8. The seven checks of ADR 0003 on the real DevLake

1. **Table shapes (check 4 of ADR 0003).** `SHOW CREATE TABLE pull_request_assignees`: `pull_request_id` and `assignee_id` `varchar(255) NOT NULL` (the primary key), `name`, `user_name` `varchar(255)` NULL, `created_at`, `updated_at` `datetime(3)` NULL, `_raw_data_params` `varchar(255)` NULL (indexed), `_raw_data_table` `varchar(255)` NULL, `_raw_data_id` `bigint unsigned` NULL, `_raw_data_remark` `longtext` NULL; every text column `utf8mb4_bin`. `pull_requests` has the same `created_at`, `updated_at`, `_raw_data_*` columns with the same types and `id varchar(255) NOT NULL`. This is the shape the test schema assumed, and the importer's `INSERT` (it leaves `_raw_data_id` and `_raw_data_remark` unset) was accepted: 102 rows written. One table does not have the assumed shape: `commits.message` is `longblob`, the test schema has `LONGTEXT` (defect A2 in section 1).
2. **sql_mode (check 6 of ADR 0003).** `@@GLOBAL.sql_mode` = `ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`: `NO_BACKSLASH_ESCAPES` is not in it, so the importer's backslash doubling is right. `VERSION()` = 8.4.11 (the compose image is `mysql:8`, not pinned; the tests ran on `mysql:8.4`, the same series).
3. **IDs and params (check 5 of ADR 0003).** `pull_requests.id` is `github:GithubPullRequest:1:<id>`; for all 297 compared PRs the number after the last colon equals the `id` of `GET /repos/{o}/{r}/pulls/{n}` (REST), although DevLake collected through GraphQL, so R4 holds on live data. `_raw_data_params` of the 1,604 rows that `pull_requests` had then is `{"ConnectionId":1,"Name":"<owner>/<repo>"}` (two distinct values, one per repo) and `_raw_data_table` is `_raw_github_graphql_prs`.
4. **Running the importer (token-free, 60 requests an hour).** `importer/github_pr_assignees.py --connection-id 1`, once per repo, then the `.sql` fed to `mysql` as in `docs/importer.md`. Launchframe/alliance-hq: 8 pages, 772 PRs read, 1 assignee row expected, **1 row written**, 0 PRs not in DevLake. sanity-io/cli: 20 pages, 1,930 PRs read, 122 rows expected, **101 rows written**, **1,098 PRs not in DevLake** (the PRs older than the Data Time Range, DevLake has 832 of the 1,930; the 21 other rows belong to them). Total **102 rows added**, no HTTP 403 (28 requests), no PR skipped for an invalid value.
5. **(1B) against (1) (check 3 of ADR 0003).** Among the 275 PRs opened in the period, (1B) differs from (1) for **2** PRs (both are `copilot` PRs of sanity-io/cli, each with two assignees, and every human reaction came from an assignee: (1B) is empty). (1) and (1B) of all 275 PRs equal the independent calculation, which reads the assignees from GitHub at fetch time.
6. **Full re-import (check 1 of ADR 0003).** `POST /blueprints/1/trigger` with `{"skipCollectors":false,"fullSync":true}` (pipeline #3, 17:43:33 to 17:51:11 UTC, `TASK_COMPLETED`). Rows with `_raw_data_table = '_raw_github_ext_pull_request_assignees'`: **102 before, 102 after**. DevLake's own rows changed a little because GitHub changed in between (`pull_requests` 1,604 to 1,605, `pull_request_commits` 5,214 to 5,216, `pull_request_comments` 8,909 to 8,914).
7. **Scope data delete (check 2 of ADR 0003).** The CSV and comparison files were saved first. `DELETE /plugins/github/connections/1/scopes/916760480?delete_data_only=true` (sanity-io/cli) answered 200. Before: 833 PRs and 101 importer rows of sanity-io/cli, 772 PRs and 1 importer row of alliance-hq. After: **0 PRs and 0 importer rows of sanity-io/cli; alliance-hq keeps its 772 PRs and its 1 importer row** (importer rows in the table: 102 to 1; rows of `repos`: 2 to 1). Way back (the same calls as check 6): trigger the blueprint again (pipeline #4, 17:52:08 to 17:58:45 UTC, `TASK_COMPLETED`; it brought back 832 PRs of sanity-io/cli, the repo had 833 before the delete because GitHub changed in between), then run the importer again for that repo (20 more requests): 101 rows written, 102 importer rows in the table again, 1,604 PRs in `pull_requests`, as after the first import. DevLake was left in this restored state.

## 9. Per-PR table

One row per PR: repo and number, the tool group of the independent calculation (Swarmia-aligned markers), items equal / items compared, and the class of each differing item. Times are not written.

| PR | tool group | equal / compared | differing items (class) |
|---|---|---|---|
| Launchframe/alliance-hq #159 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #333 | cursor | 21 / 21 |  |
| Launchframe/alliance-hq #388 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #449 | copilot | 21 / 21 |  |
| Launchframe/alliance-hq #450 | copilot | 21 / 21 |  |
| Launchframe/alliance-hq #453 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #491 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #535 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #537 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #538 | everything_else | 21 / 21 |  |
| Launchframe/alliance-hq #551 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #552 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #553 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #554 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #555 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #556 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #557 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #558 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #559 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #560 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #561 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #562 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #563 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #564 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #565 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #566 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #567 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #568 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #569 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #570 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #571 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #572 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #573 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #574 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #575 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #576 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #577 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #578 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #579 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #580 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #581 | cursor | 19 / 24 | m1 (a) |
| Launchframe/alliance-hq #582 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #583 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #584 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #585 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #586 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #587 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #588 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #589 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #590 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #591 | cursor | 19 / 24 | m1 (a) |
| Launchframe/alliance-hq #592 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #593 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #594 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #595 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #596 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #597 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #598 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #599 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #600 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #601 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #602 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #603 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #604 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #605 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #606 | cursor | 23 / 24 | m1 (a) |
| Launchframe/alliance-hq #610 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #611 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #612 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #613 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #614 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #615 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #616 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #617 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #618 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #619 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #620 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #621 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #622 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #623 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #624 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #625 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #626 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #629 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #630 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #631 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #632 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #633 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #634 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #636 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #637 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #638 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #639 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #640 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #641 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #642 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #643 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #644 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #645 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #646 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #647 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #648 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #649 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #650 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #651 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #652 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #655 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #656 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #657 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #658 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #659 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #660 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #661 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #665 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #666 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #667 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #668 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #670 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #671 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #672 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #674 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #675 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #676 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #677 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #678 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #679 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #680 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #681 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #682 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #683 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #684 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #685 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #686 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #687 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #689 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #690 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #691 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #692 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #693 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #694 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #695 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #696 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #698 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #699 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #700 | cursor | 24 / 24 |  |
| Launchframe/alliance-hq #701 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #702 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #703 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #704 | everything_else | 24 / 24 |  |
| Launchframe/alliance-hq #705 | everything_else | 24 / 24 |  |
| sanity-io/cli #1224 | cursor | 21 / 21 |  |
| sanity-io/cli #1621 | everything_else | 21 / 21 |  |
| sanity-io/cli #1762 | everything_else | 21 / 21 |  |
| sanity-io/cli #1766 | everything_else | 21 / 21 |  |
| sanity-io/cli #1774 | everything_else | 21 / 21 |  |
| sanity-io/cli #1780 | everything_else | 21 / 21 |  |
| sanity-io/cli #1784 | everything_else | 21 / 21 |  |
| sanity-io/cli #1785 | everything_else | 21 / 21 |  |
| sanity-io/cli #1786 | everything_else | 21 / 21 |  |
| sanity-io/cli #1787 | everything_else | 21 / 21 |  |
| sanity-io/cli #1789 | everything_else | 21 / 21 |  |
| sanity-io/cli #1790 | everything_else | 21 / 21 |  |
| sanity-io/cli #1791 | everything_else | 24 / 24 |  |
| sanity-io/cli #1792 | everything_else | 24 / 24 |  |
| sanity-io/cli #1793 | everything_else | 24 / 24 |  |
| sanity-io/cli #1794 | everything_else | 24 / 24 |  |
| sanity-io/cli #1795 | everything_else | 24 / 24 |  |
| sanity-io/cli #1796 | everything_else | 24 / 24 |  |
| sanity-io/cli #1797 | everything_else | 24 / 24 |  |
| sanity-io/cli #1798 | everything_else | 24 / 24 |  |
| sanity-io/cli #1799 | everything_else | 24 / 24 |  |
| sanity-io/cli #1800 | everything_else | 24 / 24 |  |
| sanity-io/cli #1801 | everything_else | 24 / 24 |  |
| sanity-io/cli #1802 | copilot | 19 / 24 | m1 (a) |
| sanity-io/cli #1803 | everything_else | 24 / 24 |  |
| sanity-io/cli #1804 | everything_else | 24 / 24 |  |
| sanity-io/cli #1805 | everything_else | 24 / 24 |  |
| sanity-io/cli #1806 | everything_else | 24 / 24 |  |
| sanity-io/cli #1807 | everything_else | 24 / 24 |  |
| sanity-io/cli #1808 | everything_else | 24 / 24 |  |
| sanity-io/cli #1809 | everything_else | 24 / 24 |  |
| sanity-io/cli #1810 | everything_else | 24 / 24 |  |
| sanity-io/cli #1811 | everything_else | 24 / 24 |  |
| sanity-io/cli #1812 | everything_else | 24 / 24 |  |
| sanity-io/cli #1813 | copilot | 19 / 24 | m1 (a) |
| sanity-io/cli #1814 | cursor | 24 / 24 |  |
| sanity-io/cli #1815 | everything_else | 24 / 24 |  |
| sanity-io/cli #1816 | everything_else | 24 / 24 |  |
| sanity-io/cli #1817 | everything_else | 24 / 24 |  |
| sanity-io/cli #1818 | everything_else | 24 / 24 |  |
| sanity-io/cli #1819 | everything_else | 24 / 24 |  |
| sanity-io/cli #1820 | everything_else | 24 / 24 |  |
| sanity-io/cli #1821 | everything_else | 24 / 24 |  |
| sanity-io/cli #1823 | everything_else | 24 / 24 |  |
| sanity-io/cli #1824 | everything_else | 24 / 24 |  |
| sanity-io/cli #1825 | everything_else | 24 / 24 |  |
| sanity-io/cli #1826 | everything_else | 24 / 24 |  |
| sanity-io/cli #1827 | everything_else | 24 / 24 |  |
| sanity-io/cli #1828 | everything_else | 24 / 24 |  |
| sanity-io/cli #1829 | everything_else | 24 / 24 |  |
| sanity-io/cli #1830 | everything_else | 24 / 24 |  |
| sanity-io/cli #1831 | everything_else | 24 / 24 |  |
| sanity-io/cli #1832 | everything_else | 24 / 24 |  |
| sanity-io/cli #1833 | everything_else | 24 / 24 |  |
| sanity-io/cli #1834 | everything_else | 24 / 24 |  |
| sanity-io/cli #1835 | everything_else | 24 / 24 |  |
| sanity-io/cli #1836 | everything_else | 24 / 24 |  |
| sanity-io/cli #1837 | everything_else | 24 / 24 |  |
| sanity-io/cli #1838 | everything_else | 24 / 24 |  |
| sanity-io/cli #1839 | everything_else | 24 / 24 |  |
| sanity-io/cli #1840 | cursor | 24 / 24 |  |
| sanity-io/cli #1841 | claude | 22 / 24 | m1 (a), m4 (c) |
| sanity-io/cli #1842 | everything_else | 24 / 24 |  |
| sanity-io/cli #1843 | cursor | 24 / 24 |  |
| sanity-io/cli #1844 | everything_else | 24 / 24 |  |
| sanity-io/cli #1845 | everything_else | 24 / 24 |  |
| sanity-io/cli #1846 | everything_else | 24 / 24 |  |
| sanity-io/cli #1847 | everything_else | 24 / 24 |  |
| sanity-io/cli #1848 | everything_else | 24 / 24 |  |
| sanity-io/cli #1849 | everything_else | 24 / 24 |  |
| sanity-io/cli #1850 | everything_else | 24 / 24 |  |
| sanity-io/cli #1851 | everything_else | 24 / 24 |  |
| sanity-io/cli #1852 | everything_else | 24 / 24 |  |
| sanity-io/cli #1853 | everything_else | 24 / 24 |  |
| sanity-io/cli #1854 | everything_else | 24 / 24 |  |
| sanity-io/cli #1855 | everything_else | 24 / 24 |  |
| sanity-io/cli #1856 | everything_else | 24 / 24 |  |
| sanity-io/cli #1857 | claude | 22 / 24 | m1 (a), m4 (a) |
| sanity-io/cli #1859 | everything_else | 24 / 24 |  |
| sanity-io/cli #1860 | everything_else | 24 / 24 |  |
| sanity-io/cli #1861 | everything_else | 24 / 24 |  |
| sanity-io/cli #1862 | everything_else | 24 / 24 |  |
| sanity-io/cli #1863 | claude | 22 / 24 | m1 (a), m4 (a) |
| sanity-io/cli #1864 | claude | 22 / 24 | m1 (a), m4 (c) |
| sanity-io/cli #1865 | everything_else | 24 / 24 |  |
| sanity-io/cli #1866 | everything_else | 24 / 24 |  |
| sanity-io/cli #1868 | cursor | 24 / 24 |  |
| sanity-io/cli #1869 | everything_else | 24 / 24 |  |
| sanity-io/cli #1870 | everything_else | 24 / 24 |  |
| sanity-io/cli #1871 | everything_else | 24 / 24 |  |
| sanity-io/cli #1872 | everything_else | 24 / 24 |  |
| sanity-io/cli #1873 | everything_else | 24 / 24 |  |
| sanity-io/cli #1874 | everything_else | 24 / 24 |  |
| sanity-io/cli #1875 | everything_else | 24 / 24 |  |
| sanity-io/cli #1877 | claude | 22 / 24 | m1 (a), m4 (a) |
| sanity-io/cli #1878 | everything_else | 24 / 24 |  |
| sanity-io/cli #1879 | everything_else | 24 / 24 |  |
| sanity-io/cli #1880 | everything_else | 24 / 24 |  |
| sanity-io/cli #1881 | everything_else | 24 / 24 |  |
| sanity-io/cli #1883 | everything_else | 24 / 24 |  |
| sanity-io/cli #1885 | everything_else | 24 / 24 |  |
| sanity-io/cli #1886 | everything_else | 24 / 24 |  |
| sanity-io/cli #1887 | everything_else | 24 / 24 |  |
| sanity-io/cli #1888 | everything_else | 24 / 24 |  |
| sanity-io/cli #1889 | everything_else | 24 / 24 |  |
| sanity-io/cli #1890 | everything_else | 24 / 24 |  |
| sanity-io/cli #1891 | everything_else | 24 / 24 |  |
| sanity-io/cli #1892 | everything_else | 24 / 24 |  |
| sanity-io/cli #1894 | everything_else | 24 / 24 |  |
| sanity-io/cli #1895 | everything_else | 24 / 24 |  |
| sanity-io/cli #1896 | everything_else | 24 / 24 |  |
| sanity-io/cli #1897 | everything_else | 24 / 24 |  |
| sanity-io/cli #1898 | everything_else | 24 / 24 |  |
| sanity-io/cli #1899 | everything_else | 24 / 24 |  |
| sanity-io/cli #1900 | everything_else | 24 / 24 |  |
| sanity-io/cli #1901 | everything_else | 24 / 24 |  |
| sanity-io/cli #1902 | everything_else | 24 / 24 |  |
| sanity-io/cli #1903 | everything_else | 24 / 24 |  |
| sanity-io/cli #1904 | cursor | 24 / 24 |  |
| sanity-io/cli #1905 | everything_else | 24 / 24 |  |
| sanity-io/cli #1906 | everything_else | 24 / 24 |  |
| sanity-io/cli #1907 | everything_else | 24 / 24 |  |
| sanity-io/cli #1908 | everything_else | 24 / 24 |  |
| sanity-io/cli #1909 | everything_else | 24 / 24 |  |
| sanity-io/cli #1910 | everything_else | 24 / 24 |  |
| sanity-io/cli #1911 | claude | 22 / 24 | m1 (a), m4 (c) |
| sanity-io/cli #1912 | everything_else | 24 / 24 |  |
| sanity-io/cli #1913 | cursor | 24 / 24 |  |
| sanity-io/cli #1914 | everything_else | 24 / 24 |  |
| sanity-io/cli #1915 | cursor | 24 / 24 |  |
| sanity-io/cli #1916 | claude | 17 / 24 | m4 (c) |
| sanity-io/cli #1917 | everything_else | 24 / 24 |  |
| sanity-io/cli #1919 | everything_else | 24 / 24 |  |
| sanity-io/cli #1920 | everything_else | 24 / 24 |  |
| sanity-io/cli #1921 | everything_else | 24 / 24 |  |
| sanity-io/cli #1923 | claude | 22 / 24 | m1 (a), m4 (c) |
| sanity-io/cli #1924 | everything_else | 24 / 24 |  |
| sanity-io/cli #1925 | cursor | 24 / 24 |  |
| sanity-io/cli #1926 | everything_else | 24 / 24 |  |
| sanity-io/cli #1927 | everything_else | 24 / 24 |  |
| sanity-io/cli #1929 | everything_else | 24 / 24 |  |
| sanity-io/cli #1930 | everything_else | 24 / 24 |  |
| sanity-io/cli #1931 | everything_else | 24 / 24 |  |
| sanity-io/cli #1932 | everything_else | 24 / 24 |  |
| sanity-io/cli #1934 | claude | 22 / 24 | m1 (a), m4 (a) |
| sanity-io/cli #1935 | everything_else | 24 / 24 |  |
| sanity-io/cli #1936 | cursor | 24 / 24 |  |

## 10. Reproduce

1. Start DevLake from the release's compose file, create the GitHub connection, run `python tools/devlake_configure.py apply ...` (`docs/devlake_configure.md`).
2. Fetch the five raw lists of every compared PR with `gh api` (read-only), run the independent script on them.
3. `python tools/run_on_devlake.py --compose-dir <folder of the compose file> --out-dir <dir> --sql sql/mysql/ai_impact_parity.sql` (and `--sql sql/mysql/checks/per_pr.sql --common-from sql/mysql/ai_impact_parity.sql`, `--include-own-markers 1`, and the U1 files).
4. Run `python importer/github_pr_assignees.py` per repo and feed the `.sql` (docs/importer.md) before the U1 per-PR file is read.

