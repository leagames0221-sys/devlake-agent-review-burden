-- Synthetic fixture for U1 (13 PRs, one repo, all times UTC, no draft PRs).
-- The expected values for this data are in expected_u1.json.
-- Ids as they appear below: account ids github:GithubAccount:1:N, PR ids
-- github:GithubPullRequest:1:1NN (P1 = 101 ... P13 = 113), comment ids c:<PR number>:<n>
-- (for example c:101:3), review ids rv:<PR number>:<n>.
-- The account "Copilot" has is_bot = 0 on purpose: DevLake's REST path cannot read the user
-- type of "Copilot" (GET /users/Copilot returns 404), so the account is stored as a non-bot.

INSERT INTO accounts (id, user_name, is_bot) VALUES
 ('github:GithubAccount:1:1', 'alice', 0),
 ('github:GithubAccount:1:2', 'bob', 0),
 ('github:GithubAccount:1:3', 'carol', 0),
 ('github:GithubAccount:1:4', 'dave', 0),
 ('github:GithubAccount:1:5', 'Copilot', 0),
 ('github:GithubAccount:1:6', 'copilot-swe-agent[bot]', 1),
 ('github:GithubAccount:1:7', 'devin-ai-integration[bot]', 1),
 ('github:GithubAccount:1:8', 'coderabbitai[bot]', 1),
 ('github:GithubAccount:1:9', 'dependabot[bot]', 1);

