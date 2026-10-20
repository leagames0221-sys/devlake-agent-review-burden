-- Per-PR values of U1 for the U4 check against GitHub's raw data (docs/validation/u4-real-data.md).
-- This file has no @common block. tools/run_on_devlake.py appends the @metric below to the @common WITH list of
-- sql/mysql/agent_review_burden.sql WITHOUT changing it. The period filter of that file is on the time a PR was opened.

-- @metric per_pr_u1
-- One row per PR opened in the period: the agent group of U1, the first human reaction (1) and the first human reaction
-- of someone who is not an assignee (1B), both in whole minutes (NULL when nobody reacted), size and outcome.
SELECT
  CONCAT('pr:', f.id) AS grp,
  pr.base_repo_id,
  pr.pull_request_key AS number,
  f.agent,
  f.status,
  f.size,
  f.first_human_min,
  f.first_human_min_excl_assignee
FROM pr_facts f
JOIN pull_requests pr ON pr.id = f.id
ORDER BY f.id
