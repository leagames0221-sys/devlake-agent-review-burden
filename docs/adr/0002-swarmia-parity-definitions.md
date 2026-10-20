# ADR 0002: Metrics and AI-tool groups defined as Swarmia defines them

Status: accepted (2026-10-20). Scope: `sql/mysql/ai_impact_parity.sql`, synthetic tests, MySQL only.

Quotes are written `> "..." (path L<n>)` and are copied word for word from the saved copy of the page. The paths are relative to the
research folder `research/v3/` (kept outside this repository; every saved file starts with its URL and the date retrieved,
2026-10-20), and the line numbers are the line numbers of the saved file. `upstream/beta18/*.txt` are single files of apache/devlake at the tag
`v1.0.3-beta18`; their first line is a heading, so their line numbers are one more than in the original file. Pages used:

| Saved file | URL |
|---|---|
| `vendor/swarmia_def_time_to_review.txt` | https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review |
| `vendor/swarmia_def_pr_cycle_time.txt` | https://help.swarmia.com/features/metrics/pull-request-cycle-time |
| `vendor/swarmia_def_throughput.txt` | https://help.swarmia.com/definitions/throughput |
| `vendor/swarmia_def_batch_size.txt` | https://help.swarmia.com/definitions/batch-size |
| `vendor/swarmia_def_data_model_pull_request.txt` | https://help.swarmia.com/data-model/entities/pull-request |
| `vendor/swarmia_impact_pr.txt` | https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics |
| `vendor/swarmia_detect.txt` | https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters |
| `vendor/swarmia_agent.txt` | https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics |
| `vendor/swarmia_def_cloud_agents.txt` | https://help.swarmia.com/features/ai-tools/cloud-agents |
| `vendor/swarmia_def_review_agents.txt` | https://help.swarmia.com/features/ai-tools/review-agents |

## Context

ADR 0001 defines five review-burden metrics per agent group. They answer "do agent PRs cost more human review?". Teams that use Swarmia
read a different set of numbers, with Swarmia's own definitions: time to first review, time in review, PR cycle time, throughput, batch size,
and every one of them split by AI tool and by way of use. Swarmia is a paid service. This ADR fixes the same numbers on DevLake's
domain-layer tables, so that a team that has DevLake gets them without a paid tool, and says for each number where it is the same as Swarmia
and where it is not. U1's metrics stay as they are (`sql/mysql/agent_review_burden.sql`).

## Decision

### Metrics

Every metric is given for each AI-tool group and each mode group (below). Medians use the method of ADR 0001 (largest value with
`percent_rank() <= 0.5`, the lower middle value for an even count; DevLake has no median function in MySQL). Means are given next to them.
Times are in minutes (`TIMESTAMPDIFF(MINUTE, ...)`, rounded down).

**`time_to_first_review`**
> "until the first review is submitted" (vendor/swarmia_def_time_to_review.txt L16)

> "Reviews completed by bots are excluded from the aggregate" (vendor/swarmia_def_time_to_review.txt L27)

> "Not defined for pull requests that have not been reviewed." (vendor/swarmia_def_data_model_pull_request.txt L248)

Here: from the time the PR was opened (D1) to the first `REVIEW` row of a person who is not a bot and not the PR author (D3), in any state
(D2). A PR without such a review is not counted; the metric gives both the number of PRs with a value and the number of PRs in the group.
Differences: the start is not "review requested" (DevLake has no such time); NORMAL comments and line comments (`DIFF`) do not count, only
review rows; a person's review in the state `COMMENTED` or `DISMISSED` ends the wait (D2, an interpretation).

**`time_in_review`** (merged PRs only)
> "from the first review request (or from when the pull request was opened, if none) to the final approval." (vendor/swarmia_def_pr_cycle_time.txt L13)

> "review time is measured from the review request until the merge." (vendor/swarmia_def_time_to_review.txt L23)

Here: from the PR being opened (D1) to the last `APPROVED` review before the merge by a person who is not a bot and not the author (D9);
without such an approval, to the merge (D5). Differences: the start (D1); a PR opened as a draft shows a longer time than in Swarmia.

