# ADR 0002: Metrics and AI-tool groups defined as Swarmia defines them

Status: accepted (2026-10-20). Scope: `sql/mysql/ai_impact_parity.sql`, synthetic tests, MySQL only.

Quotes are written `> "..." (path L<n>; URL; retrieved <date>)` and are copied word for word from the saved copy of the page. The paths are relative to the
research folder `research/v3/` (kept outside this repository). **Every citation carries the URL and the date retrieved that are written on line 1 of the cited saved file**, so that a
reader who does not have the research folder can fetch the page again (the page may have changed since; the saved copy is the one that was quoted). The line numbers are the line numbers of the saved file.
`upstream/beta18/*.txt` are single files of apache/devlake at the tag `v1.0.3-beta18`; their line 1 is a heading of the form
`<path in the repository> @ v1.0.3-beta18 (apache/devlake) retrieved <date>`, so the line numbers are one more than in the original file, and the URL given is
`https://github.com/apache/devlake/blob/v1.0.3-beta18/<that path>`. Pages used:

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
> "until the first review is submitted" (vendor/swarmia_def_time_to_review.txt L16; https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review; retrieved 2026-10-20)

> "Reviews completed by bots are excluded from the aggregate" (vendor/swarmia_def_time_to_review.txt L27; https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review; retrieved 2026-10-20)

