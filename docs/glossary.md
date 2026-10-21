# Glossary: the short labels used in the records of this repository

The records (`docs/adr/`, `docs/validation/`, the comments of the tests) were written while the work was done, and they use short labels. This page says what they mean.

## The six build steps (U1 to U6)

The work was done in six steps, in this order. A record that says "U4" means the step, not a file.

| Label | Step |
|---|---|
| U1 | The first five metrics (review burden of agent PRs), in MySQL, with a synthetic-data test (ADR 0001) |
| U2 | Metrics aligned with the definitions of the paid service that the README compares with, by AI tool and by mode (ADR 0002) |
| U3 | The import of the PR assignees from GitHub into DevLake (ADR 0003, `importer/`) |
| U4 | The check on real data: two public repositories imported into a local DevLake, every number compared with a separate calculation from GitHub's raw data (`docs/validation/u4-real-data.md`) |
| U5 | The Grafana screen (ADR 0004, `dashboards/`, `tools/build_dashboard.py`, `tools/grafana_install.py`) |
| U6 | The read-only database user for Grafana (`tools/grafana_readonly_user.py`) and the preparation for publication (ADR 0004, ADR 0005) |

## Working documents that are not published

- **SPEC** and **plan v4** are the author's working plans for the build. They are not part of this repository. The records say "SPEC section 4-3" or "plan v4 section 5-a" to name the place in that plan where a requirement came from; what the repository needs of them is written again in the ADRs.
- **`research/...` paths** (for example `research/v3/vendor/...`, `research/v5_grafana/...`) are the author's saved copies of web pages and source files. They are not published. In the ADRs, each such path is given together with the public URL of the original (documentation pages, or the DevLake and Grafana source at a tag or commit), and the line numbers are those of the saved copy (a saved source file has one header line more than the original).

## Numbers and letters in the records

| Label | Where | Meaning |
|---|---|---|
| D1, D2, ... | ADR 0002 | the numbered decisions about how a definition is built |
| F1, F2, ... | ADR 0002 | the numbered facts: a claim, the source page and line, and the words of the page |
| A1, A2 | ADR 0002, `docs/validation/u4-real-data.md` | the two SQL errors that the real-data check (U4) found and that were fixed |
| A1 to A16 | ADR 0003, `tests/importer/` | the numbered checks of the importer |
| R1 to R9 | ADR 0003 | row numbers of the table "What DevLake does at the tag": what DevLake v1.0.3-beta18 does with assignees, read from its source |
| W1 to W20 | ADR 0004 | row numbers of the source table of the plan for the Grafana screen: one quoted fact each, from a page of the paid service, of Grafana, of Docker or of DevLake; the ADR names the file and line next to the number |
| S1 to S14 | README | the rows of the table of definitions (the metrics and ways of comparing of the paid service) |
| S1 to S4 | `docs/agent_identities.md` | the four ways in which an agent login row was checked |
| V1 to V9 | ADR 0004, Appendix B | the numbered checks of the build of the screen |
| V4-nn, U6-xnn | ADR 0004, Appendices A and C | the numbered mutants (one deliberate change in one place; a test must fail) |
| m1 to m6, x1, x2 | the SQL files, ADR 0002 | the marks that tell which AI tool and mode a PR carries (m = built-in marks, x = this repository's own markers) |

A **mutant** is one deliberate change of the SQL or of a script, made on a copy; it is **killed** when a test fails because of it. A mutant that no test notices is a **survivor**; the appendices say that there are none.