**`pr_cycle_time`** (merged PRs only)
> "from the first commit or from when the pull request is opened, whichever happens first, to the first review request." (vendor/swarmia_def_pr_cycle_time.txt L12)

> "from the final approval to once the pull request is merged." (vendor/swarmia_def_pr_cycle_time.txt L14)

> "The average PR cycle time for a given time period would be the cycle time of all pull requests in that time period, averaged." (vendor/swarmia_def_pr_cycle_time.txt L28)

> "We consider all PRs the same, regardless of the draft state." (vendor/swarmia_def_pr_cycle_time.txt L81)

Here: from the earlier of the first commit (D10) and the PR being opened, to the merge. The sum of the three parts of the Swarmia text is the
same span; it is computed as one span. Draft PRs are not treated differently (D4). A PR without a row in `pull_request_commits` starts at the time it was opened.

**`throughput`**
> "the number of pull requests you get through as a team over a selected period of time." (vendor/swarmia_def_throughput.txt L6)

> "PRs merged (throughput)" (vendor/swarmia_impact_pr.txt L80)

Here: the number of merged PRs, in the period of the dashboard (by the merge time, D12), and per week (D6, `YEARWEEK(merged_date, 3)`,
Monday first). The weekly rows are split by mode, not by tool. Differences: the example in the throughput definition counts PRs "closed"
(vendor/swarmia_def_throughput.txt L10); the AI impact page calls the number "PRs merged", and that is what is counted.

**`batch_size`**
> "Batch size is calculated by the lines of code changed (lines added + lines removed) in a given pull request." (vendor/swarmia_def_batch_size.txt L10)

> "Swarmia automatically cleans up the total change count of some commonly used generated files." (vendor/swarmia_def_batch_size.txt L14)

Here: `additions + deletions`, mean and median, and the share of PRs under 200, from 200 to 499, and 500 and over. The buckets are the
benchmarks of the page (vendor/swarmia_def_batch_size.txt L30-L32: "Great", "Good", "Needs attention"). **Generated files are not removed**, so
a PR with a large lock file reads larger than in Swarmia. DevLake has a scope-config field for this,
`PrSizeExcludedFileExtensions` (upstream/beta18/github_scope_config.go.txt L53). How DevLake applies it to the stored `additions` and `deletions` was not
verified; the SQL reads the stored columns as they are.

**`cloud_agent_outcomes`**
> "show the raw number of AI cloud agent pull requests." (vendor/swarmia_agent.txt L94)

Here: for the mode `cloud_agent`: the number of PRs, and how many are MERGED, CLOSED and OPEN. PRs and CLOSED and OPEN are by the time the PR was
opened; MERGED is by the merge time (D12), so the three do not have to add up to the number of PRs. Swarmia's "merge percentage" is not computed.

**`pr_classification`** and **`diagnostics`** are not Swarmia metrics. The first gives, per PR, the marks that hit, the tools and the modes, so that
the classification can be tested directly. The second gives `check:prs_without_commit_message` and `check:tool_group_total_minus_pr_total`.

### Marks and groups

> "Any of its commits were authored or co-authored by an AI tool (high confidence)" (vendor/swarmia_detect.txt L76)

> "Any of its commits has the Made-with: Cursor Git trailer (high confidence)" (vendor/swarmia_detect.txt L77)

> "Swarmia attributes a PR to a cloud agent if the PR or its first commit has been authored by a cloud agent linked to one of the AI tools" (vendor/swarmia_detect.txt L82)

> "Swarmia attributes a PR to a review agent if it has reviews from a built-in review agent" (vendor/swarmia_detect.txt L86)

> "GitHub shows cursoragent as the author of the first commit" (vendor/swarmia_agent.txt L126)

> "The first commit in this PR was authored by Claude" (vendor/swarmia_agent.txt L127)

> "matching the author of review comments against known email addresses and GitHub login patterns" (vendor/swarmia_def_review_agents.txt L63)

> "If the agent posts a review comment on the pull request, Swarmia counts it as a review-agent review in either case." (vendor/swarmia_def_review_agents.txt L67)

Every mark is checked for every PR; the first hit does not stop the others.

