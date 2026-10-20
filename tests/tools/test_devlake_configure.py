#!/usr/bin/env python3
"""Test of tools/devlake_configure.py (U4 addendum) against a fake DevLake.

The fake is Python's http.server on 127.0.0.1 at a free port; nothing else is contacted (GitHub is not asked either:
`gh` is replaced inside the test). The fake writes down every request it gets. The expected values below are written
by hand from the specification of the script (which calls, in which order, with which body); the output of the
script is never used to compute an expectation.

Usage:
  python tests/tools/test_devlake_configure.py             run every scene (S1 .. S13)
  python tests/tools/test_devlake_configure.py --mutants   change the script in 9 places, one at a time, and show which scene fails
Exit code 0 = all passed (--mutants: every mutant was caught); 1 = something failed; 2 = environment problem.
"""
import argparse
import contextlib
import http.server
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "tools" / "devlake_configure.py"

REPO_A, REPO_B = "example-org/repo-a", "example-org/repo-b"
GID_A, GID_B = 111, 222
CFG = "/plugins/github/connections/1/scope-configs"
TRIGGER = ("POST", "/blueprints/1/trigger", {"skipCollectors": False, "fullSync": True})
ENT = ["CODE", "CODEREVIEW", "CROSS"]
SECRETS = ("SECRET-A", "SECRET-B", "SECRET-PW", "SECRET-URLTOKEN", "SECRET-OPT")


