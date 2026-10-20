# Agent identities (the `identities` list of `sql/mysql/ai_impact_parity.sql`)

Checked on 2026-10-20. One row of the SQL list is `(tool, mode, field, pattern)`. The list follows the built-in
tools of Swarmia: cloud agents ("Built-in cloud agents") and review agents ("Built-in review agents").
Add or remove rows in the `identities` CTE per company (ADR 0002, D11 and section "Identity list").

How a row was checked. Only three things were looked at, for each row:

- **S1** the saved sample of public agent PRs (`upstream/agent_pr_identity_samples.txt`, gh api search, retrieved 2026-10-20);
- **S2** one page of the vendor's own documentation, the page that Swarmia's list links to for that tool;
- **S3** one `gh api search/issues` query per tool (`is:pr author:app/<slug>`, public data) and, for the login it returned, `gh api users/<login>` (field `type`).

A row that none of these confirmed is not in the SQL; it is listed under "Not confirmed" with the places that were looked at.
The responses used are saved in `research/v3/upstream/identities/` (outside this repository; the first line of each file is
`URL retrieved 2026-10-20`): `gh_search_by_app_slug.txt` and one `<tool>.html.txt` per vendor page.

What "confirmed" means here, so that it is not read as more than it is: S3 shows that the login exists, is of type `Bot`, and has opened
public PRs. For a **review** row it does not show that the same account writes the reviews; that part is taken from Swarmia's list, which names
the same product as a review agent (swarmia_def_review_agents.txt L14-L25). The column "Review role" says where the review role itself is
shown by a source.

## A. Rows confirmed by S1 / S2 / S3 (18 rows: 10 cloud, 8 review)

| tool | mode | field | pattern in the SQL (lower case) | Basis | Review role |
|---|---|---|---|---|---|
| copilot | cloud | pr_author | `copilot` or `copilot-swe-agent[bot]` | S1: `user=Copilot type=Bot` (REST sample, and `author:app/copilot-swe-agent`). S3: the search returns `Copilot` (Bot); `gh api users/Copilot` answers 404 (the same fact as in ADR 0001). `copilot-swe-agent[bot]` is carried over from U1 rules 1 and 2 | - |
| copilot | review | review_author | `copilot` or `copilot-pull-request-reviewer[bot]` | S2: the GitHub Docs page on Copilot code review names `copilot-pull-request-reviewer[bot]` as the reviewer. S3: the search for that slug returns the user `Copilot` (Bot) | S2 |
| cursor | cloud | pr_author | `cursor[bot]` | S1: `user=cursor[bot] type=Bot`. S3: `users/cursor[bot]` type `Bot` | - |
| claude | cloud | pr_author | `claude[bot]` | S3: search returns `claude[bot]`, `users/claude[bot]` type `Bot` | - |
| codex | cloud | pr_author | `chatgpt-codex-connector[bot]` | S3: search returns it (4 public PRs only), `users/` type `Bot` | - |
| codex | review | review_author | `chatgpt-codex-connector[bot]` | S2: the Codex GitHub page shows a review by `chatgpt-codex-connector` with the badge `bot`. S3 as above | S2 |
| devin | cloud | pr_author | `devin-ai-integration[bot]` | S1: `user=devin-ai-integration[bot] type=Bot`. S2: the Devin Review page names the login (allowlist of PR authors). S3: type `Bot` | - |
| devin | review | review_author | `devin-ai-integration[bot]` | S2 and S3 as above (same account) | inferred |
| coderabbit | cloud | pr_author | `coderabbitai[bot]` | S3: search returns it (22,741 PRs), `users/` type `Bot` | - |
| coderabbit | review | review_author | `coderabbitai[bot]` | S3 as above. S2: the vendor home page shows a comment by `coderabbitai` with the badge `bot` | S2 |
| cubic | cloud | pr_author | `cubic-dev-ai[bot]` | S3: search returns it (644 PRs), `users/` type `Bot`. S2: the vendor page links `github.com/apps/cubic-dev-ai` | - |
| cubic | review | review_author | `cubic-dev-ai[bot]` | S3, S2 as above | inferred |
| graphite | cloud | pr_author | `graphite-app[bot]` | S3: search returns it (9,888 PRs), `users/` type `Bot` | - |
| graphite | review | review_author | `graphite-app[bot]` | S3 as above | inferred |
| macroscope | cloud | pr_author | `macroscopeapp[bot]` | S3: search returns it (394 PRs), `users/` type `Bot` | - |
| macroscope | review | review_author | `macroscopeapp[bot]` | S3 as above | inferred |
| qodo | cloud | pr_author | `qodo-code-review[bot]` | S3: search returns it (1,298 PRs), `users/` type `Bot` | - |
| qodo | review | review_author | `qodo-code-review[bot]` | S3 as above | inferred |

