# Agent identities (the `identities` list of `sql/mysql/ai_impact_parity.sql`)

Checked on 2026-10-20. One row of the SQL list is `(tool, mode, field, pattern)`. The list follows the built-in
tools of Swarmia: cloud agents ("Built-in cloud agents") and review agents ("Built-in review agents").
Add or remove rows in the `identities` CTE per company (ADR 0002, D11 and section "Identity list").

## How a row was checked

Only four things were looked at. Each has a tag; the tag is used in the tables below.

| Tag | What | Saved file (relative to the research folder `research/v3/`, kept outside this repository) | Line 1 of the saved file (URL, date) |
|---|---|---|---|
| S1 | a saved sample of public agent PRs (gh api search, user.login / type / head ref) | `upstream/agent_pr_identity_samples.txt` | `gh api search/issues (public) sample of agent-authored PRs: user.login/type/head ref; retrieved 2026-10-20` (no URL on line 1; the call is `GET https://api.github.com/search/issues`) |
| S2 | one page of the vendor's own documentation, the page that Swarmia's list links to for that tool | `upstream/identities/<name>.html.txt`, one per tool (named in the rows) | each file starts with its own URL and `retrieved 2026-10-20`; the URLs are in the table "Saved vendor pages" |
| S3 | one `gh api search/issues` query per tool (`is:pr author:app/<slug>`, public data) and, for the login it returned, `gh api users/<login>` (field `type`) | `upstream/identities/gh_search_by_app_slug.txt` | `https://api.github.com/search/issues?q=is:pr+author:app/<slug>` and `https://api.github.com/users/<login>`, retrieved 2026-10-20 |
| S4 | **added once, for the commit identities (director's decision of 2026-10-20):** `gh api search/commits`, one call per query: `author:cursoragent`, `committer:cursoragent`, `author:claude`, and the full-text query `"Co-Authored-By: Claude"` (public commits; 30 items each) | `upstream/identities/gh_search_commits_author_cursoragent.txt`, `upstream/identities/gh_search_commits_committer_cursoragent.txt`, `upstream/identities/gh_search_commits_author_claude.txt`, `upstream/identities/gh_search_commits_trailer_claude.txt` | each file starts with its API URL and `URL retrieved 2026-10-20`; line 2 says that the file is a projection (the raw JSON holds names and e-mail addresses of private persons, so it is not kept) |

A row that none of these confirmed is not in the SQL; it is listed under "Not confirmed" with the places that were looked at.

What "confirmed" means here, so that it is not read as more than it is:

- S3 shows that the login exists, is of type `Bot`, and has opened public PRs. For a **review** row it does not show that the same account writes the
  reviews; that part is taken from Swarmia's list (research/v3/vendor/swarmia_def_review_agents.txt L14-L25; https://help.swarmia.com/features/ai-tools/review-agents; retrieved 2026-10-20). The column "Review role" says where the review role itself
  is shown by a source. **A row marked "inferred": the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed.**
- S4 shows what the **git author and committer name and e-mail** of public commits are. The 30 items of each query are the first 30 of GitHub's own ranking, not a random
  sample; `incomplete_results` is `False` for the three account queries and `True` for the full-text query (GitHub's own flag, written on line 3 of that file).

### Saved vendor pages (S2)

| Saved file | Line 1 (URL) |
|---|---|
| `upstream/identities/copilot_code_review.html.txt` | https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review |
| `upstream/identities/copilot_cloud_agent.html.txt` | https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent |
| `upstream/identities/codex_github.html.txt` | https://developers.openai.com/codex/integrations/github |
| `upstream/identities/devin_review.html.txt` | https://docs.devin.ai/work-with-devin/devin-review |
| `upstream/identities/coderabbit.html.txt` | https://www.coderabbit.ai |
| `upstream/identities/cubic.html.txt` | https://www.cubic.dev |
| `upstream/identities/graphite.html.txt` | https://graphite.com |
| `upstream/identities/macroscope.html.txt` | https://macroscope.com |
| `upstream/identities/qodo.html.txt` | https://www.qodo.ai |
| `upstream/identities/gemini_code_review.html.txt` | https://docs.cloud.google.com/gemini/docs/code-review/review-repo-code |
| `upstream/identities/greptile.html.txt` | https://www.greptile.com |
| `upstream/identities/cursor_bugbot.html.txt` | https://cursor.com/bugbot |
| `upstream/identities/cursor_cloud_agent.html.txt` | https://cursor.com/docs/cloud-agent |
| `upstream/identities/claude_code_review.html.txt` | https://code.claude.com/docs/en/code-review |
| `upstream/identities/claude_github_actions.html.txt` | https://code.claude.com/docs/en/github-actions |

All 15 files have `retrieved 2026-10-20` on line 1.

## A. Login rows confirmed by S1 / S2 / S3 (18 rows: 10 cloud, 8 review)

| tool | mode | field | pattern in the SQL (lower case) | Basis | Review role |
|---|---|---|---|---|---|
| copilot | cloud | pr_author | `copilot` or `copilot-swe-agent[bot]` | S1: `user=Copilot type=Bot` (REST sample, and `author:app/copilot-swe-agent`). S3: the search returns `Copilot` (Bot); `gh api users/Copilot` answers 404 (the same fact as in ADR 0001). `copilot-swe-agent[bot]` is carried over from U1 rules 1 and 2 | - |
| copilot | review | review_author | `copilot` or `copilot-pull-request-reviewer[bot]` | S2 (`upstream/identities/copilot_code_review.html.txt` (https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review, retrieved 2026-10-20)): the GitHub Docs page on Copilot code review names `copilot-pull-request-reviewer[bot]` as the reviewer. S3: the search for that slug returns the user `Copilot` (Bot) | S2 |
| cursor | cloud | pr_author | `cursor[bot]` | S1: `user=cursor[bot] type=Bot`. S3: `users/cursor[bot]` type `Bot` | - |
| claude | cloud | pr_author | `claude[bot]` | S3: search returns `claude[bot]`, `users/claude[bot]` type `Bot` | - |
| codex | cloud | pr_author | `chatgpt-codex-connector[bot]` | S3: search returns it (4 public PRs only), `users/` type `Bot` | - |
| codex | review | review_author | `chatgpt-codex-connector[bot]` | S2 (`upstream/identities/codex_github.html.txt` (https://developers.openai.com/codex/integrations/github, retrieved 2026-10-20)): the Codex GitHub page shows a review by `chatgpt-codex-connector` with the badge `bot`. S3 as above | S2 |
| devin | cloud | pr_author | `devin-ai-integration[bot]` | S1: `user=devin-ai-integration[bot] type=Bot`. S2 (`upstream/identities/devin_review.html.txt` (https://docs.devin.ai/work-with-devin/devin-review, retrieved 2026-10-20)): the Devin Review page names the login (allowlist of PR authors). S3: type `Bot` | - |
| devin | review | review_author | `devin-ai-integration[bot]` | S2 and S3 as above (same account) | inferred: the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed |
| coderabbit | cloud | pr_author | `coderabbitai[bot]` | S3: search returns it (22,741 PRs), `users/` type `Bot` | - |
| coderabbit | review | review_author | `coderabbitai[bot]` | S3 as above. S2 (`upstream/identities/coderabbit.html.txt` (https://www.coderabbit.ai, retrieved 2026-10-20)): the vendor home page shows a comment by `coderabbitai` with the badge `bot` | S2 |
| cubic | cloud | pr_author | `cubic-dev-ai[bot]` | S3: search returns it (644 PRs), `users/` type `Bot`. S2 (`upstream/identities/cubic.html.txt` (https://www.cubic.dev, retrieved 2026-10-20)): the vendor page links `github.com/apps/cubic-dev-ai` | - |
| cubic | review | review_author | `cubic-dev-ai[bot]` | S3, S2 as above | inferred: the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed |
| graphite | cloud | pr_author | `graphite-app[bot]` | S3: search returns it (9,888 PRs), `users/` type `Bot` | - |
| graphite | review | review_author | `graphite-app[bot]` | S3 as above | inferred: the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed |
| macroscope | cloud | pr_author | `macroscopeapp[bot]` | S3: search returns it (394 PRs), `users/` type `Bot` | - |
| macroscope | review | review_author | `macroscopeapp[bot]` | S3 as above | inferred: the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed |
| qodo | cloud | pr_author | `qodo-code-review[bot]` | S3: search returns it (1,298 PRs), `users/` type `Bot` | - |
| qodo | review | review_author | `qodo-code-review[bot]` | S3 as above | inferred: the role (review) is taken from Swarmia's list; that this login writes the reviews is not confirmed |

Swarmia's list has 24 (tool, mode) entries: 12 cloud agents (Copilot, Cursor, Claude, Codex, CodeRabbit, Cubic, Gemini Code Assist,
Graphite, Greptile, Macroscope, Qodo, Devin; research/v3/vendor/swarmia_def_cloud_agents.txt L14 (https://help.swarmia.com/features/ai-tools/cloud-agents, retrieved 2026-10-20), "Built-in cloud agents") and 12 review agents (Copilot, Cursor Bugbot, Claude Code, Codex, CodeRabbit, Cubic, Devin
Review, Gemini Code Assist, Graphite, Greptile, Macroscope, Qodo; research/v3/vendor/swarmia_def_review_agents.txt L14-L25 (https://help.swarmia.com/features/ai-tools/review-agents, retrieved 2026-10-20)). **Login rows confirmed 18, not confirmed 6** (table C).
The Swarmia text counts Claude as three cloud products (GitHub Actions, on the web, partner agent) and Cursor as one; they are one row each here
because they share the `cursor` and `claude` tool groups.

## B. Commit rows (4 rows). Confirmed by S4 (public commits)

Swarmia's pages name the **GitHub account** of the commit author (research/v3/vendor/swarmia_agent.txt L126; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics; retrieved 2026-10-20: "GitHub shows cursoragent as the author of the first commit"). DevLake has only the **git name and e-mail** of the commit
(`pull_request_commits.commit_author_name` / `commit_author_email`). S4 shows what the agent accounts write there. The patterns are the values of S4, and the whole value is
bound with `^...$` (name, e-mail) as ADR 0002 section "Text matching" requires.

| tool | mode | field | pattern in the SQL (lower case) | What S4 shows |
|---|---|---|---|---|
| cursor | cloud | commit_author_name | `^cursor agent$` | `author:cursoragent` (`upstream/identities/gh_search_commits_author_cursoragent.txt` (https://api.github.com/search/commits?q=author:cursoragent&per_page=30, retrieved 2026-10-20)): 30 of 30 items have `commit.author.name = Cursor Agent`, GitHub login `cursoragent`. `committer:cursoragent` (`upstream/identities/gh_search_commits_committer_cursoragent.txt` (https://api.github.com/search/commits?q=committer:cursoragent&per_page=30, retrieved 2026-10-20)): 30 of 30 have `commit.committer.name = Cursor Agent`. **The git name is `Cursor Agent`, not the login `cursoragent`**; the earlier pattern `^cursoragent$` was removed |
| cursor | cloud | commit_author_email | `^cursoragent@cursor\.com$` (in the SQL file `^cursoragent@cursor\\.com$`) | the same 60 items: `commit.author.email` and `commit.committer.email` are `cursoragent@cursor.com` in every one. This replaces the placeholder `^cursoragent@` |
| claude | cloud | commit_author_name | `^claude$` | `author:claude` (`upstream/identities/gh_search_commits_author_claude.txt` (https://api.github.com/search/commits?q=author:claude&per_page=30, retrieved 2026-10-20)): 30 of 30 items have `commit.author.name = Claude` and `commit.committer.name = Claude`, GitHub login `claude` (the same items have the e-mail `noreply@anthropic.com`; there is no SQL row for that address, because it is also the address in the trailers of commits that people wrote) |
| claude | assist | coauthor | `claude\b` (after `co-authored-by:`; in the SQL file `claude\\b`) | the full-text query `"Co-Authored-By: Claude"` (`upstream/identities/gh_search_commits_trailer_claude.txt` (https://api.github.com/search/commits?q=%22Co-Authored-By:+Claude%22&per_page=30, retrieved 2026-10-20)): in the 30 items, the lines that start with `Co-authored-by:` (written `Co-Authored-By:` or `Co-authored-by:`) read `Claude <noreply@anthropic.com>`, `Claude Opus 5.5 <noreply@anthropic.com>`, `Claude Sonnet 5.5 <...>`, `Claude Fable 5.1 <...>`, and in a few lines `Claude` without an address. The word end `\b` takes all of these and not `Claudette`. The trailer is also the default of Claude Code: research/v3/research/arxiv_2507.15003v1.txt L487 (https://arxiv.org/html/2507.15003v1, retrieved 2026-10-20) ("Claude Code includes a default “Co-Authored-By: Claude” message (which can be disabled)") and the search query of that paper at research/v3/research/arxiv_2507.15003v1.txt L173 (https://arxiv.org/html/2507.15003v1, retrieved 2026-10-20) (`is:pr “Co-Authored-By: Claude”`) |

Not used by the SQL, although S4 shows them: the Claude e-mail (see above), and other lines in the same trailer search (`Co-authored-by:` of other parties, which are replaced by a marker in the saved file).
The e-mail row is kept because it is confirmed; a company that does not want the e-mail match deletes that one row of the `identities` CTE (the test scenario P-C2e, Q03, is then to be changed with it).

## C. Not confirmed (not in the SQL)

| tool | mode | What was looked at (2026-10-20) | Result |
|---|---|---|---|
| gemini (Gemini Code Assist) | cloud, review | S1: not in the sample. S2: `upstream/identities/gemini_code_review.html.txt` (https://docs.cloud.google.com/gemini/docs/code-review/review-repo-code, retrieved 2026-10-20). S3: `is:pr author:app/gemini-code-assist` | S2 has no login. S3: 0 results, so there is no login to look up with `users/` |
| greptile | cloud, review | S1: not in the sample. S2: `upstream/identities/greptile.html.txt` (https://www.greptile.com, retrieved 2026-10-20). S3: `is:pr author:app/greptile-apps` | S2 has no login (the Devin page mentions only `greptile.json`). S3: 0 results |
| cursor (Bugbot) | review | S2: `upstream/identities/cursor_bugbot.html.txt` (https://cursor.com/bugbot, retrieved 2026-10-20). The login `cursor[bot]` is confirmed only as a PR author (table A) | S2 has no login or `[bot]` string; the review author is not shown |
| claude (Claude Code review) | review | S2: `upstream/identities/claude_code_review.html.txt` (https://code.claude.com/docs/en/code-review, retrieved 2026-10-20). `claude[bot]` is confirmed only as a PR author | S2 has no login; the review author is not shown |

Also not confirmed, so not in the SQL (the four places showed nothing): commit author name, commit e-mail and `Co-authored-by`
text of Copilot, Codex, Devin and the other tools; the `Co-authored-by` text of Cursor. Pages looked at without
finding a login or a commit identity: `upstream/identities/copilot_cloud_agent.html.txt` (https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent, retrieved 2026-10-20),
`upstream/identities/cursor_cloud_agent.html.txt` (https://cursor.com/docs/cloud-agent, retrieved 2026-10-20),
`upstream/identities/claude_github_actions.html.txt` (https://code.claude.com/docs/en/github-actions, retrieved 2026-10-20).

## Counts

- Rows in the SQL list: 22 = 18 (table A) + 4 (table B).
- Confirmed: **22** = 18 by S1 / S2 / S3 (login rows) + 4 by S4 (commit rows). Of the 8 review rows in table A, 5 are marked "inferred" (devin, cubic, graphite, macroscope, qodo): the login is confirmed, the review role is taken from Swarmia's list.
- Removed in this revision: `^cursoragent$` (the login, not the git name) and the placeholder `^cursoragent@`; replaced by the two S4 values above.
- Not confirmed: **6** of Swarmia's 24 (tool, mode) entries (table C), plus the commit identities listed above.