# ------------------------------------------------------------------ the fake DevLake
def default_state():
    bp = {"id": 1, "name": "bp", "projectName": "p1", "mode": "NORMAL", "enable": True, "isManual": True,
          "cronConfig": "0 0 * * *", "timeAfter": "2026-05-31T15:00:00Z", "skipOnFail": False,
          "connections": [{"pluginName": "github", "connectionId": 1,
                           "scopes": [{"scopeId": str(GID_A)}, {"scopeId": str(GID_B)}]}]}
    return {
        "scopes": [{"githubId": GID_A, "fullName": REPO_A, "connectionId": 1},
                   {"githubId": GID_B, "fullName": REPO_B, "connectionId": 1}],
        "scope_configs": [], "blueprint": bp, "extra_blueprints": [],
        "pipelines": [{"id": 1, "status": "TASK_FAILED"}],
        "next_cfg_id": 3, "leak": False, "fail_cfg_post": False, "fail_patch": False, "scopes_status": 200,
        "change_time_after_on_patch": False,
        "tasks": [
            {"id": 2, "plugin": "github_graphql", "status": "TASK_RUNNING", "progress": 0.5, "beganAt": "2026-01-01T10:00:00Z",
             "finishedAt": None, "spentSeconds": 600, "failedSubTask": "", "message": "", "pipelineRow": 1, "pipelineCol": 1,
             "subtasks": ["a", "b", "c"], "options": {"fullName": REPO_A, "githubId": GID_A},
             "progressDetail": {"subTaskName": "Extract Pull Requests", "subTaskNumber": 6, "totalSubTasks": 18,
                                "finishedRecords": 40, "totalRecords": 100}},
            {"id": 3, "plugin": "gitextractor", "status": "TASK_COMPLETED", "progress": 1, "beganAt": "2026-01-01T10:00:00Z",
             "finishedAt": "2026-01-01T10:00:30Z", "spentSeconds": 30, "failedSubTask": "", "message": "", "pipelineRow": 1,
             "pipelineCol": 2, "subtasks": [],
             "options": {"fullName": REPO_A, "url": "https://git:SECRET-URLTOKEN@example.invalid/x.git", "token": "SECRET-OPT"}},
        ],
        "subtasks": [{"id": 2, "subtaskDetails": [
            {"name": "Collect Milestones", "beganAt": "2026-01-01T10:00:00Z", "finishedAt": "2026-01-01T10:00:05Z", "finishedRecords": 1, "isFailed": False},
            {"name": "Collect Pull Requests", "beganAt": "2026-01-01T10:00:10Z", "finishedAt": "2026-01-01T10:03:20Z", "finishedRecords": 78, "isFailed": False},
            {"name": "Extract Pull Requests", "beganAt": "2026-01-01T10:03:20Z", "finishedAt": None, "finishedRecords": 40, "isFailed": False}]}],
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        st = self.server.state
        parts = urllib.parse.urlsplit(self.path)
        path, method = parts.path, self.command
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8")) if n else None
        self.server.requests.append((method, path, body))
        leak = {"authToken": "SECRET-A"} if st["leak"] else {}
        if method == "GET":
            if path == "/version":
                return self.reply(200, {"version": "v1.0.3-beta18@test"})
            if path == "/plugins/github/connections/1/scopes":
                if st["scopes_status"] != 200:
                    return self.reply(st["scopes_status"], {"message": "connection not found"})
                return self.reply(200, {"count": len(st["scopes"]), "scopes": [{"scope": s} for s in st["scopes"]]})
            if path == CFG:
                return self.reply(200, st["scope_configs"])
            if path == "/projects/p1":
                return self.reply(200, {"name": "p1", "blueprint": st["blueprint"]})
            if path == "/blueprints":
                bps = [st["blueprint"]] + st["extra_blueprints"]
                return self.reply(200, {"count": len(bps), "blueprints": bps})
            if path == "/blueprints/1":
                return self.reply(200, dict(st["blueprint"], **leak))
            if path == "/blueprints/1/pipelines":
                return self.reply(200, {"count": len(st["pipelines"]), "pipelines": st["pipelines"]})
            if path == "/pipelines/1":
                return self.reply(200, {"id": 1, "status": "TASK_RUNNING", "finishedTasks": 1, "totalTasks": 4,
                                        "beganAt": "2026-01-01T10:00:00Z", "finishedAt": None, "spentSeconds": 600,
                                        "message": "Wraps: (1) attached stack trace\nWraps: (2) subtask X ended unexpectedly\nWraps: (3) context canceled"})
            if path == "/pipelines/1/tasks":
                return self.reply(200, {"count": len(st["tasks"]), "tasks": st["tasks"]})
            if path == "/pipelines/1/subtasks":
                return self.reply(200, {"count": 1, "subtasks": st["subtasks"]})
            return self.reply(404, {"message": "no route"})
        if method == "POST" and path == CFG:
            if st["fail_cfg_post"]:
                return self.reply(400, {"message": "bad scope config", "password": "SECRET-PW"})
            cfg = dict(body, id=st["next_cfg_id"], connectionId=1)
            st["next_cfg_id"] += 1
            st["scope_configs"].append(cfg)
            return self.reply(201, dict(cfg, **leak))
        m = re.fullmatch(r"/plugins/github/connections/1/scopes/(\d+)", path)
        if method == "PATCH" and m:
            if st["fail_patch"]:
                return self.reply(500, {"message": "boom"})
            for s in st["scopes"]:
                if str(s["githubId"]) == m.group(1):
                    s["scopeConfigId"] = body["scopeConfigId"]
                    if st["change_time_after_on_patch"]:
                        st["blueprint"]["timeAfter"] = "2026-06-02T00:00:00Z"
                    return self.reply(200, dict(s, **leak))
            return self.reply(404, {"message": "no scope"})
        if method == "POST" and path == "/blueprints/1/trigger":
            return self.reply(200, {"id": 7, "status": "TASK_CREATED", "token": "SECRET-B", "nested": {"secretKey": "SECRET-B"}})
        return self.reply(405, {"message": "not allowed"})

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = handle_any


class Fake:
    def __init__(self, **overrides):
        self.state = default_state()
        self.state.update(overrides)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.state = self.state
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.port = self.server.server_address[1]

    @property
    def requests(self):
        return self.server.requests

    @property
    def writes(self):
        return [r for r in self.requests if r[0] != "GET"]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# ------------------------------------------------------------------ harness
class Results:
    def __init__(self):
        self.rows = []
        self.scene = "?"

    def check(self, desc, cond, detail=""):
        self.rows.append((self.scene, desc, bool(cond), str(detail)))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cli(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


def args_for(cmd, fake, extra=()):
    base = ["--base-url", fake.url, cmd, "--connection-id", "1", "--repos", REPO_A, REPO_B, "--project", "p1"]
    return base + list(extra)


def no_connection_read(fake):
    """Nothing but the scope list and the scope configs of a connection may be asked (never the connection)."""
    bad = [p for _m, p, _b in fake.requests if p.startswith("/plugins/github/connections")
           and not re.fullmatch(r"/plugins/github/connections/\d+/(scopes|scope-configs|scopes/\d+)", p)]
    return not bad, bad


SCENES = []


def scene(sid):
    def deco(fn):
        SCENES.append((sid, fn))
        return fn
    return deco


@scene("S1")
def s1_plan_sends_no_write(mod, R):
    fake = Fake()
    try:
        code, out, err = cli(mod, args_for("plan", fake, ["--no-github"]))
        R.check("S1 plan exits 0 when all checks pass", code == 0, (code, err))
        R.check("S1 plan sends only GET", fake.requests and all(m == "GET" for m, _p, _b in fake.requests), [r[:2] for r in fake.requests if r[0] != "GET"])
        R.check("S1 plan read the scope list, the scope configs, the project and the blueprints",
                {("GET", "/plugins/github/connections/1/scopes"), ("GET", CFG), ("GET", "/projects/p1"), ("GET", "/blueprints"),
                 ("GET", "/blueprints/1/pipelines")} <= {r[:2] for r in fake.requests}, [r[:2] for r in fake.requests])
        R.check("S1 plan shows the five calls of apply", all(t in out for t in (
            "POST " + CFG, "PATCH /plugins/github/connections/1/scopes/111", "PATCH /plugins/github/connections/1/scopes/222",
            "GET /blueprints/1", "POST /blueprints/1/trigger")), out[-1500:])
        R.check("S1 never asks for the connection itself", no_connection_read(fake)[0], no_connection_read(fake)[1])
        code, out, err = cli(mod, ["--base-url", fake.url, "status", "--pipeline", "1"])
        R.check("S1 status sends only GET", code == 0 and all(m == "GET" for m, _p, _b in fake.requests), (code, err))
        api = mod.Api(fake.url, read_only=True)
        try:
            api.request("POST", "/x", {})
            blocked = False
        except mod.Stop as e:
            blocked = e.code == 2
        R.check("S1 a read-only Api refuses POST before sending", blocked and not any(m == "POST" for m, _p, _b in fake.requests))
    finally:
        fake.close()


@scene("S2")
def s2_apply_sequence(mod, R):
    fake = Fake()
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.txt"
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(log)]))
            R.check("S2 apply exits 0", code == 0, (code, err, out[-500:]))
            want = [("POST", CFG, {"name": "u4-code-review-only", "entities": ENT}),
                    ("PATCH", "/plugins/github/connections/1/scopes/111", {"scopeConfigId": 3}),
                    ("PATCH", "/plugins/github/connections/1/scopes/222", {"scopeConfigId": 3}),
                    TRIGGER]
            R.check("S2 the writes are, in this order: create, attach, attach, trigger (bodies as specified)", fake.writes == want, fake.writes)
            reqs = [r[:2] for r in fake.requests]
            first_write = next(i for i, r in enumerate(fake.requests) if r[0] != "GET")
            R.check("S2 every check (GET) comes before the first write",
                    {("GET", "/projects/p1"), ("GET", "/blueprints"), ("GET", "/blueprints/1/pipelines"), ("GET", CFG)} <= set(reqs[:first_write]), reqs[:first_write])
            R.check("S2 the Sync Policy is read again after the last attach and before the trigger",
                    reqs[-3:] == [("PATCH", "/plugins/github/connections/1/scopes/222"), ("GET", "/blueprints/1"), ("POST", "/blueprints/1/trigger")], reqs[-3:])
            R.check("S2 apply prints the pipeline id", "pipeline id=7" in out and "status --pipeline 7" in out, out[-400:])
            R.check("S2 the log has the trigger line", "POST /blueprints/1/trigger status=200" in log.read_text(encoding="utf-8"))
            R.check("S2 never asks for the connection itself", no_connection_read(fake)[0], no_connection_read(fake)[1])
        finally:
            fake.close()


