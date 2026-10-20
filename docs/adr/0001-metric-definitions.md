# ADR 0001: Metric definitions and agent identification

Status: accepted (2026-10-20). Scope: MySQL SQL and synthetic tests (U1).

Quotes below are marked `> "..."` and are copied word for word from the source named after them.

## Context

Question: inside one repository, do pull requests made by AI coding agents need more human review than pull requests made by people, and does it differ by agent?

Apache DevLake already holds the data in its domain layer: `pull_requests`, `pull_request_comments`, `accounts` and `pull_request_assignees`. No dashboard in DevLake groups PRs by agent and shows the human review burden. The open request #8713 asks for the first half of this ("PRs assisted by AI, PRs not assisted by AI").

DevLake does not give a median function in MySQL, has no "ready for review" time, and has no automated test for dashboard SQL (issue #9226: "There are no automated tests for dashboard SQL").

## Decision

Five metrics are computed directly from `pull_requests` and `pull_request_comments`, per agent group and per group of PRs without an agent marker.

1. **Time to first human reaction (minutes).** From PR creation to the first comment (any of NORMAL, DIFF, REVIEW) written by someone who is not the PR author, is not a bot and is not an unsent review. The research definition is
   > "the median time elapsed from PR creation to the first reviewer comment"
   (research/v3/research/arxiv_2602.17084.txt L146). The exclusion of bots and the author follows github/issue-metrics:
   > "comments by issue/pull request author's and comments by bots are excluded"
   (upstream/issue_metrics_README.md L32). DevLake's own first-review query does the same with `AND COALESCE(acc2.is_bot, false) = false` (change_lead_time_calculator.go L254 at v1.0.3-beta18).
   A second value, **1B**, also removes the assignees of the PR (`pull_request_assignees`). Reason: for agent PRs the person who asked for a change is often the assignee, which would count as "human review" for agents but not for people.
2. **Review burden (count).** Number of comments per PR, all three types, unsent reviews removed. A diff comment and the review it belongs to are both counted, as in the research definition
   > "Sum of all reviews and comments, including bot messages"
   (research/v3/research/arxiv_2601.00753v2.txt L92). The same count without bot comments is given next to it (2H).
3. **Changes requested.** Share of PRs with at least one `type = 'REVIEW'` and `status = 'CHANGES_REQUESTED'` comment. The research defines this state as
   > "explicit request for modifications"
   (research/v3/research/arxiv_2604.03196.txt L70). DevLake stores the GitHub review state unchanged (pr_review_convertor.go L93 at v1.0.3-beta18).
4. **PR size.** `additions + deletions` (`pull_request.go` L61-L62).
5. **Outcome.** Count of PRs with `status` MERGED, CLOSED, OPEN (`pull_request.go` L30-L32).

Medians use the method of DevLake's own dashboards: the largest value among rows with `percent_rank() <= 0.5` (`max(days_deployed) as median_number_of_deployment_days_per_week` with `ranks <= 0.5`, dash_sql_extract.txt L599-L615). With an even count this is the lower of the two middle values. This is stated on the dashboard.

Unsent reviews are removed everywhere: DevLake leaves the time empty when a review was not submitted (`if githubPullRequestReview.GithubSubmitAt != nil {`, pr_review_convertor.go L95 at v1.0.3-beta18), and these rows have `status = 'PENDING'`.

**Agent identification** (first match wins; the SQL in `sql/mysql/agent_review_burden.sql` keeps the same order):

| Order | Signal | Group |
|---|---|---|
| 1 | author name `Copilot` or `copilot-swe-agent[bot]` | copilot |
| 2 | author name `devin-ai-integration[bot]` | devin |
| 3-6 | `head_ref` starts with `copilot/`, `codex/`, `cursor/`, `devin/` | copilot, codex, cursor, devin |
| 7 | `head_ref` starts with `claude/`, or the PR body contains `Co-Authored-By: Claude` (case-insensitive) | claude |
| 8 | author account has `is_bot = 1` | other_bot (not part of "no marker") |
| 9 | none of the above | no_marker |

Sources: bot author names and the Claude body mark come from the AIDev search conditions, which use
> "Co-Authored-By: Claude"
(research/v3/research/arxiv_2507.15003v1.txt L179). The Claude branch prefix is the default of Anthropic's claude-code-action (`defaults to 'claude/'`, upstream/claude_code_action_action_yml.txt L24). The two names used for Copilot differ because REST and GraphQL report it differently.

The group "no marker" is not called "human-only PRs": a person can ask `@copilot` to change a person's PR, and some agents leave no mark.

## Alternatives considered

- **Use `project_pr_metrics`.** Rejected. It covers merged PRs only, and setting #9229 removes rows (the issue says "Only `project_pr_metrics` is affected", upstream/issue_9229.txt L16); "closed without merge" could not be counted.
- **Count review comments only, not NORMAL comments.** Rejected for the default. DevLake's existing first-review time counts any comment, and discussion 8317 shows that users care about which is counted ("PR pickup time is considering any comment rather than review comment", upstream/discussions_open_prs.txt L48). The dashboard text will say which comments are counted.
- **Detect agents by the `claude-code-assisted` label.** Rejected: the label is only on merged PRs, which biases outcome.
- **Compute the median with a MySQL user function or by averaging.** Rejected: DevLake's own dashboards use the `percent_rank` method; an average is pulled by single large values.
- **Check only with real data.** Rejected as the first check: no ground truth. Synthetic data with hand-computed values comes first (this repository); real-data comparison is a later step.

## Consequences

- Every number can be reproduced by `python tests/run_u1.py` (a MySQL 8 container, no network except pulling the image once). The fixture contains the cases that break naive SQL: unsent review, diff comment plus its review, a PR with no human comment, comments at the same minute, an assignee who is also the first commenter, bots of other kinds, a PR marked only in the body.
- Time to first reaction includes the time a PR was a draft; DevLake has no "ready for review" time. Agent PRs are often opened as drafts, so the agent side reads longer.
- Branch prefixes are a guess. A person can open a PR from a `codex/` or `cursor/` branch.
- **Finding for metric 1B.** In DevLake `v1.0.3-beta18` the table `pull_request_assignees` is written by the GitLab converter (`backend/plugins/gitlab/tasks/mr_assignee_convertor.go`); the GitHub plugin task list has no assignee converter, and a code search of the repository shows no other writer (evidence in research/v3/upstream/beta18/). On data imported from GitHub, 1B will therefore equal 1 until that table is filled. The SQL is correct for the table as defined; the dashboard text must say this.
- `is_bot` and the review state are only filled by the GitHub plugin; the dashboard is GitHub-only.
- No per-person values are shown.
