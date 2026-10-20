# ADR 0001: Metric definitions and agent identification

Status: accepted (2026-10-20, revised the same day). Scope: MySQL SQL and synthetic tests.

Quotes below are marked `> "..."` and are copied word for word from the source named after them.
`DevLake@beta18` means the apache/devlake tag `v1.0.3-beta18`; links to it are permalinks of the form
`https://github.com/apache/devlake/blob/v1.0.3-beta18/<path>#L<n>`.

## Context

Question: inside one repository, do pull requests made by AI coding agents need more human review than pull requests made by people, and does it differ by agent?

Apache DevLake already holds the data in its domain layer: `pull_requests`, `pull_request_comments`, `accounts` and `pull_request_assignees`. No dashboard in DevLake groups PRs by agent and shows the human review burden. The feature request [#8713](https://github.com/apache/devlake/issues/8713) (closed as stale on 2026-07-05) asks for the first half of this ("PRs assisted by AI, PRs not assisted by AI").

DevLake does not give a median function in MySQL, has no "ready for review" time, and has no automated test for dashboard SQL ([PR #9226](https://github.com/apache/devlake/pull/9226): "There are no automated tests for dashboard SQL").

## Decision

Five metrics are computed directly from `pull_requests` and `pull_request_comments`, per agent group and per group of PRs without an agent marker.

1. **Time to first human reaction (minutes).** From PR creation to the first comment (any of NORMAL, DIFF, REVIEW) written by someone who is not the PR author, is not a bot and is not an unsent review. The paper [arXiv:2602.17084](https://arxiv.org/html/2602.17084) defines
   > "the median time elapsed from PR creation to the first reviewer comment"
   The exclusion of bots and the author follows [github-community-projects/issue-metrics](https://github.com/github-community-projects/issue-metrics) (README):
   > "comments by issue/pull request author's and comments by bots are excluded"
   DevLake's own first-review query does the same with `AND COALESCE(acc2.is_bot, false) = false` ([change_lead_time_calculator.go#L253](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/dora/tasks/change_lead_time_calculator.go#L253)); the author exclusion is on the line above it (`#L252`).
   A second value, **1B**, also removes the assignees of the PR (`pull_request_assignees`). Reason: for agent PRs the person who asked for a change is often the assignee, which would count as "human review" for agents but not for people.
   **Who is a bot.** An account is a bot when `accounts.is_bot = 1` **or** its `user_name` is one of the agent bot names used in identification rules 1 and 2 (`Copilot`, `copilot-swe-agent[bot]`, `devin-ai-integration[bot]`). DevLake sets `is_bot` when the GitHub user type is "Bot" or the login ends in "[bot]" ([account_convertor.go#L150](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go#L150)). The user type is read from `/users/{login}`, and `GET /users/Copilot` answers 404, so on the REST path the account `Copilot` is stored with `is_bot = 0` and has no `[bot]` suffix. Without the name list, comments by Copilot would count as a human reaction. The test data keeps `Copilot` at `is_bot = 0` to cover this.
2. **Review burden (count).** Number of comments per PR, all three types, unsent reviews removed. A diff comment and the review it belongs to are both counted, as in the definition of [arXiv:2601.00753v2](https://arxiv.org/html/2601.00753v2)
   > "Sum of all reviews and comments, including bot messages"
   The same count without bot comments (same bot rule as above) is given next to it (2H).
3. **Changes requested.** Share of PRs with at least one `type = 'REVIEW'` and `status = 'CHANGES_REQUESTED'` comment. [arXiv:2604.03196](https://arxiv.org/html/2604.03196) defines this state as
   > "explicit request for modifications"
   DevLake stores the GitHub review state unchanged ([pr_review_convertor.go#L92](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_convertor.go#L92)). GitHub gives a dismissed review the state `DISMISSED`, so **a dismissed "changes requested" is not counted**.
4. **PR size.** `additions + deletions` ([pull_request.go#L60-L61](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request.go#L60-L61)).
5. **Outcome.** Count of PRs with `status` MERGED, CLOSED, OPEN ([pull_request.go#L29-L31](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request.go#L29-L31)).

Medians use the method of DevLake's own dashboards: the largest value among rows with `percent_rank() <= 0.5` (`max(days_deployed) as median_number_of_deployment_days_per_week` with `ranks <= 0.5`, [DORA.json#L236](https://github.com/apache/devlake/blob/v1.0.3-beta18/grafana/dashboards/mysql/DORA.json#L236)). With an even count this is the lower of the two middle values. This is stated on the dashboard.

**Unsent reviews.** DevLake drops reviews in the state `PENDING` when it extracts them: REST [pr_review_extractor.go#L72](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_extractor.go#L72) (`if body.State == "PENDING" || body.User == nil {`), GraphQL [pr_extractor.go#L101](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_extractor.go#L101) (`if apiPullRequestReview.State != "PENDING" {`). On data imported by these plugins no such row exists in `pull_request_comments`. The SQL still removes rows with `type = 'REVIEW'` and `status = 'PENDING'` from every metric as a safeguard (data that came in another way, an older import, a changed plugin); the test fixture contains such a row for that reason. A converter-level fact behind the safeguard: a review without a submit time is stored without a time (`if githubPullRequestReview.GithubSubmitAt != nil {`, [pr_review_convertor.go#L94](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_convertor.go#L94)).

**Agent identification** (first match wins; the SQL in `sql/mysql/agent_review_burden.sql` keeps the same order):

| Order | Signal | Group |
|---|---|---|
| 1 | login of the PR author's account (`accounts.user_name`; `pull_requests.author_name` only when there is no account row) is `Copilot` or `copilot-swe-agent[bot]` | copilot |
| 2 | login of the PR author's account (as in rule 1) is `devin-ai-integration[bot]` | devin |
| 3-6 | `head_ref` starts with `copilot/`, `codex/`, `cursor/`, `devin/` | copilot, codex, cursor, devin |
| 7 | `head_ref` starts with `claude/`, or the PR body contains `Co-Authored-By: Claude` (case-insensitive) | claude |
| 8 | author is a bot (see "Who is a bot" above) | other_bot (not part of "no marker") |
| 9 | none of the above | no_marker |

Because the first match wins, a PR from a `copilot/` branch whose body also carries a Claude mark is counted as copilot (rule 3 before rule 7); the fixture covers this.

Sources: bot author names and the Claude body mark come from the search conditions of [arXiv:2507.15003v1](https://arxiv.org/html/2507.15003v1), which list
> "Co-Authored-By: Claude"
as a signal in the PR body. The Claude branch prefix is the default of Anthropic's [claude-code-action](https://github.com/anthropics/claude-code-action/blob/main/action.yml) (input `branch_prefix`: `defaults to 'claude/'`). The two names used for Copilot differ because REST and GraphQL report it differently: on the GraphQL path `pull_requests.author_name` is the login without `[bot]` (`copilot-swe-agent`), while the account row of the PR author has the account's own login (`Copilot`). Rules 1 and 2 therefore read the login of that account, and `pull_requests.author_name` only when there is no account row (ADR 0002, A1; found on a real DevLake in U4).

The group "no marker" is not called "human-only PRs": a person can ask `@copilot` to change a person's PR, and some agents leave no mark.

## Alternatives considered

- **Use `project_pr_metrics`.** Rejected. It covers merged PRs only, and the setting added by [PR #9229](https://github.com/apache/devlake/pull/9229) removes rows (the PR description says "Only `project_pr_metrics` is affected"); "closed without merge" could not be counted.
- **Count review comments only, not NORMAL comments.** Rejected for the default. DevLake's existing first-review time counts any comment, and [discussion 8317](https://github.com/apache/devlake/discussions/8317) shows that users care about which is counted ("PR pickup time is considering any comment rather than review comment"). The dashboard text will say which comments are counted.
- **Detect agents by the `claude-code-assisted` label.** Rejected: the label is only on merged PRs, which biases outcome.
- **Compute the median with a MySQL user function or by averaging.** Rejected: DevLake's own dashboards use the `percent_rank` method; an average is pulled by single large values.
- **Trust `accounts.is_bot` alone.** Rejected: see "Who is a bot"; Copilot is not flagged on the REST path.
- **Check only with real data.** Rejected as the first check: no ground truth. Synthetic data with hand-computed values comes first (this repository); real-data comparison is a later step.

## Consequences

- Every number can be reproduced by `python tests/run_u1.py` (a MySQL 8.4 container started with the character set and collation of DevLake's compose file, `utf8mb4` / `utf8mb4_bin`, [docker-compose-dev-mysql.yml#L33](https://github.com/apache/devlake/blob/v1.0.3-beta18/docker-compose-dev-mysql.yml#L33); no network except pulling the image once). With the case-sensitive collation the body mark is matched after `LOWER()`; the fixture has a PR whose mark is written in lower case. The fixture contains the cases that break naive SQL: unsent review, diff comment plus its review, a PR with no human comment, comments at the same minute, an assignee who is also the first commenter, bots of other kinds, a PR marked only in the body, a non-flagged Copilot account that comments on someone else's PR, and a PR whose branch and body point to two different agents.
- Time to first reaction includes the time a PR was a draft; DevLake has no "ready for review" time. Agent PRs are often opened as drafts, so the agent side reads longer.
- Branch prefixes are a guess. A person can open a PR from a `codex/` or `cursor/` branch.
- **Finding for metric 1B.** In DevLake `v1.0.3-beta18` the table `pull_request_assignees` is written by the GitLab converter ([mr_assignee_convertor.go#L67](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go#L67)); the [GitHub plugin task list](https://github.com/apache/devlake/tree/v1.0.3-beta18/backend/plugins/github/tasks) has no PR assignee converter (only `issue_assignee_convertor.go`), and a code search for `PullRequestAssignee` in the repository at that tag finds no other writer. On data imported from GitHub, 1B will therefore equal 1 until that table is filled. The SQL is correct for the table as defined; the dashboard text must say this.
- **Size on the REST path.** The REST collector lists PRs with `repos/{repo}/pulls` ([pr_collector.go#L79](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_collector.go#L79)), a list that carries no line counts, and fetches the detail only for the PRs selected by `state != 'closed' OR merged = false` ([pr_collector.go#L109-L115](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_collector.go#L109-L115)). Metric 4 can therefore be 0 for PRs whose detail was not fetched. The real-data step counts the PRs with `additions + deletions = 0` before the size metric is shown.
- `is_bot` and the review state are only filled by the GitHub plugin; the dashboard is GitHub-only.
- No per-person values are shown.