def stops_without_change(mod, R, desc, expect_code=1, **overrides):
    fake = Fake(**overrides)
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.txt"
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(log)]))
            R.check("S3 " + desc + ": exit code %d" % expect_code, code == expect_code, (code, err, out[-300:]))
            R.check("S3 " + desc + ": nothing written", fake.writes == [], fake.writes)
            R.check("S3 " + desc + ": says nothing was changed", "Nothing was changed" in out or "STOP" in err, (out[-200:], err))
        finally:
            fake.close()


@scene("S3")
def s3_apply_stops_when_a_check_fails(mod, R):
    bp = default_state()["blueprint"]
    stops_without_change(mod, R, "Data Time Range differs", blueprint=dict(bp, timeAfter="2026-06-01T00:00:00Z"))
    stops_without_change(mod, R, "frequency is not Manual", blueprint=dict(bp, isManual=False))
    stops_without_change(mod, R, "blueprint disabled", blueprint=dict(bp, enable=False))
    stops_without_change(mod, R, "two blueprints in the project", extra_blueprints=[dict(bp, id=2, name="second")])
    stops_without_change(mod, R, "a scope is missing", scopes=default_state()["scopes"][:1])
    stops_without_change(mod, R, "a pipeline is running", pipelines=[{"id": 1, "status": "TASK_RUNNING"}])
    stops_without_change(mod, R, "the blueprint does not collect a scope",
                         blueprint=dict(bp, connections=[{"pluginName": "github", "connectionId": 1, "scopes": [{"scopeId": str(GID_A)}]}]))
    stops_without_change(mod, R, "same-name Scope Config with other entities",
                         scope_configs=[{"id": 5, "name": "u4-code-review-only", "entities": ["CODE", "CICD"], "connectionId": 1}])
    stops_without_change(mod, R, "the connection does not answer the scope list", expect_code=3, scopes_status=404)
    # The Sync Policy is read again right before the trigger: if it changed meanwhile, the trigger is not sent.
    fake = Fake(change_time_after_on_patch=True)
    with tempfile.TemporaryDirectory() as d:
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(Path(d) / "log.txt")]))
            R.check("S3 Sync Policy changed after the attach: exit 1", code == 1, (code, err))
            R.check("S3 Sync Policy changed after the attach: the trigger is not sent", TRIGGER not in fake.writes and len(fake.writes) == 3, fake.writes)
        finally:
            fake.close()
    # A failing attach stops the run: the trigger is not sent.
    fake = Fake(fail_patch=True)
    with tempfile.TemporaryDirectory() as d:
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(Path(d) / "log.txt")]))
            R.check("S3 a failing attach: exit 3 and no trigger", code == 3 and TRIGGER not in fake.writes, (code, fake.writes))
        finally:
            fake.close()


