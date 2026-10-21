#!/usr/bin/env python3
"""Test of tools/grafana_install.py against a fake docker (the function `docker` of the module is replaced; no container is touched): the override
file, the checks of plan and apply, the commands that apply runs, and the checks of status (mounts, sha256, log lines).
The expected values are written by hand.

Usage: python tests/tools/test_grafana_install.py     (the last line is "N checks, M failures"; exit code 0 = no failure)
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("grafana_install", ROOT / "tools" / "grafana_install.py")
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

rows, bad = [], []


def check(name, got, want=True):
    rows.append(name)
    if got != want:
        bad.append("%s: got %r, want %r" % (name, got, want))


COMPOSE = "services:\n  mysql:\n    image: mysql:8\n  grafana:\n    image: x\n    volumes:\n      - grafana-storage:/var/lib/grafana\nvolumes:\n  grafana-storage:\n"
JSON_SHA = hashlib.sha256((ROOT / "dashboards" / "json" / "ai-impact.json").read_bytes()).hexdigest()


class Fake:
    """Records every docker call and answers from a script."""

    def __init__(self, mounts=None, sha=None, logs=None, up_rc=0, info_rc=0, ps="abc123\n", started="2026-10-21T06:00:00.5Z", up_err=None, readonly=False):
        self.calls = []
        self.mounts = mounts if mounts is not None else self.good_mounts(readonly)
        self.sha = sha if sha is not None else JSON_SHA
        self.logs = logs if logs is not None else ('logger=provisioning.dashboard type=file name=ai-impact t=2026 level=info msg="finished to provision dashboards"\n')
        self.up_rc, self.info_rc, self.ps, self.started, self.up_err = up_rc, info_rc, ps, started, up_err

    @staticmethod
    def good_mounts(readonly=False):
        return [{"Type": "volume", "Destination": "/var/lib/grafana", "RW": True},
                {"Type": "bind", "Source": "/host/p.yml", "Destination": G.PROVIDER_TARGET, "RW": False},
                {"Type": "bind", "Source": "/host/d", "Destination": G.DASHBOARD_TARGET, "RW": False}] + (
                [{"Type": "bind", "Source": "/host/ro.yml", "Destination": G.DATASOURCE_TARGET, "RW": False}] if readonly else [])

    def __call__(self, args, cwd=None, timeout=600):
        self.calls.append((list(args), cwd))
        if args[0] == "info":
            return self.info_rc, "29.8.0\n", ""
        if args[:2] == ["compose", "up"]:
            return self.up_rc, "", self.up_err if self.up_err is not None else "Container devlake-local-grafana-1  Started\n"
        if args[:3] == ["compose", "ps", "-q"]:
            return 0, self.ps, ""
        if args[0] == "inspect" and "{{json .Mounts}}" in args:
            return 0, json.dumps(self.mounts), ""
        if args[0] == "inspect" and "{{.State.StartedAt}}" in args:
            return 0, self.started + "\n", ""
        if args[:3] == ["compose", "exec", "-T"]:
            return 0, "%s  %s\n" % (self.sha, G.JSON_IN_CONTAINER), ""
        if args[0] == "logs":
            return 0, self.logs, ""
        return 1, "", "unexpected call"


def run(command, compose_dir, fake, repo_dir=None, extra=()):
    G.docker = fake
    out = io.StringIO()
    argv = [command, "--compose-dir", str(compose_dir)] + ([] if repo_dir is None else ["--repo-dir", str(repo_dir)]) + list(extra)
    with contextlib.redirect_stdout(out):
        rc = G.main(argv)
    return rc, out.getvalue()


def fresh_compose(tmp, name="compose"):
    d = Path(tmp) / name
    d.mkdir()
    (d / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    return d


# ---------------------------------------------------------------- the override text (W12: long syntax, read_only, create_host_path false)
text = G.override_text(ROOT)
repo = ROOT.resolve().as_posix()
want = "\n".join([
    "# Written by tools/grafana_install.py of devlake-agent-review-burden (docs/dashboard.md). Compose reads this file together with",
    "# docker-compose.yml. To take the dashboard away: delete this file and run `docker compose up -d --no-deps grafana` in this folder.",
    "services:", "  grafana:", "    volumes:",
    "      - type: bind", '        source: "%s/dashboards/provisioning/ai-impact.yml"' % repo,
    "        target: /etc/grafana/provisioning/dashboards/ai-impact.yml", "        read_only: true", "        bind:", "          create_host_path: false",
    "      - type: bind", '        source: "%s/dashboards/json"' % repo,
    "        target: /etc/grafana/ai-impact", "        read_only: true", "        bind:", "          create_host_path: false", ""])
check("the override file, line by line", text, want)
check("the targets are outside /etc/grafana/dashboards (DevLake's provider path)", "/etc/grafana/dashboards" in text.replace("/etc/grafana/provisioning/dashboards", ""), False)
check("both mounts are read-only and do not create the host path", (text.count("read_only: true"), text.count("create_host_path: false")), (2, 2))
check("no short syntax mount line (- source:target)", [l for l in text.splitlines() if l.strip().startswith("- ") and "type: bind" not in l], [])
provider = (ROOT / "dashboards" / "provisioning" / "ai-impact.yml").read_text(encoding="utf-8")
for line in ("apiVersion: 1", "- name: ai-impact", "type: file", "allowUiUpdates: false", "path: /etc/grafana/ai-impact", "foldersFromFilesStructure: false"):
    check("the provider file has: " + line, line in provider, True)
check("the provider path is not DevLake's path", "/etc/grafana/dashboards" in provider.replace("# ", "").split("path:")[1], False)

# ---------------------------------------------------------------- plan and apply
with tempfile.TemporaryDirectory() as tmp:
    c = fresh_compose(tmp)
    fake = Fake()
    rc, out = run("plan", c, fake)
    check("plan on a good folder: exit 0", rc, 0)
    check("plan prints the override text", all(l in out for l in want.rstrip("\n").split("\n")[2:]), True)
    check("plan says what recreating does (the start script TRIES to delete; 404 and 409 on this Grafana, so the existing data source is kept; only grafana; volumes stay)",
          ("TRIES to delete" in out, "answered 404 and the create answered 409" in out, "is kept" in out, "ALL data sources" in out, "is gone after that" in out,
           "Only the `grafana` container" in out, "volumes stay" in out, "docker compose up -d --no-deps --force-recreate grafana" in out), (True, True, True, False, False, True, True, True))
    check("plan [4] says that taking the override away does not put the data source back, and what Grafana's page on provisioning says (deleteDatasources, prune)",
          ("does NOT put the data source back" in out, "stays" in out, "deleteDatasources" in out, "prune: true" in out, "not covered by this script" in out, "go back to the data source of DevLake" in out),
          (True, True, True, True, True, False))
    check("plan changes nothing: no override file, no docker compose up", (not (c / G.OVERRIDE_NAME).exists(), [x for x in fake.calls if x[0][:2] == ["compose", "up"]]), (True, []))

    fake = Fake()
    rc, out = run("apply", c, fake)
    check("apply: exit 0", rc, 0)
    check("apply wrote the override file with the planned text", (c / G.OVERRIDE_NAME).read_bytes().decode("utf-8"), text)
    ups = [x for x in fake.calls if x[0][0] == "compose"]
    check("apply runs exactly: docker compose up -d --no-deps --force-recreate grafana, in the compose folder", ups,
          [(["compose", "up", "-d", "--no-deps", "--force-recreate", "grafana"], str(c))])
    check("apply never runs docker compose config or reads the environment of a container",
          [x for x in fake.calls if "config" in x[0] or ("inspect" in x[0] and "--format" not in x[0])], [])

    fake = Fake()
    rc, out = run("apply", c, fake)
    check("apply a second time: the same override is not an error, up is run again", (rc, len([x for x in fake.calls if x[0][:2] == ["compose", "up"]])), (0, 1))
    rc, out = run("plan", c, Fake())
    check("plan after apply: the existing identical override is fine", (rc, "is exactly what apply would write" in out), (0, True))

    (c / G.OVERRIDE_NAME).write_text("services:\n  grafana:\n    environment:\n      A: b\n", encoding="utf-8")
    fake = Fake()
    rc, out = run("apply", c, fake)
    check("apply: an existing override with other content is not overwritten, nothing is run", (rc, [x for x in fake.calls if x[0][0] == "compose"],
                                                                                            (c / G.OVERRIDE_NAME).read_text(encoding="utf-8")),
          (1, [], "services:\n  grafana:\n    environment:\n      A: b\n"))
    rc, out = run("plan", c, Fake())
    check("plan reports it", (rc, "other content" in out, "FAIL" in out), (1, True, True))

    d = fresh_compose(tmp, "c2")
    (d / "compose.override.yaml").write_text("services: {}\n", encoding="utf-8")
    rc, out = run("plan", d, Fake())
    check("plan: another override file in the folder is a FAIL", (rc, "compose.override.yaml" in out), (1, True))

    e = Path(tmp) / "c3"
    e.mkdir()
    rc, out = run("plan", e, Fake())
    check("plan: no compose file is a FAIL", (rc, "no docker-compose.yml" in out), (1, True))
    (e / "docker-compose.yml").write_text("services:\n  mysql:\n    image: x\n", encoding="utf-8")
    fake = Fake()
    rc, out = run("apply", e, fake)
    check("apply: no grafana service stops before anything is written or run", (rc, list(e.glob("*override*")), [x for x in fake.calls if x[0][0] == "compose"]), (1, [], []))

    f = fresh_compose(tmp, "c4")
    fake = Fake(info_rc=1)
    rc, out = run("apply", f, fake)
    check("apply: Docker not answering stops before anything is written", (rc, list(f.glob("*override*"))), (1, []))

    fake = Fake(up_rc=1)
    g = fresh_compose(tmp, "c5")
    rc, out = run("apply", g, fake)
    check("apply: a failing docker compose up is reported (exit 1), the override stays", (rc, (g / G.OVERRIDE_NAME).exists()), (1, True))

    # a stale json in the repo is a FAIL (the install would put an old screen in)
    repo2 = Path(tmp) / "repo2"
    shutil.copytree(ROOT / "dashboards", repo2 / "dashboards")
    shutil.copytree(ROOT / "sql", repo2 / "sql")
    shutil.copytree(ROOT / "tools", repo2 / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    (repo2 / "dashboards" / "json" / "ai-impact.json").write_text('{"uid": "old"}\n', encoding="utf-8")
    h = fresh_compose(tmp, "c6")
    rc, out = run("plan", h, Fake(), repo_dir=repo2)
    check("plan: a json that is not what build_dashboard builds is a FAIL", (rc, "is what tools/build_dashboard.py builds" in out and "[FAIL]" in out), (1, True))
    check("plan: the reason says it differs", ": it differs" in out, True)
    (repo2 / "tools" / "build_dashboard.py").write_text("raise ZeroDivisionError('broken build in this repo')\n", encoding="utf-8")
    rc, out = run("plan", h, Fake(), repo_dir=repo2)
    check("plan: build_dashboard is imported from the tools folder of --repo-dir, and its error is shown with the type and the message",
          (rc, "ZeroDivisionError: broken build in this repo" in out), (1, True))
    shutil.rmtree(repo2 / "dashboards" / "provisioning")
    rc, out = run("plan", h, Fake(), repo_dir=repo2)
    check("plan: a missing provider file is a FAIL", (rc, "[FAIL] the repo has dashboards/provisioning/ai-impact.yml" in out), (1, True))

# ---------------------------------------------------------------- the older override of this script is replaced, any other is not; custom tools; a twin json
with tempfile.TemporaryDirectory() as tmp:
    c = fresh_compose(tmp)
    old_text = G.override_text(ROOT).replace("/dashboards/json", "/dashboards")
    (c / G.OVERRIDE_NAME).write_text(old_text, encoding="utf-8")
    rc, out = run("plan", c, Fake())
    check("plan: an older override that starts with this script's header is OK and shown as a diff",
          (rc, "apply replaces it" in out, "-        source: " in out, "+        source: " in out), (0, True, True, True))
    fake = Fake()
    rc, out = run("apply", c, fake)
    check("apply replaces the older override (header line) and runs up", (rc, (c / G.OVERRIDE_NAME).read_text(encoding="utf-8"), "replaced" in out,
                                                                          len([x for x in fake.calls if x[0][:2] == ["compose", "up"]])), (0, G.override_text(ROOT), True, 1))
    (c / G.OVERRIDE_NAME).write_text("# somebody else\n" + old_text, encoding="utf-8")
    fake = Fake()
    rc, out = run("apply", c, fake)
    check("apply: an override whose first line is not the header stays, nothing is run", (rc, [x for x in fake.calls if x[0][0] == "compose"]), (1, []))
    d = fresh_compose(tmp, "c2")
    twin = Path(tmp) / "repo3"
    shutil.copytree(ROOT / "dashboards", twin / "dashboards")
    shutil.copytree(ROOT / "sql", twin / "sql")
    shutil.copytree(ROOT / "tools", twin / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    (twin / "dashboards" / "json" / "copy.json").write_text(json.dumps({"uid": "ai-impact-pr"}), encoding="utf-8")
    rc, out = run("plan", d, Fake(), repo_dir=twin)
    check("plan: a second json file with the uid ai-impact-pr in the json folder is a FAIL", (rc, "no other json file with the uid ai-impact-pr" in out and "copy.json" in out), (1, True))
    (twin / "dashboards" / "json" / "copy.json").write_text(json.dumps({"uid": "other"}), encoding="utf-8")
    rc, out = run("plan", d, Fake(), repo_dir=twin)
    check("plan: a second json file with another uid is not a twin", rc, 0)
    cfg = Path(tmp) / "custom.json"
    cfg.write_text(json.dumps({"remove": [{"tool": "copilot", "field": "pr_author"}]}), encoding="utf-8")
    rc, out = run("plan", d, Fake(), repo_dir=twin, extra=["--custom-tools", str(cfg)])
    check("plan --custom-tools: the repo json (built without) is not the build with the config -> FAIL", (rc, "builds with --custom-tools" in out), (1, True))
    import build_dashboard as BD
    (twin / "dashboards" / "json" / "ai-impact.json").write_text(BD.to_text(BD.build(custom=json.loads(cfg.read_text(encoding="utf-8")))), encoding="utf-8")
    rc, out = run("plan", d, Fake(), repo_dir=twin, extra=["--custom-tools", str(cfg)])
    check("plan --custom-tools: after the custom build replaced ai-impact.json the freshness check passes", rc, 0)

# ---------------------------------------------------------------- status
with tempfile.TemporaryDirectory() as tmp:
    c = fresh_compose(tmp)
    fake = Fake()
    rc, out = run("status", c, fake)
    check("status, all good: exit 0 and the last line", (rc, out.strip().splitlines()[-1]), (0, "status: all 5 checks passed"))
    check("status asks the log since the start of the container", [x[0] for x in fake.calls if x[0][0] == "logs"], [["logs", "--since", "2026-10-21T06:00:00.5Z", "abc123"]])
    check("status: inspect only with --format (the environment of the container, which has passwords, is never asked)",
          [x[0] for x in fake.calls if x[0][0] == "inspect"], [["inspect", "--format", "{{json .Mounts}}", "abc123"], ["inspect", "--format", "{{.State.StartedAt}}", "abc123"]])
    check("status changes nothing: no compose up, no file", ([x for x in fake.calls if x[0][:2] == ["compose", "up"]], list(c.glob("*override*"))), ([], []))

    m = Fake.good_mounts()
    rc, out = run("status", c, Fake(mounts=[m[0], m[2]]))
    check("status: the provider mount is missing -> stops, says the override was not read, tries no other name",
          (rc, "mount %s is NOT in the container" % G.PROVIDER_TARGET in out, "was not read" in out, "Report this" in out), (1, True, True, True))
    rc, out = run("status", c, Fake(mounts=[m[0]]))
    check("status: both mounts missing", (rc, out.count("NOT in the container")), (1, 2))
    m2 = [m[0], dict(m[1], RW=True), m[2]]
    rc, out = run("status", c, Fake(mounts=m2))
    check("status: a mount that is not read-only is a FAIL", (rc, "not read-only" in out), (1, True))
    m3 = [m[0], dict(m[1], Type="volume"), m[2]]
    rc, out = run("status", c, Fake(mounts=m3))
    check("status: a mount that is not a bind mount is a FAIL", (rc, "not a bind mount" in out), (1, True))

    rc, out = run("status", c, Fake(sha="0" * 64))
    check("status: another sha256 in the container is a FAIL", (rc, "DIFFERS" in out, "status: 1 of 5 check(s) FAILED" in out), (1, True, True))
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="starting"\n'))
    check("status: no 'finished to provision dashboards' line is a FAIL", (rc, "(0 time(s)" in out), (1, True))
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="finished to provision dashboards"\nlogger=provisioning.dashboard level=error msg="cannot read" name=ai-impact\n'))
    check("status: a provisioning level=error line that names ai-impact is a FAIL and is shown", (rc, "(1 found)" in out, "cannot read" in out), (1, True, True))
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="finished to provision dashboards"\nlogger=provisioning.dashboard level=error msg="duplicate uid" name=My Dashboard\n'))
    check("status: an error that does not name ai-impact is not counted", (rc, "(0 found)" in out), (0, True))
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="finished to provision dashboards"\nlogger=provisioning.dashboard level=warn msg="the same UID is used more than once" uid=ai-impact-pr times=2 providers="[ai-impact]"\n'))
    check("status: a level=warn line of logger provisioning that names ai-impact-pr / the provider ai-impact is a FAIL", (rc, "(1 found)" in out), (1, True))
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="finished to provision dashboards"\nlogger=provisioning.dashboard level=warn msg="the same UID is used more than once" uid=grafana-irm-dashboard providers="[My Dashboard]"\nlogger=provisioning.dashboard level=warn msg="no database write permissions because of duplicates" provider="My Dashboard"\n'))
    check("status: DevLake's own duplicates warnings (provider My Dashboard) are not counted", (rc, "(0 found)" in out), (0, True))
    rc, out = run("status", c, Fake(logs='logger=other msg="finished to provision dashboards"\n'))
    check("status: the finished line must come from logger provisioning.dashboard", rc, 1)
    rc, out = run("status", c, Fake(logs='logger=provisioning.dashboard msg="finished to provision dashboards"\nlogger=live level=error msg="x ai-impact"\n'))
    check("status: an error of another logger is not counted", (rc, "(0 found)" in out), (0, True))
    rc, out = run("status", c, Fake(ps=""))
    check("status: no running grafana container is a FAIL", (rc, "no running `grafana` container" in out), (1, True))

# ---------------------------------------------------------------- U6: --readonly-db and --anonymous-viewer (the override text, written by hand)
RO_NEED = '"${GRAFANA_DB_RO_PASSWORD:?run tools/grafana_readonly_user.py apply first}"'
base_lines = want.rstrip("\n").split("\n")
ro_mount_lines = ["      - type: bind", '        source: "%s/dashboards/provisioning/datasources/ai-impact-ro.yml"' % repo,
                  "        target: /etc/grafana/provisioning/datasources/ai-impact-ro.yml", "        read_only: true", "        bind:", "          create_host_path: false"]
ro_env_lines = ["    environment:", "      GRAFANA_DB_RO_PASSWORD: " + RO_NEED, "      MYSQL_USER: grafana_ro", "      MYSQL_PASSWORD: " + RO_NEED]
anon_lines = ['      GF_AUTH_ANONYMOUS_ENABLED: "true"', "      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer"]
want_ro = "\n".join(base_lines + ro_mount_lines + ro_env_lines) + "\n"
want_anon = "\n".join(base_lines + ro_mount_lines + ro_env_lines + anon_lines) + "\n"
text_ro = G.override_text(ROOT, readonly_db=True)
text_anon = G.override_text(ROOT, readonly_db=True, anonymous_viewer=True)
check("--readonly-db: the override file, line by line (third mount, then environment)", text_ro, want_ro)
check("--anonymous-viewer: the override file, line by line (the two GF_AUTH_ANONYMOUS lines after the read-only lines)", text_anon, want_anon)
check("without the flags the override is the old text (the first line, the header, is the same in all three)", (G.override_text(ROOT) == text, text_ro.split("\n", 1)[0] == text.split("\n", 1)[0] == text_anon.split("\n", 1)[0]), (True, True))
check("--readonly-db: three mounts, all read-only and create_host_path false, long syntax", (text_ro.count("read_only: true"), text_ro.count("create_host_path: false"), text_ro.count("- type: bind")), (3, 3, 3))
check("--readonly-db: the third mount is read-only", "target: /etc/grafana/provisioning/datasources/ai-impact-ro.yml\n        read_only: true" in text_ro, True)
check("--readonly-db: the password is the variable of the .env, with the message; no value is in the file", (text_ro.count("${GRAFANA_DB_RO_PASSWORD:?run tools/grafana_readonly_user.py apply first}"), "merico" in text_ro), (2, False))
check("--readonly-db: MYSQL_USER is grafana_ro (the start script of DevLake makes its own data source with it)", "      MYSQL_USER: grafana_ro" in text_ro, True)
check("--readonly-db without --anonymous-viewer has no GF_AUTH_ANONYMOUS", "GF_AUTH_ANONYMOUS" in text_ro, False)
check("the override of --anonymous-viewer has the environment key once", text_anon.count("    environment:"), 1)
check("the targets of --readonly-db are outside DevLake's /etc/grafana/provisioning/datasources/datasource.yml (a file of its own)", "datasource.yml" in text_ro.replace("ai-impact-ro.yml", ""), False)

dsfile = (ROOT / "dashboards" / "provisioning" / "datasources" / "ai-impact-ro.yml").read_text(encoding="utf-8")
body = [l for l in dsfile.splitlines() if not l.lstrip().startswith("#")]
for line in ("apiVersion: 1", "datasources:", "  - name: mysql", "    uid: devlake-mysql-api", "    type: mysql", "    url: mysql:3306", "    database: lake",
             "    user: grafana_ro", "    secureJsonData:", "      password: $GRAFANA_DB_RO_PASSWORD", "    access: proxy", "    isDefault: true", "    editable: false"):
    check("the data source file has the line: " + line.strip(), line in body, True)
check("the data source file: the password has one `$` (not ${...}) and no value; the user is not merico", ("${" in "\n".join(body), "merico" in "\n".join(body)), (False, False))
check("the uid is the one that every panel of the dashboard uses", '"uid": "devlake-mysql-api"' in (ROOT / "dashboards" / "json" / "ai-impact.json").read_text(encoding="utf-8"), True)


def run_err(command, compose_dir, fake, extra=()):
    """Like run(), but also returns what main wrote to the error output."""
    G.docker = fake
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = G.main([command, "--compose-dir", str(compose_dir)] + list(extra))
        except SystemExit as e:      # argparse: an unknown option
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


with tempfile.TemporaryDirectory() as tmp:
    c = fresh_compose(tmp)
    # arguments
    fake = Fake()
    rc, out, err = run_err("plan", c, fake, ["--anonymous-viewer"])
    check("plan --anonymous-viewer without --readonly-db: refused (exit 2), nothing run", (rc, "only together with --readonly-db" in err, fake.calls), (2, True, []))
    fake = Fake()
    rc, out, err = run_err("apply", c, fake, ["--anonymous-viewer"])
    check("apply --anonymous-viewer without --readonly-db: refused (exit 2), no file, nothing run", (rc, list(c.glob("*override*")), fake.calls), (2, [], []))
    rc, out, err = run_err("plan", c, Fake(), ["--readonly-db", "--drop-readonly-db"])
    check("--readonly-db together with --drop-readonly-db: refused (exit 2)", rc, 2)
    rc, out, err = run_err("status", c, Fake(), ["--anonymous-viewer"])
    check("status does not take --anonymous-viewer (argparse: exit 2)", rc, 2)

    # plan
    fake = Fake()
    rc, out, err = run_err("plan", c, fake, ["--readonly-db"])
    check("plan --readonly-db: exit 0, prints the override with the third mount and the environment", (rc, all(l in out for l in ro_mount_lines + ro_env_lines)), (0, True))
    check("plan --readonly-db: says what the lines do, that .env is read by Docker Compose, and the command with --force-recreate",
          ("ai-impact-ro.yml" in out, "read by Docker Compose from the .env" in out, "up -d --no-deps --force-recreate grafana" in out), (True, True, True))
    check("plan --readonly-db changes nothing", (list(c.glob("*override*")), [x for x in fake.calls if x[0][:2] == ["compose", "up"]]), ([], []))
    check("plan without --anonymous-viewer prints no warning of it", "WARNING --anonymous-viewer" in out, False)
    fake = Fake()
    rc, out, err = run_err("plan", c, fake, ["--readonly-db", "--anonymous-viewer"])
    check("plan --anonymous-viewer: the environment lines and the warning (a time without a login, 127.0.0.1 only, how to switch it off and the 3 checks)",
          (rc, all(l in out for l in anon_lines), "WARNING --anonymous-viewer" in out, "without a login" in out, "127.0.0.1 only" in out, "run apply again with --readonly-db only" in out),
          (0, True, True, True, True, True))
    check("plan --anonymous-viewer lists the option in its header", "options:        --readonly-db, --anonymous-viewer" in out, True)

    # a repo without the data source file
    repo4 = Path(tmp) / "repo4"
    shutil.copytree(ROOT / "dashboards", repo4 / "dashboards")
    shutil.copytree(ROOT / "sql", repo4 / "sql")
    shutil.copytree(ROOT / "tools", repo4 / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    (repo4 / "dashboards" / "provisioning" / "datasources" / "ai-impact-ro.yml").unlink()
    rc, out, err = run_err("plan", c, Fake(), ["--repo-dir", str(repo4), "--readonly-db"])
    check("plan --readonly-db: the data source file missing in the repo is a FAIL", (rc, "[FAIL] the repo has dashboards/provisioning/datasources/ai-impact-ro.yml" in out), (1, True))
    rc, out, err = run_err("plan", c, Fake(), ["--repo-dir", str(repo4)])
    check("plan without --readonly-db does not need that file", rc, 0)

    # apply --readonly-db
    c2 = fresh_compose(tmp, "ro1")
    fake = Fake()
    rc, out, err = run_err("apply", c2, fake, ["--readonly-db"])
    check("apply --readonly-db: exit 0; the override is the planned text", (rc, (c2 / G.OVERRIDE_NAME).read_bytes().decode("utf-8")), (0, text_ro))
    check("apply --readonly-db: recreates grafana with --force-recreate, only that", [(x[0], x[1]) for x in fake.calls if x[0][0] == "compose"],
          [(["compose", "up", "-d", "--no-deps", "--force-recreate", "grafana"], str(c2))])
    check("apply --readonly-db tells to check with status --readonly-db", "status --compose-dir %s --wait 120 --readonly-db" % c2 in out, True)

    # apply --readonly-db when the .env line is missing: Docker Compose stops, the old state comes back
    c3 = fresh_compose(tmp, "ro2")
    fake = Fake(up_rc=1, up_err='error while interpolating services.grafana.environment.GRAFANA_DB_RO_PASSWORD: required variable GRAFANA_DB_RO_PASSWORD is missing a value: run tools/grafana_readonly_user.py apply first')
    rc, out, err = run_err("apply", c3, fake, ["--readonly-db"])
    check("apply --readonly-db, Docker Compose stops on the missing .env line: exit 1, the new override is removed again (the folder works as before)",
          (rc, list(c3.glob("*override*")), "put back as it was" in out, "grafana_readonly_user.py apply" in out), (1, [], True, True))
    (c3 / G.OVERRIDE_NAME).write_bytes(G.override_text(ROOT).encode("utf-8"))
    fake = Fake(up_rc=1, up_err="required variable GRAFANA_DB_RO_PASSWORD is missing a value: run tools/grafana_readonly_user.py apply first")
    rc, out, err = run_err("apply", c3, fake, ["--readonly-db"])
    check("... with an older override of this script: that one is written back, byte for byte", (rc, (c3 / G.OVERRIDE_NAME).read_bytes().decode("utf-8")), (1, text))
    c3b = fresh_compose(tmp, "ro2b")
    fake = Fake(up_rc=1, up_err="some other error of docker compose")
    rc, out, err = run_err("apply", c3b, fake, ["--readonly-db"])
    check("any other failure of docker compose up: the override stays (as before U6)", (rc, (c3b / G.OVERRIDE_NAME).exists()), (1, True))

    # refuse to drop the read-only lines
    c4 = fresh_compose(tmp, "ro3")
    (c4 / G.OVERRIDE_NAME).write_bytes(text_ro.encode("utf-8"))
    fake = Fake()
    rc, out, err = run_err("plan", c4, fake)
    check("plan without flags on an override that has the read-only lines: refused (FAIL), says --readonly-db / --drop-readonly-db",
          (rc, "would DROP them" in out, "--drop-readonly-db to drop them on purpose" in out), (1, True, True))
    fake = Fake()
    rc, out, err = run_err("apply", c4, fake)
    check("apply without flags: refused, the override is not changed, nothing is run", (rc, (c4 / G.OVERRIDE_NAME).read_bytes().decode("utf-8"), [x for x in fake.calls if x[0][0] == "compose"]), (1, text_ro, []))
    rc, out, err = run_err("plan", c4, Fake(), ["--readonly-db"])
    check("plan --readonly-db on the same override: fine (exactly what apply would write)", (rc, "is exactly what apply would write" in out), (0, True))
    rc, out, err = run_err("plan", c4, Fake(), ["--readonly-db", "--anonymous-viewer"])
    check("plan --readonly-db --anonymous-viewer on it: fine, a diff that adds the two lines", (rc, "+      GF_AUTH_ANONYMOUS_ENABLED" in out), (0, True))
    fake = Fake()
    rc, out, err = run_err("apply", c4, fake, ["--drop-readonly-db"])
    check("apply --drop-readonly-db: allowed; the override goes back to the two mounts; grafana is recreated",
          (rc, (c4 / G.OVERRIDE_NAME).read_bytes().decode("utf-8"), "allowed, --drop-readonly-db is given" in out and "the data source in Grafana stays as it is" in out,
           [x[0] for x in fake.calls if x[0][:2] == ["compose", "up"]]), (0, text, True, [["compose", "up", "-d", "--no-deps", "--force-recreate", "grafana"]]))
    rc, out, err = run_err("plan", c4, Fake(), ["--drop-readonly-db"])
    check("--drop-readonly-db on an override that has no read-only lines is harmless", (rc, "DROP" in out), (0, False))
    # the anonymous lines alone may be removed without the drop flag (the way back after a recording)
    c5 = fresh_compose(tmp, "ro4")
    (c5 / G.OVERRIDE_NAME).write_bytes(text_anon.encode("utf-8"))
    fake = Fake()
    rc, out, err = run_err("apply", c5, fake, ["--readonly-db"])
    check("the way back after a recording: apply --readonly-db without --anonymous-viewer replaces the override; no GF_AUTH_ANONYMOUS is left",
          (rc, (c5 / G.OVERRIDE_NAME).read_bytes().decode("utf-8"), "GF_AUTH_ANONYMOUS" in (c5 / G.OVERRIDE_NAME).read_text(encoding="utf-8")), (0, text_ro, False))
    # an override with other content (first line not the header) is still never replaced, with any flag
    (c5 / G.OVERRIDE_NAME).write_bytes(("# somebody else\n" + text_ro).encode("utf-8"))
    fake = Fake()
    rc, out, err = run_err("apply", c5, fake, ["--readonly-db"])
    check("apply --readonly-db: an override of somebody else is not replaced", (rc, [x for x in fake.calls if x[0][0] == "compose"]), (1, []))

    # status --readonly-db
    c6 = fresh_compose(tmp, "ro5")
    fake = Fake(readonly=True)
    rc, out, err = run_err("status", c6, fake, ["--readonly-db"])
    check("status --readonly-db, all good: three mounts + sha + two log checks = 6 checks", (rc, out.strip().splitlines()[-1], out.count("is a read-only bind mount")), (0, "status: all 6 checks passed", 3))
    rc, out, err = run_err("status", c6, Fake(readonly=False), ["--readonly-db"])
    check("status --readonly-db: the third mount missing -> stops, says the override was not read", (rc, "mount %s is NOT in the container" % G.DATASOURCE_TARGET in out, "was not read" in out), (1, True, True))
    m = Fake.good_mounts(True)
    rc, out, err = run_err("status", c6, Fake(mounts=[m[0], m[1], m[2], dict(m[3], RW=True)]), ["--readonly-db"])
    check("status --readonly-db: the third mount not read-only is a FAIL", (rc, "not read-only" in out), (1, True))
    rc, out, err = run_err("status", c6, Fake(readonly=False), [])
    check("status without --readonly-db does not look at the third mount (as before)", (rc, out.strip().splitlines()[-1]), (0, "status: all 5 checks passed"))

# ---------------------------------------------------------------- --anonymous-viewer needs 127.0.0.1-only ports of grafana and config-ui in the compose file
def compose_with(grafana_ports, config_ui_ports, same_indent=False):
    ind = "" if same_indent else "  "
    def ports(entries):
        return "" if entries is None else "    ports:\n" + "".join("    %s- %s\n" % (ind, e) for e in entries)
    return ("services:\n  mysql:\n    image: mysql:8\n    ports:\n      - 3306:3306\n  grafana:\n    image: x\n" + ports(grafana_ports) +
            "    volumes:\n      - grafana-storage:/var/lib/grafana\n  config-ui:\n    image: y\n" + ports(config_ui_ports) + "    env_file:\n      - ./.env\nvolumes:\n  grafana-storage:\n")


with tempfile.TemporaryDirectory() as tmp:
    def folder_with(name, text):
        d = fresh_compose(tmp, name)
        (d / "docker-compose.yml").write_text(text, encoding="utf-8")
        return d

    AN = ["--readonly-db", "--anonymous-viewer"]
    upstream = compose_with(["3002:3000"], ["4000:4000"])      # the ports of DevLake's own compose file: all interfaces
    d = folder_with("pt1", upstream)
    fake = Fake()
    rc, out, err = run_err("plan", d, fake, AN)
    check("plan --anonymous-viewer on the ports of DevLake's own compose file (3002:3000, 4000:4000): FAIL naming both",
          (rc, "[FAIL] the ports of the services grafana and config-ui" in out, "grafana: 3002:3000" in out, "config-ui: 4000:4000" in out), (1, True, True, True))
    fake = Fake()
    rc, out, err = run_err("apply", d, fake, AN)
    check("apply --anonymous-viewer on them: stops, no override written, nothing run", (rc, list(d.glob("*override*")), [x for x in fake.calls if x[0][0] == "compose"]), (1, [], []))
    rc, out, err = run_err("plan", d, Fake(), ["--readonly-db"])
    check("the same compose file without --anonymous-viewer: the ports are not looked at (exit 0)", (rc, "the ports of the services" in out), (0, False))
    d = folder_with("pt2", compose_with(["127.0.0.1:3002:3000"], ["4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("grafana on 127.0.0.1 but config-ui on all interfaces (it proxies /grafana): FAIL naming config-ui only", (rc, "config-ui: 4000:4000" in out, "grafana: 127" in out), (1, True, False))
    d = folder_with("pt3", compose_with(['"127.0.0.1:3002:3000"'], ["127.0.0.1:4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("both on 127.0.0.1 (one entry in double quotes): ok, exit 0", (rc, "[ok] the ports of the services grafana and config-ui" in out), (0, True))
    d = folder_with("pt4", compose_with(["127.0.0.1:3002:3000"], ["127.0.0.1:4000:4000"], same_indent=True))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("the list written at the indentation of the key `ports:` is read as well: ok", rc, 0)
    d = folder_with("pt4b", compose_with(["3002:3000"], ["127.0.0.1:4000:4000"], same_indent=True))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("... and an open port in such a list is found: FAIL", (rc, "grafana: 3002:3000" in out), (1, True))
    d = folder_with("pt5", compose_with(["0.0.0.0:3002:3000"], ["127.0.0.1:4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("0.0.0.0 is not loopback: FAIL", (rc, "grafana: 0.0.0.0:3002:3000" in out), (1, True))
    d = folder_with("pt6", compose_with(["127.0.0.10:3002:3000"], ["127.0.0.1:4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("127.0.0.10 is not 127.0.0.1 (the prefix includes the colon): FAIL", rc, 1)
    d = folder_with("pt7", compose_with(["3002"], ["127.0.0.1:4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("a bare container port (published on all interfaces at a random port) is a FAIL", rc, 1)
    d = folder_with("pt8", compose_with(None, None))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("no ports at all (nothing is published): ok", (rc, "[ok] the ports of the services" in out), (0, True))
    d = folder_with("pt9", "services:\n  grafana:\n    image: x\n    ports:\n      - target: 3000\n        published: 3002\n  config-ui:\n    image: y\n")
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("long syntax without host_ip: FAIL", (rc, "grafana: target: 3000 published: 3002" in out), (1, True))
    d = folder_with("pt10", "services:\n  grafana:\n    image: x\n    ports:\n      - target: 3000\n        published: 3002\n        host_ip: 127.0.0.1\n  config-ui:\n    image: y\n")
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("long syntax with host_ip: 127.0.0.1: ok", rc, 0)
    d = folder_with("pt11", compose_with(["127.0.0.1:3002:3000", "8443:3000"], ["127.0.0.1:4000:4000"]))
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("one open entry among several is enough for a FAIL", (rc, "grafana: 8443:3000" in out), (1, True))
    d = folder_with("pt12", "services:\n  mysql:\n    image: m\n    ports:\n      - 3306:3306\n  grafana:\n    image: x\n    ports:\n      - 127.0.0.1:3002:3000\n  config-ui:\n    image: y\n    ports:\n      - 127.0.0.1:4000:4000\n")
    rc, out, err = run_err("plan", d, Fake(), AN)
    check("the ports of other services (mysql 3306 on all interfaces) are not part of the check", rc, 0)
    check("devlake-local style: the ports lines of the local compose file (127.0.0.1:3002:3000 / 127.0.0.1:4000:4000) pass", G.ports_on_loopback_only(compose_with(["127.0.0.1:3002:3000"], ["127.0.0.1:4000:4000"]))[0], True)

for b in bad:
    print("FAIL " + b)
print("%d checks, %d failures" % (len(rows), len(bad)))
sys.exit(1 if bad else 0)
