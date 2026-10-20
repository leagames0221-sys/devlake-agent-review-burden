# `tools/devlake_configure.py`: set up the DevLake import by script (U4 addendum)

The first import of the U4 check was set up by hand in the web screens. It ran with every entity of the GitHub plugin
switched on and had to be stopped: the CI part of the second repository (82,245 workflow runs, the jobs of a run are asked one
run at a time) would have taken more than 16 hours. The screens also led to slips (a command typed in the wrong shell, a project
without a connection, a screen field that does not exist in v1.0.3-beta18).

DevLake offers the same operations as a REST API, so the settings are now a script: the same result every time, and a
`plan` that shows what will be sent, and how much the import will ask GitHub for, before anything is changed.

A person still does two things by hand: start DevLake, and type the GitHub token into the connection screen
(the script never creates or reads a connection and never sees the token).

## Commands

| Command | Changes something? | What it does |
|---|---|---|
| `plan --connection-id N --repos OWNER/NAME ... --project NAME` | no (GET only) | Shows the scopes and their Scope Config, the Sync Policy of the project's blueprint, the checks that `apply` runs, the calls `apply` would send (method, path, body), and an estimate of the import size |
| `apply ... --log FILE` | yes | Runs the same checks; if all pass: (1) creates the Scope Config `u4-code-review-only` with entities `CODE`, `CODEREVIEW`, `CROSS` (an existing Scope Config of the same name is reused), (2) attaches it to the scopes, (3) reads the blueprint again, (4) triggers the blueprint with `{"skipCollectors":false,"fullSync":true}`. Appends what it did to `FILE` |
| `status --pipeline ID` | no (GET only) | Prints the pipeline, its tasks, the running subtask and the record counts, once |

`--base-url` is accepted but only `http://127.0.0.1[:port]` is allowed. Redirects are not followed, the proxy settings of the
environment are ignored. `plan` and `status` cannot send anything but GET (checked in the request function as well).

The checks (all of them must pass, otherwise `apply` stops before any change and `plan` ends with exit code 1):

- the scope list of the connection answers HTTP 200 (this is how the connection is checked; `GET .../connections` is never sent),
- every `--repos` entry is a scope of the connection,
- the project has exactly one blueprint, it is enabled, collects those scopes, and no pipeline of it is running,
- its Sync Policy is: Data Time Range starts at `2026-05-31T15:00:00Z` (2026-06-01 00:00 in Japan) and the frequency is Manual
  (if not, the script stops; it does not repair it, that is a decision for a person),
- if a Scope Config of the same name exists, its entities are the three above.

Nothing a response contains is printed or logged without `redact()`: values under a key that contains `token`, `password` or
`secret` are replaced, and so is the user info of a URL. Of the task options only the repository name is printed (the options of
the `gitextractor` task contain a clone URL).

## The estimate in `plan`

It is an estimate, not a measurement. For each repository it reads four counts with `gh api` (read-only GET; if `gh` is missing or
fails the cell says `not fetched`; `--no-github` skips it): the number of PRs, of issues, of workflow runs
(`total_count` of `actions/runs`), and the upper bound of the number of PR authors (= the number of PRs). It lists the subtasks of
the `github_graphql` task that run with the three entities and those that do not, and it shows what DevLake measured in the first
import (`--reference-pipeline`, default 1): the subtasks that stay, with their times, and the total time of the subtasks that are
taken out.

`CODE` also adds one `gitextractor` task per repository: a git clone inside DevLake (about half a minute per repository in the first
import), not calls to the GitHub API.

## Where each fact comes from (DevLake v1.0.3-beta18)