INSERT INTO pull_requests
 (id, base_repo_id, status, description, author_name, author_id, created_date, merged_date, closed_date, head_ref, additions, deletions, is_draft) VALUES
 ('github:GithubPullRequest:1:101', 'github:GithubRepo:1:1', 'MERGED', '', 'Copilot', 'github:GithubAccount:1:5', '2026-03-02 10:00:00', '2026-03-03 10:00:00', '2026-03-03 10:00:00', 'copilot/fix-1', 30, 10, 0),
 ('github:GithubPullRequest:1:102', 'github:GithubRepo:1:1', 'CLOSED', '', 'copilot-swe-agent[bot]', 'github:GithubAccount:1:6', '2026-03-04 00:00:00', NULL, '2026-03-05 00:00:00', 'copilot/feat-2', 100, 0, 0),
 ('github:GithubPullRequest:1:103', 'github:GithubRepo:1:1', 'MERGED', '', 'devin-ai-integration[bot]', 'github:GithubAccount:1:7', '2026-03-06 00:00:00', '2026-03-06 06:00:00', '2026-03-06 06:00:00', 'devin/task-3', 5, 5, 0),
 ('github:GithubPullRequest:1:104', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-10 00:00:00', NULL, NULL, 'codex/refactor-4', 50, 50, 0),
 ('github:GithubPullRequest:1:105', 'github:GithubRepo:1:1', 'MERGED', 'Adds feature x.\n\nCo-Authored-By: Claude <noreply@anthropic.com>', 'bob', 'github:GithubAccount:1:2', '2026-03-12 00:00:00', '2026-03-12 12:00:00', '2026-03-12 12:00:00', 'feature/x', 20, 0, 0),
 ('github:GithubPullRequest:1:106', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-13 00:00:00', '2026-03-13 02:00:00', '2026-03-13 02:00:00', 'claude/issue-6', 7, 3, 0),
 ('github:GithubPullRequest:1:107', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-02 00:00:00', '2026-03-02 05:00:00', '2026-03-02 05:00:00', 'feature/a', 3, 1, 0),
 ('github:GithubPullRequest:1:108', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-03 00:00:00', '2026-03-03 10:00:00', '2026-03-03 10:00:00', 'fix/b', 10, 10, 0),
 ('github:GithubPullRequest:1:109', 'github:GithubRepo:1:1', 'CLOSED', '', 'dave', 'github:GithubAccount:1:4', '2026-03-04 00:00:00', NULL, '2026-03-04 08:00:00', 'feat/c', 200, 0, 0),
 ('github:GithubPullRequest:1:110', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-20 00:00:00', NULL, NULL, 'docs/d', 1, 1, 0),
 ('github:GithubPullRequest:1:111', 'github:GithubRepo:1:1', 'MERGED', '', 'dependabot[bot]', 'github:GithubAccount:1:9', '2026-03-05 00:00:00', '2026-03-05 01:00:00', '2026-03-05 01:00:00', 'dependabot/npm/x', 2, 2, 0),
 ('github:GithubPullRequest:1:112', 'github:GithubRepo:1:1', 'MERGED', 'Add Y

co-authored-by: claude <noreply@anthropic.com>', 'dave', 'github:GithubAccount:1:4', '2026-03-14 00:00:00', '2026-03-14 03:00:00', '2026-03-14 03:00:00', 'feature/y', 4, 4, 0),
 ('github:GithubPullRequest:1:113', 'github:GithubRepo:1:1', 'OPEN', 'Docs

Co-Authored-By: Claude <noreply@anthropic.com>', 'bob', 'github:GithubAccount:1:2', '2026-03-15 00:00:00', NULL, NULL, 'copilot/doc-13', 6, 0, 0);

INSERT INTO pull_request_assignees (pull_request_id, assignee_id, name, user_name) VALUES
 ('github:GithubPullRequest:1:101', 'github:GithubAccount:1:1', 'alice', 'alice'),
 ('github:GithubPullRequest:1:103', 'github:GithubAccount:1:3', 'carol', 'carol');

-- DIFF row shares review_id with its REVIEW row.
INSERT INTO pull_request_comments (id, pull_request_id, body, account_id, created_date, type, review_id, status) VALUES
 -- P1
 ('c:101:1', 'github:GithubPullRequest:1:101', 'bot review',   'github:GithubAccount:1:8', '2026-03-02 10:05:00', 'REVIEW', 'rv:101:1', 'COMMENTED'),
 ('c:101:2', 'github:GithubPullRequest:1:101', 'please fix',   'github:GithubAccount:1:1', '2026-03-02 10:30:00', 'NORMAL', '',         ''),
 ('c:101:3', 'github:GithubPullRequest:1:101', 'changes',      'github:GithubAccount:1:2', '2026-03-02 12:00:00', 'REVIEW', 'rv:101:2', 'CHANGES_REQUESTED'),
 ('c:101:4', 'github:GithubPullRequest:1:101', 'line comment', 'github:GithubAccount:1:2', '2026-03-02 12:00:00', 'DIFF',   'rv:101:2', ''),
 ('c:101:5', 'github:GithubPullRequest:1:101', 'ok',           'github:GithubAccount:1:1', '2026-03-03 09:00:00', 'REVIEW', 'rv:101:3', 'APPROVED'),
 -- P2 (bob's review is unsent: PENDING, no time)
 ('c:102:1', 'github:GithubPullRequest:1:102', 'bot review',   'github:GithubAccount:1:8', '2026-03-04 00:01:00', 'REVIEW', 'rv:102:1', 'COMMENTED'),
 ('c:102:2', 'github:GithubPullRequest:1:102', 'draft review', 'github:GithubAccount:1:2', NULL,                  'REVIEW', 'rv:102:2', 'PENDING'),
 -- P3
 ('c:103:1', 'github:GithubPullRequest:1:103', 'please fix',   'github:GithubAccount:1:3', '2026-03-06 01:00:00', 'NORMAL', '',         ''),
 ('c:103:2', 'github:GithubPullRequest:1:103', 'ok',           'github:GithubAccount:1:4', '2026-03-06 03:00:00', 'REVIEW', 'rv:103:1', 'APPROVED'),
 -- P4 (alice is the author; carol and bob's review are at the same time 02:00)
 ('c:104:1', 'github:GithubPullRequest:1:104', 'author note',  'github:GithubAccount:1:1', '2026-03-10 00:10:00', 'NORMAL', '',         ''),
 ('c:104:2', 'github:GithubPullRequest:1:104', 'changes',      'github:GithubAccount:1:2', '2026-03-10 02:00:00', 'REVIEW', 'rv:104:1', 'CHANGES_REQUESTED'),
 ('c:104:3', 'github:GithubPullRequest:1:104', 'question',     'github:GithubAccount:1:3', '2026-03-10 02:00:00', 'NORMAL', '',         ''),
 -- P5
 ('c:105:1', 'github:GithubPullRequest:1:105', 'ok',           'github:GithubAccount:1:1', '2026-03-12 00:45:00', 'REVIEW', 'rv:105:1', 'APPROVED'),
 -- P6
 ('c:106:1', 'github:GithubPullRequest:1:106', 'nit',          'github:GithubAccount:1:2', '2026-03-13 00:20:00', 'NORMAL', '',         ''),
 -- P7
 ('c:107:1', 'github:GithubPullRequest:1:107', 'bot review',   'github:GithubAccount:1:8', '2026-03-02 00:05:00', 'REVIEW', 'rv:107:1', 'COMMENTED'),
 ('c:107:2', 'github:GithubPullRequest:1:107', 'changes',      'github:GithubAccount:1:1', '2026-03-02 00:30:00', 'REVIEW', 'rv:107:2', 'CHANGES_REQUESTED'),
 ('c:107:3', 'github:GithubPullRequest:1:107', 'ok',           'github:GithubAccount:1:1', '2026-03-02 03:00:00', 'REVIEW', 'rv:107:3', 'APPROVED'),
 -- P8
 ('c:108:1', 'github:GithubPullRequest:1:108', 'nit',          'github:GithubAccount:1:4', '2026-03-03 01:00:00', 'NORMAL', '',         ''),
 ('c:108:2', 'github:GithubPullRequest:1:108', 'ok',           'github:GithubAccount:1:4', '2026-03-03 02:00:00', 'REVIEW', 'rv:108:1', 'APPROVED'),
 ('c:108:3', 'github:GithubPullRequest:1:108', 'agent review', 'github:GithubAccount:1:5', '2026-03-03 00:30:00', 'REVIEW', 'rv:108:2', 'COMMENTED'),
 -- P9: none
 -- P10 (DIFF and NORMAL at the same time 03:00)
 ('c:110:1', 'github:GithubPullRequest:1:110', 'typo',         'github:GithubAccount:1:2', '2026-03-20 03:00:00', 'NORMAL', '',         ''),
 ('c:110:2', 'github:GithubPullRequest:1:110', 'line comment', 'github:GithubAccount:1:2', '2026-03-20 03:00:00', 'DIFF',   'rv:110:1', ''),
 -- P11: none
 -- P12 (body mark written in lower case)
 ('c:112:1', 'github:GithubPullRequest:1:112', 'nit',          'github:GithubAccount:1:3', '2026-03-14 00:15:00', 'NORMAL', '',         ''),
 -- P13 (copilot/ branch and a Claude mark in the body: the branch rule comes first)
 ('c:113:1', 'github:GithubPullRequest:1:113', 'changes',      'github:GithubAccount:1:1', '2026-03-15 01:00:00', 'REVIEW', 'rv:113:1', 'CHANGES_REQUESTED');
