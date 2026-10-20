-- Synthetic fixture for U2 (56 PRs, one repo, all times UTC). Expected values: expected_u2_parity.json
-- (include_own_markers = 0) and expected_u2_own.json (= 1); the per-PR values are written in each file under _per_pr.
-- Ids: accounts github:GithubAccount:1:N, PRs github:GithubPullRequest:1:2NN (Qk = 200 + k, Q01 = 201 ... Q56 = 256),
-- commit shas sha-2NN-n, comment ids c:2NN:n, review ids rv:2NN:n. Period of the test: 2026-03-01 .. 2026-03-31.
-- The account coderabbitai[bot] has is_bot = 0 on purpose (only the identities list marks it as a bot, D11);
-- Copilot has is_bot = 0 as in U1 (GET /users/Copilot answers 404 on the REST path).
-- The accounts CodeRabbitAI[bot] (is_bot = 1) and Qodo-Code-Review[bot] (is_bot = 0) have capitals in the login on purpose (Q46, Q47).
-- The git name of the Cursor agent is "Cursor Agent" and its e-mail cursoragent@cursor.com (docs/agent_identities.md, table B).
-- Scenario of each PR (SPEC section 4):
--   Q01 (201): P-C1 PR author is the agent login (cursor[bot]); MERGED
--   Q02 (202): P-C2 PR author human, first commit author name Cursor Agent (the git name of the agent, mixed case)
--   Q03 (203): P-C2e PR author human, commit name human, commit e-mail is the agent's
--   Q04 (204): P-C3 only the 2nd commit is the agent: ai_assisted, not cloud_agent
--   Q05 (205): P-C4 cloud agent PR CLOSED (devin)
--   Q06 (206): P-C5 cloud agent PR OPEN (devin)
--   Q07 (207): P-C6 review agent (coderabbit) opened the PR: cloud_agent
--   Q08 (208): P-C7 two first commits at the same time, one is the agent (claude)
--   Q09 (209): P-A1 2nd commit, 3rd line: Co-authored-by of an AI tool (claude)
--   Q10 (210): P-A1h Co-authored-by is a person only
--   Q11 (211): P-A1m co-authored-by: Claude is in the middle of a sentence
--   Q12 (212): P-A2 first line MADE-WITH: cursor (mixed case)
--   Q13 (213): P-A3 made-with: cursor only inside a sentence
--   Q14 (214): P-A4 body in DevLake's JSON-string shape (quotes and the 2 characters \n); trailer on the 3rd line
--   Q15 (215): P-A5 CRLF line breaks; trailer on the 3rd line
--   Q16 (216): P-A6 commits row missing (pull_request_commits has the row, commits has not)
--   Q17 (217): P-M1 two tools: Co-authored-by Claude and Made-with: Cursor
--   Q18 (218): P-M2 cloud_agent (devin) and review_agent (qodo)
--   Q19 (219): P-R1 only a review agent review (coderabbit, is_bot = 0): review_agent, not counted for time to first review
--   Q20 (220): P-R2 NORMAL comment (30 min) before the human COMMENTED review (90 min)
--   Q21 (221): P-R3 the author's own review is the earliest (D3)
--   Q22 (222): P-R4 first review is DISMISSED (D2)
--   Q23 (223): P-R5 only a DIFF row of a review agent (D13)
--   Q24 (224): P-V1 two APPROVED, time in review ends at the 2nd
--   Q25 (225): P-V2 merged without APPROVED: ends at the merge (D5)
--   Q26 (226): P-V3 an APPROVED after the merge is not counted (D9)
--   Q27 (227): P-V4 only a bot APPROVED (dependabot): not counted, ends at the merge (D9)
--   Q28 (228): P-U1 reviewed but not merged (OPEN)
--   Q29 (229): P-T1 first commit (03-22 20:00) is before the PR is opened (03-23 00:00)
--   Q30 (230): P-T2 first commit (03-24 02:00) is after the PR is opened (03-24 00:00)
--   Q31 (231): P-D1 opened as a draft (is_draft = 1): same calculation (D4)
--   Q32 (232): P-B1 size 199 (additions + deletions)
--   Q33 (233): P-B1 size 200 (additions + deletions)
--   Q34 (234): P-B1 size 499 (additions + deletions)
--   Q35 (235): P-B1 size 500 (additions + deletions)
--   Q36 (236): P-W1 merged on Sunday 03-08 (ISO week 10)
--   Q37 (237): P-W1 merged on Monday 03-09 (ISO week 11)
--   Q38 (238): P-P1 opened 02-27 (before the period), merged 03-03 (inside): throughput yes, time to first review no
--   Q39 (239): P-N1 no mark at all
--   Q40 (240): P-O1 dependabot (a bot that is not an agent): everything_else
--   Q41 (241): P-X1 only the branch prefix codex/
--   Q42 (242): P-X2 only the PR body Co-Authored-By: Claude
--   Q43 (243): P-N2 login copilot-fan contains the word copilot (anchors, M7)
--   Q44 (244): P-C0 author Copilot (not flagged is_bot), copilot/ branch
--   Q45 (245): P-C0b author copilot-swe-agent[bot], CLOSED
--   Q46 (246): P-L1 review agent login in capitals (CodeRabbitAI[bot], is_bot = 1) writes the only review: m6 needs LOWER (mutation A)
--   Q47 (247): P-L2 review agent login in capitals and NOT flagged (Qodo-Code-Review[bot], is_bot = 0): acct needs LOWER, so the review is a bot review (mutation B)
--   Q48 (248): P-L3 first commit e-mail in capitals (CursorAgent@Cursor.com), human name: m2 and m3 need LOWER on the e-mail (mutation C)
--   Q49 (249): P-L4 JSON-string body, Made-with: Cursor on the 3rd line (the JSON shape of m5, mutation E)
--   Q50 (250): P-L5 JSON-string body, the FIRST line is a Co-authored-by trailer of Claude (the opening quote only, m4, mutation D)
--   Q51 (251): P-L6 JSON-string body, the FIRST line is Made-with: Cursor (the opening quote only, m5, mutation D); OPEN
--   Q52 (252): P-L7 Co-authored-by: Claudette (a person whose name starts with Claude): not a Claude trailer, the word end is needed (mutation F)
--   Q53 (253): P-L8 commit e-mail xcursoragent@cursor.com with a human name: not the agent, the start anchor of the e-mail is needed (mutation G)
--   Q54 (254): P-L9 an APPROVED at exactly the merge time is not counted (strict <, D9); the earlier APPROVED ends Time in review (mutation H)
--   Q55 (255): P-R1 (U4) the shape of a real DevLake: the account is cursor[bot] (is_bot = 1) but pull_requests.author_name is "cursor" (GraphQL path, no [bot]): m1 must read the account (ADR 0002 A1); OPEN
--   Q56 (256): P-R2 (U4) commits.message is a LONGBLOB (as in a real DevLake) and the trailer is written "Co-Authored-By: Claude": m4 needs CONVERT before LOWER (ADR 0002 A2); OPEN
-- P-E1 (even count, median as in U1): the group tool:cursor has 8 PRs merged in the period (Q01 Q02 Q03 Q04 Q12 Q17 Q48 Q49); their time in review is
--   30 30 40 45 60 90 120 240 (sorted); the two middle values are 45 and 60 and the method of DevLake's dashboards gives 45 (the lower one), not 52.5.
-- P-W1: Q36 is merged on Sunday 2026-03-08 and Q37 on Monday 2026-03-09, so they fall in ISO weeks 202610 and 202611.