@scene("S4")
def s4_only_127_0_0_1(mod, R):
    refused = ["http://localhost:8080", "http://127.0.0.2:8080", "http://[::1]:8080", "https://127.0.0.1:8080",
               "http://127.0.0.1@evil.example/", "http://user:pw@127.0.0.1:8080", "http://127.0.0.1:8080/api", "http://0.0.0.0:8080",
               "http://127.0.0.1.evil.example:8080", "ftp://127.0.0.1", "http://127.0.0.1:99999", "http://127.0.0.1:8080/?x=1", "", "127.0.0.1:8080"]
    for url in refused:
        try:
            mod.check_base_url(url)
            ok = False
        except mod.Stop as e:
            ok = e.code == 2
        R.check("S4 check_base_url refuses %r" % url, ok)
    for url, want in (("http://127.0.0.1:8080", "http://127.0.0.1:8080"), ("http://127.0.0.1", "http://127.0.0.1"), ("http://127.0.0.1:8080/", "http://127.0.0.1:8080")):
        try:
            got = mod.check_base_url(url)
        except mod.Stop as e:
            got = "refused: %s" % e
        R.check("S4 check_base_url accepts %r" % url, got == want, got)
    # Through the command line, to a name that does point at the fake server: nothing must reach it.
    fake = Fake()
    try:
        for url in ("http://localhost:%d" % fake.port, "http://user:pw@127.0.0.1:%d" % fake.port, "https://127.0.0.1:%d" % fake.port):
            code, out, err = cli(mod, ["--base-url", url, "plan", "--connection-id", "1", "--repos", REPO_A, "--project", "p1", "--no-github"])
            R.check("S4 plan to %s is refused (exit 2)" % url.split(":")[0] + "://...", code == 2, (code, err))
            code, out, err = cli(mod, ["--base-url", url, "status", "--pipeline", "1"])
            R.check("S4 status to %s is refused (exit 2)" % url.split(":")[0] + "://...", code == 2, (code, err))
        R.check("S4 the fake DevLake received no request at all", fake.requests == [], fake.requests)
    finally:
        fake.close()