| Mark | Meaning | Kind |
|---|---|---|
| m1 | the PR author is a cloud agent (identities, mode `cloud`, field `pr_author`) | Swarmia |
| m2 | the author of the first commit (D10), by name or e-mail, is a cloud agent | Swarmia |
| m3 | the author of any commit is an AI tool (fields `commit_author_name`, `commit_author_email`, modes `cloud` and `assist`) | Swarmia |
| m4 | a commit message has a `Co-authored-by:` line of an AI tool, at the start of a line | Swarmia |
| m5 | a commit message has a `Made-with: Cursor` line, at the start of a line | Swarmia |
| m6 | a review row (`REVIEW`, or a line comment `DIFF`, D13) is written by a review agent | Swarmia |
| x1 | `head_ref` starts with `copilot/`, `codex/`, `cursor/`, `devin/` or `claude/` | own (ADR 0001, rules 3 to 7) |
| x2 | the PR body has `Co-Authored-By: Claude` | own (ADR 0001, rule 7) |

x1 and x2 are used only when the dashboard variable `include_own_markers` is 1. The default 0 is the view that is aligned with Swarmia.

- **AI-tool groups.** A PR is in the group of every tool that has a mark on it. A PR with no mark is in `tool:everything_else`. The groups overlap:
  > "A single pull request can be associated with multiple AI tools and modes." (vendor/swarmia_impact_pr.txt L99)

  `check:tool_group_total_minus_pr_total` shows the amount of overlap. U1's `other_bot` (a bot that is not an agent, for example dependabot) is in `everything_else`.
- **Mode groups.** `cloud_agent` = m1 or m2. `ai_assisted` = m3, m4 or m5 (and x1 or x2 when own markers are on). `review_agent` = m6. `ai_used` = any of the three (D7).
  `everything_else` = none. A cloud agent PR is also `ai_assisted` when m3 hits (D14); the page allows the overlap (L99 above).
  > "AI used: AI-assisted PRs (based on the tools and modes you select) vs everything else." (vendor/swarmia_impact_pr.txt L90)

### Where the source text does not decide (D1 to D14)

Rows marked **interpretation** are my reading of the text. All other rows are the rule that was fixed instead of a rule in the source.

