#!/usr/bin/env python3
"""Set up the DevLake side of the U4 check by script instead of by hand in the web screens.
(U4 addendum, see docs/devlake_configure.md)

What a person still does by hand (two things): start DevLake, and type the GitHub token into the connection screen.
Everything else is done here through the REST API of the local DevLake (v1.0.3-beta18):

  plan    changes nothing. Reads the scopes, the Scope Configs and the blueprint of the project, runs the checks
          that `apply` runs, prints what `apply` would send, and prints an ESTIMATE of how much the import asks
          GitHub for (not a measurement).
  apply   runs the same checks, and only if all of them pass: (1) creates the Scope Config (or reuses the one with
          the same name), (2) attaches it to the scopes, (3) checks the Sync Policy again, (4) triggers the
          blueprint with fullSync. Appends what it did to the file given with --log.
  status  changes nothing. Prints the state of one pipeline, its tasks, the running subtask and the record counts,
          once. (A caller who wants to watch calls it again after its own interval.)

Safety:
  * The only address it talks to is http://127.0.0.1[:port]. Another host, scheme, user info or path is refused
    before a connection is opened. Redirects are not followed and proxy settings of the environment are ignored.
  * It never creates or reads a connection. The connection is only used by number; its existence is checked through the
    scope list of that connection (HTTP 200). GET .../connections is never sent. The token is never seen.
  * plan and status can only send GET (checked in the request function as well).
  * Everything it prints or logs from a response goes through redact(): a key that contains token, password or
    secret is replaced, and so is the user info part of a URL.
  * GitHub is asked only by plan, only through `gh api <path> --jq .total_count` (read-only GET; the token of gh is
    not touched), for the estimate. If gh is missing or fails, the number is shown as "not fetched".

Standard library only. Exit code 0 = done / all checks passed; 1 = a check failed (nothing was changed by that
command); 2 = a bad argument or a refused address; 3 = DevLake answered with an error or could not be reached.

Usage:
  python tools/devlake_configure.py plan   --connection-id 1 --repos OWNER/NAME OWNER/NAME --project NAME
  python tools/devlake_configure.py apply  --connection-id 1 --repos OWNER/NAME OWNER/NAME --project NAME --log FILE
  python tools/devlake_configure.py status --pipeline 1
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOST = "127.0.0.1"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
PLUGIN = "github"
SCOPE_CONFIG_NAME = "u4-code-review-only"
# The values of `entities` of a Scope Config: plugin.DOMAIN_TYPE_CODE / _CODE_REVIEW / _CROSS
# (backend/core/plugin/plugin_task.go L82, L84, L85 of v1.0.3-beta18).
ENTITIES = ["CODE", "CODEREVIEW", "CROSS"]
# 2026-06-01 00:00 in Japan = 2026-05-31T15:00:00Z. The screen of DevLake shows the Data Time Range as `timeAfter`.
TIME_AFTER = "2026-05-31T15:00:00Z"
TRIGGER_BODY = {"skipCollectors": False, "fullSync": True}
REPO_RE = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
RUNNING = ("TASK_CREATED", "TASK_RERUN", "TASK_RESUME", "TASK_RUNNING")
HTTP_TIMEOUT = 60
MAX_BODY = 8 * 1024 * 1024

# ------------------------------------------------------------------------------------------------
# The subtasks of the `github_graphql` task (the route of a connection with "Use GraphQL APIs" on).
# One row = (Name, EnabledByDefault, DomainTypes, where the SubTaskMeta is: file:line of v1.0.3-beta18).
# The order is the order in SubTaskMetas() of backend/plugins/github_graphql/impl/impl.go (L80-L140).
# A subtask is in the plan when it is EnabledByDefault and one of its DomainTypes is in `entities`
# (MakePipelinePlanSubtasks, backend/helpers/pluginhelper/api/pipeline_plan.go L33-L58).
# ------------------------------------------------------------------------------------------------
SUBTASKS = (
    ('Collect Milestones', True, ('TICKET',), 'github/tasks/milestone_collector.go:37'),
    ('Extract Milestones', True, ('TICKET',), 'github/tasks/milestone_extractor.go:32'),
    ('Collect Issues', True, ('TICKET',), 'github_graphql/tasks/issue_collector.go:107'),
    ('Extract Issues', True, ('TICKET',), 'github_graphql/tasks/issue_extractor.go:36'),
    ('Collect Pull Requests', True, ('CODEREVIEW',), 'github_graphql/tasks/pr_collector.go:159'),
    ('Extract Pull Requests', True, ('CODEREVIEW',), 'github_graphql/tasks/pr_extractor.go:33'),
    ('Collect Workflow Runs', True, ('CICD',), 'github/tasks/cicd_run_collector.go:62'),
    ('Extract Workflow Runs', True, ('CICD',), 'github/tasks/cicd_run_extractor.go:32'),
    ('Collect Job Runs', True, ('CICD',), 'github_graphql/tasks/job_collector.go:192'),
    ('Extract Jobs', True, ('CICD',), 'github_graphql/tasks/job_extractor.go:35'),
    ('Collect Comments', True, ('CODEREVIEW', 'TICKET'), 'github/tasks/comment_collector.go:38'),
    ('Extract Comments', True, ('CODEREVIEW', 'TICKET'), 'github/tasks/comment_extractor.go:36'),
    ('Collect Events', True, ('TICKET',), 'github/tasks/event_collector.go:48'),
    ('Extract Events', True, ('TICKET',), 'github/tasks/event_extractor.go:32'),
    ('Collect PR Review Comments', True, ('CROSS', 'CODEREVIEW'), 'github/tasks/pr_review_comment_collector.go:40'),
    ('Extract PR Review Comments', True, ('CROSS', 'CODEREVIEW'), 'github/tasks/pr_review_comment_extractor.go:38'),
    ('Collect Users', True, ('CROSS',), 'github_graphql/tasks/account_collector.go:60'),
    ('Extract Users', True, ('CROSS',), 'github_graphql/tasks/account_extractor.go:32'),
    ('Convert Workflow Runs', True, ('CICD',), 'github/tasks/cicd_run_convertor.go:37'),
    ('Convert Jobs', True, ('CICD',), 'github/tasks/cicd_job_convertor.go:35'),
    ('Enrich PR Issues', True, ('CROSS',), 'github/tasks/pr_issue_enricher.go:36'),
    ('Convert Repos', True, ('CODE', 'TICKET', 'CICD', 'CODEREVIEW', 'CROSS'), 'github/tasks/repo_convertor.go:55'),
    ('Convert Issues', True, ('TICKET',), 'github/tasks/issue_convertor.go:38'),
    ('Convert Commits', False, ('CODE',), 'github/tasks/commit_convertor.go:34'),
    ('Convert Issue Labels', True, ('TICKET',), 'github/tasks/issue_label_convertor.go:34'),
    ('Convert PR Commits', True, ('CROSS', 'CODEREVIEW'), 'github/tasks/pr_commit_convertor.go:34'),
    ('Convert Pull Requests', True, ('CROSS', 'CODEREVIEW'), 'github/tasks/pr_convertor.go:35'),
    ('Convert PR Reviews', True, ('CODEREVIEW',), 'github/tasks/pr_review_convertor.go:35'),
    ('Convert PR Labels', True, ('CODEREVIEW',), 'github/tasks/pr_label_convertor.go:34'),
    ('Convert PR Issues', True, ('CROSS',), 'github/tasks/pr_issue_convertor.go:36'),
    ('Convert Issue Assignees', True, ('TICKET',), 'github/tasks/issue_assignee_convertor.go:34'),
    ('Convert Issue Comments', True, ('TICKET',), 'github/tasks/issue_comment_convertor.go:35'),
    ('Convert PR Comments', True, ('CODEREVIEW',), 'github/tasks/pr_comment_convertor.go:35'),
    ('Convert Reviews', True, ('CODEREVIEW',), 'github/tasks/review_convertor.go:34'),
    ('Convert Milestones', True, ('TICKET',), 'github/tasks/milestone_converter.go:38'),
    ('Convert Users', True, ('CROSS',), 'github/tasks/account_convertor.go:52'),
    ('Collect Deployments', True, ('CICD',), 'github_graphql/tasks/deployment_collector.go:38'),
    ('Extract Deployments', True, ('CICD',), 'github_graphql/tasks/deployment_extractor.go:35'),
    ('Convert Deployments', True, ('CICD',), 'github_graphql/tasks/deployment_convertor.go:39'),
    ('Collect Releases', True, ('CICD',), 'github_graphql/tasks/release_collector.go:78'),
    ('Extract Releases', True, ('CICD',), 'github_graphql/tasks/release_extractor.go:34'),
    ('Convert Releases', True, ('CICD',), 'github/tasks/release_convertor.go:39'),
)
ALL_DOMAIN_TYPES = ("CODE", "TICKET", "CODEREVIEW", "CROSS", "CICD", "CODEQUALITY")


def split_subtasks(entities):
    """(kept, dropped) for a Scope Config with these entities. kept = names; dropped = (name, reason)."""
    wanted = set(entities)
    kept, dropped = [], []
    for name, enabled, domains, _src in SUBTASKS:
        if not enabled:
            dropped.append((name, "not enabled by default"))
        elif wanted & set(domains):
            kept.append(name)
        else:
            dropped.append((name, "only for " + "/".join(domains)))
    return kept, dropped


# ---------------------------------------------------------------- stop / redaction
class Stop(Exception):
    """A reason to end the command. `code` is the exit code."""

    def __init__(self, message, code=1):
        Exception.__init__(self, message)
        self.code = code


SENSITIVE_KEY = re.compile(r"token|password|secret", re.I)
URL_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s@\"']+@")
TEXT_SECRET = re.compile(r"(\"[^\"]*(?:token|password|secret)[^\"]*\"\s*:\s*)\"[^\"]*\"", re.I)


def redact(value):
    """A copy of a decoded json value without secrets: values under a key that contains token, password or secret
    are replaced, and so is the user info of a URL inside a string."""
    if isinstance(value, dict):
        return {k: ("***" if SENSITIVE_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return URL_USERINFO.sub(r"\1***@", value)
    return value


def safe_text(text, limit=400):
    """Text of a response made fit for printing and logging: json is redacted as json, other text by pattern."""
    try:
        text = json.dumps(redact(json.loads(text)), ensure_ascii=True, sort_keys=True)
    except ValueError:
        text = URL_USERINFO.sub(r"\1***@", TEXT_SECRET.sub(r'\1"***"', text))
        text = text.encode("ascii", "replace").decode("ascii")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "...(cut)"


# ---------------------------------------------------------------- the address and the HTTP calls
def check_base_url(url):
    """Returns the base URL to use, or raises Stop. Only http://127.0.0.1[:port] is accepted."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        raise Stop("refused: %r is not a usable address; only http://127.0.0.1[:port] is allowed" % url[:80], 2)
    host_ok = parts.hostname == ALLOWED_HOST
    if (parts.scheme != "http" or not host_ok or parts.username is not None or parts.password is not None
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise Stop("refused: %r is not allowed; only http://127.0.0.1[:port] is allowed" % url[:80], 2)
    return "http://%s%s" % (ALLOWED_HOST, "" if port is None else ":%d" % port)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApiError(Stop):
    def __init__(self, method, path, status, text):
        Stop.__init__(self, "DevLake answered %s to %s %s: %s" % (status, method, path, text), 3)
        self.status = status


class Api:
    """The calls to the local DevLake. read_only=True makes every method other than GET impossible."""

    def __init__(self, base_url, read_only, log=None):
        self.base = check_base_url(base_url)
        self.read_only = read_only
        self.log = log  # a function(line) or None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None):
        """Returns (status, decoded json or None). Raises ApiError for status >= 400, Stop(…, 3) if unreachable."""
        if self.read_only and method != "GET":
            raise Stop("internal error: a read-only command tried to send %s %s" % (method, path), 2)
        if not path.startswith("/"):
            raise Stop("internal error: bad path %r" % path, 2)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        status, raw = 0, b""
        try:
            with self.opener.open(req, timeout=HTTP_TIMEOUT) as resp:
                status, raw = resp.status, resp.read(MAX_BODY)
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read(MAX_BODY)
        except (urllib.error.URLError, OSError) as e:
            self._log(method, path, body, "unreachable", "")
            raise Stop("could not reach DevLake at %s (%s)" % (self.base, type(e).__name__), 3)
        text = raw.decode("utf-8", "replace")
        self._log(method, path, body, status, text)
        if not 200 <= status < 300:
            raise ApiError(method, path, status, safe_text(text))
        try:
            return status, (json.loads(text) if text.strip() else None)
        except ValueError:
            raise Stop("DevLake answered %s %s with something that is not json" % (method, path), 3)

    def get(self, path):
        return self.request("GET", path)[1]

    def _log(self, method, path, body, status, text):
        if self.log is None:
            return
        line = "%s %s status=%s" % (method, path, status)
        if method != "GET":
            line += " body=%s response=%s" % (safe_text(json.dumps(body)) if body is not None else "-", safe_text(text, 300))
        self.log(line)


# ---------------------------------------------------------------- small helpers
def parse_time(value):
    if not value or not isinstance(value, str):
        return None
    try:
        d = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def fmt_time(value):
    d = parse_time(value)
    return d.astimezone(datetime.timezone.utc).strftime("%H:%M:%S") + " UTC" if d else "-"


def fmt_dur(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return "%dh%02dm" % (seconds // 3600, seconds % 3600 // 60)
    if seconds >= 60:
        return "%dm%02ds" % (seconds // 60, seconds % 60)
    return "%ds" % seconds


def span_seconds(began, finished):
    b, f = parse_time(began), parse_time(finished)
    return None if b is None or f is None else max(0, int((f - b).total_seconds()))


def short_error(message):
    """The last two causes of a DevLake error message (the full text is a Go stack trace)."""
    causes = [c.strip() for c in re.findall(r"Wraps: \(\d+\) ([^\n]+)", message or "")
              if not c.startswith("attached stack trace")]
    return safe_text(" / ".join(causes[-2:]), 200) if causes else ""


def say(text=""):
    print(text)


# ---------------------------------------------------------------- reading the state (GET only)
def read_state(api, args):
    cid = args.connection_id
    st = {}
    try:
        st["version"] = (api.get("/version") or {}).get("version", "unknown")
    except ApiError:
        st["version"] = "unknown"
    # The scope list of the connection: HTTP 200 is how the existence of the connection is checked.
    scopes, page = [], 1
    while True:
        body = api.get("/plugins/%s/connections/%d/scopes?pageSize=100&page=%d" % (PLUGIN, cid, page)) or {}
        items = body.get("scopes") or []
        scopes.extend(i.get("scope") or {} for i in items)
        if not items or len(scopes) >= int(body.get("count", 0)) or page >= 50:
            break
        page += 1
    st["scopes"] = scopes
    st["scope_configs"] = api.get("/plugins/%s/connections/%d/scope-configs" % (PLUGIN, cid)) or []
    project = api.get("/projects/%s" % urllib.parse.quote(args.project, safe=""))
    st["project_blueprint"] = (project or {}).get("blueprint")
    bps, page = [], 1
    while True:
        body = api.get("/blueprints?pageSize=100&page=%d" % page) or {}
        items = body.get("blueprints") or []
        bps.extend(items)
        if not items or len(bps) >= int(body.get("count", 0)) or page >= 50:
            break
        page += 1
    st["blueprints"] = [b for b in bps if b.get("projectName") == args.project]
    bp = st["project_blueprint"]
    st["pipelines"] = []
    if bp and bp.get("id") is not None:
        st["pipelines"] = (api.get("/blueprints/%d/pipelines" % int(bp["id"])) or {}).get("pipelines") or []
    st["repo_scopes"] = {}
    by_name = {str(s.get("fullName", "")).lower(): s for s in scopes}
    for repo in args.repos:
        st["repo_scopes"][repo] = by_name.get(repo.lower())
    return st


def sync_policy_checks(bp):
    """The Sync Policy checks of the blueprint: [(ok, text)]."""
    bp = bp or {}
    want = parse_time(TIME_AFTER)
    got = parse_time(bp.get("timeAfter"))
    return [
        (bp.get("enable") is True, "blueprint is enabled (a disabled blueprint cannot be triggered): enable=%s" % bp.get("enable")),
        (got is not None and got == want,
         "Data Time Range starts at %s: timeAfter=%s" % (TIME_AFTER, bp.get("timeAfter"))),
        (bp.get("isManual") is True, "frequency is Manual: isManual=%s" % bp.get("isManual")),
    ]


def precondition_checks(args, st):
    checks = [(True, "connection %d answered the scope list with HTTP 200 (%d scopes)" % (args.connection_id, len(st["scopes"])))]
    for repo, scope in st["repo_scopes"].items():
        checks.append((scope is not None, "scope exists for %s" % repo))
    bps = st["blueprints"]
    bp = st["project_blueprint"]
    checks.append((len(bps) == 1 and bp is not None and bps[0].get("id") == bp.get("id"),
                   "project %s has exactly one blueprint (found %d)" % (args.project, len(bps))))
    checks.extend(sync_policy_checks(bp))
    if bp:
        have = set()
        for c in bp.get("connections") or []:
            if c.get("pluginName") == PLUGIN and c.get("connectionId") == args.connection_id:
                have.update(str(s.get("scopeId")) for s in c.get("scopes") or [])
        for repo, scope in st["repo_scopes"].items():
            if scope is not None:
                checks.append((str(scope.get("githubId")) in have, "the blueprint collects the scope of %s" % repo))
    running = [p.get("id") for p in st["pipelines"] if p.get("status") in RUNNING]
    checks.append((not running, "no pipeline of the blueprint is running (running: %s)" % (running or "none")))
    same = [c for c in st["scope_configs"] if c.get("name") == args.scope_config_name]
    if same:
        checks.append((sorted(same[0].get("entities") or []) == sorted(ENTITIES),
                       "existing Scope Config %r has entities %s" % (args.scope_config_name, ENTITIES)))
    return checks


# ---------------------------------------------------------------- the steps of apply
NEW_ID = "<id of the Scope Config created in step 1>"


def build_steps(args, st):
    """The calls that apply makes, in order: dicts with method, path, body, note. Used by plan to print them and
    by apply to run them, so the two cannot differ."""
    cid, bp = args.connection_id, st["project_blueprint"] or {}
    steps = []
    same = [c for c in st["scope_configs"] if c.get("name") == args.scope_config_name]
    if same:
        cfg_id = same[0].get("id")
        steps.append({"method": None, "note": "Scope Config %r exists (id=%s): reuse it, create nothing" % (args.scope_config_name, cfg_id)})
    else:
        cfg_id = NEW_ID
        steps.append({"method": "POST", "path": "/plugins/%s/connections/%d/scope-configs" % (PLUGIN, cid),
                      "body": {"name": args.scope_config_name, "entities": list(ENTITIES)},
                      "note": "create the Scope Config", "creates": True})
    for repo in args.repos:
        scope = st["repo_scopes"].get(repo) or {}
        if cfg_id != NEW_ID and scope.get("scopeConfigId") == cfg_id:
            steps.append({"method": None, "note": "scope %s already has Scope Config %s: nothing to do" % (repo, cfg_id)})
        else:
            steps.append({"method": "PATCH", "path": "/plugins/%s/connections/%d/scopes/%s" % (PLUGIN, cid, scope.get("githubId")),
                          "body": {"scopeConfigId": cfg_id}, "note": "attach the Scope Config to %s" % repo})
    steps.append({"method": "GET", "path": "/blueprints/%s" % bp.get("id"), "body": None, "recheck": True,
                  "note": "check the Sync Policy again just before the trigger"})
    steps.append({"method": "POST", "path": "/blueprints/%s/trigger" % bp.get("id"), "body": dict(TRIGGER_BODY),
                  "note": "run the import (fullSync)", "trigger": True})
    return steps


def describe_step(i, step):
    if step["method"] is None:
        return "  %d. (skip) %s" % (i, step["note"])
    body = "" if step["body"] is None else " " + json.dumps(step["body"], sort_keys=True)
    return "  %d. %s %s%s   # %s" % (i, step["method"], step["path"], body, step["note"])


# ---------------------------------------------------------------- the estimate (plan only)
def run_gh(path):
    """One read-only GitHub REST call through the gh CLI, returning total_count as int, or None if gh is missing
    or fails. The command is always `gh api <path> --jq .total_count` (a GET; no -X, no body)."""
    exe = shutil.which("gh")
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "api", path, "--jq", ".total_count"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    out = p.stdout.strip()
    return int(out) if p.returncode == 0 and out.isdigit() else None


def estimate_counts(repos, use_github):
    rows = []
    for repo in repos:
        if not use_github:
            rows.append((repo, None, None, None))
            continue
        prs = run_gh("search/issues?q=repo:%s+is:pr&per_page=1" % repo)
        issues = run_gh("search/issues?q=repo:%s+is:issue&per_page=1" % repo)
        runs = run_gh("repos/%s/actions/runs?per_page=1" % repo)
        rows.append((repo, prs, issues, runs))
    return rows


def num(value):
    return "not fetched" if value is None else "{:,}".format(value)


def print_estimate(api, args):
    say("[4] ESTIMATE of what the import asks GitHub for. This is an estimate, not a measurement.")
    say("    Counts are read now with `gh api` (read-only). PRs and issues are totals over all time; DevLake only reads what changed")
    say("    after the Data Time Range start, so those two are upper bounds. The workflow-run count is the total_count of GitHub's API;")
    say("    it can come out smaller than the real number (example: sanity-io/cli showed 40,000, DevLake got 82,245).")
    head = ("repo", "PRs", "issues", "workflow runs", "PR authors (upper bound = PRs)")
    rows = [head]
    for repo, prs, issues, runs in estimate_counts(args.repos, not args.no_github):
        rows.append((repo, num(prs), num(issues), num(runs), num(prs)))
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    for r in rows:
        say("    " + "  ".join(r[i].ljust(widths[i]) for i in range(len(head))))
    say("    The entities CODE/CODEREVIEW/CROSS take out the workflow-run, job, deployment, release, issue, milestone and")
    say("    event subtasks (list below). The number of calls is not computed here; the reference below is measured.")
    say()
    kept, dropped = split_subtasks(ENTITIES)
    say("    Subtasks of the github_graphql task with entities %s (%d run, %d do not)." % (",".join(ENTITIES), len(kept), len(dropped)))
    say("      run : " + ", ".join(kept))
    say("      off : " + ", ".join("%s [%s]" % d for d in dropped))
    say("    Besides these, CODE adds one `gitextractor` task per repo (a git clone inside DevLake, not GitHub API calls).")
    say("    Subtask list source: " + "SubTaskMetas of github_graphql + MakePipelinePlanSubtasks (see docs/devlake_configure.md).")
    if args.reference_pipeline:
        say()
        print_reference(api, args.reference_pipeline, kept)


def print_reference(api, pid, kept):
    say("    Reference from the first run (pipeline #%d), measured by DevLake, for orientation only:" % pid)
    try:
        tasks = (api.get("/pipelines/%d/tasks" % pid) or {}).get("tasks") or []
        subtasks = (api.get("/pipelines/%d/subtasks" % pid) or {}).get("subtasks") or []
    except ApiError as e:
        say("      not available (%s)" % ("HTTP %s" % e.status))
        return
    detail = {s.get("id"): s.get("subtaskDetails") or [] for s in subtasks}
    for t in sorted(tasks, key=lambda t: (t.get("pipelineRow", 0), t.get("pipelineCol", 0))):
        repo = (t.get("options") or {}).get("fullName") or "-"
        if t.get("plugin") == "gitextractor":
            say("      task %s gitextractor %s: %s, %s" % (t.get("id"), repo, t.get("status"), fmt_dur(t.get("spentSeconds") or 0)))
        elif t.get("plugin") == "github_graphql":
            spent = t.get("spentSeconds") or 0
            say("      task %s github_graphql %s: %s, %s in total with all %d subtasks (CI and tickets included)"
                % (t.get("id"), repo, t.get("status"), fmt_dur(spent), len(t.get("subtasks") or [])))
            done = [d for d in detail.get(t.get("id"), []) if d.get("name") in kept and d.get("finishedAt")]
            for d in done:
                say("        stays: %-28s %s - %s  (%s, records %s)" % (
                    d["name"], fmt_time(d.get("beganAt")), fmt_time(d.get("finishedAt")),
                    fmt_dur(span_seconds(d.get("beganAt"), d.get("finishedAt")) or 0), d.get("finishedRecords")))
            sums = sum(span_seconds(d.get("beganAt"), d.get("finishedAt")) or 0 for d in done)
            say("        %d of %d staying subtasks had finished in #%d, %s together (the others were not reached: not measured)"
                % (len(done), len(kept), pid, fmt_dur(sums)))
            gone = [d for d in detail.get(t.get("id"), []) if d.get("name") not in kept and d.get("beganAt")]
            total = sum(span_seconds(d.get("beganAt"), d.get("finishedAt") or t.get("finishedAt")) or 0 for d in gone)
            say("        subtasks that would be taken out and had started in #%d took %s together" % (pid, fmt_dur(total)))


# ---------------------------------------------------------------- commands
def print_state(args, st):
    say("[1] Scopes of connection %d and their Scope Config" % args.connection_id)
    for repo in args.repos:
        s = st["repo_scopes"].get(repo)
        if s is None:
            say("    %-30s NOT FOUND among the scopes of the connection" % repo)
        else:
            say("    %-30s githubId=%s scopeConfigId=%s" % (repo, s.get("githubId"), s.get("scopeConfigId") or "(none)"))
    if st["scope_configs"]:
        for c in st["scope_configs"]:
            say("    Scope Config on the connection: id=%s name=%s entities=%s" % (c.get("id"), c.get("name"), c.get("entities")))
    else:
        say("    Scope Configs on the connection: (none)")
    say()
    bp = st["project_blueprint"] or {}
    say("[2] Blueprint of project %s and its Sync Policy" % args.project)
    say("    blueprint id=%s name=%s mode=%s" % (bp.get("id"), bp.get("name"), bp.get("mode")))
    say("    Sync Policy: timeAfter=%s isManual=%s cronConfig=%s skipOnFail=%s" % (
        bp.get("timeAfter"), bp.get("isManual"), bp.get("cronConfig"), bp.get("skipOnFail")))
    say("    pipelines of the blueprint: " + (", ".join("#%s %s" % (p.get("id"), p.get("status")) for p in st["pipelines"]) or "(none)"))


def cmd_plan(args):
    api = Api(args.base_url, read_only=True)  # PLAN-READ-ONLY
    say("devlake_configure plan (changes nothing)")
    say("DevLake at %s" % api.base)
    st = read_state(api, args)
    say("DevLake version: %s" % st["version"])
    say()
    print_state(args, st)
    checks = precondition_checks(args, st)
    say()
    say("    Checks that apply runs first:")
    for ok, text in checks:
        say("      [%s] %s" % ("ok" if ok else "FAIL", text))
    say()
    steps = build_steps(args, st)
    say("[3] What apply would do (in this order):")
    for i, step in enumerate(steps, 1):
        say(describe_step(i, step))
    say()
    print_estimate(api, args)
    bad = [t for ok, t in checks if not ok]
    say()
    say("plan: %s" % ("all checks passed" if not bad else "%d check(s) FAILED, apply would stop without changing anything" % len(bad)))
    return 0 if not bad else 1


def cmd_apply(args):
    if not args.log:
        raise Stop("apply needs --log FILE (it appends what it did to that file)", 2)
    try:
        logf = open(args.log, "a", encoding="utf-8")
    except OSError as e:
        raise Stop("cannot open the log file: %s" % type(e).__name__, 2)
    with logf:
        def log(line):
            logf.write("%s  %s\n" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), line))
            logf.flush()
        api = Api(args.base_url, read_only=False, log=log)
        log("apply start: base=%s connection=%d project=%s repos=%s scope_config=%s" % (
            api.base, args.connection_id, args.project, ",".join(args.repos), args.scope_config_name))
        say("devlake_configure apply")
        st = read_state(api, args)
        checks = precondition_checks(args, st)
        for ok, text in checks:
            say("  [%s] %s" % ("ok" if ok else "FAIL", text))
        bad = [t for ok, t in checks if not ok]
        if bad:
            log("apply stopped before any change: %d check(s) failed: %s" % (len(bad), "; ".join(bad)))
            say("apply: stopped. %d check(s) failed. Nothing was changed." % len(bad))
            return 1
        steps = build_steps(args, st)
        cfg_id = None
        if steps[0]["method"] is None:
            cfg_id = next((c.get("id") for c in st["scope_configs"] if c.get("name") == args.scope_config_name), None)
        pipeline_id = None
        try:
            for i, step in enumerate(steps, 1):
                if step["method"] is None:
                    say(describe_step(i, step))
                    continue
                body = step["body"]
                if body is not None and body.get("scopeConfigId") == NEW_ID:
                    body = dict(body, scopeConfigId=cfg_id)
                say(describe_step(i, dict(step, body=body)))
                status, resp = api.request(step["method"], step["path"], body)
                resp = resp if isinstance(resp, dict) else {}
                if step.get("creates"):
                    cfg_id = resp.get("id")
                    if not isinstance(cfg_id, int) or cfg_id <= 0:
                        raise Stop("the Scope Config was created but DevLake did not return its id; nothing further was done", 3)
                    say("     -> HTTP %s, Scope Config id=%s" % (status, cfg_id))
                elif step.get("recheck"):
                    changed = [t for ok, t in sync_policy_checks(resp) if not ok]
                    if changed:
                        raise Stop("Sync Policy changed before the trigger: %s. The import was not started." % "; ".join(changed), 1)
                    say("     -> HTTP %s, Sync Policy still as expected" % status)
                elif step.get("trigger"):
                    pipeline_id = resp.get("id")
                    say("     -> HTTP %s, pipeline id=%s status=%s" % (status, pipeline_id, resp.get("status")))
                else:
                    say("     -> HTTP %s" % status)
        except Stop as e:
            log("apply stopped: %s" % safe_text(str(e), 300))
            raise
        log("apply done: pipeline=%s" % pipeline_id)
    say("apply: done. Watch it with: python tools/devlake_configure.py status --pipeline %s" % pipeline_id)
    return 0


def cmd_status(args):
    api = Api(args.base_url, read_only=True)
    p = api.get("/pipelines/%d" % args.pipeline) or {}
    tasks = (api.get("/pipelines/%d/tasks" % args.pipeline) or {}).get("tasks") or []
    subtasks = (api.get("/pipelines/%d/subtasks" % args.pipeline) or {}).get("subtasks") or []
    detail = {s.get("id"): s.get("subtaskDetails") or [] for s in subtasks}
    say("pipeline #%s  %s  tasks finished %s/%s" % (p.get("id"), p.get("status"), p.get("finishedTasks"), p.get("totalTasks")))
    say("  began %s  finished %s  spent %s" % (fmt_time(p.get("beganAt")), fmt_time(p.get("finishedAt")), fmt_dur(p.get("spentSeconds") or 0)))
    err = short_error(p.get("message"))
    if err:
        say("  error: " + err)
    for t in sorted(tasks, key=lambda t: (t.get("pipelineRow", 0), t.get("pipelineCol", 0))):
        opts = t.get("options") or {}
        repo = opts.get("fullName") if isinstance(opts.get("fullName"), str) else "-"
        say("  task %s  %-14s %-28s %-15s %3d%%  began %s  finished %s  spent %s" % (
            t.get("id"), t.get("plugin"), repo, t.get("status"), round(100 * (t.get("progress") or 0)),
            fmt_time(t.get("beganAt")), fmt_time(t.get("finishedAt")), fmt_dur(t.get("spentSeconds") or 0)))
        d = detail.get(t.get("id"), [])
        started = [x for x in d if x.get("beganAt")]
        running = [x for x in started if not x.get("finishedAt") and not x.get("isFailed")]
        pd = t.get("progressDetail") or {}
        if running or pd.get("subTaskName"):
            name = pd.get("subTaskName") or running[0].get("name")
            say("      current subtask: %s (%s/%s)  records %s of %s" % (
                name, pd.get("subTaskNumber", "?"), pd.get("totalSubTasks", "?"),
                pd.get("finishedRecords", running[0].get("finishedRecords") if running else "?"), pd.get("totalRecords", "?")))
        if started:
            ok = [x for x in started if x.get("finishedAt") and not x.get("isFailed")]
            say("      subtasks started %d, finished %d, failed or stopped %d, records written by finished ones %s" % (
                len(started), len(ok), len([x for x in started if x.get("isFailed")]),
                sum(x.get("finishedRecords") or 0 for x in ok)))
        if t.get("failedSubTask"):
            say("      failed subtask: %s" % t.get("failedSubTask"))
        err = short_error(t.get("message"))
        if err:
            say("      error: " + err)
    return 0


# ---------------------------------------------------------------- command line
def build_parser():
    ap = argparse.ArgumentParser(description="Set up and start the DevLake import of the U4 check (see docs/devlake_configure.md).")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="only http://127.0.0.1[:port] is accepted")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, helptext in (("plan", "change nothing; show the checks, the calls of apply and an estimate"),
                           ("apply", "do what plan shows (needs --log)")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--connection-id", type=int, required=True, help="number of the GitHub connection (connections/github/<n> in the screen URL)")
        p.add_argument("--repos", nargs="+", required=True, metavar="OWNER/NAME")
        p.add_argument("--project", required=True)
        p.add_argument("--scope-config-name", default=SCOPE_CONFIG_NAME)
        if name == "plan":
            p.add_argument("--no-github", action="store_true", help="do not ask GitHub for the counts of the estimate")
            p.add_argument("--reference-pipeline", type=int, default=1, help="pipeline whose measured times are shown as reference (0 = none)")
        else:
            p.add_argument("--log", help="file that gets what apply did, appended")
    p = sub.add_parser("status", help="change nothing; show one pipeline once")
    p.add_argument("--pipeline", type=int, required=True)
    return ap


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        if args.command in ("plan", "apply"):
            seen = set()
            for repo in args.repos:
                if not REPO_RE.fullmatch(repo):
                    raise Stop("bad --repos value %r (expected OWNER/NAME)" % repo[:60], 2)
                if repo.lower() in seen:
                    raise Stop("--repos lists %s twice" % repo, 2)
                seen.add(repo.lower())
            if args.connection_id < 1:
                raise Stop("--connection-id must be 1 or more", 2)
        return {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status}[args.command](args)
    except Stop as e:
        print("STOP: %s" % e, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