@scene("S5")
def s5_secrets_are_not_shown(mod, R):
    data = {"a": {"authToken": "X1", "list": [{"Password": "X2"}, {"ok": "fine"}]}, "url": "https://user:X3@example.invalid/p.git", "secretKey": "X4"}
    red = json.dumps(mod.redact(data))
    R.check("S5 redact hides the values of token/password/secret keys", not any(v in red for v in ("X1", "X2", "X4")), red)
    R.check("S5 redact hides the user info of a URL and keeps the rest", "X3" not in red and "https://***@example.invalid/p.git" in red and "fine" in red, red)
    text = mod.safe_text('plain text "token": "X5" see https://u:X6@h.invalid/x')
    R.check("S5 safe_text hides secrets in text that is not json", "X5" not in text and "X6" not in text, text)
    fake = Fake(leak=True)
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.txt"
        try:
            outs = []
            outs.append(cli(mod, args_for("plan", fake, ["--no-github"])))
            outs.append(cli(mod, ["--base-url", fake.url, "status", "--pipeline", "1"]))
            outs.append(cli(mod, args_for("apply", fake, ["--log", str(log)])))
        finally:
            fake.close()
        shown = "\n".join(o[1] + o[2] for o in outs)
        logged = log.read_text(encoding="utf-8")
        R.check("S5 responses with token keys: the commands succeeded", [o[0] for o in outs] == [0, 0, 0], [o[0] for o in outs])
        R.check("S5 no secret value in what plan/status/apply print", not any(s in shown for s in SECRETS), [s for s in SECRETS if s in shown])
        R.check("S5 no secret value in the log", not any(s in logged for s in SECRETS), [s for s in SECRETS if s in logged])
        R.check("S5 the log shows the response bodies with the values replaced", '"token": "***"' in logged and '"authToken": "***"' in logged, logged[-600:])
    fake = Fake(fail_cfg_post=True)
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.txt"
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(log)]))
        finally:
            fake.close()
        logged = log.read_text(encoding="utf-8")
        R.check("S5 an error answer: exit 3, status shown", code == 3 and "400" in err, (code, err))
        R.check("S5 an error answer with a password key: not printed, not logged", "SECRET-PW" not in out + err + logged, (err, logged[-300:]))


@scene("S6")
def s6_same_name_scope_config_is_reused(mod, R):
    existing = {"id": 5, "name": "u4-code-review-only", "entities": ["CROSS", "CODE", "CODEREVIEW"], "connectionId": 1}
    fake = Fake(scope_configs=[dict(existing)])
    with tempfile.TemporaryDirectory() as d:
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(Path(d) / "log.txt")]))
            want = [("PATCH", "/plugins/github/connections/1/scopes/111", {"scopeConfigId": 5}),
                    ("PATCH", "/plugins/github/connections/1/scopes/222", {"scopeConfigId": 5}), TRIGGER]
            R.check("S6 same name: no POST of a Scope Config, the existing id 5 is attached", code == 0 and fake.writes == want, (code, fake.writes))
        finally:
            fake.close()
    both = [dict(s, scopeConfigId=5) for s in default_state()["scopes"]]
    fake = Fake(scope_configs=[dict(existing)], scopes=both)
    with tempfile.TemporaryDirectory() as d:
        try:
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(Path(d) / "log.txt")]))
            R.check("S6 already attached: only the trigger is sent", code == 0 and fake.writes == [TRIGGER], (code, fake.writes))
        finally:
            fake.close()
    fake = Fake(scope_configs=[dict(existing)])
    try:
        code, out, err = cli(mod, args_for("plan", fake, ["--no-github"]))
        R.check("S6 plan says the Scope Config is reused", "reuse it, create nothing" in out and "POST " + CFG not in out, out[-1200:])
    finally:
        fake.close()