Line numbers are those of the file at the tag `v1.0.3-beta18`
([browse at the tag](https://github.com/apache/devlake/tree/v1.0.3-beta18)).

| # | Fact | Source |
|---|---|---|
| A1 | The routes of the GitHub plugin: `connections/:connectionId/scopes` (GET, PUT), `.../scopes/:scopeId` (GET, PATCH, DELETE), `.../scope-configs` (POST, GET), `.../scope-configs/:scopeConfigId` (PATCH, GET, DELETE) | [`backend/plugins/github/impl/impl.go` L196-L216](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/impl/impl.go#L196-L216) |
| A2 | The body of a Scope Config: `name` (required, unique), `entities`; `connectionId` is overwritten by the server from the path. The values of `entities` are `CODE`, `TICKET`, `CODEREVIEW`, `CROSS`, `CICD`, `CODEQUALITY` (the screen names: Source Code Management, Issue Tracking, Code Review, Cross Domain, CI/CD, Code Quality Domain) | [`backend/core/models/common/base.go` L99-L104](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/common/base.go#L99-L104), [`backend/plugins/github/models/scope_config.go` L28-L53](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/scope_config.go#L28-L53), [`ds_scope_config_api_helper.go` L72-L80](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/ds_scope_config_api_helper.go#L72-L80), [`plugin_task.go` L82-L87](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/plugin/plugin_task.go#L82-L87), [`config-ui/src/config/entities.ts` L19-L27](https://github.com/apache/devlake/blob/v1.0.3-beta18/config-ui/src/config/entities.ts#L19-L27). A POST answers 201 with the created object ([`model_api_helper.go` L66-L81](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/model_api_helper.go#L66-L81)) |
| A3 | Attaching a Scope Config to an existing scope is `PATCH .../scopes/:scopeId` with `{"scopeConfigId": N}`: the handler reads the scope by `connectionId` and `scopeId` (the GitHub repo id), merges the body into it and saves it. The scope list answers `{"count":..,"scopes":[{"scope":{"githubId":..,"fullName":..,"scopeConfigId":..}}]}` | [`scope_api.go` L103-L106](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/api/scope_api.go#L103-L106), [`model_api_helper.go` L138-L168](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/model_api_helper.go#L138-L168), [`ds_scope_api_helper.go` L54](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/ds_scope_api_helper.go#L54), [`models/repo.go` L30-L44](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/repo.go#L30-L44), [`common/base.go` L84-L88](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/common/base.go#L84-L88), [`scope_generic_helper.go` L63-L71](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/scope_generic_helper.go#L63-L71) |
| A4 | `POST /blueprints/{id}/trigger` with `{"skipCollectors":..,"fullSync":..}` starts a pipeline and answers it; a disabled blueprint is refused; in `NORMAL` mode the plan is made again at the trigger, so a Scope Config attached before the trigger is used. `GET /blueprints/{id}` and `GET /blueprints` read the blueprint, `GET /blueprints/{id}/pipelines` its pipelines. The Sync Policy fields are `timeAfter`, `isManual`, `cronConfig`, `skipOnFail` | [`server/api/blueprints/blueprints.go` L163-L199](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/server/api/blueprints/blueprints.go#L163-L199), [`server/services/blueprint.go` L312-L317, L414-L440](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/server/services/blueprint.go#L312-L317), [`core/models/blueprint.go` L32-L47, L86-L95](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/blueprint.go#L32-L47) |
| A5 | The subtasks of the `github_graphql` task and the rule that picks them: a subtask is planned when it is enabled by default and one of its `DomainTypes` is in the `entities`. With `CODE`, `CODEREVIEW`, `CROSS` the CI (`CICD`) and issue (`TICKET`) subtasks are not planned; `CODE` adds the `gitextractor` task. The table is `SUBTASKS` in the script, one row per `SubTaskMeta` (the file and line are in the row) | [`github_graphql/impl/impl.go` L80-L140](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/impl/impl.go#L80-L140), [`pipeline_plan.go` L33-L58](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/pipeline_plan.go#L33-L58), [`github/api/blueprint_v200.go` L123-L145, L201-L232](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/api/blueprint_v200.go#L123-L145) |
| A6 | A pipeline is read with `GET /pipelines/{id}`, `/pipelines/{id}/tasks` (status, progress, the running subtask in `progressDetail`) and `/pipelines/{id}/subtasks` (begin, end and records of each subtask) | [`server/api/pipelines/pipelines.go` L89-L116](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/server/api/pipelines/pipelines.go#L89-L116), [`server/api/task/task.go` L52-L97](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/server/api/task/task.go#L52-L97), [`core/models/task.go` L42-L51, L86-L144](https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/task.go#L42-L51) |

The set of subtasks the script computes for "every entity" is 41, the same 41 that DevLake planned for the first import
(`GET /pipelines/1/tasks`), which is how the table was checked against a real plan.

## Tests

`python tests/tools/test_devlake_configure.py` runs the script against a fake DevLake (Python's `http.server` on 127.0.0.1;
GitHub and `gh` are not contacted). `--mutants` changes the script in 9 places, one at a time, and shows which scene fails.