> "Not defined for pull requests that have not been reviewed." (vendor/swarmia_def_data_model_pull_request.txt L248; https://help.swarmia.com/data-model/entities/pull-request; retrieved 2026-10-20)

Here: from the time the PR was opened (D1) to the first `REVIEW` row of a person who is not a bot and not the PR author (D3), in any state
(D2). A PR without such a review is not counted; the metric gives both the number of PRs with a value and the number of PRs in the group.
Differences: the start is not "review requested" (DevLake has no such time); NORMAL comments and line comments (`DIFF`) do not count, only
review rows; a person's review in the state `COMMENTED` or `DISMISSED` ends the wait (D2, an interpretation).

**`time_in_review`** (merged PRs only)
> "from the first review request (or from when the pull request was opened, if none) to the final approval." (vendor/swarmia_def_pr_cycle_time.txt L13; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20)

> "review time is measured from the review request until the merge." (vendor/swarmia_def_time_to_review.txt L23; https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review; retrieved 2026-10-20)

Here: from the PR being opened (D1) to the last `APPROVED` review before the merge by a person who is not a bot and not the author (D9);
without such an approval, to the merge (D5). Differences: the start (D1); a PR opened as a draft shows a longer time than in Swarmia.

**`pr_cycle_time`** (merged PRs only)
> "from the first commit or from when the pull request is opened, whichever happens first, to the first review request." (vendor/swarmia_def_pr_cycle_time.txt L12; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20)

> "from the final approval to once the pull request is merged." (vendor/swarmia_def_pr_cycle_time.txt L14; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20)

> "The average PR cycle time for a given time period would be the cycle time of all pull requests in that time period, averaged." (vendor/swarmia_def_pr_cycle_time.txt L28; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20)

> "We consider all PRs the same, regardless of the draft state." (vendor/swarmia_def_pr_cycle_time.txt L81; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20)

Here: from the earlier of the first commit (D10) and the PR being opened, to the merge. The sum of the three parts of the Swarmia text is the
same span; it is computed as one span. Draft PRs are not treated differently (D4). A PR without a row in `pull_request_commits` starts at the time it was opened.

**`throughput`**
> "the number of pull requests you get through as a team over a selected period of time." (vendor/swarmia_def_throughput.txt L6; https://help.swarmia.com/definitions/throughput; retrieved 2026-10-20)

> "PRs merged (throughput)" (vendor/swarmia_impact_pr.txt L80; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics; retrieved 2026-10-20)

Here: the number of merged PRs, in the period of the dashboard (by the merge time, D12), and per week (D6, `YEARWEEK(merged_date, 3)`,
Monday first). The weekly rows (`week:<YEARWEEK>`) are split by mode; the rows `tool:<name>|week:<YEARWEEK>` give the PRs of one tool merged in
that week (only the combinations that have at least one PR; a PR in two tools is in both rows). Differences: the example in the throughput definition counts PRs "closed"
(vendor/swarmia_def_throughput.txt L10; https://help.swarmia.com/definitions/throughput; retrieved 2026-10-20); the AI impact page calls the number "PRs merged", and that is what is counted.

**`batch_size`**
> "Batch size is calculated by the lines of code changed (lines added + lines removed) in a given pull request." (vendor/swarmia_def_batch_size.txt L10; https://help.swarmia.com/definitions/batch-size; retrieved 2026-10-20)

> "Swarmia automatically cleans up the total change count of some commonly used generated files." (vendor/swarmia_def_batch_size.txt L14; https://help.swarmia.com/definitions/batch-size; retrieved 2026-10-20)

Here: `additions + deletions`, mean and median, and the share of PRs under 200, from 200 to 499, and 500 and over. The buckets are the
benchmarks of the page (vendor/swarmia_def_batch_size.txt L30-L32; https://help.swarmia.com/definitions/batch-size; retrieved 2026-10-20: "Great", "Good", "Needs attention"). **Generated files are not removed**, so
a PR with a large lock file reads larger than in Swarmia. DevLake has a scope-config field for this,
`PrSizeExcludedFileExtensions` (upstream/beta18/github_scope_config.go.txt L53; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/scope_config.go; retrieved 2026-10-20). How DevLake applies it to the stored `additions` and `deletions` was not
verified; the SQL reads the stored columns as they are.

**`cloud_agent_outcomes`**
> "show the raw number of AI cloud agent pull requests." (vendor/swarmia_agent.txt L94; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics; retrieved 2026-10-20)

Here: for the mode `cloud_agent` (row `mode:cloud_agent`): the number of PRs, and how many are MERGED, CLOSED and OPEN. PRs and CLOSED and OPEN are by the time the PR was
opened; MERGED is by the merge time (D12), so the three do not have to add up to the number of PRs. The rows `mode:cloud_agent|tool:<name>` give the same four
numbers for the cloud agent PRs of one tool, that is the PRs that have the mark m1 or m2 of that tool (not every PR in the tool's group: a human PR with a Claude
co-author trailer is in `tool:claude` but is not a cloud agent PR of Claude). A PR whose m1 and m2 name two tools is in both rows, so the tool rows can add up to more than the
first row. Swarmia's "merge percentage" is not computed.

**`pr_classification`** and **`diagnostics`** are not Swarmia metrics. The first gives, per PR, the marks that hit, the tools and the modes, so that
the classification can be tested directly. The second gives `check:prs_without_commit_message` and `check:tool_group_total_minus_pr_total`.

### Marks and groups

> "Any of its commits were authored or co-authored by an AI tool (high confidence)" (vendor/swarmia_detect.txt L76; https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters; retrieved 2026-10-20)

> "Any of its commits has the Made-with: Cursor Git trailer (high confidence)" (vendor/swarmia_detect.txt L77; https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters; retrieved 2026-10-20)

> "Swarmia attributes a PR to a cloud agent if the PR or its first commit has been authored by a cloud agent linked to one of the AI tools" (vendor/swarmia_detect.txt L82; https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters; retrieved 2026-10-20)

> "Swarmia attributes a PR to a review agent if it has reviews from a built-in review agent" (vendor/swarmia_detect.txt L86; https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters; retrieved 2026-10-20)

> "GitHub shows cursoragent as the author of the first commit" (vendor/swarmia_agent.txt L126; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics; retrieved 2026-10-20)

That sentence names the GitHub account. The git name and e-mail that DevLake stores for such a commit were read from public commits (docs/agent_identities.md, table B):
name `Cursor Agent`, e-mail `cursoragent@cursor.com`.

> "The first commit in this PR was authored by Claude" (vendor/swarmia_agent.txt L127; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics; retrieved 2026-10-20)

> "matching the author of review comments against known email addresses and GitHub login patterns" (vendor/swarmia_def_review_agents.txt L63; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20)

> "If the agent posts a review comment on the pull request, Swarmia counts it as a review-agent review in either case." (vendor/swarmia_def_review_agents.txt L67; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20)

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
  > "A single pull request can be associated with multiple AI tools and modes." (vendor/swarmia_impact_pr.txt L99; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics; retrieved 2026-10-20)

  `check:tool_group_total_minus_pr_total` shows the amount of overlap. U1's `other_bot` (a bot that is not an agent, for example dependabot) is in `everything_else`.
- **Mode groups.** `cloud_agent` = m1 or m2. `ai_assisted` = m3, m4 or m5 (and x1 or x2 when own markers are on). `review_agent` = m6. `ai_used` = any of the three (D7).
  `everything_else` = none. A cloud agent PR is also `ai_assisted` when m3 hits (D14); the page allows the overlap (L99 above).
  > "AI used: AI-assisted PRs (based on the tools and modes you select) vs everything else." (vendor/swarmia_impact_pr.txt L90; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics; retrieved 2026-10-20)

### Where the source text does not decide (D1 to D14)

Rows marked **interpretation** are my reading of the text. All other rows are the rule that was fixed instead of a rule in the source.

| # | Not decided | What is done | Reason |
|---|---|---|---|
| D1 | the start of the wait (time the review is requested) | the time the PR was opened (`created_date`) | DevLake has no time of a review request and no "ready for review" time (see "DevLake data"). The text of Time in review uses the time the PR was opened when there is no request: "(or from when the pull request was opened, if none)" (vendor/swarmia_def_pr_cycle_time.txt L13; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20). Using it for Time to first review as well is an **extension**: Swarmia's own time to first review is "after being considered ready for review" (vendor/swarmia_def_data_model_pull_request.txt L248; https://help.swarmia.com/data-model/entities/pull-request; retrieved 2026-10-20), so a PR that was a draft for a while reads longer here |
| D2 | does a `COMMENTED` review end Time to first review | **interpretation**: yes. The first submitted review ends it, whatever its state | L16 names "an approval or request for changes" in a parenthesis, but L18 says "before receiving any feedback" (vendor/swarmia_def_time_to_review.txt L18; https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review; retrieved 2026-10-20), so a review with comments is read as feedback |
| D3 | reviews by the PR author | not counted | not in the Swarmia text. GitHub's issue-metrics excludes them: "comments by issue/pull request author's and comments by bots are excluded" (upstream/issue_metrics_README.md L32; https://github.com/github-community-projects/issue-metrics; retrieved 2026-10-20). DevLake's DORA code excludes them too: `(pr2.author_id IS NULL OR pr2.author_id = '' OR prc2.account_id != pr2.author_id)` (upstream/beta18/change_lead_time_calculator.go.txt L253; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/dora/tasks/change_lead_time_calculator.go; retrieved 2026-10-20). U1's metric 1 does the same |
| D4 | draft period | not treated differently | for cycle time this is the text: "We consider all PRs the same, regardless of the draft state." (vendor/swarmia_def_pr_cycle_time.txt L81; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20). For time to first review it becomes the difference in D1 |
| D5 | merged without an approval | the end of Time in review is the merge | "In these situations, review time is measured from the review request until the merge." (vendor/swarmia_def_time_to_review.txt L23; https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review; retrieved 2026-10-20) |
| D6 | the weeks of throughput | the week of the merge time, Monday first, `YEARWEEK(merged_date, 3)`; the total of the dashboard period is given as well | the text says only "over a selected period of time" (vendor/swarmia_def_throughput.txt L6; https://help.swarmia.com/definitions/throughput; retrieved 2026-10-20) |
| D7 | what "AI used" is | **interpretation**: a PR that is in any mode (`cloud_agent`, `ai_assisted`, `review_agent`) | the text: "AI-assisted PRs (based on the tools and modes you select)" (vendor/swarmia_impact_pr.txt L90; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics; retrieved 2026-10-20); read as the value when all modes are selected |
| D8 | mean or median | both are given; the comparison with Swarmia is the mean | the text says "averaged" (vendor/swarmia_def_pr_cycle_time.txt L28; https://help.swarmia.com/features/metrics/pull-request-cycle-time; retrieved 2026-10-20); the median is added to match U1 and the DevLake dashboards |
| D9 | which approval ends Time in review | the last `APPROVED` before the merge, by a person who is neither the author nor a bot (D11). A dismissed approval has the GitHub state `DISMISSED`, so it is not `APPROVED` | **interpretation**: "the final approval" (L13) is read as "before the merge"; bots are left out to match L27, which leaves bots out of Time to first review (**interpretation**) |
| D10 | the first commit | the smallest `pull_request_commits.commit_authored_date`; if several commits have that time, m2 hits when **any one** of them is an agent | DevLake takes the same minimum (upstream/beta18/change_lead_time_calculator.go.txt L207-L211; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/dora/tasks/change_lead_time_calculator.go; retrieved 2026-10-20, `batchFetchFirstCommits` at L197), orders the rows by `pull_request_id, commit_authored_date` only (L215), and then keeps **one** commit per PR: "Only keep the first commit if multiple commits have the same timestamp" (upstream/beta18/change_lead_time_calculator.go.txt L225; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/dora/tasks/change_lead_time_calculator.go; retrieved 2026-10-20). Which one of several commits with the same time is kept is not decided by the code. This SQL does not pick one: m2 hits if any commit with the smallest time is an agent. **Difference:** DevLake's own "first commit" is one commit, this SQL looks at all commits of that time. The tie rule is my decision (**interpretation**) |
| D11 | what a bot is | an account with `accounts.is_bot = 1`, or whose name is one of U1's agent bot names, or whose login matches a login row of `identities` (fields `pr_author`, `review_author`) | widens U1's rule: a review agent such as `coderabbitai[bot]` can be stored with `is_bot = 0` |
| D12 | which time the period filter uses | the merge time for throughput, pr_cycle_time, time_in_review and the MERGED count of cloud_agent_outcomes; the time the PR was opened for everything else | **interpretation**: a metric that is defined by the merge is cut by the merge. The throughput example says "closed" (vendor/swarmia_def_throughput.txt L10; https://help.swarmia.com/definitions/throughput; retrieved 2026-10-20), the AI impact page says "PRs merged" (vendor/swarmia_impact_pr.txt L80; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-impact-on-pr-metrics; retrieved 2026-10-20) |
| D13 | which rows of the review agent count in m6 | rows with `type` `REVIEW` or `DIFF` | the text: "posts a review comment" ... "counts it as a review-agent review" (vendor/swarmia_def_review_agents.txt L67; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20). A review agent that only writes a summary into the PR description (Bugbot: "posts a summary to the PR description", vendor/swarmia_def_review_agents.txt L15; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20) cannot be seen; that is a difference |
| D14 | does a cloud agent PR also count as ai_assisted | **interpretation**: yes, when m3 hits. The modes overlap | the rule of L76 is applied as it is written; the overlap is allowed by L99 |

### Text matching

DevLake's database collation is `utf8mb4_bin` (docker-compose-dev-mysql.yml, as in ADR 0001), so a match is case-sensitive unless the text is lowered first.
The probes of Appendix A were run on `mysql:8.4` with that collation; what they show is built into the SQL:

- **Case.** Every match is on `LOWER(text)` with a lower-case pattern (probe 1a: without it, `Co-Authored-By: Claude` does not match; 1c: a pattern read from a CTE column does not change that).
  The text of a commit is first converted with `CONVERT(... USING utf8mb4)` because the real column is a `longblob` (A2 above); the probes of Appendix A were run on a text column.
- **PR author.** m1 matches the login of the account of the PR author, not `pull_requests.author_name` (A1 above).
- **Logins and names** are anchored with `^...$` (probe 2a: `copilot-fan` matches an unanchored `copilot`). A literal `[bot]` is written `\\[bot\\]` in the SQL file (the first level is MySQL's
  string escape); unescaped, `[bot]` is a character class (probes 3b, 3c).
- **Trailers** (`Co-authored-by:`, `Made-with:`) count only at the start of a line, in two shapes, because a message can be in two shapes:
  real line breaks (`'m'` flag, LF and CRLF, probes 4a, 5a), or DevLake's JSON-string body (below), which has the quotes and the two characters `\n` and no line break
  (probes 6a to 6d): `(^"?|\\\\n)co-authored-by:...`. A trailer in the middle of a sentence matches neither (probes 4c, 6d, 8b).

### DevLake data (what the SQL has to live with)

`pull_request_commits` has the commit author name and e-mail and no message. The message is in `commits`, which the default GitHub import does not
always fill:

> "EnabledByDefault: false" (upstream/beta18/github_commit_convertor.go.txt L38; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/commit_convertor.go; retrieved 2026-10-20)

> "Message json.RawMessage" (upstream/beta18/github_pr_commit_extractor.go.txt L68; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_commit_extractor.go; retrieved 2026-10-20)

> "grc.repo_id = ? AND grc.connection_id = ?" (upstream/beta18/github_commit_convertor.go.txt L75; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/commit_convertor.go; retrieved 2026-10-20)

The first line says the conversion into `commits` is off by default. The second shows that, on the REST path, the message is kept as JSON (the value
keeps its quotes and the two-character `\n`). The third is a join of `_tool_github_commits` with `_tool_github_repo_commits` on the repository (L75 above: the conversion reads only the commits that have a row there). **An inference from the
saved source, not run:** if the GraphQL import does not fill `_tool_github_repo_commits` (the saved files do not show which tool-layer tables the GraphQL path fills), its commits are not
converted into `commits`. I did not run the import to check this. How DevLake's git extractor (gitextractor) fills `commits` was not verified in the saved sources either; U4 measures it on real data. The SQL therefore:

1. joins `commits` with a `LEFT JOIN`;
2. keeps a PR in every count when its message is missing;
3. matches both shapes of the message (above);
4. gives `check:prs_without_commit_message`, the number of PRs for which no message could be read.

A review is stored with type `REVIEW`, the state of GitHub in `status` and, for a review without a submit time, no time
(upstream/beta18/pr_review_convertor.go.txt L92-L96; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_convertor.go; retrieved 2026-10-20). Unsent (`PENDING`) reviews are dropped at import
(upstream/beta18/github_pr_review_extractor.go.txt L73; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_extractor.go; retrieved 2026-10-20: `if body.State == "PENDING" || body.User == nil {`; upstream/beta18/graphql_pr_extractor.go.txt L102 (https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_extractor.go, retrieved 2026-10-20):
`if apiPullRequestReview.State != "PENDING" {`) and, as in U1, removed again by the SQL as a safeguard.
The time a review was **requested** is in no DevLake table that was searched (beta18, plugins `github` and `github_graphql`, the domain-layer `code` models; searched for
`review_request|requested_reviewer|timeline`). The GraphQL query asks for `reviewRequests` (upstream/beta18/graphql_pr_collector.go.txt L106; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_collector.go; retrieved 2026-10-20) but it carries no time.

### What a real DevLake showed (U4): two corrections, A1 and A2

U4 (docs/validation/u4-real-data.md) ran this SQL on a real DevLake v1.0.3-beta18 (two public repositories, 297 PRs of 2026-09) and compared every PR with GitHub's raw data.
It found two shapes of the real tables that the synthetic tests did not have. Both were in the SQL, both are corrected, and both have a scene in the fixture that fails without the correction.

**A1: the PR author is read from `accounts`, not from `pull_requests.author_name`.**

- *Source.* On the GraphQL path the extractor stores the login that the GraphQL answer gives: `githubPull.AuthorName = author.Login` (upstream/beta18/graphql_pr_extractor.go.txt L192;
  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_extractor.go; retrieved 2026-10-20). The account row is built from the REST user: `isBot := githubUser.Type == "Bot" || strings.HasSuffix(githubUser.Login, "[bot]")`
  and `UserName: githubUser.Login` (upstream/beta18/github_account_convertor.go.txt L151 and L157;
  https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go; retrieved 2026-10-20). The two logins are not the same string for a bot.
- *Real data (SELECT on the DevLake database `lake`, 2026-10-21, 1,604 rows of `pull_requests`):*

  ```sql
  SELECT p.author_name, a.user_name, a.is_bot, COUNT(*) n
  FROM pull_requests p LEFT JOIN accounts a ON a.id = p.author_id
  WHERE p.author_name IN ('cursor','claude','copilot-swe-agent','copilot','Copilot')
  GROUP BY 1,2,3 ORDER BY 1,2,3;
  ```

  | author_name | accounts.user_name | is_bot | PRs |
  |---|---|---|---|
  | claude | claude[bot] | 1 | 25 |
  | copilot-swe-agent | Copilot | 0 | 14 |
  | cursor | cursor[bot] | 1 | 95 |

  `SELECT user_name, is_bot, COUNT(*) FROM accounts WHERE user_name LIKE '%[bot]' GROUP BY 1,2` lists, among others, `claude[bot]` (3 rows: is_bot 0, 0, 1), `copilot-swe-agent[bot]` (1 row, is_bot 0) and `cursor[bot]` (2 rows: is_bot 0, 1).
  The account of the Copilot PRs is `Copilot`, which the pattern `^(copilot|...)$` of m1 matches after `LOWER()`. No PR of the 1,604 is without an account row (`SUM(a.id IS NULL)` = 0).
  `pull_requests.author_name` is therefore the login without `[bot]`, and a pattern written for the REST form (`^cursor\[bot\]$`) never matches it: in U4, 43 PRs lost the m1 mark.
- *Correction.* `pr_base` has `author_login`: `accounts.user_name` of `pull_requests.author_id`, and `pull_requests.author_name` only when there is no account row (`CASE WHEN au.id IS NULL THEN pr.author_name ELSE au.user_name END`). m1 matches `LOWER(author_login)`.
- *Not done: a `[bot]` that is optional in the pattern, or added to `author_name`.* A person whose login is `cursor` or `claude` would then be taken for an agent. The account route keeps the exact login (`cursor[bot]`) and the type flag of GitHub.
- *U1.* Rules 1 and 2 of `agent_review_burden.sql` have the same shape (`pr.author_name IN ('Copilot', 'copilot-swe-agent[bot]')`, `pr.author_name = 'devin-ai-integration[bot]'`). On the real data the rule 1 test on `author_name` is true for 0 of the 1,604 PRs and the same test on `accounts.user_name` for 14
  (`SELECT SUM(pr.author_name IN ('Copilot','copilot-swe-agent[bot]')), SUM(a.user_name IN ('Copilot','copilot-swe-agent[bot]')), SUM(pr.author_name = 'devin-ai-integration[bot]'), SUM(a.user_name = 'devin-ai-integration[bot]') FROM pull_requests pr LEFT JOIN accounts a ON a.id = pr.author_id` gave 0, 14, 0, 0;
  the rule 2 test is 0 on both because the two repositories have no Devin PR). U1 got the same correction (CTE `pr_login`: the account first, `author_name` only without an account row). In the U4 data U1's per-PR agent groups (275 PRs) and all its group values are identical before and after the correction (the CSV files of the two runs are equal), because all 14 PRs of `copilot-swe-agent` carry a `copilot/` branch (SELECT on `head_ref`), so rule 3 gave the same group;
  the fixture `fixture_u1.sql` (P14 to P16) makes the difference visible. The expected values of `expected_u1.json` were recalculated by hand from the fixture (copilot: 5 PRs, devin: 2 PRs).

**A2: the text of a commit is a binary string.**

- *Source.* The model of the domain layer has `Message string` with no `gorm` type (upstream/beta18/commit.go.txt L34, https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/commit.go, retrieved 2026-10-20;
  an archived copy of the model in the core migration scripts has the same line: upstream/beta18/core_migrationscripts_archived_commit.go.txt L31, https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/migrationscripts/archived/commit.go, retrieved 2026-10-21).
  The synthetic schema followed that line and used `LONGTEXT` (my reading of gorm's usual MySQL type for a Go `string` without a tag, not run; marked "default" in tests/schema_mysql.sql).
- *Real data (`information_schema.columns`, `table_schema = 'lake' AND table_name = 'commits' AND column_name = 'message'`):* `data_type` = `longblob`, `column_type` = `longblob`, `character_set_name` and `collation_name` empty.
  The saved source does not say why the column is binary (a search for `blob` in `backend/core`, `impls`, `helpers`, `server` and `plugins/gitextractor` of the tag found nothing about this column); the fact comes from the database, and the SQL does not depend on the reason.
- *Effect.* `LOWER()` does nothing on a binary string and `REGEXP_LIKE` on it is case-sensitive, so the pattern `co-authored-by` did not match the line `Co-Authored-By: Claude`. On the 2,769 rows of `commits`,
  `SUM(LOCATE('co-authored-by', LOWER(message)) > 0)` = 0 and `SUM(LOCATE('co-authored-by', LOWER(CONVERT(message USING utf8mb4))) > 0)` = 1,621. In U4 the m4 mark was found for 0 of the 9 PRs that have it in GitHub's data.
- *Correction.* `pr_commit.message` is `CONVERT(cm.message USING utf8mb4)`; m4 and m5 read it with `LOWER()` and `REGEXP_LIKE` as before. `tests/schema_mysql.sql` has `commits.message LONGBLOB`, so that all tests use the real type (a string literal is stored as bytes).
  After the correction 4 of the 9 PRs are found; the other 5 have no commit message in DevLake at all (class (c) of U4: `commits` is filled by DevLake's git extractor and has 2,769 rows for 5,213 rows of `pull_request_commits`, so a message could be read for 45 of the 275 PRs opened in the period).
  That is a lack of data, not an error of the SQL, and it stays.

Scenes: `fixture_u2.sql` Q55 (the account is `cursor[bot]`, `author_name` is `cursor`: m1) and Q56 (a person's PR, the commit text `Co-Authored-By: Claude <...>` in a LONGBLOB: m4); `fixture_u1.sql` P14 (account `Copilot`, `author_name` `copilot-swe-agent`),
P15 (account `devin-ai-integration[bot]`, `author_name` `devin-ai-integration`), P16 (no account row: `author_name` is used). Mutations: Appendix B3.

### Identity list

The tool and its identities are one CTE at the start of the SQL, `identities(tool, mode, field, pattern)`. How each row was checked, and the rows that
could not be, are in `docs/agent_identities.md`. U1's rules 1 and 2 (`Copilot`, `copilot-swe-agent[bot]`, `devin-ai-integration[bot]`) are carried over.
Only values that were seen in a saved public source are in the list. The commit rows were read from public commits with `gh api search/commits`
(research/v3/upstream/identities/gh_search_commits_author_cursoragent.txt; https://api.github.com/search/commits?q=author:cursoragent&per_page=30; retrieved 2026-10-20, `gh_search_commits_committer_cursoragent.txt`, `gh_search_commits_author_claude.txt`,
`gh_search_commits_trailer_claude.txt`; the URL and the date are on line 1 of each, listed in `docs/agent_identities.md`): the git name of the Cursor agent is `Cursor Agent` (not
its login `cursoragent`) and its e-mail is `cursoragent@cursor.com`; the git name of the Claude account is `Claude`; the Claude trailer reads `Claude ...` with or without a model name. The name and e-mail
patterns bind the whole value with `^...$`. The scenario P-C2e (Q03) stays because the e-mail is confirmed. The list is an **adjustment point**: a company adds the names and addresses of its own agents and removes
what it does not want.

## Alternatives considered

- **Start Time to first review at the first review request using the PR timeline.** Rejected: no DevLake table has it (above).
- **Take one tool per PR (the first mark that hits).** Rejected: Swarmia allows several (L99), and the exclusive rule gives different groups (mutation M2).
- **Use the commit author's GitHub login.** Not possible: `pull_request_commits` has name and e-mail only. Swarmia matches accounts; here names and e-mails are matched, which is a difference that U4 has to measure.
- **Remove generated files from batch size.** Not done: the SQL has no list of files; the DevLake scope setting is named above.

## Consequences and limits

- Swarmia's AI-assisted mode has two more conditions: the label `claude-code-assisted` (vendor/swarmia_detect.txt L78; https://help.swarmia.com/features/ai-tools/ai-tool-detection-and-filters; retrieved 2026-10-20) and the 24-hour rule for authors who used a tool (L79). Neither is
  implemented. The label is not read, and the 24-hour rule needs the usage data of the vendors. **Only the kinds of marks that Swarmia calls "high confidence" are used** (L76: commit authored or co-authored by an AI tool;
  L77: the `Made-with: Cursor` trailer; the cloud agent rule of L82). **But m2 and m3 match the git name and e-mail of the commit author, not the GitHub account** (Swarmia's pages name accounts, e.g. `cursoragent` at
  vendor/swarmia_agent.txt L126 (https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics, retrieved 2026-10-20)), so a commit whose git identity differs from the account is not seen, and a person who uses the same name is.
- Review agents that write only a summary comment: **Swarmia counts CodeRabbit's summary comment.** "When CodeRabbit doesn't find anything to flag, it posts a summary comment instead of a formal review. Swarmia still counts the pull request as reviewed by CodeRabbit" (vendor/swarmia_def_review_agents.txt L75; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20).
  **This SQL does not:** m6 reads only `REVIEW` and `DIFF` rows (D13), and a summary comment that is not a formal review is not stored as a `REVIEW` row (the comment types in DevLake are `NORMAL`, `DIFF` and `REVIEW`: upstream/beta18/pull_request_comment.go.txt L44-L46 (https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_comment.go, retrieved 2026-10-20); I did not trace which type an issue comment gets), so such a PR is not in `review_agent` here. This is a difference (this SQL gives lower review_agent numbers for CodeRabbit).
  The Codex case ("no issues" is a plain comment or a reaction) is not counted by Swarmia either (vendor/swarmia_def_review_agents.txt L79-L84; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20), so there the two agree.
- Throughput per week is given per mode (`week:`) and per tool (`tool:<name>|week:`).
- Swarmia attributes a cloud agent PR to the person who started it; here the PR keeps its author and is counted in the agent's group.
- The commit identities (`Cursor Agent`, `cursoragent@cursor.com`, `Claude`, the trailer `Claude`) were read from public commits (30 items per query, GitHub's own ranking, not a random sample; `docs/agent_identities.md`, table B).
  Each company adds the names and e-mail addresses that its own agents use (adjustment point); a company that does not want the e-mail match removes that one row of the `identities` CTE.
- The numbers can be reproduced with `python tests/run_u1.py --sql sql/mysql/ai_impact_parity.sql --fixture tests/fixture_u2.sql --expected tests/expected_u2_parity.json --var include_own_markers=0`
  (and `expected_u2_own.json` with `=1`). The expected values were worked out by hand from the fixture, PR by PR; the per-PR values are in the `_per_pr` part of the
  json files. U1's metric 1 and Time to first review are checked on the same fixture (`tests/expected_u2_u1_cross.json`); scenario P-R2 shows the difference: 30 minutes (the first
  comment of any kind) against 90 (the first review).

## Appendix A: regular expression probes (section 3-3 of the U2 specification)

Run on 2026-10-20 in a throw-away container, `mysql 8.4.11, server collation utf8mb4_bin, connection collation utf8mb4_0900_ai_ci`.
The text under test is a `LONGTEXT` value (a commit text in a real DevLake is a `longblob`, converted first: A2) in a table created with the server default collation (`utf8mb4_bin`), as DevLake's tables are.
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

## Appendix B: mutation tests (section 5-4 of the U2 specification, and the review fixes)

Each row: the SQL was changed in one place (a copy in a scratch directory; the repository file was not touched), and the two tests of U2 were run on it (`include_own_markers` 0 and 1, 685 and 687 values compared). A mutant is detected when the number of mismatches is above 0 in at least one of the two tests (the own markers x1 and x2 are used only when `include_own_markers` is 1, so a change in them can only be seen by the second test: row M5-12). All 35 mutants below are detected (the run was made on the final SQL and the final fixture of that time, 54 PRs; the tests of U2 compare 685 and 687 values there, 697 and 699 values with the 56 PRs after U4).


### B1. The twelve mutations of the specification

| # | Change | Mismatches, own markers off | Mismatches, own markers on | First mismatch (own markers off) |
|---|---|---|---|---|
| M1 | m2 (first commit) removed | 28 | 28 | `time_to_first_review mode:cloud_agent prs: expected 11 got 7` |
| M2 | tool groups exclusive (one tool per PR) | 30 | 30 | `time_to_first_review tool:cursor prs: expected 9 got 8` |
| M3 | D2: first review = APPROVED / CHANGES_REQUESTED only | 13 | 13 | `time_to_first_review tool:claude n_defined: expected 6 got 4` |
| M4 | D5 removed (no merge-time fallback) | 16 | 15 | `time_in_review tool:claude n: expected 6 got 4` |
| M5 | `LOWER()` removed, **one place at a time** (12 places in the SQL, rows M5-01 to M5-12 below). Detected: 12 of 12 | (rows below) | (rows below) | |
| M5-01 | `LOWER()` removed: `acct`: the login of a bot account (`LOWER(a.user_name)`) | 8 | 8 | `time_to_first_review tool:qodo n_defined: expected 1 got 2` |
| M5-02 | `LOWER()` removed: m1: the PR author (`LOWER(p.author_login)`; `LOWER(p.author_name)` when the row was measured) | 74 | 19 | `time_to_first_review tool:copilot prs: expected 2 got 1` |
| M5-03 | `LOWER()` removed: m2: the commit author name | 23 | 23 | `time_to_first_review mode:cloud_agent prs: expected 11 got 9` |
| M5-04 | `LOWER()` removed: m2: the commit author e-mail | 18 | 18 | `time_to_first_review mode:cloud_agent prs: expected 11 got 10` |
| M5-05 | `LOWER()` removed: m3: the commit author name | 75 | 75 | `time_to_first_review tool:cursor prs: expected 9 got 8` |
| M5-06 | `LOWER()` removed: m3: the commit author e-mail | 16 | 15 | `time_to_first_review mode:ai_assisted prs: expected 13 got 12` |
| M5-07 | `LOWER()` removed: m4: the message, real-line-break shape | 77 | 77 | `time_to_first_review tool:claude prs: expected 6 got 3` |
| M5-08 | `LOWER()` removed: m4: the message, JSON-string shape | 82 | 81 | `time_to_first_review tool:claude prs: expected 6 got 4` |
| M5-09 | `LOWER()` removed: m5: the message, real-line-break shape | 16 | 16 | `time_to_first_review tool:cursor prs: expected 9 got 8` |
| M5-10 | `LOWER()` removed: m5: the message, JSON-string shape | 78 | 77 | `time_to_first_review tool:cursor prs: expected 9 got 7` |
| M5-11 | `LOWER()` removed: m6: the review author (`LOWER(c.user_name)`) | 38 | 35 | `time_to_first_review tool:coderabbit prs: expected 4 got 3` |
| M5-12 | `LOWER()` removed: x2: the PR body (`LOWER(p.description)`) | 0 | 71 | `time_to_first_review tool:claude prs: expected 7 got 6` (own markers on; the test with own markers off cannot see this place) |
| M6 | start-of-line condition removed | 34 | 38 | `time_to_first_review tool:claude prs: expected 6 got 7` |
| M7 | `^...$` anchors removed from the login/name patterns | 93 | 96 | `time_to_first_review tool:copilot prs: expected 2 got 3` |
| M8 | `[bot]` escape removed | 208 | 181 | `time_to_first_review tool:coderabbit prs: expected 4 got 0` |
| M9 | `YEARWEEK` mode 3 -> 0 | 37 | 37 | `throughput week:202610 merged: expected 6 got 11` |
| M10 | D3 removed (author's own review counted) | 4 | 4 | `time_to_first_review tool:everything_else mean_minutes: expected 67.647059 got 64.4118` |
| M11 | m6: `DIFF` removed | 30 | 27 | `time_to_first_review tool:coderabbit prs: expected 4 got 3` |
| M12 | `ai_used` = `ai_assisted` only | 17 | 15 | `time_to_first_review mode:ai_used prs: expected 24 got 13` |

### B2. The eight mutations of the review fixes (one change each; the scenario that kills it is named)

| # | Change | Scenario (fixture) | Mismatches, own markers off | Mismatches, own markers on | First mismatch (own markers off) |
|---|---|---|---|---|---|
| 1 | m6: `LOWER` removed from `REGEXP_LIKE(LOWER(c.user_name), i.pattern)` | Q46: review login `CodeRabbitAI[bot]` in capitals (`is_bot` = 1) | 38 | 35 | `time_to_first_review tool:coderabbit prs: expected 4 got 3` |
| 2 | `acct`: `LOWER` removed from the bot test of the login | Q47: review login `Qodo-Code-Review[bot]` in capitals, `is_bot` = 0 | 8 | 8 | `time_to_first_review tool:qodo n_defined: expected 1 got 2` |
| 3 | e-mail: `LOWER` removed in m2 and m3 | Q48: e-mail `CursorAgent@Cursor.com`, human name | 88 | 86 | `time_to_first_review tool:cursor prs: expected 9 got 8` |
| 3a | same, in m2 only | Q48 | 18 | 18 | `time_to_first_review mode:cloud_agent prs: expected 11 got 10` |
| 3b | same, in m3 only | Q48 | 16 | 15 | `time_to_first_review mode:ai_assisted prs: expected 13 got 12` |
| 4 | `(^"?` -> `(^` in m4 and m5 | Q50 (m4) and Q51 (m5): JSON-string body whose first line is the trailer | 80 | 77 | `time_to_first_review tool:claude prs: expected 6 got 5` |
| 4a | same, in m4 only | Q50 | 73 | 69 | `time_to_first_review tool:claude prs: expected 6 got 5` |
| 4b | same, in m5 only | Q51 | 28 | 25 | `time_to_first_review tool:cursor prs: expected 9 got 8` |
| 5 | m5: the JSON-string alternative removed | Q49 (and Q51): JSON-string body, `Made-with: Cursor` on the 3rd line | 78 | 77 | `time_to_first_review tool:cursor prs: expected 9 got 7` |
| 6 | coauthor pattern `claude\\b` -> `claude` | Q52: `Co-authored-by: Claudette` | 66 | 69 | `time_to_first_review tool:claude prs: expected 6 got 7` |
| 7 | e-mail pattern `^cursoragent@cursor\\.com$` -> `cursoragent@cursor\\.com$` | Q53: e-mail `xcursoragent@cursor.com` | 83 | 83 | `time_to_first_review tool:cursor prs: expected 9 got 10` |
| 8 | D9: `hr.created_date < p.merged_date` -> `<=` | Q54: an APPROVED at exactly the merge time | 2 | 2 | `time_in_review tool:everything_else mean_minutes: expected 300.6 got 310.2000` |

The rows 3a, 3b, 4a, 4b are the same mutation applied at one of its two places; each place alone is detected, so neither place is carried by the other.

### B3. The mutations of the corrections A1 and A2 (U4; fixture of 56 PRs and 16 U1 PRs)

Same method as B1 and B2 (a copy of the SQL in a scratch directory; the repository file was not touched). U2: the two tests with 697 and 699 values compared; U1: `python tests/run_u1.py`, 119 values compared.

| # | Change | Scenario (fixture) | Mismatches, own markers off | Mismatches, own markers on | First mismatch (own markers off) |
|---|---|---|---|---|---|
| A1 | m1 reads `pull_requests.author_name` again (`author_login` = `pr.author_name`) | Q55: account `cursor[bot]`, `author_name` `cursor` | 33 | 31 | `time_to_first_review tool:cursor prs: expected 10 got 9` |
| A2 | `CONVERT(cm.message USING utf8mb4)` removed (`cm.message`) | Q56: `Co-Authored-By: Claude` in a LONGBLOB (and every other m4/m5 scene, whose text is a LONGBLOB too) | 131 | 129 | `time_to_first_review tool:claude prs: expected 7 got 1` |

| # | Change (U1, `agent_review_burden.sql`) | Scenario | Mismatches of 119 | First mismatch |
|---|---|---|---|---|
| U1-1 | rules 1 and 2 read `pr.author_name` again | P14, P15 | 24 | `m1_first_human_reaction copilot pr_count: expected 5 got 4` |
| U1-1a | rule 1 only | P14 | 14 | `m1_first_human_reaction copilot pr_count: expected 5 got 4` |
| U1-1b | rule 2 only | P15 | 14 | `m1_first_human_reaction devin pr_count: expected 2 got 1` |
| U1-2 | no fallback to `author_name` when the account row is missing (`a.user_name AS login`) | P16 | 14 | `m1_first_human_reaction copilot pr_count: expected 5 got 4` |

All six are detected (A1, A2, U1-1, U1-1a, U1-1b, U1-2). Mutation A1 fails on the row `pr:github:GithubPullRequest:1:255` of `pr_classification` (marks, tools, modes, ai_used), mutation A2 on the row `...:256`, and both on the group values that depend on them.
