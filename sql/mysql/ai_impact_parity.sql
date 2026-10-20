-- AI impact metrics defined as Swarmia defines them, from Apache DevLake domain-layer tables (MySQL 8).
-- Definitions, sources (file:line of the saved Swarmia pages) and every place where the source text
-- does not decide are in docs/adr/0002-swarmia-parity-definitions.md (rows D1..D14). Agent identities:
-- docs/agent_identities.md.
--
-- File layout (read by tests/run_u1.py; a Grafana panel pastes @common + one @metric), same as U1:
--   "-- @common"          one WITH list: identities, marks, groups and per-PR facts
--   "-- @metric <name>"   one SELECT per metric; it is appended to @common
-- The first column of every metric is the row key: tool:<name>, mode:<name>, week:<YEARWEEK>,
-- pr:<PR id>, check:<name>. Grafana macros, as written in DevLake dashboards:
--   $__timeFilter(pr.created_date)   the dashboard time range, on the time the PR was opened
--   $__timeFilter(pr.merged_date)    the same range, on the time the PR was merged
--   ${repo_id}                       the repo variable
--   ${include_own_markers}           0 = only Swarmia's markers (default), 1 = also the markers of U1
-- The test runner replaces them with fixed values (2026-03-01 .. 2026-03-31, one repo).
--
-- Marks (every mark is checked for every PR; the first hit does not stop the others):
--   m1 PR author is a cloud agent        m2 first commit author (name or e-mail) is a cloud agent
--   m3 any commit author is an AI tool   m4 a commit message has a Co-authored-by line of an AI tool
--   m5 a commit message has a Made-with: Cursor line      m6 a review row is written by a review agent
--   x1 head_ref prefix (copilot/ codex/ cursor/ devin/ claude/)   x2 PR body has Co-Authored-By: Claude
-- x1 and x2 are U1's own markers; they are used only when ${include_own_markers} = 1.
-- Modes: cloud_agent = m1 or m2; ai_assisted = m3, m4, m5 (and x1, x2); review_agent = m6;
-- ai_used = any of the three. A PR may be in several tools and several modes.
--
-- Text matching (DevLake's collation is utf8mb4_bin, so every match is made on LOWER(text) with a
-- lower-case pattern): login and name patterns are anchored with ^...$ and a literal [bot] is written
-- \\[bot\\] (the first backslash level is MySQL's string escape). A trailer is counted only at the start
-- of a line, in two shapes: real line breaks ('m' flag, LF and CRLF) and DevLake's JSON-string body
-- (the body of a REST import keeps the quotes and the two characters \n, see ADR 0002).
--
-- Median: the method of DevLake's dashboards, as in U1: max(value) among rows with percent_rank() <= 0.5
-- (with an even count this is the lower of the two middle values).

-- @common
WITH identities(tool, mode, field, pattern) AS (
  -- tool, mode (cloud | assist | review), field (pr_author | commit_author_name | commit_author_email |
  -- coauthor | review_author), pattern (lower case). Add or remove rows here per company.
  -- Basis of each row: docs/agent_identities.md.
  SELECT 'copilot', 'cloud', 'pr_author', '^(copilot|copilot-swe-agent\\[bot\\])$'
  UNION ALL SELECT 'copilot', 'review', 'review_author', '^(copilot|copilot-pull-request-reviewer\\[bot\\])$'
  UNION ALL SELECT 'cursor', 'cloud', 'pr_author', '^cursor\\[bot\\]$'
  UNION ALL SELECT 'cursor', 'cloud', 'commit_author_name', '^cursoragent$'
  UNION ALL SELECT 'cursor', 'cloud', 'commit_author_email', '^cursoragent@'   -- UNVERIFIED placeholder (mechanism test), see agent_identities.md
  UNION ALL SELECT 'claude', 'cloud', 'pr_author', '^claude\\[bot\\]$'
  UNION ALL SELECT 'claude', 'cloud', 'commit_author_name', '^claude$'
  UNION ALL SELECT 'claude', 'assist', 'coauthor', 'claude\\b'
  UNION ALL SELECT 'codex', 'cloud', 'pr_author', '^chatgpt-codex-connector\\[bot\\]$'
  UNION ALL SELECT 'codex', 'review', 'review_author', '^chatgpt-codex-connector\\[bot\\]$'
  UNION ALL SELECT 'devin', 'cloud', 'pr_author', '^devin-ai-integration\\[bot\\]$'
  UNION ALL SELECT 'devin', 'review', 'review_author', '^devin-ai-integration\\[bot\\]$'
  UNION ALL SELECT 'coderabbit', 'cloud', 'pr_author', '^coderabbitai\\[bot\\]$'
  UNION ALL SELECT 'coderabbit', 'review', 'review_author', '^coderabbitai\\[bot\\]$'
  UNION ALL SELECT 'cubic', 'cloud', 'pr_author', '^cubic-dev-ai\\[bot\\]$'
  UNION ALL SELECT 'cubic', 'review', 'review_author', '^cubic-dev-ai\\[bot\\]$'
  UNION ALL SELECT 'graphite', 'cloud', 'pr_author', '^graphite-app\\[bot\\]$'
  UNION ALL SELECT 'graphite', 'review', 'review_author', '^graphite-app\\[bot\\]$'
  UNION ALL SELECT 'macroscope', 'cloud', 'pr_author', '^macroscopeapp\\[bot\\]$'
  UNION ALL SELECT 'macroscope', 'review', 'review_author', '^macroscopeapp\\[bot\\]$'
  UNION ALL SELECT 'qodo', 'cloud', 'pr_author', '^qodo-code-review\\[bot\\]$'
  UNION ALL SELECT 'qodo', 'review', 'review_author', '^qodo-code-review\\[bot\\]$'
),
all_groups AS (
  SELECT DISTINCT CONCAT('tool:', tool) AS grp FROM identities
  UNION ALL SELECT 'tool:everything_else'
  UNION ALL SELECT 'mode:cloud_agent'
  UNION ALL SELECT 'mode:ai_assisted'
  UNION ALL SELECT 'mode:review_agent'
  UNION ALL SELECT 'mode:ai_used'
  UNION ALL SELECT 'mode:everything_else'
),
acct AS (
  SELECT
    a.id,
    a.user_name,
    -- bot (D11): the is_bot flag, U1's agent bot names, or a login of the identities list
    CASE WHEN COALESCE(a.is_bot, 0) = 1
           OR a.user_name IN ('Copilot', 'copilot-swe-agent[bot]', 'devin-ai-integration[bot]')
           OR EXISTS (SELECT 1 FROM identities i
                       WHERE i.field IN ('pr_author', 'review_author')
                         AND REGEXP_LIKE(LOWER(a.user_name), i.pattern))
         THEN 1 ELSE 0 END AS is_bot
  FROM accounts a
),
pr_base AS (
  -- every PR that was opened or merged in the period; the metrics pick in_created or in_merged (D12)
  SELECT
    pr.id,
    pr.author_id,
    pr.author_name,
    pr.status,
    pr.created_date,
    pr.merged_date,
    pr.head_ref,
    pr.description,
    COALESCE(pr.additions, 0) + COALESCE(pr.deletions, 0) AS size,
    CASE WHEN $__timeFilter(pr.created_date) THEN 1 ELSE 0 END AS in_created,
    CASE WHEN $__timeFilter(pr.merged_date) THEN 1 ELSE 0 END AS in_merged
  FROM pull_requests pr
  WHERE ($__timeFilter(pr.created_date) OR $__timeFilter(pr.merged_date))
    AND pr.base_repo_id IN (${repo_id})
),
valid_comments AS (
  SELECT
    c.pull_request_id,
    c.account_id,
    c.created_date,
    c.type,
    c.status,
    ca.user_name,
    COALESCE(ca.is_bot, 0) AS is_bot
  FROM pull_request_comments c
  JOIN pr_base p ON p.id = c.pull_request_id
  LEFT JOIN acct ca ON ca.id = c.account_id
  WHERE NOT (c.type = 'REVIEW' AND COALESCE(c.status, '') = 'PENDING')                       -- unsent reviews out (as in U1)
),
human_reviews AS (
  -- review rows of people: not a bot, not the PR author (D3)
  SELECT c.pull_request_id AS pr_id, c.created_date, c.status
  FROM valid_comments c
  JOIN pr_base p ON p.id = c.pull_request_id
  WHERE c.type = 'REVIEW'
    AND c.is_bot = 0
    AND c.created_date IS NOT NULL
    AND (p.author_id IS NULL OR p.author_id = '' OR c.account_id <> p.author_id)
),
first_review AS (
  -- D2: the first submitted review of any state (approved, changes requested, commented, dismissed)
  SELECT pr_id, MIN(created_date) AS at_time
  FROM human_reviews
  GROUP BY pr_id
),
final_approval AS (
  -- D9: the last APPROVED review before the merge
  SELECT hr.pr_id, MAX(hr.created_date) AS at_time
  FROM human_reviews hr
  JOIN pr_base p ON p.id = hr.pr_id
  WHERE hr.status = 'APPROVED' AND p.merged_date IS NOT NULL AND hr.created_date < p.merged_date
  GROUP BY hr.pr_id
),
pr_commit AS (
  -- commits is joined with LEFT JOIN: a PR whose message is not in commits stays in every count
  SELECT
    prc.pull_request_id AS pr_id,
    prc.commit_sha,
    prc.commit_author_name,
    prc.commit_author_email,
    prc.commit_authored_date,
    cm.message,
    MIN(prc.commit_authored_date) OVER (PARTITION BY prc.pull_request_id) AS first_commit_at
  FROM pull_request_commits prc
  JOIN pr_base p ON p.id = prc.pull_request_id
  LEFT JOIN commits cm ON cm.sha = prc.commit_sha
),
marks AS (
  -- m1: the PR author is a cloud agent
  SELECT p.id AS pr_id, i.tool, 'm1' AS mark
  FROM pr_base p
  JOIN identities i ON i.mode = 'cloud' AND i.field = 'pr_author' AND REGEXP_LIKE(LOWER(p.author_name), i.pattern)
  UNION
  -- m2: the first commit (D10: all commits with the earliest time) is authored by a cloud agent, by name or e-mail
  SELECT pc.pr_id, i.tool, 'm2'
  FROM pr_commit pc
  JOIN identities i ON i.mode = 'cloud'
   AND pc.commit_authored_date = pc.first_commit_at
   AND ((i.field = 'commit_author_name' AND REGEXP_LIKE(LOWER(pc.commit_author_name), i.pattern))
     OR (i.field = 'commit_author_email' AND REGEXP_LIKE(LOWER(pc.commit_author_email), i.pattern)))
  UNION
  -- m3: any commit is authored by an AI tool
  SELECT pc.pr_id, i.tool, 'm3'
  FROM pr_commit pc
  JOIN identities i ON i.mode IN ('cloud', 'assist')
   AND ((i.field = 'commit_author_name' AND REGEXP_LIKE(LOWER(pc.commit_author_name), i.pattern))
     OR (i.field = 'commit_author_email' AND REGEXP_LIKE(LOWER(pc.commit_author_email), i.pattern)))
  UNION
  -- m4: a Co-authored-by line of an AI tool, at the start of a line (real line breaks, or the JSON-string shape)
  SELECT pc.pr_id, i.tool, 'm4'
  FROM pr_commit pc
  JOIN identities i ON i.mode IN ('cloud', 'assist') AND i.field = 'coauthor'
   AND (REGEXP_LIKE(LOWER(pc.message), CONCAT('^co-authored-by:[ \\t]*', i.pattern), 'm')
     OR REGEXP_LIKE(LOWER(pc.message), CONCAT('(^"?|\\\\n)co-authored-by:[ \\t]*', i.pattern)))
  UNION
  -- m5: a "Made-with: Cursor" line, at the start of a line
  SELECT pc.pr_id, 'cursor', 'm5'
  FROM pr_commit pc
  WHERE REGEXP_LIKE(LOWER(pc.message), '^made-with:[ \\t]*cursor\\b', 'm')
     OR REGEXP_LIKE(LOWER(pc.message), '(^"?|\\\\n)made-with:[ \\t]*cursor\\b')
  UNION
  -- m6: a review row (REVIEW or a line comment of a review, D13) written by a review agent
  SELECT c.pull_request_id, i.tool, 'm6'
  FROM valid_comments c
  JOIN identities i ON i.mode = 'review' AND i.field = 'review_author' AND REGEXP_LIKE(LOWER(c.user_name), i.pattern)
  WHERE c.type IN ('REVIEW', 'DIFF')
  UNION
  -- x1 (own marker): head_ref prefix
  SELECT p.id, x.tool, 'x1'
  FROM pr_base p
  JOIN (SELECT 'copilot/' AS prefix, 'copilot' AS tool
        UNION ALL SELECT 'codex/', 'codex'
        UNION ALL SELECT 'cursor/', 'cursor'
        UNION ALL SELECT 'devin/', 'devin'
        UNION ALL SELECT 'claude/', 'claude') x ON p.head_ref LIKE CONCAT(x.prefix, '%')
  WHERE ${include_own_markers} = 1
  UNION
  -- x2 (own marker): the PR body has Co-Authored-By: Claude
  SELECT p.id, 'claude', 'x2'
  FROM pr_base p
  WHERE ${include_own_markers} = 1 AND LOWER(p.description) LIKE '%co-authored-by: claude%'
),
pr_tool AS (
  SELECT DISTINCT pr_id, tool FROM marks
),
pr_mode AS (
  SELECT pr_id, 'cloud_agent' AS mode FROM marks WHERE mark IN ('m1', 'm2')
  UNION
  SELECT pr_id, 'ai_assisted' FROM marks WHERE mark IN ('m3', 'm4', 'm5', 'x1', 'x2')
  UNION
  SELECT pr_id, 'review_agent' FROM marks WHERE mark = 'm6'
),
pr_group AS (
  SELECT pr_id, CONCAT('tool:', tool) AS grp FROM pr_tool
  UNION ALL
  SELECT p.id, 'tool:everything_else' FROM pr_base p
   WHERE NOT EXISTS (SELECT 1 FROM pr_tool t WHERE t.pr_id = p.id)
  UNION ALL
  SELECT pr_id, CONCAT('mode:', mode) FROM pr_mode
  UNION ALL
  SELECT DISTINCT pr_id, 'mode:ai_used' FROM pr_mode
  UNION ALL
  SELECT p.id, 'mode:everything_else' FROM pr_base p
   WHERE NOT EXISTS (SELECT 1 FROM pr_mode m WHERE m.pr_id = p.id)
),
first_commit AS (
  SELECT DISTINCT pr_id, first_commit_at FROM pr_commit
),
pr_facts AS (
  SELECT
    p.id,
    p.status,
    p.size,
    p.in_created,
    p.in_merged,
    -- time to first review: from the PR being opened (D1) to the first human review
    TIMESTAMPDIFF(MINUTE, p.created_date, fr.at_time) AS ttfr_min,
    -- time in review: from the PR being opened (D1) to the final approval, or to the merge (D5); merged PRs only
    CASE WHEN p.merged_date IS NOT NULL
         THEN TIMESTAMPDIFF(MINUTE, p.created_date, COALESCE(fa.at_time, p.merged_date)) END AS tir_min,
    -- cycle time: from the first commit or the opening of the PR, whichever is earlier, to the merge; merged PRs only
    CASE WHEN p.merged_date IS NOT NULL
         THEN TIMESTAMPDIFF(MINUTE, LEAST(p.created_date, COALESCE(fc.first_commit_at, p.created_date)), p.merged_date) END AS cycle_min,
    CASE WHEN p.merged_date IS NOT NULL THEN YEARWEEK(p.merged_date, 3) END AS yw           -- D6: ISO week, Monday first
  FROM pr_base p
  LEFT JOIN first_review fr ON fr.pr_id = p.id
  LEFT JOIN final_approval fa ON fa.pr_id = p.id
  LEFT JOIN first_commit fc ON fc.pr_id = p.id
),
grp_vals AS (
  SELECT g.grp, 'ttfr' AS m, f.ttfr_min AS v
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_created = 1 AND f.ttfr_min IS NOT NULL
  UNION ALL
  SELECT g.grp, 'tir', f.tir_min
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_merged = 1 AND f.tir_min IS NOT NULL
  UNION ALL
  SELECT g.grp, 'cycle', f.cycle_min
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_merged = 1 AND f.cycle_min IS NOT NULL
  UNION ALL
  SELECT g.grp, 'size', f.size
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_created = 1
),
grp_ranked AS (
  SELECT grp, m, v, percent_rank() OVER (PARTITION BY grp, m ORDER BY v) AS rk
  FROM grp_vals
),
grp_stats AS (
  SELECT grp, m, COUNT(*) AS n, AVG(v) AS mean_v, MAX(CASE WHEN rk <= 0.5 THEN v END) AS median_v
  FROM grp_ranked
  GROUP BY grp, m
)

-- @metric time_to_first_review
-- D1 start = PR opened; D2 end = first human review of any state; PRs opened in the period; bots and the author excluded.
SELECT
  ag.grp,
  COALESCE(sz.prs, 0) AS prs,
  COALESCE(s.n, 0) AS n_defined,
  s.mean_v AS mean_minutes,
  s.median_v AS median_minutes
FROM all_groups ag
LEFT JOIN (
  SELECT g.grp, COUNT(*) AS prs
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_created = 1
  GROUP BY g.grp
) sz ON sz.grp = ag.grp
LEFT JOIN grp_stats s ON s.grp = ag.grp AND s.m = 'ttfr'
ORDER BY ag.grp

-- @metric time_in_review
-- Merged PRs only, merged in the period (D12).
SELECT
  ag.grp,
  COALESCE(s.n, 0) AS n,
  s.mean_v AS mean_minutes,
  s.median_v AS median_minutes
FROM all_groups ag
LEFT JOIN grp_stats s ON s.grp = ag.grp AND s.m = 'tir'
ORDER BY ag.grp

-- @metric pr_cycle_time
-- Merged PRs only, merged in the period (D12).
SELECT
  ag.grp,
  COALESCE(s.n, 0) AS n,
  s.mean_v AS mean_minutes,
  s.median_v AS median_minutes
FROM all_groups ag
LEFT JOIN grp_stats s ON s.grp = ag.grp AND s.m = 'cycle'
ORDER BY ag.grp

-- @metric throughput
-- Merged PRs merged in the period. tool:/mode: rows = the period total of the group.
-- week:<YEARWEEK(merged_date, 3)> rows = the PRs merged in that week, all and per mode.
SELECT
  ag.grp,
  COALESCE(s.merged, 0) AS merged,
  NULL AS merged_cloud_agent,
  NULL AS merged_ai_assisted,
  NULL AS merged_review_agent,
  NULL AS merged_ai_used,
  NULL AS merged_everything_else
FROM all_groups ag
LEFT JOIN (
  SELECT g.grp, COUNT(*) AS merged
  FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
  WHERE f.in_merged = 1
  GROUP BY g.grp
) s ON s.grp = ag.grp
UNION ALL
SELECT
  CONCAT('week:', f.yw),
  COUNT(*),
  SUM(CASE WHEN EXISTS (SELECT 1 FROM pr_group g WHERE g.pr_id = f.id AND g.grp = 'mode:cloud_agent') THEN 1 ELSE 0 END),
  SUM(CASE WHEN EXISTS (SELECT 1 FROM pr_group g WHERE g.pr_id = f.id AND g.grp = 'mode:ai_assisted') THEN 1 ELSE 0 END),
  SUM(CASE WHEN EXISTS (SELECT 1 FROM pr_group g WHERE g.pr_id = f.id AND g.grp = 'mode:review_agent') THEN 1 ELSE 0 END),
  SUM(CASE WHEN EXISTS (SELECT 1 FROM pr_group g WHERE g.pr_id = f.id AND g.grp = 'mode:ai_used') THEN 1 ELSE 0 END),
  SUM(CASE WHEN EXISTS (SELECT 1 FROM pr_group g WHERE g.pr_id = f.id AND g.grp = 'mode:everything_else') THEN 1 ELSE 0 END)
FROM pr_facts f
WHERE f.in_merged = 1
GROUP BY f.yw
ORDER BY 1

-- @metric batch_size
-- additions + deletions of PRs opened in the period. Generated files are NOT excluded (see ADR 0002).
-- Buckets as the benchmarks of Swarmia's page: under 200, 200..499, 500 and over.
SELECT
  ag.grp,
  COALESCE(s.n, 0) AS prs,
  s.mean_v AS mean_size,
  s.median_v AS median_size,
  b.share_lt200,
  b.share_200_499,
  b.share_ge500
FROM all_groups ag
LEFT JOIN grp_stats s ON s.grp = ag.grp AND s.m = 'size'
LEFT JOIN (
  SELECT grp,
         AVG(CASE WHEN v < 200 THEN 1 ELSE 0 END) AS share_lt200,
         AVG(CASE WHEN v >= 200 AND v < 500 THEN 1 ELSE 0 END) AS share_200_499,
         AVG(CASE WHEN v >= 500 THEN 1 ELSE 0 END) AS share_ge500
  FROM grp_vals WHERE m = 'size' GROUP BY grp
) b ON b.grp = ag.grp
ORDER BY ag.grp

-- @metric cloud_agent_outcomes
-- prs, closed, open: PRs opened in the period. merged: PRs merged in the period (D12), so merged + closed
-- + open can differ from prs.
SELECT
  'mode:cloud_agent' AS grp,
  (SELECT COUNT(*) FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
    WHERE g.grp = 'mode:cloud_agent' AND f.in_created = 1) AS prs,
  (SELECT COUNT(*) FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
    WHERE g.grp = 'mode:cloud_agent' AND f.in_merged = 1 AND f.status = 'MERGED') AS merged,
  (SELECT COUNT(*) FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
    WHERE g.grp = 'mode:cloud_agent' AND f.in_created = 1 AND f.status = 'CLOSED') AS closed,
  (SELECT COUNT(*) FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
    WHERE g.grp = 'mode:cloud_agent' AND f.in_created = 1 AND f.status = 'OPEN') AS open

-- @metric pr_classification
-- One row per PR: the marks that hit (mark:tool), the tools, the modes. For checking the classification directly.
SELECT
  CONCAT('pr:', p.id) AS grp,
  (SELECT GROUP_CONCAT(DISTINCT CONCAT(m.mark, ':', m.tool) ORDER BY m.mark, m.tool SEPARATOR ',')
     FROM marks m WHERE m.pr_id = p.id) AS marks,
  COALESCE((SELECT GROUP_CONCAT(DISTINCT t.tool ORDER BY t.tool SEPARATOR ',')
              FROM pr_tool t WHERE t.pr_id = p.id), 'everything_else') AS tools,
  COALESCE((SELECT GROUP_CONCAT(DISTINCT md.mode ORDER BY md.mode SEPARATOR ',')
              FROM pr_mode md WHERE md.pr_id = p.id), 'everything_else') AS modes,
  CASE WHEN EXISTS (SELECT 1 FROM pr_mode md WHERE md.pr_id = p.id) THEN 1 ELSE 0 END AS ai_used,
  p.in_created,
  p.in_merged
FROM pr_base p
ORDER BY p.id

-- @metric diagnostics
-- prs_without_commit_message: PRs opened in the period for which no commit message could be read (see ADR 0002).
-- tool_group_total_minus_pr_total: the sum of the tool groups minus the number of PRs (the overlap), PRs opened in the period.
SELECT
  'check:prs_without_commit_message' AS grp,
  (SELECT COUNT(*) FROM pr_base p
    WHERE p.in_created = 1
      AND NOT EXISTS (SELECT 1 FROM pr_commit pc WHERE pc.pr_id = p.id AND pc.message IS NOT NULL)) AS value
UNION ALL
SELECT
  'check:tool_group_total_minus_pr_total',
  (SELECT COUNT(*) FROM pr_group g JOIN pr_facts f ON f.id = g.pr_id
    WHERE g.grp LIKE 'tool:%' AND f.in_created = 1)
  - (SELECT COUNT(*) FROM pr_base p WHERE p.in_created = 1)
