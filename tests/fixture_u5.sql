-- Synthetic fixture for U5 (12 PRs, one repo, all times UTC): the scenes of the dashboard variables (SPEC V2, ADR 0004). Own file, so that the fixtures
-- of U1 and U2 and their expected values stay as they are. Expected values: expected_u5_vars.json, worked out by hand from the rows below.
-- Ids: accounts github:GithubAccount:1:N, PRs github:GithubPullRequest:1:3NN (Pk = 300 + k), commit shas sha-3NN-1, comment ids c:3NN:n.
-- Period of the test: 2026-03-01 .. 2026-03-31. Every PR is opened at 00:00 of its day, has one commit authored at that time, and is merged.
-- The account coderabbitai[bot] has is_bot = 0 on purpose: only the identities list makes it a bot (ADR 0002 D11). The identities list must not be filtered
-- by the selection of tools (ADR 0004): scene P4 shows it.
--   P1  (301) the PR author is cursor[bot] (m1, cursor, cloud agent). First review by bob after 60 minutes.
--   P2  (302) a human PR; the commit text has "Made-with: Cursor" (m5, cursor, AI-assisted). First review after 30 minutes.
--   P3  (303) a human PR; the commit text has "Co-authored-by: Claude" (m4, claude, AI-assisted). First review after 90 minutes.
--   P4  (304) a human PR; coderabbitai[bot] reviews after 10 minutes (m6, coderabbit, review agent; a bot only through identities); bob reviews after 45.
--   P5  (305) no mark. First review after 120 minutes.
--   P6  (306) no mark. First review after 180 minutes.
--   P7  (307) the first commit is authored by "Cursor Agent" (m2 and m3, cursor: cloud agent and AI-assisted). First review after 40 minutes.
--   P8  (308) branch claude/p8 (x1, claude; only with own markers). A line comment (DIFF) of carol after 35 minutes, the first review by bob after 50.
--   P9  (309) the PR body has Co-Authored-By: Claude (x2, claude; only with own markers). First review after 70 minutes.
--   P10 (310) the PR author is acme-agent[bot] (a custom tool in scene 7; no mark otherwise). First review after 20 minutes.
--   P11 (311) "Co-authored-by: Claude" in the commit (m4, claude). A NORMAL comment by carol after 15 minutes, the first review (COMMENTED) by bob after 100.
--   P12 (312) a line comment (DIFF) of coderabbitai[bot] after 8 minutes (m6, coderabbit); an unsent review (PENDING) of carol after 2 minutes and a NORMAL
--        comment of the PR author bob after 5 minutes (neither counts, D3 and the safeguard); the first review (APPROVED) by carol after 60 minutes.

INSERT INTO accounts (id, user_name, is_bot) VALUES
 ('github:GithubAccount:1:1', 'alice', 0),
 ('github:GithubAccount:1:2', 'bob', 0),
 ('github:GithubAccount:1:3', 'carol', 0),
 ('github:GithubAccount:1:4', 'coderabbitai[bot]', 0),
 ('github:GithubAccount:1:5', 'cursor[bot]', 1),
 ('github:GithubAccount:1:6', 'acme-agent[bot]', 0);

