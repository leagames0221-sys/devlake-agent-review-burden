-- Review burden by AI agent, from Apache DevLake domain-layer tables (MySQL 8).
--
-- File layout (read by tests/run_u1.py; a Grafana panel pastes @common + one @metric):
--   "-- @common"          one WITH list that classifies every PR and derives per-PR facts
--   "-- @metric <name>"   one SELECT per metric; it is appended to @common
-- Grafana macros are kept as they are written in DevLake dashboards:
--   $__timeFilter(pr.created_date)   -> the dashboard time range
--   ${repo_id}                       -> the repo variable
-- The test runner replaces them with fixed values (2026-03-01 .. 2026-03-31, one repo).
--
-- Median: DevLake has no median function in MySQL, so the same method as the existing
-- DevLake dashboards is used: max(value) among the rows whose percent_rank() <= 0.5
-- (apache/devlake grafana/dashboards/mysql/DORA.json, the panel SQL with
-- "max(days_deployed) as median_number_of_deployment_days_per_week" and "ranks <= 0.5":
-- https://github.com/apache/devlake/blob/v1.0.3-beta18/grafana/dashboards/mysql/DORA.json#L236).
-- With an even number of values this returns the lower of the two middle values.
-- Here percent_rank() is computed per agent (PARTITION BY agent).
--
-- Agent groups (first match wins; the order is the same as in docs/adr/0001-metric-definitions.md):
--   1 author login in (Copilot, copilot-swe-agent[bot])       -> copilot
--   2 author login = devin-ai-integration[bot]                -> devin
--     (author login = accounts.user_name of the PR author; pull_requests.author_name only when the account row is missing)
--   3 head_ref copilot/ -> copilot   4 codex/ -> codex   5 cursor/ -> cursor
--   6 devin/ -> devin
--   7 head_ref claude/  or  description contains "Co-Authored-By: Claude" -> claude
--   8 author is a bot (see "Bot" below)                       -> other_bot
--   9 otherwise                                               -> no_marker
--
-- Bot: an account counts as a bot when accounts.is_bot = 1 OR its user_name is one of the
-- agent bot names of rules 1 and 2. DevLake sets is_bot when the GitHub user type is "Bot" or
-- the login ends in "[bot]"
-- (https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go#L150).
-- The user type comes from GET /users/{login}, and "Copilot" answers 404 there, so on the REST
-- path the account "Copilot" is stored with is_bot = 0. The name list closes that gap.
--
-- Unsent reviews: DevLake already drops reviews in state PENDING when it extracts them
-- (REST: https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_extractor.go#L72 ,
-- GraphQL: https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_extractor.go#L101 ),
-- so normally no such row reaches pull_request_comments. The condition below is a safeguard for
-- data that came in another way: it removes rows with type 'REVIEW' and status 'PENDING' from every
-- metric. The converter stores a review with Type "REVIEW", Status = the GitHub state and, for a
-- review without a submit time, no time
-- (https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_review_convertor.go#L91-L96).

-- @common
WITH agents AS (
  SELECT 'copilot' AS agent, 1 AS sort_no
  UNION ALL SELECT 'devin', 2
  UNION ALL SELECT 'codex', 3
  UNION ALL SELECT 'claude', 4
  UNION ALL SELECT 'cursor', 5
  UNION ALL SELECT 'other_bot', 6
  UNION ALL SELECT 'no_marker', 7
),
acct AS (
  SELECT
    a.id,
    a.user_name,
    CASE WHEN COALESCE(a.is_bot, 0) = 1
           OR a.user_name IN ('Copilot', 'copilot-swe-agent[bot]', 'devin-ai-integration[bot]')
         THEN 1 ELSE 0 END AS is_bot                                                         -- bot by flag or by agent name
  FROM accounts a
),
pr_login AS (
  -- the login of the PR author: accounts.user_name when the account row exists; pull_requests.author_name only when it does not.
  -- DevLake's GraphQL path stores author_name without "[bot]" ("copilot-swe-agent", "devin-ai-integration") while accounts.user_name
  -- has the account's own login ("Copilot", "devin-ai-integration[bot]"), so rules 1 and 2 read the account (ADR 0002 A1)
  SELECT pr.id, CASE WHEN a.id IS NULL THEN pr.author_name ELSE a.user_name END AS login
  FROM pull_requests pr
  LEFT JOIN accounts a ON a.id = pr.author_id
),
pr_base AS (
  SELECT
    pr.id,
    pr.author_id,
    pr.status,
    pr.created_date,
    pr.additions + pr.deletions AS size,
    CASE
      WHEN pl.login IN ('Copilot', 'copilot-swe-agent[bot]') THEN 'copilot'                -- rule 1
      WHEN pl.login = 'devin-ai-integration[bot]' THEN 'devin'                              -- rule 2
      WHEN pr.head_ref LIKE 'copilot/%' THEN 'copilot'                                      -- rule 3
      WHEN pr.head_ref LIKE 'codex/%' THEN 'codex'                                          -- rule 4
      WHEN pr.head_ref LIKE 'cursor/%' THEN 'cursor'                                        -- rule 5
      WHEN pr.head_ref LIKE 'devin/%' THEN 'devin'                                          -- rule 6
      WHEN pr.head_ref LIKE 'claude/%'
        OR LOWER(pr.description) LIKE '%co-authored-by: claude%' THEN 'claude'              -- rule 7
      WHEN COALESCE(au.is_bot, 0) = 1 THEN 'other_bot'                                      -- rule 8
      ELSE 'no_marker'                                                                      -- rule 9
    END AS agent
  FROM pull_requests pr
  LEFT JOIN acct au ON au.id = pr.author_id
  LEFT JOIN pr_login pl ON pl.id = pr.id
  WHERE $__timeFilter(pr.created_date)
    AND pr.base_repo_id IN (${repo_id})
),
valid_comments AS (
  SELECT
    c.pull_request_id,
    c.account_id,
    c.created_date,
    c.type,
    c.status,
    COALESCE(ca.is_bot, 0) AS is_bot
  FROM pull_request_comments c
  JOIN pr_base p ON p.id = c.pull_request_id
  LEFT JOIN acct ca ON ca.id = c.account_id
  WHERE NOT (c.type = 'REVIEW' AND COALESCE(c.status, '') = 'PENDING')                      -- safeguard: unsent reviews out
),
pr_facts AS (
  SELECT
    p.id,
    p.agent,
    p.status,
    p.size,
    -- metric 2: all three comment types counted (NORMAL, DIFF, REVIEW)
    (SELECT COUNT(*) FROM valid_comments c
      WHERE c.pull_request_id = p.id) AS n_comments,
    (SELECT COUNT(*) FROM valid_comments c
      WHERE c.pull_request_id = p.id AND c.is_bot = 0) AS n_comments_human,
    -- metric 3
    (SELECT COUNT(*) FROM valid_comments c
      WHERE c.pull_request_id = p.id AND c.type = 'REVIEW' AND c.status = 'CHANGES_REQUESTED') AS n_changes_requested,
    -- metric 1: first comment by someone who is not the author and not a bot
    (SELECT MIN(TIMESTAMPDIFF(MINUTE, p.created_date, c.created_date)) FROM valid_comments c
      WHERE c.pull_request_id = p.id
        AND c.is_bot = 0
        AND (p.author_id IS NULL OR p.author_id = '' OR c.account_id <> p.author_id)) AS first_human_min,
    -- metric 1B: the same, and the commenter is not an assignee of the PR
    (SELECT MIN(TIMESTAMPDIFF(MINUTE, p.created_date, c.created_date)) FROM valid_comments c
      WHERE c.pull_request_id = p.id
        AND c.is_bot = 0
        AND (p.author_id IS NULL OR p.author_id = '' OR c.account_id <> p.author_id)
        AND NOT EXISTS (SELECT 1 FROM pull_request_assignees asg
                         WHERE asg.pull_request_id = p.id AND asg.assignee_id = c.account_id)) AS first_human_min_excl_assignee
  FROM pr_base p
)

-- @metric m1_first_human_reaction
SELECT
  g.agent,
  COALESCE(s.pr_count, 0) AS pr_count,
  COALESCE(s.reacted, 0) AS reacted,
  m.median_value AS median_minutes,
  COALESCE(s.reacted_b, 0) AS reacted_excl_assignee,
  mb.median_value AS median_minutes_excl_assignee
FROM agents g
LEFT JOIN (
  SELECT agent, COUNT(*) AS pr_count, COUNT(first_human_min) AS reacted, COUNT(first_human_min_excl_assignee) AS reacted_b
  FROM pr_facts GROUP BY agent
) s ON s.agent = g.agent
LEFT JOIN (
  SELECT agent, MAX(v) AS median_value FROM (
    SELECT agent, first_human_min AS v, percent_rank() OVER (PARTITION BY agent ORDER BY first_human_min) AS rk
    FROM pr_facts WHERE first_human_min IS NOT NULL
  ) r WHERE rk <= 0.5 GROUP BY agent
) m ON m.agent = g.agent
LEFT JOIN (
  SELECT agent, MAX(v) AS median_value FROM (
    SELECT agent, first_human_min_excl_assignee AS v, percent_rank() OVER (PARTITION BY agent ORDER BY first_human_min_excl_assignee) AS rk
    FROM pr_facts WHERE first_human_min_excl_assignee IS NOT NULL
  ) r WHERE rk <= 0.5 GROUP BY agent
) mb ON mb.agent = g.agent
ORDER BY g.sort_no

-- @metric m2_review_burden
SELECT
  g.agent,
  COALESCE(s.pr_count, 0) AS pr_count,
  m.median_value AS median_comments,
  mh.median_value AS median_comments_excl_bots
FROM agents g
LEFT JOIN (
  SELECT agent, COUNT(*) AS pr_count FROM pr_facts GROUP BY agent
) s ON s.agent = g.agent
LEFT JOIN (
  SELECT agent, MAX(v) AS median_value FROM (
    SELECT agent, n_comments AS v, percent_rank() OVER (PARTITION BY agent ORDER BY n_comments) AS rk
    FROM pr_facts
  ) r WHERE rk <= 0.5 GROUP BY agent
) m ON m.agent = g.agent
LEFT JOIN (
  SELECT agent, MAX(v) AS median_value FROM (
    SELECT agent, n_comments_human AS v, percent_rank() OVER (PARTITION BY agent ORDER BY n_comments_human) AS rk
    FROM pr_facts
  ) r WHERE rk <= 0.5 GROUP BY agent
) mh ON mh.agent = g.agent
ORDER BY g.sort_no

-- @metric m3_changes_requested
-- A review that was dismissed later has the state DISMISSED in GitHub; DevLake stores the state
-- as it is (pr_review_convertor.go#L92), so a dismissed "changes requested" is not counted here.
SELECT
  g.agent,
  COALESCE(s.pr_count, 0) AS pr_count,
  COALESCE(s.changes_requested_prs, 0) AS changes_requested_prs,
  s.changes_requested_ratio
FROM agents g
LEFT JOIN (
  SELECT agent,
         COUNT(*) AS pr_count,
         SUM(CASE WHEN n_changes_requested >= 1 THEN 1 ELSE 0 END) AS changes_requested_prs,
         AVG(CASE WHEN n_changes_requested >= 1 THEN 1 ELSE 0 END) AS changes_requested_ratio
  FROM pr_facts GROUP BY agent
) s ON s.agent = g.agent
ORDER BY g.sort_no

-- @metric m4_pr_size
SELECT
  g.agent,
  COALESCE(s.pr_count, 0) AS pr_count,
  m.median_value AS median_size
FROM agents g
LEFT JOIN (
  SELECT agent, COUNT(*) AS pr_count FROM pr_facts GROUP BY agent
) s ON s.agent = g.agent
LEFT JOIN (
  SELECT agent, MAX(v) AS median_value FROM (
    SELECT agent, size AS v, percent_rank() OVER (PARTITION BY agent ORDER BY size) AS rk
    FROM pr_facts
  ) r WHERE rk <= 0.5 GROUP BY agent
) m ON m.agent = g.agent
ORDER BY g.sort_no

-- @metric m5_outcome
SELECT
  g.agent,
  COALESCE(s.pr_count, 0) AS pr_count,
  COALESCE(s.merged, 0) AS merged,
  COALESCE(s.closed, 0) AS closed,
  COALESCE(s.open, 0) AS open
FROM agents g
LEFT JOIN (
  SELECT agent,
         COUNT(*) AS pr_count,
         SUM(CASE WHEN status = 'MERGED' THEN 1 ELSE 0 END) AS merged,
         SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed,
         SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open
  FROM pr_facts GROUP BY agent
) s ON s.agent = g.agent
ORDER BY g.sort_no