@scene("S7")
def s7_status(mod, R):
    fake = Fake()
    try:
        code, out, err = cli(mod, ["--base-url", fake.url, "status", "--pipeline", "1"])
        R.check("S7 status exits 0 and sends only GET", code == 0 and all(m == "GET" for m, _p, _b in fake.requests), (code, err))
        R.check("S7 pipeline line", "pipeline #1  TASK_RUNNING  tasks finished 1/4" in out, out)
        R.check("S7 the error is the last two causes, not the stack trace", "error: subtask X ended unexpectedly / context canceled" in out, out)
        R.check("S7 task line has plugin, repo, status and progress", re.search(r"task 2\s+github_graphql\s+example-org/repo-a\s+TASK_RUNNING\s+50%", out), out)
        R.check("S7 current subtask and its records", "current subtask: Extract Pull Requests (6/18)  records 40 of 100" in out, out)
        R.check("S7 subtask counts and records of finished ones", "subtasks started 3, finished 2, failed or stopped 0, records written by finished ones 79" in out, out)
        R.check("S7 no option of the tasks is printed", "example.invalid" not in out and "SECRET" not in out, out)
    finally:
        fake.close()


@scene("S8")
def s8_estimate(mod, R):
    calls = []
    answers = {"search/issues?q=repo:%s+is:pr&per_page=1" % REPO_A: 1234, "search/issues?q=repo:%s+is:issue&per_page=1" % REPO_A: 56,
               "repos/%s/actions/runs?per_page=1" % REPO_A: 78901, "search/issues?q=repo:%s+is:pr&per_page=1" % REPO_B: 7,
               "search/issues?q=repo:%s+is:issue&per_page=1" % REPO_B: 8}  # the workflow-run count of repo-b is missing: gh failed

    def fake_gh(path):
        calls.append(path)
        return answers.get(path)
    old, mod.run_gh = mod.run_gh, fake_gh
    fake = Fake()
    try:
        code, out, err = cli(mod, args_for("plan", fake))
    finally:
        mod.run_gh = old
        fake.close()
    R.check("S8 gh is called six times, read-only paths only, in this order", calls == [
        "search/issues?q=repo:%s+is:pr&per_page=1" % REPO_A, "search/issues?q=repo:%s+is:issue&per_page=1" % REPO_A, "repos/%s/actions/runs?per_page=1" % REPO_A,
        "search/issues?q=repo:%s+is:pr&per_page=1" % REPO_B, "search/issues?q=repo:%s+is:issue&per_page=1" % REPO_B, "repos/%s/actions/runs?per_page=1" % REPO_B], calls)
    a = re.search(r"example-org/repo-a\s+1,234\s+56\s+78,901\s+1,234", out)
    b = re.search(r"example-org/repo-b\s+7\s+8\s+not fetched\s+7", out)
    R.check("S8 the table has the four counts (authors = PRs) and 'not fetched' where gh failed", a and b, out[out.find("[4]"):][:900])
    R.check("S8 plan says it is an estimate, not a measurement", "estimate, not a measurement" in out, out)
    R.check("S8 the reference from pipeline #1 is shown with the finished staying subtask",
            "stays: Collect Pull Requests" in out and "10:00:10 UTC - 10:03:20 UTC  (3m10s, records 78)" in out
            and "1 of 18 staying subtasks had finished in #1, 3m10s together" in out and "took 5s together" in out, out[out.find("Reference"):][:1500])
    # --no-github: gh is not called at all
    calls.clear()
    mod.run_gh = fake_gh
    fake = Fake()
    try:
        code, out, err = cli(mod, args_for("plan", fake, ["--no-github"]))
    finally:
        mod.run_gh = old
        fake.close()
    R.check("S8 --no-github: gh is not called and the counts say 'not fetched'", calls == [] and out.count("not fetched") >= 8, (calls, out.count("not fetched")))
    # run_gh itself: the command line, and the failures
    seen = []

    def fake_run(argv, **kw):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, fake_run.rc, stdout=fake_run.out, stderr="")
    old_run, old_which = mod.subprocess.run, mod.shutil.which
    mod.subprocess.run, mod.shutil.which = fake_run, lambda name: "/fake/gh"
    try:
        fake_run.rc, fake_run.out = 0, "42\n"
        r1 = mod.run_gh("repos/o/r/actions/runs?per_page=1")
        fake_run.rc, fake_run.out = 1, ""
        r2 = mod.run_gh("repos/o/r/actions/runs?per_page=1")
        fake_run.rc, fake_run.out = 0, "not a number"
        r3 = mod.run_gh("repos/o/r/actions/runs?per_page=1")
        mod.shutil.which = lambda name: None
        r4 = mod.run_gh("repos/o/r/actions/runs?per_page=1")
    finally:
        mod.subprocess.run, mod.shutil.which = old_run, old_which
    R.check("S8 run_gh runs exactly `gh api <path> --jq .total_count` (a GET) and returns the number",
            r1 == 42 and seen[0] == ["/fake/gh", "api", "repos/o/r/actions/runs?per_page=1", "--jq", ".total_count"], seen)
    R.check("S8 run_gh gives None when gh fails, prints a non-number, or is missing", r2 is None and r3 is None and r4 is None, (r2, r3, r4))


