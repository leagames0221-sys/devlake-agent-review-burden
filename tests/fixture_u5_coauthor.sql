-- Synthetic fixture for U5, the coauthor pattern scene (3 PRs, one repo, all times UTC, period 2026-03-01 .. 2026-03-31). Expected values:
-- expected_u5_vars.json, key "coauthor_scene", worked out by hand. Used with a custom tool acme whose only row is {"field": "coauthor", "pattern": "acme|acme-bot"}:
-- the SQL puts the pattern after `^co-authored-by:[ \t]*` inside a group, so a top-level | does not let the second alternative match anywhere in the text.
--   P21 (331) the commit has a trailer "Co-authored-by: acme-bot <...>" on its 3rd line: m4, acme. First review after 30 minutes.
--   P22 (332) the commit text only names acme-bot in a sentence, no trailer: no mark (everything_else). First review after 60 minutes.
--   P23 (333) the commit has a trailer "Co-authored-by: Acme <...>" (mixed case): m4, acme. First review after 90 minutes.

INSERT INTO accounts (id, user_name, is_bot) VALUES
 ('github:GithubAccount:1:1', 'alice', 0),
 ('github:GithubAccount:1:2', 'bob', 0),
 ('github:GithubAccount:1:3', 'carol', 0);

INSERT INTO pull_requests
 (id, base_repo_id, status, description, author_name, author_id, created_date, merged_date, closed_date, head_ref, additions, deletions, is_draft) VALUES
 ('github:GithubPullRequest:1:331', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-02 00:00:00', '2026-03-02 06:00:00', '2026-03-02 06:00:00', 'feature/p21', 10, 0, 0),
 ('github:GithubPullRequest:1:332', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-03 00:00:00', '2026-03-03 06:00:00', '2026-03-03 06:00:00', 'feature/p22', 10, 0, 0),
 ('github:GithubPullRequest:1:333', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-04 00:00:00', '2026-03-04 06:00:00', '2026-03-04 06:00:00', 'feature/p23', 10, 0, 0);

INSERT INTO pull_request_commits (commit_sha, pull_request_id, commit_author_name, commit_author_email, commit_authored_date) VALUES
 ('sha-331-1', 'github:GithubPullRequest:1:331', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00'),
 ('sha-332-1', 'github:GithubPullRequest:1:332', 'Pat Dev', 'pat@example.com', '2026-03-03 00:00:00'),
 ('sha-333-1', 'github:GithubPullRequest:1:333', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00');

INSERT INTO commits (sha, message, author_name, author_email, authored_date, committer_name, committer_email) VALUES
 ('sha-331-1', 'Add a\n\nCo-authored-by: acme-bot <bot@example.com>', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-332-1', 'Thanks to acme-bot for the idea', 'Pat Dev', 'pat@example.com', '2026-03-03 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-333-1', 'Fix\n\nCo-authored-by: Acme <acme@example.com>', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00', 'Pat Dev', 'pat@example.com');

INSERT INTO pull_request_comments (id, pull_request_id, body, account_id, created_date, type, review_id, status) VALUES
 ('c:331:1', 'github:GithubPullRequest:1:331', 'text', 'github:GithubAccount:1:2', '2026-03-02 00:30:00', 'REVIEW', 'rv:331:1', 'APPROVED'),
 ('c:332:1', 'github:GithubPullRequest:1:332', 'text', 'github:GithubAccount:1:3', '2026-03-03 01:00:00', 'REVIEW', 'rv:332:1', 'APPROVED'),
 ('c:333:1', 'github:GithubPullRequest:1:333', 'text', 'github:GithubAccount:1:1', '2026-03-04 01:30:00', 'REVIEW', 'rv:333:1', 'APPROVED');