| # | Not decided | What is done | Reason |
|---|---|---|---|
| D1 | the start of the wait (time the review is requested) | the time the PR was opened (`created_date`) | DevLake has no time of a review request and no "ready for review" time (see "DevLake data"). The text of Time in review uses the time the PR was opened when there is no request: "(or from when the pull request was opened, if none)" (vendor/swarmia_def_pr_cycle_time.txt L13). Using it for Time to first review as well is an **extension**: Swarmia's own time to first review is "after being considered ready for review" (vendor/swarmia_def_data_model_pull_request.txt L248), so a PR that was a draft for a while reads longer here |
| D2 | does a `COMMENTED` review end Time to first review | **interpretation**: yes. The first submitted review ends it, whatever its state | L16 names "an approval or request for changes" in a parenthesis, but L18 says "before receiving any feedback" (vendor/swarmia_def_time_to_review.txt L18), so a review with comments is read as feedback |
| D3 | reviews by the PR author | not counted | not in the Swarmia text. GitHub's issue-metrics excludes them: "comments by issue/pull request author's and comments by bots are excluded" (upstream/issue_metrics_README.md L32). DevLake's DORA code excludes them too: `(pr2.author_id IS NULL OR pr2.author_id = '' OR prc2.account_id != pr2.author_id)` (upstream/beta18/change_lead_time_calculator.go.txt L253). U1's metric 1 does the same |
| D4 | draft period | not treated differently | for cycle time this is the text: "We consider all PRs the same, regardless of the draft state." (vendor/swarmia_def_pr_cycle_time.txt L81). For time to first review it becomes the difference in D1 |
| D5 | merged without an approval | the end of Time in review is the merge | "In these situations, review time is measured from the review request until the merge." (vendor/swarmia_def_time_to_review.txt L23) |
| D6 | the weeks of throughput | the week of the merge time, Monday first, `YEARWEEK(merged_date, 3)`; the total of the dashboard period is given as well | the text says only "over a selected period of time" (vendor/swarmia_def_throughput.txt L6) |
| D7 | what "AI used" is | **interpretation**: a PR that is in any mode (`cloud_agent`, `ai_assisted`, `review_agent`) | the text: "AI-assisted PRs (based on the tools and modes you select)" (vendor/swarmia_impact_pr.txt L90); read as the value when all modes are selected |
| D8 | mean or median | both are given; the comparison with Swarmia is the mean | the text says "averaged" (vendor/swarmia_def_pr_cycle_time.txt L28); the median is added to match U1 and the DevLake dashboards |
| D9 | which approval ends Time in review | the last `APPROVED` before the merge, by a person who is neither the author nor a bot (D11). A dismissed approval has the GitHub state `DISMISSED`, so it is not `APPROVED` | **interpretation**: "the final approval" (L13) is read as "before the merge"; bots are left out to match L27, which leaves bots out of Time to first review (**interpretation**) |
| D10 | the first commit | the smallest `pull_request_commits.commit_authored_date`; if several commits have that time, m2 hits when any of them is an agent | DevLake's DORA code takes the same minimum and keeps every commit with that time (upstream/beta18/change_lead_time_calculator.go.txt L207-L211, `batchFetchFirstCommits` at L197) and does not order them. The tie rule is my decision (**interpretation**) |
| D11 | what a bot is | an account with `accounts.is_bot = 1`, or whose name is one of U1's agent bot names, or whose login matches a login row of `identities` (fields `pr_author`, `review_author`) | widens U1's rule: a review agent such as `coderabbitai[bot]` can be stored with `is_bot = 0` |
| D12 | which time the period filter uses | the merge time for throughput, pr_cycle_time, time_in_review and the MERGED count of cloud_agent_outcomes; the time the PR was opened for everything else | **interpretation**: a metric that is defined by the merge is cut by the merge. The throughput example says "closed" (vendor/swarmia_def_throughput.txt L10), the AI impact page says "PRs merged" (vendor/swarmia_impact_pr.txt L80) |
| D13 | which rows of the review agent count in m6 | rows with `type` `REVIEW` or `DIFF` | the text: "posts a review comment" ... "counts it as a review-agent review" (vendor/swarmia_def_review_agents.txt L67). A review agent that only writes a summary into the PR description (Bugbot: "posts a summary to the PR description", vendor/swarmia_def_review_agents.txt L15) cannot be seen; that is a difference |
| D14 | does a cloud agent PR also count as ai_assisted | **interpretation**: yes, when m3 hits. The modes overlap | the rule of L76 is applied as it is written; the overlap is allowed by L99 |

### Text matching

DevLake's database collation is `utf8mb4_bin` (docker-compose-dev-mysql.yml, as in ADR 0001), so a match is case-sensitive unless the text is lowered first.
The probes of Appendix A were run on `mysql:8.4` with that collation; what they show is built into the SQL:

- **Case.** Every match is on `LOWER(text)` with a lower-case pattern (probe 1a: without it, `Co-Authored-By: Claude` does not match; 1c: a pattern read from a CTE column does not change that).
- **Logins and names** are anchored with `^...$` (probe 2a: `copilot-fan` matches an unanchored `copilot`). A literal `[bot]` is written `\\[bot\\]` in the SQL file (the first level is MySQL's
  string escape); unescaped, `[bot]` is a character class (probes 3b, 3c).
- **Trailers** (`Co-authored-by:`, `Made-with:`) count only at the start of a line, in two shapes, because a message can be in two shapes:
  real line breaks (`'m'` flag, LF and CRLF, probes 4a, 5a), or DevLake's JSON-string body (below), which has the quotes and the two characters `\n` and no line break
  (probes 6a to 6d): `(^"?|\\\\n)co-authored-by:...`. A trailer in the middle of a sentence matches neither (probes 4c, 6d, 8b).

### DevLake data (what the SQL has to live with)

`pull_request_commits` has the commit author name and e-mail and no message. The message is in `commits`, which the default GitHub import does not
always fill:

> "EnabledByDefault: false" (upstream/beta18/github_commit_convertor.go.txt L38)