INSERT INTO accounts (id, user_name, is_bot) VALUES
 ('github:GithubAccount:1:1', 'alice', 0),
 ('github:GithubAccount:1:2', 'bob', 0),
 ('github:GithubAccount:1:3', 'carol', 0),
 ('github:GithubAccount:1:4', 'dave', 0),
 ('github:GithubAccount:1:5', 'Copilot', 0),
 ('github:GithubAccount:1:6', 'copilot-swe-agent[bot]', 1),
 ('github:GithubAccount:1:7', 'cursor[bot]', 1),
 ('github:GithubAccount:1:8', 'devin-ai-integration[bot]', 1),
 ('github:GithubAccount:1:9', 'coderabbitai[bot]', 0),
 ('github:GithubAccount:1:10', 'qodo-code-review[bot]', 1),
 ('github:GithubAccount:1:11', 'dependabot[bot]', 1),
 ('github:GithubAccount:1:12', 'copilot-fan', 0),
 ('github:GithubAccount:1:13', 'CodeRabbitAI[bot]', 1),
 ('github:GithubAccount:1:14', 'Qodo-Code-Review[bot]', 0);

INSERT INTO pull_requests
 (id, base_repo_id, status, description, author_name, author_id, created_date, merged_date, closed_date, head_ref, additions, deletions, is_draft) VALUES
 ('github:GithubPullRequest:1:201', 'github:GithubRepo:1:1', 'MERGED', '', 'cursor[bot]', 'github:GithubAccount:1:7', '2026-03-02 00:00:00', '2026-03-02 06:00:00', '2026-03-02 06:00:00', 'agent/c1', 20, 10, 0),
 ('github:GithubPullRequest:1:202', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-03 00:00:00', '2026-03-03 10:00:00', '2026-03-03 10:00:00', 'feature/c2', 40, 0, 0),
 ('github:GithubPullRequest:1:203', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-04 00:00:00', '2026-03-04 08:00:00', '2026-03-04 08:00:00', 'feature/c2e', 25, 5, 0),
 ('github:GithubPullRequest:1:204', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-05 00:00:00', '2026-03-05 04:00:00', '2026-03-05 04:00:00', 'feature/c3', 15, 5, 0),
 ('github:GithubPullRequest:1:205', 'github:GithubRepo:1:1', 'CLOSED', '', 'devin-ai-integration[bot]', 'github:GithubAccount:1:8', '2026-03-04 00:00:00', NULL, '2026-03-05 00:00:00', 'devin/c4', 8, 2, 0),
 ('github:GithubPullRequest:1:206', 'github:GithubRepo:1:1', 'OPEN', '', 'devin-ai-integration[bot]', 'github:GithubAccount:1:8', '2026-03-06 00:00:00', NULL, NULL, 'devin/c5', 12, 3, 0),
 ('github:GithubPullRequest:1:207', 'github:GithubRepo:1:1', 'MERGED', '', 'coderabbitai[bot]', 'github:GithubAccount:1:9', '2026-03-10 00:00:00', '2026-03-10 06:00:00', '2026-03-10 06:00:00', 'coderabbit/fix', 6, 6, 0),
 ('github:GithubPullRequest:1:208', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-11 00:00:00', '2026-03-11 05:00:00', '2026-03-11 05:00:00', 'feature/c7', 30, 10, 0),
 ('github:GithubPullRequest:1:209', 'github:GithubRepo:1:1', 'MERGED', '', 'dave', 'github:GithubAccount:1:4', '2026-03-12 00:00:00', '2026-03-12 03:00:00', '2026-03-12 03:00:00', 'feature/a1', 10, 2, 0),
 ('github:GithubPullRequest:1:210', 'github:GithubRepo:1:1', 'MERGED', '', 'dave', 'github:GithubAccount:1:4', '2026-03-12 06:00:00', '2026-03-12 08:00:00', '2026-03-12 08:00:00', 'feature/a1h', 4, 1, 0),
 ('github:GithubPullRequest:1:211', 'github:GithubRepo:1:1', 'OPEN', '', 'carol', 'github:GithubAccount:1:3', '2026-03-13 00:00:00', NULL, NULL, 'feature/a1m', 3, 3, 0),
 ('github:GithubPullRequest:1:212', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-13 06:00:00', '2026-03-13 08:00:00', '2026-03-13 08:00:00', 'feature/a2', 9, 1, 0),
 ('github:GithubPullRequest:1:213', 'github:GithubRepo:1:1', 'OPEN', '', 'bob', 'github:GithubAccount:1:2', '2026-03-13 12:00:00', NULL, NULL, 'feature/a3', 2, 2, 0),
 ('github:GithubPullRequest:1:214', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-14 00:00:00', '2026-03-14 04:00:00', '2026-03-14 04:00:00', 'feature/a4', 7, 3, 0),
 ('github:GithubPullRequest:1:215', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-14 06:00:00', '2026-03-14 09:00:00', '2026-03-14 09:00:00', 'feature/a5', 5, 5, 0),
 ('github:GithubPullRequest:1:216', 'github:GithubRepo:1:1', 'OPEN', '', 'dave', 'github:GithubAccount:1:4', '2026-03-15 00:00:00', NULL, NULL, 'feature/a6', 1, 0, 0),
 ('github:GithubPullRequest:1:217', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-15 06:00:00', '2026-03-15 10:00:00', '2026-03-15 10:00:00', 'feature/m1', 18, 2, 0),
 ('github:GithubPullRequest:1:218', 'github:GithubRepo:1:1', 'MERGED', '', 'devin-ai-integration[bot]', 'github:GithubAccount:1:8', '2026-03-16 00:00:00', '2026-03-16 06:00:00', '2026-03-16 06:00:00', 'devin/m2', 22, 8, 0),
 ('github:GithubPullRequest:1:219', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-16 12:00:00', NULL, NULL, 'feature/r1', 5, 5, 0),
 ('github:GithubPullRequest:1:220', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-17 00:00:00', '2026-03-17 05:00:00', '2026-03-17 05:00:00', 'feature/r2', 14, 6, 0),
 ('github:GithubPullRequest:1:221', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-17 06:00:00', '2026-03-17 10:00:00', '2026-03-17 10:00:00', 'feature/r3', 11, 4, 0),
 ('github:GithubPullRequest:1:222', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-18 00:00:00', '2026-03-18 04:00:00', '2026-03-18 04:00:00', 'feature/r4', 13, 2, 0),
 ('github:GithubPullRequest:1:223', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-18 06:00:00', NULL, NULL, 'feature/r5', 4, 4, 0),
 ('github:GithubPullRequest:1:224', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-19 00:00:00', '2026-03-19 05:00:00', '2026-03-19 05:00:00', 'feature/v1', 16, 4, 0),
 ('github:GithubPullRequest:1:225', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-19 06:00:00', '2026-03-19 10:00:00', '2026-03-19 10:00:00', 'feature/v2', 9, 9, 0),
 ('github:GithubPullRequest:1:226', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-20 00:00:00', '2026-03-20 05:00:00', '2026-03-20 05:00:00', 'feature/v3', 12, 8, 0),
 ('github:GithubPullRequest:1:227', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-20 06:00:00', '2026-03-20 09:20:00', '2026-03-20 09:20:00', 'feature/v4', 3, 1, 0),
 ('github:GithubPullRequest:1:228', 'github:GithubRepo:1:1', 'OPEN', '', 'carol', 'github:GithubAccount:1:3', '2026-03-21 00:00:00', NULL, NULL, 'feature/u1', 6, 2, 0),
 ('github:GithubPullRequest:1:229', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-23 00:00:00', '2026-03-23 10:00:00', '2026-03-23 10:00:00', 'feature/t1', 21, 9, 0),
 ('github:GithubPullRequest:1:230', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-24 00:00:00', '2026-03-24 10:00:00', '2026-03-24 10:00:00', 'feature/t2', 17, 3, 0),
 ('github:GithubPullRequest:1:231', 'github:GithubRepo:1:1', 'MERGED', '', 'dave', 'github:GithubAccount:1:4', '2026-03-25 00:00:00', '2026-03-25 12:00:00', '2026-03-25 12:00:00', 'feature/d1', 19, 1, 1),
 ('github:GithubPullRequest:1:232', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-26 00:00:00', '2026-03-26 02:00:00', '2026-03-26 02:00:00', 'feature/b199', 150, 49, 0),
 ('github:GithubPullRequest:1:233', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-26 00:00:00', '2026-03-26 02:00:00', '2026-03-26 02:00:00', 'feature/b200', 100, 100, 0),
 ('github:GithubPullRequest:1:234', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-26 00:00:00', '2026-03-26 02:00:00', '2026-03-26 02:00:00', 'feature/b499', 400, 99, 0),
 ('github:GithubPullRequest:1:235', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-26 00:00:00', '2026-03-26 02:00:00', '2026-03-26 02:00:00', 'feature/b500', 300, 200, 0),
 ('github:GithubPullRequest:1:236', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-08 00:00:00', '2026-03-08 12:00:00', '2026-03-08 12:00:00', 'feature/w1a', 5, 5, 0),
 ('github:GithubPullRequest:1:237', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-09 00:00:00', '2026-03-09 12:00:00', '2026-03-09 12:00:00', 'feature/w1b', 5, 5, 0),
 ('github:GithubPullRequest:1:238', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-02-27 00:00:00', '2026-03-03 12:00:00', '2026-03-03 12:00:00', 'feature/p1', 30, 10, 0),
 ('github:GithubPullRequest:1:239', 'github:GithubRepo:1:1', 'MERGED', '', 'dave', 'github:GithubAccount:1:4', '2026-03-27 00:00:00', '2026-03-27 04:00:00', '2026-03-27 04:00:00', 'feature/n1', 8, 2, 0),
 ('github:GithubPullRequest:1:240', 'github:GithubRepo:1:1', 'MERGED', '', 'dependabot[bot]', 'github:GithubAccount:1:11', '2026-03-27 06:00:00', '2026-03-27 07:00:00', '2026-03-27 07:00:00', 'dependabot/npm/x', 2, 2, 0),
 ('github:GithubPullRequest:1:241', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-28 00:00:00', '2026-03-28 06:00:00', '2026-03-28 06:00:00', 'codex/refactor', 50, 10, 0),
 ('github:GithubPullRequest:1:242', 'github:GithubRepo:1:1', 'MERGED', 'Add y\n\nCo-Authored-By: Claude <noreply@anthropic.com>', 'bob', 'github:GithubAccount:1:2', '2026-03-28 12:00:00', '2026-03-28 14:00:00', '2026-03-28 14:00:00', 'feature/x2', 14, 6, 0),
 ('github:GithubPullRequest:1:243', 'github:GithubRepo:1:1', 'OPEN', '', 'copilot-fan', 'github:GithubAccount:1:12', '2026-03-29 00:00:00', NULL, NULL, 'feature/n2', 1, 1, 0),
 ('github:GithubPullRequest:1:244', 'github:GithubRepo:1:1', 'MERGED', '', 'Copilot', 'github:GithubAccount:1:5', '2026-03-29 06:00:00', '2026-03-29 12:00:00', '2026-03-29 12:00:00', 'copilot/fix-44', 28, 12, 0),
 ('github:GithubPullRequest:1:245', 'github:GithubRepo:1:1', 'CLOSED', '', 'copilot-swe-agent[bot]', 'github:GithubAccount:1:6', '2026-03-30 00:00:00', NULL, '2026-03-30 12:00:00', 'feature/z', 10, 0, 0),
 ('github:GithubPullRequest:1:246', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-30 06:00:00', NULL, NULL, 'feature/l1', 3, 3, 0),
 ('github:GithubPullRequest:1:247', 'github:GithubRepo:1:1', 'OPEN', '', 'alice', 'github:GithubAccount:1:1', '2026-03-30 12:00:00', NULL, NULL, 'feature/l2', 3, 3, 0),
 ('github:GithubPullRequest:1:248', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-28 18:00:00', '2026-03-29 09:00:00', '2026-03-29 09:00:00', 'feature/l3', 10, 2, 0),
 ('github:GithubPullRequest:1:249', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-10 12:00:00', '2026-03-10 16:00:00', '2026-03-10 16:00:00', 'feature/l4', 4, 1, 0),
 ('github:GithubPullRequest:1:250', 'github:GithubRepo:1:1', 'MERGED', '', 'alice', 'github:GithubAccount:1:1', '2026-03-30 06:00:00', '2026-03-30 09:00:00', '2026-03-30 09:00:00', 'feature/l5', 6, 0, 0),
 ('github:GithubPullRequest:1:251', 'github:GithubRepo:1:1', 'OPEN', '', 'dave', 'github:GithubAccount:1:4', '2026-03-31 00:00:00', NULL, NULL, 'feature/l6', 2, 1, 0),
 ('github:GithubPullRequest:1:252', 'github:GithubRepo:1:1', 'MERGED', '', 'carol', 'github:GithubAccount:1:3', '2026-03-12 12:00:00', '2026-03-12 14:00:00', '2026-03-12 14:00:00', 'feature/l7', 5, 0, 0),
 ('github:GithubPullRequest:1:253', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-18 12:00:00', '2026-03-18 15:00:00', '2026-03-18 15:00:00', 'feature/l8', 4, 4, 0),
 ('github:GithubPullRequest:1:254', 'github:GithubRepo:1:1', 'MERGED', '', 'bob', 'github:GithubAccount:1:2', '2026-03-17 12:00:00', '2026-03-17 18:00:00', '2026-03-17 18:00:00', 'feature/l9', 7, 3, 0),
 ('github:GithubPullRequest:1:255', 'github:GithubRepo:1:1', 'OPEN', '', 'cursor', 'github:GithubAccount:1:7', '2026-03-19 00:00:00', NULL, NULL, 'agent/r1', 7, 5, 0),
 ('github:GithubPullRequest:1:256', 'github:GithubRepo:1:1', 'OPEN', '', 'dave', 'github:GithubAccount:1:4', '2026-03-19 12:00:00', NULL, NULL, 'feature/r2', 4, 2, 0);

INSERT INTO pull_request_commits (commit_sha, pull_request_id, commit_author_name, commit_author_email, commit_authored_date) VALUES
 ('sha-201-1', 'github:GithubPullRequest:1:201', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00'),
 ('sha-202-1', 'github:GithubPullRequest:1:202', 'Cursor Agent', 'noreply@example.com', '2026-03-03 00:00:00'),
 ('sha-203-1', 'github:GithubPullRequest:1:203', 'Bob Builder', 'cursoragent@cursor.com', '2026-03-04 00:00:00'),
 ('sha-204-1', 'github:GithubPullRequest:1:204', 'Carol', 'carol@example.com', '2026-03-05 00:00:00'),
 ('sha-204-2', 'github:GithubPullRequest:1:204', 'Cursor Agent', 'noreply@example.com', '2026-03-05 01:00:00'),
 ('sha-205-1', 'github:GithubPullRequest:1:205', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00'),
 ('sha-206-1', 'github:GithubPullRequest:1:206', 'Pat Dev', 'pat@example.com', '2026-03-06 00:00:00'),
 ('sha-207-1', 'github:GithubPullRequest:1:207', 'Pat Dev', 'pat@example.com', '2026-03-10 00:00:00'),
 ('sha-208-1', 'github:GithubPullRequest:1:208', 'Dave', 'dave@example.com', '2026-03-11 00:00:00'),
 ('sha-208-2', 'github:GithubPullRequest:1:208', 'Claude', 'noreply@example.com', '2026-03-11 00:00:00'),
 ('sha-209-1', 'github:GithubPullRequest:1:209', 'Dave', 'dave@example.com', '2026-03-12 00:00:00'),
 ('sha-209-2', 'github:GithubPullRequest:1:209', 'Dave', 'dave@example.com', '2026-03-12 00:30:00'),
 ('sha-210-1', 'github:GithubPullRequest:1:210', 'Dave', 'dave@example.com', '2026-03-12 06:00:00'),
 ('sha-211-1', 'github:GithubPullRequest:1:211', 'Carol', 'carol@example.com', '2026-03-13 00:00:00'),
 ('sha-212-1', 'github:GithubPullRequest:1:212', 'Bob', 'bob@example.com', '2026-03-13 06:00:00'),
 ('sha-213-1', 'github:GithubPullRequest:1:213', 'Bob', 'bob@example.com', '2026-03-13 12:00:00'),
 ('sha-214-1', 'github:GithubPullRequest:1:214', 'Alice', 'alice@example.com', '2026-03-14 00:00:00'),
 ('sha-215-1', 'github:GithubPullRequest:1:215', 'Carol', 'carol@example.com', '2026-03-14 06:00:00'),
 ('sha-216-1', 'github:GithubPullRequest:1:216', 'Dave', 'dave@example.com', '2026-03-15 00:00:00'),
 ('sha-217-1', 'github:GithubPullRequest:1:217', 'Bob', 'bob@example.com', '2026-03-15 06:00:00'),
 ('sha-218-1', 'github:GithubPullRequest:1:218', 'Pat Dev', 'pat@example.com', '2026-03-16 00:00:00'),
 ('sha-219-1', 'github:GithubPullRequest:1:219', 'Pat Dev', 'pat@example.com', '2026-03-16 12:00:00'),
 ('sha-220-1', 'github:GithubPullRequest:1:220', 'Pat Dev', 'pat@example.com', '2026-03-17 00:00:00'),
 ('sha-221-1', 'github:GithubPullRequest:1:221', 'Pat Dev', 'pat@example.com', '2026-03-17 06:00:00'),
 ('sha-222-1', 'github:GithubPullRequest:1:222', 'Pat Dev', 'pat@example.com', '2026-03-18 00:00:00'),
 ('sha-223-1', 'github:GithubPullRequest:1:223', 'Pat Dev', 'pat@example.com', '2026-03-18 06:00:00'),
 ('sha-224-1', 'github:GithubPullRequest:1:224', 'Pat Dev', 'pat@example.com', '2026-03-19 00:00:00'),
 ('sha-225-1', 'github:GithubPullRequest:1:225', 'Pat Dev', 'pat@example.com', '2026-03-19 06:00:00'),
 ('sha-226-1', 'github:GithubPullRequest:1:226', 'Pat Dev', 'pat@example.com', '2026-03-20 00:00:00'),
 ('sha-227-1', 'github:GithubPullRequest:1:227', 'Pat Dev', 'pat@example.com', '2026-03-20 06:00:00'),
 ('sha-228-1', 'github:GithubPullRequest:1:228', 'Pat Dev', 'pat@example.com', '2026-03-21 00:00:00'),
 ('sha-229-1', 'github:GithubPullRequest:1:229', 'Carol', 'carol@example.com', '2026-03-22 20:00:00'),
 ('sha-230-1', 'github:GithubPullRequest:1:230', 'Carol', 'carol@example.com', '2026-03-24 02:00:00'),
 ('sha-231-1', 'github:GithubPullRequest:1:231', 'Pat Dev', 'pat@example.com', '2026-03-25 00:00:00'),
 ('sha-232-1', 'github:GithubPullRequest:1:232', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00'),
 ('sha-233-1', 'github:GithubPullRequest:1:233', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00'),
 ('sha-234-1', 'github:GithubPullRequest:1:234', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00'),
 ('sha-235-1', 'github:GithubPullRequest:1:235', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00'),
 ('sha-236-1', 'github:GithubPullRequest:1:236', 'Pat Dev', 'pat@example.com', '2026-03-08 00:00:00'),
 ('sha-237-1', 'github:GithubPullRequest:1:237', 'Pat Dev', 'pat@example.com', '2026-03-09 00:00:00'),
 ('sha-238-1', 'github:GithubPullRequest:1:238', 'Pat Dev', 'pat@example.com', '2026-02-27 00:00:00'),
 ('sha-239-1', 'github:GithubPullRequest:1:239', 'Pat Dev', 'pat@example.com', '2026-03-27 00:00:00'),
 ('sha-240-1', 'github:GithubPullRequest:1:240', 'Pat Dev', 'pat@example.com', '2026-03-27 06:00:00'),
 ('sha-241-1', 'github:GithubPullRequest:1:241', 'Pat Dev', 'pat@example.com', '2026-03-28 00:00:00'),
 ('sha-242-1', 'github:GithubPullRequest:1:242', 'Pat Dev', 'pat@example.com', '2026-03-28 12:00:00'),
 ('sha-243-1', 'github:GithubPullRequest:1:243', 'Pat Dev', 'pat@example.com', '2026-03-29 00:00:00'),
 ('sha-244-1', 'github:GithubPullRequest:1:244', 'Pat Dev', 'pat@example.com', '2026-03-29 06:00:00'),
 ('sha-245-1', 'github:GithubPullRequest:1:245', 'Pat Dev', 'pat@example.com', '2026-03-30 00:00:00'),
 ('sha-246-1', 'github:GithubPullRequest:1:246', 'Pat Dev', 'pat@example.com', '2026-03-30 06:00:00'),
 ('sha-247-1', 'github:GithubPullRequest:1:247', 'Pat Dev', 'pat@example.com', '2026-03-30 12:00:00'),
 ('sha-248-1', 'github:GithubPullRequest:1:248', 'Gina Human', 'CursorAgent@Cursor.com', '2026-03-28 18:00:00'),
 ('sha-249-1', 'github:GithubPullRequest:1:249', 'Carol', 'carol@example.com', '2026-03-10 12:00:00'),
 ('sha-250-1', 'github:GithubPullRequest:1:250', 'Alice', 'alice@example.com', '2026-03-30 06:00:00'),
 ('sha-251-1', 'github:GithubPullRequest:1:251', 'Dave', 'dave@example.com', '2026-03-31 00:00:00'),
 ('sha-252-1', 'github:GithubPullRequest:1:252', 'Carol', 'carol@example.com', '2026-03-12 12:00:00'),
 ('sha-253-1', 'github:GithubPullRequest:1:253', 'Hank Human', 'xcursoragent@cursor.com', '2026-03-18 12:00:00'),
 ('sha-254-1', 'github:GithubPullRequest:1:254', 'Pat Dev', 'pat@example.com', '2026-03-17 12:00:00'),
 ('sha-255-1', 'github:GithubPullRequest:1:255', 'Pat Dev', 'pat@example.com', '2026-03-19 00:00:00'),
 ('sha-256-1', 'github:GithubPullRequest:1:256', 'Dave', 'dave@example.com', '2026-03-19 12:00:00');

-- commits: the message of every commit except the one of Q16 (P-A6: the row is missing). commits.message is a LONGBLOB (tests/schema_mysql.sql),
-- as in a real DevLake: a string literal is stored as bytes.
INSERT INTO commits (sha, message, author_name, author_email, authored_date, committer_name, committer_email) VALUES
 ('sha-201-1', 'Work 201', 'Pat Dev', 'pat@example.com', '2026-03-02 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-202-1', 'Implement c2', 'Cursor Agent', 'noreply@example.com', '2026-03-03 00:00:00', 'Cursor Agent', 'noreply@example.com'),
 ('sha-203-1', 'Implement c2e', 'Bob Builder', 'cursoragent@cursor.com', '2026-03-04 00:00:00', 'Bob Builder', 'cursoragent@cursor.com'),
 ('sha-204-1', 'Start c3', 'Carol', 'carol@example.com', '2026-03-05 00:00:00', 'Carol', 'carol@example.com'),
 ('sha-204-2', 'Continue c3', 'Cursor Agent', 'noreply@example.com', '2026-03-05 01:00:00', 'Cursor Agent', 'noreply@example.com'),
 ('sha-205-1', 'Work 205', 'Pat Dev', 'pat@example.com', '2026-03-04 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-206-1', 'Work 206', 'Pat Dev', 'pat@example.com', '2026-03-06 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-207-1', 'Work 207', 'Pat Dev', 'pat@example.com', '2026-03-10 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-208-1', 'Human part', 'Dave', 'dave@example.com', '2026-03-11 00:00:00', 'Dave', 'dave@example.com'),
 ('sha-208-2', 'Agent part', 'Claude', 'noreply@example.com', '2026-03-11 00:00:00', 'Claude', 'noreply@example.com'),
 ('sha-209-1', 'Start a1', 'Dave', 'dave@example.com', '2026-03-12 00:00:00', 'Dave', 'dave@example.com'),
 ('sha-209-2', 'Fix bug\n\nCo-authored-by: Claude <noreply@anthropic.com>', 'Dave', 'dave@example.com', '2026-03-12 00:30:00', 'Dave', 'dave@example.com'),
 ('sha-210-1', 'Fix\n\nCo-authored-by: Erin Human <erin@example.com>', 'Dave', 'dave@example.com', '2026-03-12 06:00:00', 'Dave', 'dave@example.com'),
 ('sha-211-1', 'We paired a bit; co-authored-by: Claude <noreply@anthropic.com> suggested it', 'Carol', 'carol@example.com', '2026-03-13 00:00:00', 'Carol', 'carol@example.com'),
 ('sha-212-1', 'MADE-WITH: cursor\n\nAdd thing', 'Bob', 'bob@example.com', '2026-03-13 06:00:00', 'Bob', 'bob@example.com'),
 ('sha-213-1', 'This was made-with: cursor earlier\nbut it is not a trailer', 'Bob', 'bob@example.com', '2026-03-13 12:00:00', 'Bob', 'bob@example.com'),
 ('sha-214-1', '"Add feature\\n\\nCo-authored-by: Claude <noreply@anthropic.com>"', 'Alice', 'alice@example.com', '2026-03-14 00:00:00', 'Alice', 'alice@example.com'),
 ('sha-215-1', 'Add feature\r\n\r\nCo-authored-by: Claude <noreply@anthropic.com>', 'Carol', 'carol@example.com', '2026-03-14 06:00:00', 'Carol', 'carol@example.com'),
 ('sha-217-1', 'Add x\n\nCo-authored-by: Claude <noreply@anthropic.com>\nMade-with: Cursor', 'Bob', 'bob@example.com', '2026-03-15 06:00:00', 'Bob', 'bob@example.com'),
 ('sha-218-1', 'Work 218', 'Pat Dev', 'pat@example.com', '2026-03-16 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-219-1', 'Work 219', 'Pat Dev', 'pat@example.com', '2026-03-16 12:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-220-1', 'Work 220', 'Pat Dev', 'pat@example.com', '2026-03-17 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-221-1', 'Work 221', 'Pat Dev', 'pat@example.com', '2026-03-17 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-222-1', 'Work 222', 'Pat Dev', 'pat@example.com', '2026-03-18 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-223-1', 'Work 223', 'Pat Dev', 'pat@example.com', '2026-03-18 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-224-1', 'Work 224', 'Pat Dev', 'pat@example.com', '2026-03-19 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-225-1', 'Work 225', 'Pat Dev', 'pat@example.com', '2026-03-19 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-226-1', 'Work 226', 'Pat Dev', 'pat@example.com', '2026-03-20 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-227-1', 'Work 227', 'Pat Dev', 'pat@example.com', '2026-03-20 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-228-1', 'Work 228', 'Pat Dev', 'pat@example.com', '2026-03-21 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-229-1', 'Early work', 'Carol', 'carol@example.com', '2026-03-22 20:00:00', 'Carol', 'carol@example.com'),
 ('sha-230-1', 'Late work', 'Carol', 'carol@example.com', '2026-03-24 02:00:00', 'Carol', 'carol@example.com'),
 ('sha-231-1', 'Work 231', 'Pat Dev', 'pat@example.com', '2026-03-25 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-232-1', 'Work 232', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-233-1', 'Work 233', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-234-1', 'Work 234', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-235-1', 'Work 235', 'Pat Dev', 'pat@example.com', '2026-03-26 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-236-1', 'Work 236', 'Pat Dev', 'pat@example.com', '2026-03-08 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-237-1', 'Work 237', 'Pat Dev', 'pat@example.com', '2026-03-09 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-238-1', 'Work 238', 'Pat Dev', 'pat@example.com', '2026-02-27 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-239-1', 'Work 239', 'Pat Dev', 'pat@example.com', '2026-03-27 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-240-1', 'Work 240', 'Pat Dev', 'pat@example.com', '2026-03-27 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-241-1', 'Work 241', 'Pat Dev', 'pat@example.com', '2026-03-28 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-242-1', 'Work 242', 'Pat Dev', 'pat@example.com', '2026-03-28 12:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-243-1', 'Work 243', 'Pat Dev', 'pat@example.com', '2026-03-29 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-244-1', 'Work 244', 'Pat Dev', 'pat@example.com', '2026-03-29 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-245-1', 'Work 245', 'Pat Dev', 'pat@example.com', '2026-03-30 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-246-1', 'Work 246', 'Pat Dev', 'pat@example.com', '2026-03-30 06:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-247-1', 'Work 247', 'Pat Dev', 'pat@example.com', '2026-03-30 12:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-248-1', 'Work l3', 'Gina Human', 'CursorAgent@Cursor.com', '2026-03-28 18:00:00', 'Gina Human', 'CursorAgent@Cursor.com'),
 ('sha-249-1', '"Fix y\\n\\nMade-with: Cursor"', 'Carol', 'carol@example.com', '2026-03-10 12:00:00', 'Carol', 'carol@example.com'),
 ('sha-250-1', '"Co-authored-by: Claude <noreply@anthropic.com>\\nmore text"', 'Alice', 'alice@example.com', '2026-03-30 06:00:00', 'Alice', 'alice@example.com'),
 ('sha-251-1', '"Made-with: Cursor\\nmore text"', 'Dave', 'dave@example.com', '2026-03-31 00:00:00', 'Dave', 'dave@example.com'),
 ('sha-252-1', 'Fix z\n\nCo-authored-by: Claudette <claudette@example.com>', 'Carol', 'carol@example.com', '2026-03-12 12:00:00', 'Carol', 'carol@example.com'),
 ('sha-253-1', 'Work l8', 'Hank Human', 'xcursoragent@cursor.com', '2026-03-18 12:00:00', 'Hank Human', 'xcursoragent@cursor.com'),
 ('sha-254-1', 'Work 254', 'Pat Dev', 'pat@example.com', '2026-03-17 12:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-255-1', 'Work 255', 'Pat Dev', 'pat@example.com', '2026-03-19 00:00:00', 'Pat Dev', 'pat@example.com'),
 ('sha-256-1', 'Add r2\n\nCo-Authored-By: Claude <noreply@anthropic.com>', 'Dave', 'dave@example.com', '2026-03-19 12:00:00', 'Dave', 'dave@example.com');

-- Comments. type REVIEW carries the GitHub state in status; DIFF and NORMAL have status ''.
INSERT INTO pull_request_comments (id, pull_request_id, body, account_id, created_date, type, review_id, status) VALUES
 ('c:201:1', 'github:GithubPullRequest:1:201', 'text', 'github:GithubAccount:1:2', '2026-03-02 02:00:00', 'REVIEW', 'rv:201:1', 'APPROVED'),
 ('c:202:1', 'github:GithubPullRequest:1:202', 'text', 'github:GithubAccount:1:3', '2026-03-03 01:00:00', 'REVIEW', 'rv:202:1', 'COMMENTED'),
 ('c:202:2', 'github:GithubPullRequest:1:202', 'text', 'github:GithubAccount:1:3', '2026-03-03 04:00:00', 'REVIEW', 'rv:202:2', 'APPROVED'),
 ('c:203:1', 'github:GithubPullRequest:1:203', 'text', 'github:GithubAccount:1:4', '2026-03-04 00:30:00', 'REVIEW', 'rv:203:1', 'APPROVED'),
 ('c:204:1', 'github:GithubPullRequest:1:204', 'text', 'github:GithubAccount:1:1', '2026-03-05 01:30:00', 'REVIEW', 'rv:204:1', 'APPROVED'),
 ('c:207:1', 'github:GithubPullRequest:1:207', 'text', 'github:GithubAccount:1:2', '2026-03-10 01:00:00', 'REVIEW', 'rv:207:1', 'APPROVED'),
 ('c:208:1', 'github:GithubPullRequest:1:208', 'text', 'github:GithubAccount:1:2', '2026-03-11 00:30:00', 'REVIEW', 'rv:208:1', 'COMMENTED'),
 ('c:209:1', 'github:GithubPullRequest:1:209', 'text', 'github:GithubAccount:1:1', '2026-03-12 01:00:00', 'REVIEW', 'rv:209:1', 'APPROVED'),
 ('c:210:1', 'github:GithubPullRequest:1:210', 'text', 'github:GithubAccount:1:2', '2026-03-12 06:20:00', 'REVIEW', 'rv:210:1', 'APPROVED'),
 ('c:212:1', 'github:GithubPullRequest:1:212', 'text', 'github:GithubAccount:1:1', '2026-03-13 06:45:00', 'REVIEW', 'rv:212:1', 'APPROVED'),
 ('c:214:1', 'github:GithubPullRequest:1:214', 'text', 'github:GithubAccount:1:2', '2026-03-14 02:00:00', 'REVIEW', 'rv:214:1', 'COMMENTED'),
 ('c:215:1', 'github:GithubPullRequest:1:215', 'text', 'github:GithubAccount:1:1', '2026-03-14 06:30:00', 'REVIEW', 'rv:215:1', 'APPROVED'),
 ('c:217:1', 'github:GithubPullRequest:1:217', 'text', 'github:GithubAccount:1:3', '2026-03-15 07:00:00', 'REVIEW', 'rv:217:1', 'APPROVED'),
 ('c:218:1', 'github:GithubPullRequest:1:218', 'text', 'github:GithubAccount:1:10', '2026-03-16 00:10:00', 'REVIEW', 'rv:218:1', 'COMMENTED'),
 ('c:218:2', 'github:GithubPullRequest:1:218', 'text', 'github:GithubAccount:1:2', '2026-03-16 02:00:00', 'REVIEW', 'rv:218:2', 'APPROVED'),
 ('c:219:1', 'github:GithubPullRequest:1:219', 'text', 'github:GithubAccount:1:9', '2026-03-16 12:10:00', 'REVIEW', 'rv:219:1', 'COMMENTED'),
 ('c:220:1', 'github:GithubPullRequest:1:220', 'text', 'github:GithubAccount:1:2', '2026-03-17 00:30:00', 'NORMAL', '', ''),
 ('c:220:2', 'github:GithubPullRequest:1:220', 'text', 'github:GithubAccount:1:3', '2026-03-17 01:30:00', 'REVIEW', 'rv:220:2', 'COMMENTED'),
 ('c:221:1', 'github:GithubPullRequest:1:221', 'text', 'github:GithubAccount:1:1', '2026-03-17 06:05:00', 'REVIEW', 'rv:221:1', 'COMMENTED'),
 ('c:221:2', 'github:GithubPullRequest:1:221', 'text', 'github:GithubAccount:1:2', '2026-03-17 07:00:00', 'REVIEW', 'rv:221:2', 'COMMENTED'),
 ('c:221:3', 'github:GithubPullRequest:1:221', 'text', 'github:GithubAccount:1:1', '2026-03-17 07:40:00', 'REVIEW', 'rv:221:3', 'APPROVED'),
 ('c:222:1', 'github:GithubPullRequest:1:222', 'text', 'github:GithubAccount:1:2', '2026-03-18 00:45:00', 'REVIEW', 'rv:222:1', 'DISMISSED'),
 ('c:222:2', 'github:GithubPullRequest:1:222', 'text', 'github:GithubAccount:1:3', '2026-03-18 02:00:00', 'REVIEW', 'rv:222:2', 'APPROVED'),
 ('c:223:1', 'github:GithubPullRequest:1:223', 'text', 'github:GithubAccount:1:9', '2026-03-18 06:15:00', 'DIFF', 'rv:223:1', ''),
 ('c:224:1', 'github:GithubPullRequest:1:224', 'text', 'github:GithubAccount:1:3', '2026-03-19 01:00:00', 'REVIEW', 'rv:224:1', 'APPROVED'),
 ('c:224:2', 'github:GithubPullRequest:1:224', 'text', 'github:GithubAccount:1:4', '2026-03-19 03:00:00', 'REVIEW', 'rv:224:2', 'APPROVED'),
 ('c:225:1', 'github:GithubPullRequest:1:225', 'text', 'github:GithubAccount:1:3', '2026-03-19 07:00:00', 'REVIEW', 'rv:225:1', 'COMMENTED'),
 ('c:226:1', 'github:GithubPullRequest:1:226', 'text', 'github:GithubAccount:1:3', '2026-03-20 02:00:00', 'REVIEW', 'rv:226:1', 'APPROVED'),
 ('c:226:2', 'github:GithubPullRequest:1:226', 'text', 'github:GithubAccount:1:4', '2026-03-20 06:40:00', 'REVIEW', 'rv:226:2', 'APPROVED'),
 ('c:227:1', 'github:GithubPullRequest:1:227', 'text', 'github:GithubAccount:1:11', '2026-03-20 06:30:00', 'REVIEW', 'rv:227:1', 'APPROVED'),
 ('c:228:1', 'github:GithubPullRequest:1:228', 'text', 'github:GithubAccount:1:4', '2026-03-21 01:00:00', 'REVIEW', 'rv:228:1', 'APPROVED'),
 ('c:229:1', 'github:GithubPullRequest:1:229', 'text', 'github:GithubAccount:1:4', '2026-03-23 02:00:00', 'REVIEW', 'rv:229:1', 'APPROVED'),
 ('c:230:1', 'github:GithubPullRequest:1:230', 'text', 'github:GithubAccount:1:4', '2026-03-24 03:00:00', 'REVIEW', 'rv:230:1', 'APPROVED'),
 ('c:231:1', 'github:GithubPullRequest:1:231', 'text', 'github:GithubAccount:1:3', '2026-03-25 01:00:00', 'REVIEW', 'rv:231:1', 'APPROVED'),
 ('c:238:1', 'github:GithubPullRequest:1:238', 'text', 'github:GithubAccount:1:2', '2026-03-01 10:00:00', 'REVIEW', 'rv:238:1', 'APPROVED'),
 ('c:239:1', 'github:GithubPullRequest:1:239', 'text', 'github:GithubAccount:1:3', '2026-03-27 01:00:00', 'REVIEW', 'rv:239:1', 'APPROVED'),
 ('c:241:1', 'github:GithubPullRequest:1:241', 'text', 'github:GithubAccount:1:2', '2026-03-28 00:30:00', 'REVIEW', 'rv:241:1', 'APPROVED'),
 ('c:242:1', 'github:GithubPullRequest:1:242', 'text', 'github:GithubAccount:1:4', '2026-03-28 12:20:00', 'REVIEW', 'rv:242:1', 'APPROVED'),
 ('c:244:1', 'github:GithubPullRequest:1:244', 'text', 'github:GithubAccount:1:1', '2026-03-29 07:00:00', 'REVIEW', 'rv:244:1', 'APPROVED'),
 ('c:246:1', 'github:GithubPullRequest:1:246', 'text', 'github:GithubAccount:1:13', '2026-03-30 06:10:00', 'REVIEW', 'rv:246:1', 'COMMENTED'),
 ('c:247:1', 'github:GithubPullRequest:1:247', 'text', 'github:GithubAccount:1:14', '2026-03-30 12:10:00', 'REVIEW', 'rv:247:1', 'COMMENTED'),
 ('c:248:1', 'github:GithubPullRequest:1:248', 'text', 'github:GithubAccount:1:2', '2026-03-28 18:30:00', 'REVIEW', 'rv:248:1', 'APPROVED'),
 ('c:249:1', 'github:GithubPullRequest:1:249', 'text', 'github:GithubAccount:1:4', '2026-03-10 12:40:00', 'REVIEW', 'rv:249:1', 'APPROVED'),
 ('c:250:1', 'github:GithubPullRequest:1:250', 'text', 'github:GithubAccount:1:2', '2026-03-30 06:50:00', 'REVIEW', 'rv:250:1', 'APPROVED'),
 ('c:252:1', 'github:GithubPullRequest:1:252', 'text', 'github:GithubAccount:1:1', '2026-03-12 12:20:00', 'REVIEW', 'rv:252:1', 'APPROVED'),
 ('c:253:1', 'github:GithubPullRequest:1:253', 'text', 'github:GithubAccount:1:3', '2026-03-18 12:25:00', 'REVIEW', 'rv:253:1', 'APPROVED'),
 ('c:254:1', 'github:GithubPullRequest:1:254', 'text', 'github:GithubAccount:1:3', '2026-03-17 14:00:00', 'REVIEW', 'rv:254:1', 'APPROVED'),
 ('c:254:2', 'github:GithubPullRequest:1:254', 'text', 'github:GithubAccount:1:4', '2026-03-17 18:00:00', 'REVIEW', 'rv:254:2', 'APPROVED');