@scene("S9")
def s9_apply_needs_a_log_and_appends(mod, R):
    fake = Fake()
    try:
        code, out, err = cli(mod, args_for("apply", fake))
        R.check("S9 apply without --log: exit 2 and no request", code == 2 and fake.requests == [], (code, fake.requests))
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.txt"
            log.write_text("OLD LINE\n", encoding="utf-8")
            code, out, err = cli(mod, args_for("apply", fake, ["--log", str(log)]))
            text = log.read_text(encoding="utf-8")
            R.check("S9 the log is appended to, not overwritten", code == 0 and text.startswith("OLD LINE\n") and "apply start:" in text and "apply done: pipeline=7" in text, text[:300])
            R.check("S9 the log has one line per request with status", "POST %s status=201" % CFG in text and "PATCH /plugins/github/connections/1/scopes/111 status=200" in text, text)
    finally:
        fake.close()


@scene("S10")
def s10_subtask_table(mod, R):
    kept, dropped = mod.split_subtasks(mod.ENTITIES)
    want_kept = ["Collect Pull Requests", "Extract Pull Requests", "Collect Comments", "Extract Comments", "Collect PR Review Comments",
                 "Extract PR Review Comments", "Collect Users", "Extract Users", "Enrich PR Issues", "Convert Repos", "Convert PR Commits",
                 "Convert Pull Requests", "Convert PR Reviews", "Convert PR Labels", "Convert PR Issues", "Convert PR Comments",
                 "Convert Reviews", "Convert Users"]
    R.check("S10 entities are CODE, CODEREVIEW, CROSS", mod.ENTITIES == ENT, mod.ENTITIES)
    R.check("S10 the 18 subtasks that stay (written from the SubTaskMeta of each, not from the script)", kept == want_kept, kept)
    names = [r[0] for r in mod.SUBTASKS]
    R.check("S10 every subtask is either kept or dropped, once", len(names) == 42 == len(set(names)) and sorted(kept + [d[0] for d in dropped]) == sorted(names), len(names))
    gone = {d[0] for d in dropped}
    R.check("S10 the CI and ticket subtasks are dropped", {"Collect Workflow Runs", "Extract Workflow Runs", "Collect Job Runs", "Extract Jobs", "Convert Workflow Runs",
                                                            "Convert Jobs", "Collect Issues", "Collect Events", "Collect Deployments", "Collect Releases"} <= gone, sorted(gone))
    R.check("S10 Convert Commits is off by default, so it is dropped even though it is for CODE", "Convert Commits" in gone)
    every = [n for n, en, dom, _s in mod.SUBTASKS if en and set(dom) & set(mod.ALL_DOMAIN_TYPES)]
    R.check("S10 with every entity 41 subtasks run: the number DevLake planned for pipeline #1 of the first import", len(every) == 41, len(every))