INSERT INTO pull_requests
 (id, base_repo_id, status, description, author_name, author_id, created_date, merged_date, closed_date, head_ref, additions, deletions, is_draft) VALUES
 ('github:GithubPullRequest:1:301', 'github:GithubRepo:1:1', 'MERGED', '', 'cursor[bot]', 'github:GithubAccount:1:5', '2026-03-02 00:00:00', '2026-03-02 06:00:00', '2026-03-02 06:00:00', 'agent/p1', 10, 0, 0),
 ('github:GithubPullRequest:1:302', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-03 00:00:00', '2026-03-03 06:00:00', '2026-03-03 06:00:00', 'feature/p2', 10, 0, 0),
 ('github:GithubPullRequest:1:303', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-04 00:00:00', '2026-03-04 06:00:00', '2026-03-04 06:00:00', 'feature/p3', 10, 0, 0),
 ('github:GithubPullRequest:1:304', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-05 00:00:00', '2026-03-05 06:00:00', '2026-03-05 06:00:00', 'feature/p4', 10, 0, 0),
 ('github:GithubPullRequest:1:305', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-06 00:00:00', '2026-03-06 06:00:00', '2026-03-06 06:00:00', 'feature/p5', 10, 0, 0),
 ('github:GithubPullRequest:1:306', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-09 00:00:00', '2026-03-09 06:00:00', '2026-03-09 06:00:00', 'feature/p6', 10, 0, 0),
 ('github:GithubPullRequest:1:307', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-10 00:00:00', '2026-03-10 06:00:00', '2026-03-10 06:00:00', 'feature/p7', 10, 0, 0),
 ('github:GithubPullRequest:1:308', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-11 00:00:00', '2026-03-11 06:00:00', '2026-03-11 06:00:00', 'claude/p8', 10, 0, 0),
 ('github:GithubPullRequest:1:309', 'github:GithubRepo:1:1', 'MERGED', 'Add y\n\nCo-Authored-By: Claude <noreply@anthropic.com>', 'bob', 'github:GithubAccount:1:2', '2026-03-12 00:00:00', '2026-03-12 06:00:00', '2026-03-12 06:00:00', 'feature/p9', 10, 0, 0),
 ('github:GithubPullRequest:1:310', 'github:GithubRepo:1:1', 'MERGED', '', 'acme-agent[bot]', 'github:GithubAccount:1:6', '2026-03-13 00:00:00', '2026-03-13 06:00:00', '2026-03-13 06:00:00', 'acme/p10', 10, 0, 0),
 ('github:GithubPullRequest:1:311', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-16 00:00:00', '2026-03-16 06:00:00', '2026-03-16 06:00:00', 'feature/p11', 10, 0, 0),
 ('github:GithubPullRequest:1:312', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-17 00:00:00', '2026-03-17 06:00:00', '2026-03-17 06:00:00', 'feature/p12', 10, 0, 0);

INSERT INTO pull_request_commits (commit_sha, pull_request_id, commit_author_name, commit_author_email, commit_authored_date) VALUES
 ('sha-301-1', 'github:GithubPullRequest:1:301', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00'),
 ('sha-302-1', 'github:GithubPullRequest:1:302', 'Pat Dev', 'pat@example.com', '2026-03-03 00:00:00'),
 ('sha-303-1', 'github:GithubPullRequest:1:303', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00'),
 ('sha-304-1', 'github:GithubPullRequest:1:304', 'Pat Dev', 'pat@example.com', '2026-03-05 00:00:00'),
 ('sha-305-1', 'github:GithubPullRequest:1:305', 'Pat Dev', 'pat@example.com', '2026-03-06 00:00:00'),
 ('sha-306-1', 'github:GithubPullRequest:1:306', 'Pat Dev', 'pat@example.com', '2026-03-09 00:00:00'),
 ('sha-307-1', 'github:GithubPullRequest:1:307', 'Cursor Agent', 'noreply@example.com', '2026-03-10 00:00:00'),
 ('sha-308-1', 'github:GithubPullRequest:1:308', 'Pat Dev', 'pat@example.com', '2026-03-11 00:00:00'),
 ('sha-309-1', 'github:GithubPullRequest:1:309', 'Pat Dev', 'pat@example.com', '2026-03-12 00:00:00'),
 ('sha-310-1', 'github:GithubPullRequest:1:310', 'Pat Dev', 'pat@example.com', '2026-03-13 00:00:00'),
 ('sha-311-1', 'github:GithubPullRequest:1:311', 'Pat Dev', 'pat@example.com', '2026-03-16 00:00:00'),
 ('sha-312-1', 'github:GithubPullRequest:1:312', 'Pat Dev', 'pat@example.com', '2026-03-17 00:00:00');

-- commits.message is a LONGBLOB as in a real DevLake (tests/schema_mysql.sql)
INSERT INTO commits (sha, message, author_name, author_email, authored_date, committer_name, committer_email) VALUES
 ('sha-301-1', 'Work 301', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-302-1', 'Add p2\n\nMade-with: Cursor', 'Pat Dev', 'pat@example.com', '2026-03-03 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-303-1', 'Fix p3\n\nCo-authored-by: Claude <noreply@anthropic.com>', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-304-1', 'Work 304', 'Pat Dev', 'pat@example.com', '2026-03-05 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-305-1', 'Work 305', 'Pat Dev', 'pat@example.com', '2026-03-06 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-306-1', 'Work 306', 'Pat Dev', 'pat@example.com', '2026-03-09 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-307-1', 'Implement p7', 'Cursor Agent', 'noreply@example.com', '2026-03-10 00:00:00', 'Cursor Agent', 'noreply@example.com'),
 ('sha-308-1', 'Work 308', 'Pat Dev', 'pat@example.com', '2026-03-11 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-309-1', 'Work 309', 'Pat Dev', 'pat@example.com', '2026-03-12 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-310-1', 'Work 310', 'Pat Dev', 'pat@example.com', '2026-03-13 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-311-1', 'Fix p11\n\nCo-authored-by: Claude <noreply@anthropic.com>', 'Pat Dev', 'pat@example.com', '2026-03-16 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-312-1', 'Work 312', 'Pat Dev', 'pat@example.com', '2026-03-17 00:00:00', 'Pat Dev', 'pat@example.com');

-- Comments. type REVIEW carries the GitHub state in status; DIFF and NORMAL have status ''.
INSERT INTO pull_request_comments (id, pull_request_id, body, account_id, created_date, type, review_id, status) VALUES
 ('c:301:1', 'github:GithubPullRequest:1:301', 'text', 'github:GithubAccount:1:2', '2026-03-02 01:00:00', 'REVIEW', 'rv:301:1', 'APPROVED'),
 ('c:302:1', 'github:GithubPullRequest:1:302', 'text', 'github:GithubAccount:1:2', '2026-03-03 00:30:00', 'REVIEW', 'rv:302:1', 'APPROVED'),
 ('c:303:1', 'github:GithubPullRequest:1:303', 'text', 'github:GithubAccount:1:3', '2026-03-04 01:30:00', 'REVIEW', 'rv:303:1', 'APPROVED'),
 ('c:304:1', 'github:GithubPullRequest:1:304', 'text', 'github:GithubAccount:1:4', '2026-03-05 00:10:00', 'REVIEW', 'rv:304:1', 'COMMENTED'),
 ('c:304:2', 'github:GithubPullRequest:1:304', 'text', 'github:GithubAccount:1:2', '2026-03-05 00:45:00', 'REVIEW', 'rv:304:2', 'APPROVED'),
 ('c:305:1', 'github:GithubPullRequest:1:305', 'text', 'github:GithubAccount:1:2', '2026-03-06 02:00:00', 'REVIEW', 'rv:305:1', 'APPROVED'),
 ('c:306:1', 'github:GithubPullRequest:1:306', 'text', 'github:GithubAccount:1:3', '2026-03-09 03:00:00', 'REVIEW', 'rv:306:1', 'APPROVED'),
 ('c:307:1', 'github:GithubPullRequest:1:307', 'text', 'github:GithubAccount:1:2', '2026-03-10 00:40:00', 'REVIEW', 'rv:307:1', 'APPROVED'),
 ('c:308:1', 'github:GithubPullRequest:1:308', 'text', 'github:GithubAccount:1:2', '2026-03-11 00:50:00', 'REVIEW', 'rv:308:1', 'APPROVED'),
 ('c:308:2', 'github:GithubPullRequest:1:308', 'text', 'github:GithubAccount:1:3', '2026-03-11 00:35:00', 'DIFF', 'rv:308:2', ''),
 ('c:309:1', 'github:GithubPullRequest:1:309', 'text', 'github:GithubAccount:1:3', '2026-03-12 01:10:00', 'REVIEW', 'rv:309:1', 'APPROVED'),
 ('c:310:1', 'github:GithubPullRequest:1:310', 'text', 'github:GithubAccount:1:2', '2026-03-13 00:20:00', 'REVIEW', 'rv:310:1', 'APPROVED'),
 ('c:311:1', 'github:GithubPullRequest:1:311', 'text', 'github:GithubAccount:1:3', '2026-03-16 00:15:00', 'NORMAL', '', ''),
 ('c:311:2', 'github:GithubPullRequest:1:311', 'text', 'github:GithubAccount:1:2', '2026-03-16 01:40:00', 'REVIEW', 'rv:311:2', 'COMMENTED'),
 ('c:312:1', 'github:GithubPullRequest:1:312', 'text', 'github:GithubAccount:1:3', '2026-03-17 00:02:00', 'REVIEW', 'rv:312:1', 'PENDING'),
 ('c:312:2', 'github:GithubPullRequest:1:312', 'text', 'github:GithubAccount:1:2', '2026-03-17 00:05:00', 'NORMAL', '', ''),
 ('c:312:3', 'github:GithubPullRequest:1:312', 'text', 'github:GithubAccount:1:4', '2026-03-17 00:08:00', 'DIFF', 'rv:312:3', ''),
 ('c:312:4', 'github:GithubPullRequest:1:312', 'text', 'github:GithubAccount:1:3', '2026-03-17 01:00:00', 'REVIEW', 'rv:312:4', 'APPROVED');