> "Message json.RawMessage" (upstream/beta18/github_pr_commit_extractor.go.txt L68)

> "grc.repo_id = ? AND grc.connection_id = ?" (upstream/beta18/github_commit_convertor.go.txt L75)

The first line says the conversion into `commits` is off by default. The second shows that, on the REST path, the message is kept as JSON (the value
keeps its quotes and the two-character `\n`). The third is a join on the repository that makes the GraphQL path drop commits on conversion. How DevLake's git extractor
(gitextractor) fills `commits` was not verified in the saved sources; U4 measures it on real data. The SQL therefore:

1. joins `commits` with a `LEFT JOIN`;
2. keeps a PR in every count when its message is missing;
3. matches both shapes of the message (above);
4. gives `check:prs_without_commit_message`, the number of PRs for which no message could be read.

A review is stored with type `REVIEW`, the state of GitHub in `status` and, for a review without a submit time, no time
(upstream/beta18/pr_review_convertor.go.txt L92-L96). Unsent (`PENDING`) reviews are dropped at import
(upstream/beta18/github_pr_review_extractor.go.txt L73: `if body.State == "PENDING" || body.User == nil {`; upstream/beta18/graphql_pr_extractor.go.txt L102:
`if apiPullRequestReview.State != "PENDING" {`) and, as in U1, removed again by the SQL as a safeguard.
The time a review was **requested** is in no DevLake table that was searched (beta18, plugins `github` and `github_graphql`, the domain-layer `code` models; searched for
`review_request|requested_reviewer|timeline`). The GraphQL query asks for `reviewRequests` (upstream/beta18/graphql_pr_collector.go.txt L106) but it carries no time.

### Identity list

The tool and its identities are one CTE at the start of the SQL, `identities(tool, mode, field, pattern)`. How each row was checked, and the rows that
could not be, are in `docs/agent_identities.md`. U1's rules 1 and 2 (`Copilot`, `copilot-swe-agent[bot]`, `devin-ai-integration[bot]`) are carried over.

## Alternatives considered

- **Start Time to first review at the first review request using the PR timeline.** Rejected: no DevLake table has it (above).
- **Take one tool per PR (the first mark that hits).** Rejected: Swarmia allows several (L99), and the exclusive rule gives different groups (mutation M2).
- **Use the commit author's GitHub login.** Not possible: `pull_request_commits` has name and e-mail only. Swarmia matches accounts; here names and e-mails are matched, which is a difference that U4 has to measure.
- **Remove generated files from batch size.** Not done: the SQL has no list of files; the DevLake scope setting is named above.

## Consequences and limits

- Swarmia's AI-assisted mode has two more conditions: the label `claude-code-assisted` (vendor/swarmia_detect.txt L78) and the 24-hour rule for authors who used a tool (L79). Neither is
  implemented. The label is not read, and the 24-hour rule needs the usage data of the vendors. Everything implemented is "high confidence" in the sense of that page.
- Review agents that write only a summary comment (CodeRabbit with nothing to flag, Codex "no issues") are invisible to m6 (vendor/swarmia_def_review_agents.txt L75, L79-L84).
- Throughput per week is given per mode, not per tool.
- Swarmia attributes a cloud agent PR to the person who started it; here the PR keeps its author and is counted in the agent's group.
- The e-mail row of the Cursor identity is a placeholder (`docs/agent_identities.md`, table B).
- The numbers can be reproduced with `python tests/run_u1.py --sql sql/mysql/ai_impact_parity.sql --fixture tests/fixture_u2.sql --expected tests/expected_u2_parity.json --var include_own_markers=0`
  (and `expected_u2_own.json` with `=1`). The expected values were worked out by hand from the fixture, PR by PR; the per-PR values are in the `_per_pr` part of the
  json files. U1's metric 1 and Time to first review are checked on the same fixture (`tests/expected_u2_u1_cross.json`); scenario P-R2 shows the difference: 30 minutes (the first
  comment of any kind) against 90 (the first review).

## Appendix A: regular expression probes (section 3-3 of the U2 specification)

