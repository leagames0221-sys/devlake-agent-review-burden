# ADR 0003: GitHub pull request assignees are put into DevLake by a small script

Status: accepted (2026-10-20). Scope: `importer/github_pr_assignees.py`, `tests/importer/`, `docs/importer.md`; MySQL only.

Quotes are written `> "..." (path L<n>; URL; retrieved <date>)` and are copied word for word from the saved copy of the file (leading tabs and spaces of a source line are left out).
The paths are relative to the author's research folder `research/`, which is not published (see `docs/glossary.md`); the repository path at the tag, and so the public URL, is given for each file. **Every citation carries the URL and the date retrieved that are written on line 1 of the cited saved file.**
The line numbers are the line numbers of the saved file. `v3/upstream/beta18/*.txt` are single files of apache/devlake at the tag `v1.0.3-beta18`; their line 1 is
`<path in the repository> @ v1.0.3-beta18 (apache/devlake) retrieved <date>`, so their line numbers are one more than in the original file, and the URL given is
`https://github.com/apache/devlake/blob/v1.0.3-beta18/<that path>`. The files of `v3/upstream/beta18/r9_scan/` are the 220 `.go` files of `backend/plugins/github/` and
`backend/plugins/github_graphql/` at the same tag, saved the same way (file name = path with `/` written as `__`). Files read for this ADR:

| Saved copy (under `research/v3/upstream/beta18/`, not published) | Repository path at the tag (URL: `https://github.com/apache/devlake/blob/v1.0.3-beta18/` + the path) |
|---|---|
| `didgen_domain_id_generator.go.txt` | backend/core/models/domainlayer/didgen/domain_id_generator.go |
| `github_pr_convertor.go.txt` | backend/plugins/github/tasks/pr_convertor.go |
| `github_models_pr.go.txt` | backend/plugins/github/models/pr.go |
| `github_pr_extractor.go.txt` | backend/plugins/github/tasks/pr_extractor.go |
| `graphql_pr_extractor.go.txt` | backend/plugins/github_graphql/tasks/pr_extractor.go |
| `graphql_pr_collector.go.txt` | backend/plugins/github_graphql/tasks/pr_collector.go |
| `github_account_convertor.go.txt` | backend/plugins/github/tasks/account_convertor.go |
| `github_models_account.go.txt` | backend/plugins/github/models/account.go |
| `github_models_repo.go.txt` | backend/plugins/github/models/repo.go |
| `gitlab_mr_assignee_convertor.go.txt` | backend/plugins/gitlab/tasks/mr_assignee_convertor.go |
| `gitlab_mr_convertor.go.txt` | backend/plugins/gitlab/tasks/mr_convertor.go |
| `pull_request_assignees.go.txt` | backend/core/models/domainlayer/code/pull_request_assignees.go |
| `common_base.go.txt` | backend/core/models/common/base.go |
| `batch_save_divider.go.txt` | backend/helpers/pluginhelper/api/batch_save_divider.go |
| `data_convertor_stateful.go.txt` | backend/helpers/pluginhelper/api/data_convertor_stateful.go |
| `subtask_state_manager.go.txt` | backend/helpers/pluginhelper/api/subtask_state_manager.go |
| `utils_json.go.txt` | backend/core/utils/json.go |
| `plugin_datasource.go.txt` | backend/core/plugin/plugin_datasource.go |
| `srvhelper_scope_service_helper.go.txt` | backend/helpers/srvhelper/scope_service_helper.go |
| `scope_generic_helper.go.txt` | backend/helpers/pluginhelper/api/scope_generic_helper.go |
| `ds_scope_api_helper.go.txt` | backend/helpers/pluginhelper/api/ds_scope_api_helper.go |
| `domaininfo.go.txt` | backend/core/models/domainlayer/domaininfo/domaininfo.go |
| `docker-compose-dev-mysql.yml.txt` | docker-compose-dev-mysql.yml |
| `github_r9_scan_result.txt`, `r9_scan/` | the scan of R9 (below) |
| `../../../build/1_2_github_rest_pulls.txt` | https://docs.github.com/en/rest/pulls/pulls (GitHub REST docs, "List pull requests") |
| `../../../build/12_github_rest_pagination.txt` | https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api |
| `../../../build/3_github_rest_rate_limits.txt` | https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api |
| `../vendor/swarmia_agent.txt` | https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics |

## Context

U1's metric 1B ("first human reaction, not counting the assignees") reads `pull_request_assignees`
(`sql/mysql/agent_review_burden.sql` line 124 and the next line). If the table is empty, 1B is the same number as the plain first reaction.
At DevLake v1.0.3-beta18 the table is empty for GitHub data (R6 and R9 below). The assignee matters because the vendor whose numbers this repository reproduces (ADR 0002) uses it to find the person behind an agent PR:

> "from the person the agent assigned to the pull request" (v3/vendor/swarmia_agent.txt L115; https://help.swarmia.com/measure-the-productivity-impact-of-ai-tools/ai-agent-metrics; retrieved 2026-10-20)

## Decision

DevLake is not changed (plan v4 section 5-c, approved 2026-10-20). A small script, `importer/github_pr_assignees.py`, reads the assignees from GitHub's public REST API
("List pull requests", `GET /repos/{owner}/{repo}/pulls?state=all&per_page=100`, the next page by the `rel="next"` URL of the `Link` header) and writes a `.sql` file. The person who runs it feeds the file to MySQL
(`docs/importer.md`). The script never connects to a database and uses only the Python standard library. It costs nothing: GitHub allows

> "The primary rate limit for unauthenticated requests is 60 requests per hour." (build/3_github_rest_rate_limits.txt L284; https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api; retrieved 2026-10-19)

and 5,000 requests an hour with a token (same file, the next paragraph). One request reads up to 100 pull requests (`per_page` is "max 100" in `build/1_2_github_rest_pulls.txt`).

## What DevLake does at the tag (R1 to R9)

The line numbers below are those of the saved files. The reviewer's first reading (made on 2026-10-20) used the original files' numbers; where a number differs by more than the one heading line, the saved file's number is the one given here.

### R1: the form of a domain id

> "prefix: fmt.Sprintf("%s:%s", pluginName, structName)," (v3/upstream/beta18/didgen_domain_id_generator.go.txt L64; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/didgen/domain_id_generator.go; retrieved 2026-10-20)

> "id += ":" + fmt.Sprintf("%v", pkValue)" (v3/upstream/beta18/didgen_domain_id_generator.go.txt L77; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/didgen/domain_id_generator.go; retrieved 2026-10-20)

Answer: `<plugin name>:<struct name>` followed by `:<value>` for each primary key field, in the order of the fields. For GitHub: `github:GithubPullRequest:<connection_id>:<id>`.

### R2: the id of a pull request

> "Id: prIdGen.Generate(data.Options.ConnectionId, pr.GithubId)," (v3/upstream/beta18/github_pr_convertor.go.txt L84; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_convertor.go; retrieved 2026-10-20)

> "prIdGen := didgen.NewDomainIdGenerator(&models.GithubPullRequest{})" (v3/upstream/beta18/github_pr_convertor.go.txt L55; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_convertor.go; retrieved 2026-10-20)

> "ConnectionId    uint64 `gorm:"primaryKey"`" (v3/upstream/beta18/github_models_pr.go.txt L28; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/pr.go; retrieved 2026-10-20)

> "GithubId        int    `gorm:"primaryKey"`" (v3/upstream/beta18/github_models_pr.go.txt L29; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/pr.go; retrieved 2026-10-20)

Answer: the key order of `GithubPullRequest` is `ConnectionId`, then `GithubId` (the original file has them at lines 27 and 28), so the id is `github:GithubPullRequest:<ConnectionId>:<GithubId>`.

### R3: where `GithubId` comes from (REST)

> "GithubId int             `json:"id"`" (v3/upstream/beta18/github_pr_extractor.go.txt L51; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_extractor.go; retrieved 2026-10-20)

> "Number   int             `json:"number"`" (v3/upstream/beta18/github_pr_extractor.go.txt L52; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_extractor.go; retrieved 2026-10-20)

Answer: `GithubId` is the REST field `id` of the pull request, not `number` (`number` is a separate field, `Number`). The script therefore builds the id from `id`.

### R4: where `GithubId` comes from (GraphQL)

> "GithubId:        pull.DatabaseId," (v3/upstream/beta18/graphql_pr_extractor.go.txt L165; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_extractor.go; retrieved 2026-10-20)

Answer: on the GraphQL path `GithubId` is the pull request's database id, which is the same number as the REST `id` (that the two are the same number was not checked against live data; it is the premise of using one id for both paths, see U4 below).

### R5: the id of an assignee (an account) and its names

> "accountIdGen := didgen.NewDomainIdGenerator(&models.GithubAccount{})" (v3/upstream/beta18/github_account_convertor.go.txt L70; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go; retrieved 2026-10-20)

> "DomainEntity: domainlayer.DomainEntity{Id: accountIdGen.Generate(data.Options.ConnectionId, githubUser.Id)}," (v3/upstream/beta18/github_account_convertor.go.txt L154; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go; retrieved 2026-10-20)

> "ConnectionId uint64 `gorm:"primaryKey"`" (v3/upstream/beta18/github_models_account.go.txt L26; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/account.go; retrieved 2026-10-20)

> "Id           int    `json:"id" gorm:"primaryKey;autoIncrement:false"`" (v3/upstream/beta18/github_models_account.go.txt L27; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/account.go; retrieved 2026-10-20)

> "FullName:     githubUser.Name," (v3/upstream/beta18/github_account_convertor.go.txt L156; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go; retrieved 2026-10-20)

> "UserName:     githubUser.Login," (v3/upstream/beta18/github_account_convertor.go.txt L157; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/account_convertor.go; retrieved 2026-10-20)

The pull request's author id is made by the same generator, which is why a comment's `account_id` and an assignee's `assignee_id` can be compared (U1 does that):

> "domainPr.AuthorId = accountIdGen.Generate(data.Options.ConnectionId, pr.AuthorId)" (v3/upstream/beta18/github_pr_convertor.go.txt L113; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_convertor.go; retrieved 2026-10-20)

Answer: an account id is `github:GithubAccount:<ConnectionId>:<user id>`; the account's `UserName` is the GitHub login and its `FullName` is the GitHub profile name.

### R6: who writes `PullRequestAssignee` at the tag

> "domainPrAssigne := &code.PullRequestAssignee{" (v3/upstream/beta18/gitlab_mr_assignee_convertor.go.txt L68; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go; retrieved 2026-10-20)

> "PullRequestId: mrIdGen.Generate(data.Options.ConnectionId, mrAssignee.MergeRequestId)," (v3/upstream/beta18/gitlab_mr_assignee_convertor.go.txt L69; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go; retrieved 2026-10-20)

> "AssigneeId:    accountIdGen.Generate(data.Options.ConnectionId, mrAssignee.AssigneeId)," (v3/upstream/beta18/gitlab_mr_assignee_convertor.go.txt L70; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go; retrieved 2026-10-20)

> "Name:          mrAssignee.Name," (v3/upstream/beta18/gitlab_mr_assignee_convertor.go.txt L71; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go; retrieved 2026-10-20)

> "UserName:      mrAssignee.Username," (v3/upstream/beta18/gitlab_mr_assignee_convertor.go.txt L72; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_assignee_convertor.go; retrieved 2026-10-20)

Answer: the example of how DevLake fills the table is the GitLab convertor (lines 68 to 72; in the original file 67 to 71). Its `Name` is the GitLab assignee's name field. The table definition itself:

> "PullRequestId string `json:"id" gorm:"primaryKey;type:varchar(255);comment:This key is generated based on details from the original plugin"` // format: <Plugin>:<Entity>:<PK0>:<PK1>" (v3/upstream/beta18/pull_request_assignees.go.txt L26; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_assignees.go; retrieved 2026-10-20)

### R7: what a full re-import of DevLake deletes

> "return fmt.Sprintf("_raw_%s", args.Table)" (v3/upstream/beta18/subtask_state_manager.go.txt L44; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/subtask_state_manager.go; retrieved 2026-10-20)

> "Table:          RAW_PULL_REQUEST_TABLE," (v3/upstream/beta18/github_pr_convertor.go.txt L62; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_convertor.go; retrieved 2026-10-20)

> "const RAW_PULL_REQUEST_TABLE = "github_api_pull_requests"" (v3/upstream/beta18/r9_scan/backend__plugins__github__tasks__pr_collector.go.txt L41; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_collector.go; retrieved 2026-10-20)

> "batch, err := divider.ForType(reflect.TypeOf(result))" (v3/upstream/beta18/data_convertor_stateful.go.txt L173; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/data_convertor_stateful.go; retrieved 2026-10-20)

> "if !d.incrementalMode {" (v3/upstream/beta18/batch_save_divider.go.txt L83; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/batch_save_divider.go; retrieved 2026-10-20)

> "dal.Where("_raw_data_table = ? AND _raw_data_params = ?", d.table, d.params)," (v3/upstream/beta18/batch_save_divider.go.txt L89; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/batch_save_divider.go; retrieved 2026-10-20)

> "origin.Set(reflect.ValueOf(inputRow).Elem().FieldByName(RAW_DATA_ORIGIN))" (v3/upstream/beta18/data_convertor_stateful.go.txt L180; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/data_convertor_stateful.go; retrieved 2026-10-20)

Answer: when a converter runs in full-sync mode (`!d.incrementalMode`), for the first result of each output type (`ForType`, `batch_save_divider.go` lines 64 to 98, the delete itself at lines 87 to 90) it deletes the rows of
**that output type's table** where `_raw_data_table = '_raw_' + Table` and `_raw_data_params` = the scope's params. For the pull request convertor that is `pull_requests` with `_raw_data_table = '_raw_github_api_pull_requests'`;
`pull_request_assignees` is not an output type of any GitHub convertor (R9), so a full re-import never deletes from it. And its condition would match only the exact name `_raw_` + `Table`; the name chosen in E2 is not any `Table` of the GitHub plugin
(`grep "github_ext"` over the 220 files of R9 finds nothing). The reviewer's reading "the delete is on the type that the convertor output" is the same, and the lines are 173 (`ForType` called with `reflect.TypeOf(result)`) and 87 to 90 (not 63 to 65).
The row's own `_raw_data_params` and `_raw_data_table` are copied from the input row (`origin.Set(...)`, line 180); that is why a row written by DevLake carries the params of its source.

### R8: what a scope deletion deletes

> "rawDataParams := plugin.MarshalScopeParams(scope.ScopeParams())" (v3/upstream/beta18/srvhelper_scope_service_helper.go.txt L231; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/srvhelper/scope_service_helper.go; retrieved 2026-10-20)

> "where = "_raw_data_table LIKE ? AND _raw_data_params = ?"" (v3/upstream/beta18/srvhelper_scope_service_helper.go.txt L250; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/srvhelper/scope_service_helper.go; retrieved 2026-10-20)

> "rawDataTablePrefix := fmt.Sprintf("_raw_%s%%", scopeSrv.pluginName)" (v3/upstream/beta18/srvhelper_scope_service_helper.go.txt L252; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/srvhelper/scope_service_helper.go; retrieved 2026-10-20)

> "for _, domainModel := range domaininfo.GetDomainTablesInfo() {" (v3/upstream/beta18/srvhelper_scope_service_helper.go.txt L299; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/srvhelper/scope_service_helper.go; retrieved 2026-10-20)

> "ok = hasField(domainModel, "RawDataParams")" (v3/upstream/beta18/srvhelper_scope_service_helper.go.txt L301; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/srvhelper/scope_service_helper.go; retrieved 2026-10-20)

> "&code.PullRequestAssignee{}," (v3/upstream/beta18/domaininfo.go.txt L45; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/domaininfo/domaininfo.go; retrieved 2026-10-20)

> "common.NoPKModel" (v3/upstream/beta18/pull_request_assignees.go.txt L31; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/models/domainlayer/code/pull_request_assignees.go; retrieved 2026-10-20)

> "return &GithubApiParams{" (v3/upstream/beta18/github_models_repo.go.txt L60; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/repo.go; retrieved 2026-10-20)

> "Name:         r.FullName," (v3/upstream/beta18/github_models_repo.go.txt L62; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/models/repo.go; retrieved 2026-10-20)

> "Name:         data.Options.Name," (v3/upstream/beta18/github_pr_convertor.go.txt L65; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_convertor.go; retrieved 2026-10-20)

> "op.Name = githubRepo.FullName" (v3/upstream/beta18/r9_scan/backend__plugins__github__impl__impl.go.txt L299; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/impl/impl.go; retrieved 2026-10-20)

> "return utils.ToJsonString(args.Params)" (v3/upstream/beta18/subtask_state_manager.go.txt L51; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/subtask_state_manager.go; retrieved 2026-10-20)

> "b, err := json.Marshal(x)" (v3/upstream/beta18/utils_json.go.txt L79; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/utils/json.go; retrieved 2026-10-20)

> "bytes, err := json.Marshal(params)" (v3/upstream/beta18/plugin_datasource.go.txt L144; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/core/plugin/plugin_datasource.go; retrieved 2026-10-20)

Which of the two helpers the GitHub plugin uses for the deletion (the reviewer's reading had both `srvhelper/scope_service_helper.go` lines 173 to 265 and `pluginhelper/api/scope_generic_helper.go` lines 526 to 563):

> "return dsHelper.ScopeApi.Delete(input)" (v3/upstream/beta18/r9_scan/backend__plugins__github__api__scope_api.go.txt L154; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/api/scope_api.go; retrieved 2026-10-20)

> "refs, err := scopeApi.ScopeSrvHelper.DeleteScope(scope, input.Query.Get("delete_data_only") == "true")" (v3/upstream/beta18/ds_scope_api_helper.go.txt L142; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/ds_scope_api_helper.go; retrieved 2026-10-20)

Answer: the GitHub plugin's `DeleteScope` calls `dsHelper.ScopeApi.Delete`, which calls `ScopeSrvHelper.DeleteScope` of `srvhelper/scope_service_helper.go` (the deletion is `deleteScopeData`, lines 230 to 267). No file of the GitHub plugins refers to `GenericScopeApiHelper`
(`github_r9_scan_result.txt` is the scan of the 220 files; `grep GenericScopeApiHelper` over them finds nothing). The generic helper has the same clauses:

> "where = "_raw_data_table LIKE ? AND _raw_data_params = ?"" (v3/upstream/beta18/scope_generic_helper.go.txt L560; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/helpers/pluginhelper/api/scope_generic_helper.go; retrieved 2026-10-20)

so the conclusion does not depend on which one is used. For a domain table, the scope deletion runs `DELETE FROM <table> WHERE _raw_data_table LIKE '_raw_github%' AND _raw_data_params = '<params>'`, and `pull_request_assignees` is one of the
domain tables it visits (it is in `domaininfo.go` and embeds `NoPKModel`, which carries `RawDataParams`, `common_base.go` lines 55 and 71). The params are `json.Marshal` of `GithubApiParams{ConnectionId, Name: FullName}`;
the converters write `json.Marshal` of `GithubApiParams{ConnectionId, Name: Options.Name}`, and `Options.Name` is set to the repo's `FullName` when the repo is found (`impl.go` line 299 of the saved file).

### R9: no GitHub path writes or deletes `pull_request_assignees`

The scan: every `.go` file under `backend/plugins/github/` and `backend/plugins/github_graphql/` at the tag (220 files; the file list is the recursive git tree of the tag, which was not truncated), searched for `PullRequestAssignee` and `pull_request_assignees`.

> "--- grep -in 'PullRequestAssignee|pull_request_assignees' (expect empty):" (v3/upstream/beta18/github_r9_scan_result.txt L225; gh api repos/apache/devlake/git/trees/v1.0.3-beta18?recursive=1 and repos/apache/devlake/contents/<path>?ref=v1.0.3-beta18; retrieved 2026-10-20)

In the saved result file that line is directly followed (line 226) by the next heading: no line matched; line 3 of the file is the count of matching files, `0`. Of the files that contain the word "assignee" (listed in the result file), the ones about pull requests are these two; the others concern issue assignees (`issue_extractor.go`, `issue_assignee_convertor.go`, which write the issue tables, not this one), an `assignees_url` field of API data types, or a comment:

> "Assignee        *GithubAccountResponse `json:"assignee"`" (v3/upstream/beta18/github_pr_extractor.go.txt L60; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_extractor.go; retrieved 2026-10-20)

> "// FIXME now domain layer just support one assignee" (v3/upstream/beta18/graphql_pr_collector.go.txt L78; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github_graphql/tasks/pr_collector.go; retrieved 2026-10-20)

The REST extractor reads the single `assignee` of a pull request and does not store it (the model `GithubPullRequest` has no such column, `github_models_pr.go.txt`); the GraphQL collector asks for one (`assignees(first: 1)`, line 80) and its extractor
(`graphql_pr_extractor.go.txt`) does not use it. The one place in DevLake that deletes `PullRequestAssignee` without looking at `_raw_data_table` is GitLab's:

> "if err := db.Delete(&code.PullRequestAssignee{}, dal.Where("pull_request_id = ?", mrId)); err != nil {" (v3/upstream/beta18/gitlab_mr_convertor.go.txt L70; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/gitlab/tasks/mr_convertor.go; retrieved 2026-10-20)

and GitHub has no counterpart. (The earlier check, `github_plugin_tasks_and_assignee_usage.txt`, used a code search of the default branch; this scan is pinned to the tag.)

Also read, for the extractor of accounts: the REST pull request extractor emits an account row for the pull request's `user` and `merged_by`, not for the assignees:

> "// Emit a repo_account for the merged-by user too, so pull_requests.merged_by_id" (v3/upstream/beta18/github_pr_extractor.go.txt L155; https://github.com/apache/devlake/blob/v1.0.3-beta18/backend/plugins/github/tasks/pr_extractor.go; retrieved 2026-10-20)

so an assignee who never wrote anything on any pull request of the repo may have no `accounts` row. 1B compares account ids and does not need the row.

The premises of E2 and E3 held: the full re-import deletes only by `_raw_` + the exact `Table` of the output type (R7), no GitHub path writes or deletes `pull_request_assignees` (R9), the scope deletion matches `_raw_github%` and the params of the repo (R8),
and the params of a row are copied from the source row (R7, R8).

## Decisions

| # | Decision | Reason |
|---|---|---|
| E1 | `pull_request_id` and `assignee_id` are made as DevLake makes them: `github:GithubPullRequest:<connection_id>:<REST id of the PR>` and `github:GithubAccount:<connection_id>:<id of the user>` | R1, R2, R5. U1's join (`asg.pull_request_id = p.id AND asg.assignee_id = c.account_id`) works unchanged |
| E2 | `_raw_data_table` = `_raw_github_ext_pull_request_assignees` | Not equal to any `_raw_` + `Table` that a GitHub convertor deletes by (R7), so a full re-import keeps the rows. It starts with `_raw_github`, so the scope deletion's `LIKE '_raw_github%'` (R8) removes them together with the repo's other data |
| E3 | `_raw_data_params` is copied from the `pull_requests` row of the same PR (`SELECT ..., pr._raw_data_params ... FROM pull_requests pr`) | The scope deletion's condition on params and the params the converter writes come from the same struct (R8); copying the PR's value means that whatever removes the PR (the scope deletion) removes the assignee row |
| E4 | `user_name` = `login`; `name` = `login` too | In GitLab `Name` is the display name (R6). A GitHub account has a display name (`FullName`, R5) but an element of `assignees` in "List pull requests" has none: the example's elements have `login`, `id`, ... and no `name` |
| E5 | An assignee who was removed from a PR disappears at the next run | The run deletes the script's own rows of every PR it read, then inserts what GitHub reports |
| E6 | Rows that DevLake wrote (another `_raw_data_table`) are never touched | The `DELETE` always has `_raw_data_table = '<E2 name>'` |

The element of `assignees` in the example response (`build/1_2_github_rest_pulls.txt`, from line 523):

> ""assignees": [" (build/1_2_github_rest_pulls.txt L523; https://docs.github.com/en/rest/pulls/pulls; retrieved 2026-10-19)

> ""login": "octocat"," (build/1_2_github_rest_pulls.txt L525; https://docs.github.com/en/rest/pulls/pulls; retrieved 2026-10-19)

Implementation choices that the SPEC left to the implementer, and what they mean:

- **A PR that fails a check is skipped as a whole.** An `id` that is not an integer (a JSON number; `true` and text are refused), an `assignees` that is not a list, an assignee whose `id` is not an integer or whose `login` does not match `^[A-Za-z0-9-]{1,39}$` (checked with `re.fullmatch`, because `$` alone also accepts a value that ends with a newline):
  the PR is left out of both the `DELETE` list and the inserts (so its existing rows stay as they were) and is counted in `prs_skipped_invalid`, which is printed and put in the check `SELECT`.
- **The `DELETE` lists every PR that was read**, also the ones with 0 assignees (that is how an emptied PR loses its rows).
- **The same PR on two pages** (a page boundary can move while the pages are read) keeps the union of the assignees read, each (PR, assignee) once (the SPEC: "the same (PR, assignee id) twice: merge into one").
- **A PR that DevLake does not have** gets no row: every `INSERT` is `INSERT ... SELECT ... FROM pull_requests pr WHERE pr.id = '<id>'`. The check `SELECT` at the end reports the number of rows now in the table (`rows_in_table`), the number the script wrote if every PR existed
  (`rows_expected_if_all_prs_in_devlake`) and the number of PRs DevLake does not have (`prs_not_in_devlake`).
- **A key collision fails loudly.** If DevLake itself one day wrote a row with the same (pull_request_id, assignee_id), the `INSERT` stops with a duplicate-key error and the transaction (`START TRANSACTION;` ... `COMMIT;`) is not committed; nothing changes.
- **Strings in the SQL**: a backslash is written `\\` first, then a quote `''` (MySQL reads a backslash as an escape). Values that can reach the SQL are the `login`, the repo name (checked by `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$` with `re.fullmatch`, `.` and `..` refused as a part) and the page URLs of the check `SELECT`;
  numbers are written through `int()`. A server with `NO_BACKSLASH_ESCAPES` in `sql_mode` would read `\\` as two characters; only the page URL column could be affected, because the other strings cannot contain a backslash.
- **Network**: the token is added with `add_unredirected_header`, so a redirect does not carry it; only a next-page URL that starts with `https://api.github.com/` is followed; the first error (HTTP 403, 429, any other) stops the run with exit code 1, writes no `.sql`, prints how many pages were read and the rate-limit headers if GitHub sent them,
  and does not retry. A `Link` that returns to a URL already read, or more than 1,000 pages, also stops it.
  After each answer, `resp.geturl()` must start with `https://api.github.com/` (urllib follows redirects by itself; a redirect to another host is stopped before the body is read, exit code 1);
  a renamed repository that GitHub redirects within `api.github.com` is followed, and a 301/302/307/308 that ends as an error prints "give its new name in --repo" (`docs/importer.md`).
  In `--from-file` the `url` field of each page plays the role of `geturl()`. `http.client.HTTPException` (for example `IncompleteRead`) and a json that is nested too deep (`RecursionError`) also stop the run (exit code 1 for GitHub, 2 for a file).
- **No old output after a stop**: the `.sql` is written to `<out>.tmp` and renamed at the end; when the run stops (exit code 1 or 2), a plain file already at `--out` is removed (never the `--from-file` input), so that a `.sql` of an earlier run cannot be fed to the database after a failed run.
- **Write permission**: the user in DevLake's compose (`merico`) owns `lake` through `MYSQL_DATABASE`/`MYSQL_USER`. Writing the rows into a real DevLake database is checked in U4 (see "What U4 must check on a real DevLake").

## Tests

`python tests/importer/test_importer.py` starts a `mysql:8.4` container (utf8mb4 / utf8mb4_bin, the options of DevLake's compose file), loads `tests/schema_mysql.sql` (U1, unchanged) and `tests/importer/schema_extra.sql`
(the columns `_raw_data_*`, `created_at`, `updated_at`; types from `common_base.go.txt`), and runs scenes A1 to A17 on the inputs `tests/importer/pages_*.json` (described in `pages_README.md`), then removes the container.
The expected values are written by hand from the inputs. Scenes N1 to N9 exercise the network code with a fake `open_url` (nothing is sent). U1's SQL for 1B is run on one PR before and after the import (A13): 10 minutes both times before; 10 and 60 after (the assignee's comment is first, then another person's).

### Mutations

`python tests/importer/test_importer.py --mutants` changes `importer/github_pr_assignees.py` in one place at a time (the text to change must occur exactly once) and runs all scenes:

| # | Change (one at a time) | Scene it must fail | Scenes that failed | Result |
|---|---|---|---|---|
| 1 | DELETE without the _raw_data_table condition | A5 | A5 | caught |
| 2 | PR id built from `number` instead of `id` | A2 | A10, A13, A14, A2, A3, A4, A4z, A5o, A6, A7, A8, A9, N5, N7 | caught |
| 3 | backslash not escaped in SQL strings | A8 | A8 | caught |
| 4 | E2 name does not start with _raw_github | A10 | A10, A14, A2, A4, A4z, A5o, A6, A7, A8, A9 | caught |
| 5 | DELETE without the IN (...) condition | A5o | A4z, A5o | caught |
| 6 | duplicates (same PR, same assignee) not merged | A2 | A1, A10, A11, A12, A2, A3, A6, A9 | caught |
| 7 | login checked with `match` instead of `fullmatch` (a trailing newline passes) | A14 | A14 | caught |
| 8 | `--repo` checked with `match` instead of `fullmatch` | A14 | A14 | caught |
| 9 | the URL the answer came from (`resp.geturl()`) is not checked | N7 | N7 | caught |
| 10 | the `url` of an input page is not checked | A17 | A15, A17 | caught |
| 11 | `http.client.HTTPException` not caught | N9 | N1 to N9 (the scene stops on the uncaught exception) | caught |
| 12 | `RecursionError` of json not caught | N9 | N1 to N9 (the scene stops on the uncaught exception) | caught |
| 13 | an old `--out` is not removed when the run stops | A15 | A14, A15, A16, A17, A7, A8, N2, N3, N4, N7, N8, N9 | caught |

Last line of the run: `13 mutants, 13 caught`. Mutants 1 to 6 are the ones of the SPEC; 7 to 13 were added with the fixes of the first review (the newline, the redirect, the errors that were not caught, the old output). Several scenes fail in a mutant when the scene that checks the data (A2) or the stored name (E2) breaks all the later scenes that read the rows, or when a SQL error stops a scene; the table lists every scene that failed.

## Differences and limits

- Only assignees that GitHub reports **now** are known. The script does not know who was assigned in the past, so a PR whose assignee was later removed shows no assignee in 1B.
- Only the pull requests that GitHub lists (`state=all`) are read, newest first; reading a big repo takes one request per 100 PRs and the whole list is read each time.
- The first reaction of 1B excludes comments by an assignee, as the SQL defines; the importer only supplies the table.
- `name` is the login, not the profile name (E4), because "List pull requests" does not return it.

## What U4 must check on a real DevLake

1. Import, then run the script, then run a full re-import of the repo in DevLake: the number of rows with `_raw_data_table = '_raw_github_ext_pull_request_assignees'` does not change.
2. Delete the scope (repo) in DevLake: the script's rows go too.
3. On real data, the number of PRs for which 1B differs from the plain first reaction.
4. `SHOW CREATE TABLE pull_request_assignees` and `pull_requests`: the real column types and NULL rules of `_raw_data_params`, `_raw_data_table`, `_raw_data_id`, `_raw_data_remark`, `created_at`, `updated_at` (the test schema is the usual gorm mapping, `tests/importer/schema_extra.sql`), and that the script's `INSERT` (which leaves `_raw_data_id` and `_raw_data_remark` unset) is accepted.
5. That `pull_requests._raw_data_params` of a real row has the form `{"ConnectionId":<n>,"Name":"<owner>/<repo>"}`; and that the REST `id` and the GraphQL `databaseId` of a pull request are the same number (R4), by comparing the ids in `pull_requests` of a repo imported by each path.
6. That the real `sql_mode` does not contain `NO_BACKSLASH_ESCAPES`.