def run_suite(path, name):
    mod = load(path, name)
    R = Results()
    for sid, fn in SCENES:
        R.scene = sid
        try:
            fn(mod, R)
        except Exception as e:  # a crash is a failure of the scene
            R.check("%s crashed: %s: %s" % (sid, type(e).__name__, e), False)
    return R.rows


# ------------------------------------------------------------------ mutants
MUTANTS = [
    ("plan sends a POST", "S1", '    api = Api(args.base_url, read_only=True)  # PLAN-READ-ONLY\n',
     '    api = Api(args.base_url, read_only=False)\n    api.request("POST", "/plugins/%s/connections/%d/scope-configs" % (PLUGIN, args.connection_id), {"name": "x"})\n'),
    ("the read-only guard of Api removed", "S1", '        if self.read_only and method != "GET":', '        if False:'),
    ("address check removed", "S4", '    host_ok = parts.hostname == ALLOWED_HOST\n', '    host_ok = True\n'),
    ("redaction removed", "S5", '("***" if SENSITIVE_KEY.search(str(k)) else redact(v))', 'redact(v)'),
    ("Data Time Range check removed", "S3", 'got is not None and got == want', 'True'),
    ("Sync Policy check before the trigger removed", "S3", '                    if changed:\n', '                    if False:\n'),
    ("running-pipeline check removed", "S3", '    checks.append((not running,', '    checks.append((True or not running,'),
    ("same-name Scope Config not reused", "S6", '    if same:\n        cfg_id = same[0].get("id")', '    if False:\n        cfg_id = None'),
    ("trigger without fullSync", "S2", 'TRIGGER_BODY = {"skipCollectors": False, "fullSync": True}', 'TRIGGER_BODY = {"skipCollectors": False, "fullSync": False}'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    try:
        if not a.mutants:
            rows = run_suite(SCRIPT, "devlake_configure_under_test")
            bad = [r for r in rows if not r[2]]
            if a.verbose:
                for r in rows:
                    print("%s %s %s" % ("ok  " if r[2] else "FAIL", r[0], r[1]))
            for r in bad:
                print("FAIL %s %s | %s" % (r[0], r[1], r[3][:600]))
            print("%d checks, %d failures" % (len(rows), len(bad)))   # the last line of the output
            return 1 if bad else 0
        src = SCRIPT.read_text(encoding="utf-8")
        caught = 0
        with tempfile.TemporaryDirectory() as mdir:
            for i, (desc, expected, old, new) in enumerate(MUTANTS, 1):
                if src.count(old) != 1:
                    print("ERROR: mutant %d: the text to change is found %d times (must be 1): %r" % (i, src.count(old), old))
                    return 2
                path = Path(mdir) / ("mutant_%d.py" % i)
                path.write_text(src.replace(old, new), encoding="utf-8")
                rows = run_suite(path, "devlake_configure_mutant_%d" % i)
                failed = sorted({r[0] for r in rows if not r[2]})
                if a.verbose:
                    for r in rows:
                        if not r[2]:
                            print("    FAIL %s %s | %s" % (r[0], r[1][:90], r[3][:200]))
                ok = expected in failed
                caught += ok
                print("mutant %d: %-46s expected to fail %-3s -> failed scenes: %s -> %s"
                      % (i, desc, expected, ", ".join(failed) or "(none)", "CAUGHT" if ok else "NOT CAUGHT"))
        print("%d mutants, %d caught" % (len(MUTANTS), caught))   # the last line of the output
        return 0 if caught == len(MUTANTS) else 1
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