Swarmia's list has 24 (tool, mode) entries: 12 cloud agents (Copilot, Cursor, Claude, Codex, CodeRabbit, Cubic, Gemini Code Assist,
Graphite, Greptile, Macroscope, Qodo, Devin) and 12 review agents (Copilot, Cursor Bugbot, Claude Code, Codex, CodeRabbit, Cubic, Devin
Review, Gemini Code Assist, Graphite, Greptile, Macroscope, Qodo). **Confirmed 18, not confirmed 6** (table C).
The Swarmia text counts Claude as three cloud products (GitHub Actions, on the web, partner agent) and Cursor as one; they are one row each here
because they share the `cursor` and `claude` tool groups.

## B. Commit-based rows (4 rows). Not covered by S1 / S2 / S3.

Swarmia decides m2 / m3 / m4 from the **GitHub account** of the commit author. DevLake has only the **git name and e-mail** of the commit
(`pull_request_commits.commit_author_name` / `commit_author_email`), and none of the three sources shows what an agent writes there. The rows
below are therefore not "confirmed"; their basis is written out.

| tool | mode | field | pattern | Basis | Status |
|---|---|---|---|---|---|
| cursor | cloud | commit_author_name | `^cursoragent$` | Swarmia's own text: "GitHub shows cursoragent as the author of the first commit" (swarmia_agent.txt L126). It is the GitHub account name, not proven to be the git name | named by Swarmia, git name not verified |
| claude | cloud | commit_author_name | `^claude$` | Swarmia's own text: "The first commit in this PR was authored by Claude" (swarmia_agent.txt L127) | named by Swarmia, git name not verified |
| claude | assist | coauthor | `claude\b` (after `co-authored-by:`) | the string `Co-Authored-By: Claude` as a Claude Code attribution: arXiv 2507.15003v1 (saved text, quoted in ADR 0001). Swarmia L127 names "Claude" | named in a paper, not one of S1 / S2 / S3 |
| cursor | cloud | commit_author_email | `^cursoragent@` | **UNVERIFIED PLACEHOLDER.** Nothing saved shows the e-mail an agent commit carries. The pattern assumes that the part before `@` is the account name `cursoragent`. It exists so that the e-mail path of m2 / m3 (scenario P-C2e) is exercised. Delete this line of the SQL if the placeholder is not accepted; the test for P-C2e then has to be changed with it | placeholder; U4 measures real data |

## C. Not confirmed (not in the SQL)

| tool | mode | What was looked at (2026-10-20) | Result |
|---|---|---|---|
| gemini (Gemini Code Assist) | cloud, review | S1: not in the sample. S2: https://docs.cloud.google.com/gemini/docs/code-review/review-repo-code (saved as `gemini_code_review.html.txt`). S3: `is:pr author:app/gemini-code-assist` | S2 has no login. S3: 0 results, so there is no login to look up with `users/` |
| greptile | cloud, review | S1: not in the sample. S2: https://www.greptile.com (saved as `greptile.html.txt`). S3: `is:pr author:app/greptile-apps` | S2 has no login (the Devin page mentions only `greptile.json`). S3: 0 results |
| cursor (Bugbot) | review | S2: https://cursor.com/bugbot (saved as `cursor_bugbot.html.txt`). The login `cursor[bot]` is confirmed only as a PR author (table A) | S2 has no login or `[bot]` string; the review author is not shown |
| claude (Claude Code review) | review | S2: https://code.claude.com/docs/en/code-review (saved as `claude_code_review.html.txt`). `claude[bot]` is confirmed only as a PR author | S2 has no login; the review author is not shown |

Also not confirmed, so not in the SQL (the same three places showed nothing): commit author name, commit e-mail and `Co-authored-by`
text of Copilot, Codex, Devin and the other tools; the `Co-authored-by` text of Cursor; the git name `Cursor Agent`. Pages looked at without
finding a login or a commit identity: the GitHub Docs page on the Copilot cloud agent, https://cursor.com/docs/cloud-agent,
https://code.claude.com/docs/en/github-actions (each saved as `<name>.html.txt`).

## Counts

- Rows in the SQL list: 22 = 18 (table A) + 4 (table B).
- Confirmed by S1 / S2 / S3: **18**. Of the 4 rows of table B: 3 named by Swarmia or a paper but not by the three sources, 1 placeholder.
- Not confirmed: **6** of Swarmia's 24 (tool, mode) entries (table C), plus the commit identities listed above.
