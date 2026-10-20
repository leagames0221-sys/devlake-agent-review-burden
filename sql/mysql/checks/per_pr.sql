-- Per-PR values for the U4 check against GitHub's raw data (docs/validation/u4-real-data.md).
-- This file has no @common block. tools/run_on_devlake.py appends the @metric below to the @common WITH list of
-- sql/mysql/ai_impact_parity.sql WITHOUT changing it, so the times, the size and the outcome that are compared are the
-- ones the real metrics are built from (pr_facts). Macros and the row key (first column) are as in that file.

-- @metric per_pr
-- One row per PR that was opened or merged in the period: DevLake's repo id, the PR number, the outcome, size
-- (additions + deletions), the two period flags, the three times in whole minutes (NULL when undefined), the ISO week.
SELECT
  CONCAT('pr:', f.id) AS grp,
  pr.base_repo_id,
  pr.pull_request_key AS number,
  f.status,
  f.size,
  f.in_created,
  f.in_merged,
  f.ttfr_min,
  f.tir_min,
  f.cycle_min,
  f.yw
FROM pr_facts f
JOIN pull_requests pr ON pr.id = f.id
ORDER BY f.id
