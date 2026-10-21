# Input files of the importer test (`pages_*.json`)

These are written by hand from the documented response of GitHub's "List pull requests"
(https://docs.github.com/en/rest/pulls/pulls, retrieved 2026-10-19; the text of those pages is GitHub Docs content under CC BY 4.0, see the NOTICE). The `Link` header strings follow the pagination page
(https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api, retrieved 2026-10-20).

Format of a file: `[{"url": <the page's URL>, "link": <Link header string or null>, "body": <the page's array of pull requests>}]`.
Only `id` of a pull request and `id` / `login` of each assignee are read by the script; the other fields are in the files on purpose, to show that they are ignored.

## What was changed from the documented example

- In the example both assignees (`octocat` L525-L526 and `hubot` L545-L546, and also `other_user` L567-L568) have `"id": 1`.
  With that, the primary key of `pull_request_assignees` (pull_request_id, assignee_id) would collide, so the test inputs give them different ids:
  **`octocat` = 7001, `hubot` = 7002**. (In `pages_a13.json` the assignee is `alice` with id 1, to match the account ids of the U1 fixture.)
- In the example the pull request has `"id": 1` and `"number": 1347`. In the test inputs every pull request has an `id` and a `number` that differ from each other, from every user id and from every other pull request:
  ids 4000001 ... 5000001, numbers 11 ... 51 (the number is always different from the id, so a script that builds the DevLake id from `number` is caught).
- The documented example has one page. The test adds the second page, the `Link` strings and the unusable values by hand.

## Files and the scene that uses them

| File | Content | Scene |
|---|---|---|
| `pages_basic.json` | 4 PRs: 4000001 no assignee; 4000002 two assignees (octocat, hubot); 4000003 one assignee (DevLake does not have this PR in the test); 4000004 lists hubot twice | A1 A2 A3 A6 A9 A10 A11 A12 |
| `pages_a4_first.json` | 4000012: octocat, hubot; 4000013: octocat | A4 A4z A5 A5o |
| `pages_a4_second.json` | 4000012: octocat only (4000013 is not in this input) | A4 A5 A5o |
| `pages_a4_zero.json` | 4000012: no assignee | A4z |
| `pages_two_pages.json` | page 1 (4000021: octocat) with `rel="next"`; page 2 (4000022: hubot) | A7 |
| `pages_bad_host.json` | page 1 whose `rel="next"` is on another host | A7 (must stop) |
| `pages_truncated.json` | page 1 with `rel="next"`, and no page 2 in the file | A7 (must stop) |
| `pages_escape.json` | the page URL contains `'` and `\`; 4000031 is valid; 4000032 has a login with `'` and `\`; 4000033 has a 40-character login; 4000034 has a text `id` | A8 |
| `pages_a13.json` | one PR (5000001), assignee alice (id 1), for the U1 query 1B on connection 1 | A13 |
| `pages_a14_newline.json` | 4000041: assignee octocat; 4000042: the login is `hubot` followed by a newline (a trailing newline must be refused) | A14 |
| `pages_bad_url.json` | one valid PR on a page whose `url` is on another host (the file version of the check on `resp.geturl()`) | A15 A17 (must stop) |

The expected values are in `test_importer.py`, written by hand from these files (for example: `pages_basic.json` gives 3 rows, because 4000001 has none, 4000003 is not in DevLake, and hubot of 4000004 is listed twice).