Run on 2026-10-20 in a throw-away container, `mysql 8.4.11, server collation utf8mb4_bin, connection collation utf8mb4_0900_ai_ci`.
The text under test is a `LONGTEXT` value in a table created with the server default collation (`utf8mb4_bin`), as DevLake's tables are.
`text` is the MySQL string literal that was inserted; `SQL` is the expression exactly as it was sent to MySQL, written as in `sql/mysql/ai_impact_parity.sql` (the same two backslashes for one backslash of the regular expression); `hit` is the result: 1 = match.

| Probe | Text inserted | Expression | hit |
|---|---|---|---|
| 1a case: text not lowered (bin column, lower-case pattern) | `'Co-Authored-By: Claude <x>'` | `REGEXP_LIKE(txt, '^co-authored-by: claude', 'm')` | 0 |
| 1b case: LOWER() first | `'Co-Authored-By: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by: claude', 'm')` | 1 |
| 1c case: pattern from a CTE column (as in the identities list), text not lowered | `'Claude'` | `(WITH i(p) AS (SELECT 'claude') SELECT REGEXP_LIKE(txt, i.p) FROM i)` | 0 |
| 1d case: pattern from a CTE column, LOWER() first | `'Claude'` | `(WITH i(p) AS (SELECT 'claude') SELECT REGEXP_LIKE(LOWER(txt), i.p) FROM i)` | 1 |
| 2a login not anchored, 'copilot-fan' | `'copilot-fan'` | `REGEXP_LIKE(LOWER(txt), '(copilot\|copilot-swe-agent\\[bot\\])')` | 1 |
| 2b login anchored ^...$, 'copilot-fan' | `'copilot-fan'` | `REGEXP_LIKE(LOWER(txt), '^(copilot\|copilot-swe-agent\\[bot\\])$')` | 0 |
| 2c login anchored, 'Copilot' | `'Copilot'` | `REGEXP_LIKE(LOWER(txt), '^(copilot\|copilot-swe-agent\\[bot\\])$')` | 1 |
| 3a [bot] escaped (\\[bot\\]), the real login | `'devin-ai-integration[bot]'` | `REGEXP_LIKE(LOWER(txt), '^devin-ai-integration\\[bot\\]$')` | 1 |
| 3b [bot] NOT escaped, the real login | `'devin-ai-integration[bot]'` | `REGEXP_LIKE(LOWER(txt), '^devin-ai-integration[bot]$')` | 0 |
| 3c [bot] NOT escaped, another name 'devin-ai-integrationb' | `'devin-ai-integrationb'` | `REGEXP_LIKE(LOWER(txt), '^devin-ai-integration[bot]$')` | 1 |
| 3d [bot] escaped, another name 'devin-ai-integrationb' | `'devin-ai-integrationb'` | `REGEXP_LIKE(LOWER(txt), '^devin-ai-integration\\[bot\\]$')` | 0 |
| 4a LF: trailer on line 3, 'm' flag | `'fix\n\nCo-authored-by: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 1 |
| 4b LF: same without 'm' | `'fix\n\nCo-authored-by: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b')` | 0 |
| 4c LF: in the middle of a sentence, 'm' flag | `'We paired; co-authored-by: Claude <x> helped'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 0 |
| 5a CRLF: trailer on line 3, 'm' flag | `'add\r\n\r\nCo-authored-by: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 1 |
| 5b CRLF: same without 'm' | `'add\r\n\r\nCo-authored-by: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b')` | 0 |
| 6a JSON-string body (quotes and the 2 characters backslash-n), 'm' pattern alone | `'\"add\\n\\nCo-authored-by: Claude <x>\"'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 0 |
| 6b JSON-string body, pattern (^"?\|\\n) | `'\"add\\n\\nCo-authored-by: Claude <x>\"'` | `REGEXP_LIKE(LOWER(txt), '(^\"?\|\\\\n)co-authored-by:[ \\t]*claude\\b')` | 1 |
| 6c JSON-string body, trailer on the first line (after the opening quote) | `'\"Co-authored-by: Claude <x>\\nmore\"'` | `REGEXP_LIKE(LOWER(txt), '(^\"?\|\\\\n)co-authored-by:[ \\t]*claude\\b')` | 1 |
| 6d JSON-string body, in the middle of a sentence | `'\"We paired; co-authored-by: Claude <x>\"'` | `REGEXP_LIKE(LOWER(txt), '(^\"?\|\\\\n)co-authored-by:[ \\t]*claude\\b')` | 0 |
| 6e real LF text, JSON pattern alone (the real-line-break shape is not caught by it) | `'fix\n\nCo-authored-by: Claude <x>'` | `REGEXP_LIKE(LOWER(txt), '(^\"?\|\\\\n)co-authored-by:[ \\t]*claude\\b')` | 0 |
| 7a word end: 'Claude Code' matches claude\\b | `'Co-authored-by: Claude Code <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 1 |
| 7b word end: 'Claudeville' does not | `'Co-authored-by: Claudeville <x>'` | `REGEXP_LIKE(LOWER(txt), '^co-authored-by:[ \\t]*claude\\b', 'm')` | 0 |
| 8a Made-with: first line in capitals (MADE-WITH: cursor) | `'MADE-WITH: cursor\n\nAdd thing'` | `REGEXP_LIKE(LOWER(txt), '^made-with:[ \\t]*cursor\\b', 'm')` | 1 |
| 8b made-with: cursor inside a sentence | `'This was made-with: cursor earlier\nbut it is not a trailer'` | `REGEXP_LIKE(LOWER(txt), '^made-with:[ \\t]*cursor\\b', 'm')` | 0 |

Reading: 1a/1c = 0 and 1b/1d = 1 (case: lower the text first); 2a = 1 and 2b = 0 (anchors); 3a = 1, 3b = 0, 3c = 1, 3d = 0 (escape of `[bot]`); 4a = 1, 4b = 0, 4c = 0 (line start, `'m'` flag); 5a = 1 and 5b = 0 (CRLF); 6a = 0, 6b = 1, 6c = 1, 6d = 0, 6e = 0 (the two shapes of the body); 7a = 1, 7b = 0 (word end); 8a = 1, 8b = 0 (`Made-with`).

## Appendix B: mutation tests (section 5-4 of the U2 specification)

Each row: the SQL was changed in one place (a copy in a scratch directory; the repository file was not touched), and the two tests of U2 were run on it (`include_own_markers` 0 and 1, 572 values compared each). A mutant is detected when the number of mismatches is above 0.

| # | Change | Mismatches, own markers off | Mismatches, own markers on | First mismatch (own markers off) |
|---|---|---|---|---|
| M1 | m2 (first commit) removed | 22 | 22 | `time_to_first_review mode:cloud_agent prs: expected 10 got 7` |
| M2 | tool groups exclusive (one tool per PR) | 33 | 33 | `time_to_first_review tool:cursor prs: expected 6 got 5` |
| M3 | D2: first review = APPROVED / CHANGES_REQUESTED only | 13 | 13 | `time_to_first_review tool:claude n_defined: expected 5 got 3` |
| M4 | D5 removed (no merge-time fallback) | 13 | 14 | `time_in_review tool:claude n: expected 5 got 3` |
| M5 | LOWER() removed everywhere | 144 | 132 | `time_to_first_review tool:claude prs: expected 5 got 0` |
| M6 | start-of-line condition removed | 36 | 33 | `time_to_first_review tool:claude prs: expected 5 got 6` |
| M7 | ^...$ anchors removed from the login/name patterns | 29 | 27 | `time_to_first_review tool:copilot prs: expected 2 got 3` |
| M8 | [bot] escape removed | 182 | 158 | `time_to_first_review tool:coderabbit prs: expected 3 got 0` |
| M9 | YEARWEEK mode 3 -> 0 | 18 | 21 | `throughput week:202610 merged: expected 6 got 9` |
| M10 | D3 removed (author's own review counted) | 4 | 4 | `time_to_first_review tool:everything_else mean_minutes: expected 70.357143 got 66.4286` |
| M11 | m6: DIFF removed | 26 | 26 | `time_to_first_review tool:coderabbit prs: expected 3 got 2` |
| M12 | ai_used = ai_assisted only | 16 | 14 | `time_to_first_review mode:ai_used prs: expected 18 got 9` |

