#!/usr/bin/env python3
"""Puts the dashboard dashboards/json/ai-impact.json into the Grafana of a local DevLake by Grafana's own "provisioning from files" (U5, ADR 0004).
Nothing is typed into Grafana and no Grafana API (which needs the password of Grafana's admin) is used.

How: Grafana reads dashboards from files that a provider file names (docs: "Provision Grafana", section Dashboards; several provider files may
be added). This script adds a provider file of its own (dashboards/provisioning/ai-impact.yml) and the dashboard folder to the `grafana` service
of DevLake's compose project by a compose override file, written next to DevLake's docker-compose.yml:

  <compose-dir>/docker-compose.override.yml     two bind mounts of the `grafana` service, long syntax, read-only, create_host_path: false
      <repo>/dashboards/provisioning/ai-impact.yml  ->  /etc/grafana/provisioning/dashboards/ai-impact.yml
      <repo>/dashboards/json                        ->  /etc/grafana/ai-impact      (outside DevLake's /etc/grafana/dashboards; json files only)

  --readonly-db   (U6, ADR 0004 "A read-only database user for Grafana") the data source of Grafana is the read-only database user grafana_ro: a third mount,
      <repo>/dashboards/provisioning/datasources/ai-impact-ro.yml  ->  /etc/grafana/provisioning/datasources/ai-impact-ro.yml
      and in the `environment` of the grafana service GRAFANA_DB_RO_PASSWORD, MYSQL_USER=grafana_ro and MYSQL_PASSWORD (both passwords are
      ${GRAFANA_DB_RO_PASSWORD:?...} of the .env of the compose folder; tools/grafana_readonly_user.py apply creates the user and the .env line first).
      An existing override that has these lines is never replaced by one without them unless --drop-readonly-db is given (plan and apply).
  --anonymous-viewer   only together with --readonly-db: GF_AUTH_ANONYMOUS_ENABLED "true" and GF_AUTH_ANONYMOUS_ORG_ROLE Viewer, i.e. the screen
      can be seen without a login while it is on. plan and apply check first that every port of the services grafana and config-ui in the compose file of the
      folder is published on 127.0.0.1 only (DevLake's own compose file publishes 3002:3000 and 4000:4000 on all interfaces; config-ui proxies /grafana);
      otherwise the command stops. For a recording; apply again without the flag to switch it off.
  --drop-readonly-db only removes the lines from the override. It does not change the data source in Grafana (it stays grafana_ro, editable false; a
      provisioned data source goes only with deleteDatasources / prune in a provisioning file); see [4] of plan.

  plan    changes nothing. Checks the compose folder, the repo files and the override file; prints the override that apply would write, what
          recreating the grafana container does, and the commands.
          An existing override is replaced only when its first line is the header line that this script writes itself (plan shows old and new
          as a diff); any other existing override stops the command.
          --custom-tools FILE: the freshness check builds the dashboard with that config (docs/dashboard.md). The custom build replaces
          dashboards/json/ai-impact.json (tools/build_dashboard.py --custom-tools FILE); do not put a second file in dashboards/json/.
  apply   runs the same checks, writes the override file, and runs `docker compose up -d --no-deps --force-recreate grafana` in the compose
          folder (only the grafana container is recreated, every time, so that it reads the files again; the data volumes stay).
  status  changes nothing. Checks (1) both mounts (with --readonly-db three) are in the container and read-only, (2) sha256 of /etc/grafana/ai-impact/ai-impact.json in the
          container equals the repo file, (3) the log of the container since it was started has "finished to provision dashboards" from
          logger provisioning.dashboard (one line for all providers) and no line of logger provisioning at level=warn or level=error that
          contains ai-impact (this covers ai-impact-pr and a duplicates warning that names the provider ai-impact). --wait SECONDS polls for (3).
          It does not prove that the uid is in Grafana's database; looking at the screen does.
          If a mount is missing, the override was not read: the script says so and stops (it does not try another file name).

Safety: it never reads .env, never runs `docker compose config` and never prints `docker inspect` as a whole (the environment of the container
has passwords); only Go-template fields (Mounts, State.StartedAt) are asked for. Docker Compose reads the .env of the folder by itself when it
runs; this script never sees it. Standard library and the docker CLI only.

Exit code 0 = done / all checks passed; 1 = a check failed (plan and status change nothing; apply stops before it changes anything);
2 = a bad argument.

Usage:
  python tools/grafana_install.py plan   --compose-dir <compose-dir>   [--readonly-db [--anonymous-viewer]] [--drop-readonly-db]
  python tools/grafana_install.py apply  --compose-dir <compose-dir>   [--readonly-db [--anonymous-viewer]] [--drop-readonly-db]
  python tools/grafana_install.py status --compose-dir <compose-dir> --wait 120   [--readonly-db]
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

SERVICE = "grafana"
OVERRIDE_NAME = "docker-compose.override.yml"
BASE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")
OTHER_OVERRIDES = ("docker-compose.override.yaml", "compose.override.yaml", "compose.override.yml")
JSON_DIR = "dashboards/json"
UID = "ai-impact-pr"
PROVIDER_TARGET = "/etc/grafana/provisioning/dashboards/ai-impact.yml"
DASHBOARD_TARGET = "/etc/grafana/ai-impact"
JSON_IN_CONTAINER = DASHBOARD_TARGET + "/ai-impact.json"
DATASOURCE_FILE = "dashboards/provisioning/datasources/ai-impact-ro.yml"
DATASOURCE_TARGET = "/etc/grafana/provisioning/datasources/ai-impact-ro.yml"
RO_ENV = "GRAFANA_DB_RO_PASSWORD"
RO_USER = "grafana_ro"
RO_NEEDS = "${%s:?run tools/grafana_readonly_user.py apply first}" % RO_ENV
FINISHED = "finished to provision dashboards"


def say(text=""):
    print(text)


class Stop(Exception):
    def __init__(self, message, code=1):
        Exception.__init__(self, message)
        self.code = code


# ------------------------------------------------------------------ docker
def docker(args, cwd=None, timeout=600):
    """Runs the docker CLI. Returns (returncode, stdout, stderr) as text. MSYS_NO_PATHCONV keeps Git Bash from rewriting /etc/... arguments."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    try:
        r = subprocess.run(["docker"] + list(args), capture_output=True, cwd=cwd, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", "could not run docker (%s)" % type(e).__name__
    clean = "\n".join(l for l in r.stderr.decode("utf-8", "replace").splitlines() if "attribute `version` is obsolete" not in l)
    return r.returncode, r.stdout.decode("utf-8", "replace"), clean


# ------------------------------------------------------------------ the override file
def yaml_str(text):
    """A double-quoted YAML scalar (a json string is one)."""
    return json.dumps(text, ensure_ascii=True)


def override_text(repo_dir, readonly_db=False, anonymous_viewer=False):
    repo = Path(repo_dir).resolve()
    provider = (repo / "dashboards" / "provisioning" / "ai-impact.yml").as_posix()
    folder = (repo / "dashboards" / "json").as_posix()
    datasource = (repo / DATASOURCE_FILE).as_posix()
    ro_mount, env = [], []
    if readonly_db:
        ro_mount = ["      - type: bind",
                    "        source: " + yaml_str(datasource),
                    "        target: " + DATASOURCE_TARGET,
                    "        read_only: true",
                    "        bind:",
                    "          create_host_path: false"]
        env = ["    environment:",
               "      %s: %s" % (RO_ENV, yaml_str(RO_NEEDS)),
               "      MYSQL_USER: " + RO_USER,
               "      MYSQL_PASSWORD: " + yaml_str(RO_NEEDS)]
        if anonymous_viewer:
            env += ['      GF_AUTH_ANONYMOUS_ENABLED: "true"', "      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer"]
    return "\n".join([
        "# Written by tools/grafana_install.py of devlake-agent-review-burden (docs/dashboard.md). Compose reads this file together with",
        "# docker-compose.yml. To take the dashboard away: delete this file and run `docker compose up -d --no-deps grafana` in this folder.",
        "services:",
        "  %s:" % SERVICE,
        "    volumes:",
        "      - type: bind",
        "        source: " + yaml_str(provider),
        "        target: " + PROVIDER_TARGET,
        "        read_only: true",
        "        bind:",
        "          create_host_path: false",
        "      - type: bind",
        "        source: " + yaml_str(folder),
        "        target: " + DASHBOARD_TARGET,
        "        read_only: true",
        "        bind:",
        "          create_host_path: false"] + ro_mount + env + [""])


def read_text(path):
    return Path(path).read_bytes().decode("utf-8").replace("\r\n", "\n")


def load_build_dashboard(repo_dir):
    """tools/build_dashboard.py of the repo that is installed (--repo-dir), not of the folder of this script."""
    path = Path(repo_dir) / "tools" / "build_dashboard.py"
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("build_dashboard_of_repo", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(path.parent))


def other_uid_files(json_dir):
    """The json files in the json folder (any depth) other than ai-impact.json that have the uid of this dashboard."""
    found = []
    for f in sorted(Path(json_dir).rglob("*.json")):
        if f.name == "ai-impact.json" and f.parent == Path(json_dir):
            continue
        try:
            if json.loads(read_text(f)).get("uid") == UID:
                found.append(f.name)
        except (ValueError, AttributeError, OSError):
            pass
    return found


def header_line():
    return override_text(ROOT).split("\n", 1)[0]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def service_ports(compose_text, service):
    """The `ports:` entries of a service in a compose file, as a list of text blocks (None when the service is not in the file).
    A short entry is its text without quotes (`127.0.0.1:3002:3000`); an entry of the long syntax is all its lines joined by a space."""
    lines = [l.rstrip() for l in compose_text.split("\n")]
    start = next((i for i, l in enumerate(lines) if re.fullmatch(r"\s*%s:\s*" % re.escape(service), l) and _indent(l) == 2), None)
    if start is None:
        return None
    body = []
    for l in lines[start + 1:]:
        if l.strip() and not l.lstrip().startswith("#") and _indent(l) <= 2:
            break
        body.append(l)
    entries, k = [], None
    for idx, l in enumerate(body):
        if re.fullmatch(r"\s*ports:\s*", l):
            k = idx
            break
    if k is None:
        return []
    key_indent = _indent(body[k])
    for l in body[k + 1:]:
        t = l.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("-") and _indent(l) >= key_indent:
            entries.append(re.split(r"\s+#", t[1:].strip(), 1)[0].strip().strip("\"'"))
        elif _indent(l) > key_indent and entries:
            entries[-1] += " " + t
        else:
            break
    return entries


def ports_on_loopback_only(compose_text):
    """(ok, text) for --anonymous-viewer: every port of grafana and config-ui must start with 127.0.0.1: (short syntax) or have host_ip: 127.0.0.1 (long syntax)."""
    open_ports = []
    for service in ("grafana", "config-ui"):
        for e in service_ports(compose_text, service) or []:
            if not (e.startswith("127.0.0.1:") or re.search(r"host_ip:\s*[\"']?127\.0\.0\.1[\"']?(\s|$)", e)):
                open_ports.append("%s: %s" % (service, e[:60]))
    return (not open_ports, "the ports of the services grafana and config-ui in the compose file are published on 127.0.0.1 only%s" % (
        "" if not open_ports else " -- NOT: " + "; ".join(open_ports) + " (the screen would be open without a login to every machine that can reach this one)"))


def has_readonly_lines(override):
    """True when an override text has any of the read-only database lines that --readonly-db writes."""
    return any(marker in override for marker in (DATASOURCE_TARGET, RO_ENV, "MYSQL_USER: " + RO_USER))


def options(args):
    return {"readonly_db": getattr(args, "readonly_db", False), "anonymous_viewer": getattr(args, "anonymous_viewer", False),
            "drop_readonly_db": getattr(args, "drop_readonly_db", False)}


def preconditions(compose_dir, repo_dir, custom_tools=None, readonly_db=False, anonymous_viewer=False, drop_readonly_db=False):
    """[(ok, text)] for plan and apply, and the state: {"override": path, "existing": text or None, "text": text to write, "replace": bool}."""
    checks = []
    compose = Path(compose_dir)
    base = next((compose / n for n in BASE_NAMES if (compose / n).is_file()), None)
    checks.append((base is not None, "the compose folder has %s" % (base.name if base else "no docker-compose.yml / compose.yaml")))
    has_service = False
    if base is not None:
        has_service = re.search(r"(?m)^  %s:\s*$" % SERVICE, read_text(base)) is not None and re.search(r"(?m)^services:\s*$", read_text(base)) is not None
    checks.append((has_service, "it defines the service `%s`" % SERVICE))
    repo = Path(repo_dir)
    json_file = repo / JSON_DIR / "ai-impact.json"
    for rel in (JSON_DIR + "/ai-impact.json", "dashboards/provisioning/ai-impact.yml") + ((DATASOURCE_FILE,) if readonly_db else ()):
        checks.append(((repo / rel).is_file(), "the repo has %s" % rel))
    why = ""
    fresh = False
    if json_file.is_file():
        try:
            bd = load_build_dashboard(repo)
            custom = None
            if custom_tools:
                custom = json.loads(Path(custom_tools).read_text(encoding="utf-8"))
            fresh = read_text(json_file) == bd.to_text(bd.build(repo / "sql/mysql/ai_impact_parity.sql", repo / "sql/mysql/agent_review_burden.sql", custom))
            if not fresh:
                why = ": it differs"
        except Exception as e:
            why = ": %s: %s" % (type(e).__name__, str(e)[:200])
    checks.append((fresh, "%s/ai-impact.json is what tools/build_dashboard.py builds%s from the SQL files now (same as --check)%s" % (
        JSON_DIR, " with --custom-tools" if custom_tools else "", why)))
    twins = other_uid_files(repo / JSON_DIR)
    checks.append((not twins, "%s has no other json file with the uid %s%s" % (JSON_DIR, UID, "" if not twins else " (found: " + ", ".join(twins) + ")")))
    target = compose / OVERRIDE_NAME
    existing = read_text(target) if target.is_file() else None
    text = override_text(repo_dir, readonly_db, anonymous_viewer)
    replace = existing is not None and existing != text and existing.split("\n", 1)[0] == header_line()
    if existing is None:
        note, ok = "does not exist yet", True
    elif existing == text:
        note, ok = "is exactly what apply would write", True
    elif replace:
        note, ok = "exists with older content that this script wrote (first line is its header): apply replaces it (diff below)", True
    else:
        note, ok = "exists with other content (its first line is not the header of this script): it is not overwritten", False
    checks.append((ok, "%s %s" % (OVERRIDE_NAME, note)))
    if replace and has_readonly_lines(existing) and not has_readonly_lines(text):
        checks.append((drop_readonly_db, "the existing override has the read-only database lines (data source of grafana_ro) and the new one would DROP them%s" % (
            ": allowed, --drop-readonly-db is given (only the override loses these lines: the data source in Grafana stays as it is, see [4] of plan)" if drop_readonly_db else
            ": give --readonly-db to keep them, or --drop-readonly-db to drop them on purpose")))
    if anonymous_viewer and readonly_db and base is not None:
        checks.append(ports_on_loopback_only(read_text(base)))
    others = [n for n in OTHER_OVERRIDES if (compose / n).is_file()]
    checks.append((not others, "no other override file is in the folder%s" % ("" if not others else " (found: " + ", ".join(others) + ")")))
    rc, out, err = docker(["info", "--format", "{{.ServerVersion}}"])
    checks.append((rc == 0, "Docker answers%s" % (" (server %s)" % out.strip() if rc == 0 else ": " + err.strip()[:100])))
    return checks, {"override": target, "existing": existing, "text": text, "replace": replace}


def print_checks(checks):
    for ok, text in checks:
        say("  [%s] %s" % ("ok" if ok else "FAIL", text))


def cmd_plan(args):
    opt = options(args)
    say("grafana_install plan   (changes nothing)")
    say("  compose folder: %s" % args.compose_dir)
    say("  repo:           %s" % args.repo_dir)
    say("  options:        %s" % (", ".join("--" + k.replace("_", "-") for k, v in opt.items() if v) or "(none)"))
    say()
    say("[1] Checks that apply runs first:")
    checks, st = preconditions(args.compose_dir, args.repo_dir, args.custom_tools, **opt)
    print_checks(checks)
    say()
    say("[2] apply would write %s with this content:" % st["override"])
    for line in st["text"].rstrip("\n").split("\n"):
        say("    | " + line)
    if st["replace"]:
        say("    It replaces the older file; the difference (old -, new +):")
        for line in difflib.unified_diff(st["existing"].splitlines(), st["text"].splitlines(), "old", "new", lineterm="", n=0):
            say("    " + line)
    say()
    say("[3] apply would then run, in the compose folder:   docker compose up -d --no-deps --force-recreate %s" % SERVICE)
    say("    Only the `%s` container is recreated (mysql, devlake and config-ui are not touched; `--no-deps`). The data volumes stay." % SERVICE)
    say("    When the container starts, DevLake's start script TRIES to delete the data sources of Grafana and to create its own one (uid devlake-mysql-api,")
    say("    https://github.com/apache/devlake/blob/v1.0.3-beta18/grafana/scripts/entrypoint.sh lines 159-188 and 226-233). On the Grafana 13.2.2 of this DevLake the delete by id answered 404 and the create answered 409")
    say("    (log lines of 2026-10-21), so the data source that is already there is kept.")
    say("    The dashboards of DevLake itself are read again from the image, as at every start.")
    if opt["readonly_db"]:
        say("    --readonly-db: Grafana's provisioning reads %s (user %s, password from the environment of the container) and the start script gets" % (DATASOURCE_TARGET, RO_USER))
        say("    MYSQL_USER=%s, so the data source is %s whether the start script keeps the existing one or creates its own (entrypoint.sh lines 44-57 and 226-233, URL above)." % (RO_USER, RO_USER))
        say("    The password is not in this file: the lines ${%s:?...} are read by Docker Compose from the .env of the compose folder." % RO_ENV)
        say("    If that .env line is missing, Docker Compose stops with the message `run tools/grafana_readonly_user.py apply first` and apply puts the old override back.")
    if opt["anonymous_viewer"]:
        say()
        say("    WARNING --anonymous-viewer: while this is on, a time without a login exists. Anybody who can open the Grafana port of this machine")
        say("    (check [1] has read the ports of grafana and config-ui in the compose file: 127.0.0.1 only) sees the dashboards as role Viewer, and a Viewer can run queries of the")
        say("    data source (read-only user grafana_ro, but every table of lake). Switch it off after the recording: run apply again with --readonly-db only")
        say("    and check (a) the override has no GF_AUTH_ANONYMOUS, (b) the container started after the override was updated, (c) a browser without login gets the login page.")
    say()
    say("[4] To take the dashboard away again: delete %s, then `docker compose up -d --no-deps --force-recreate %s` in the compose folder." % (OVERRIDE_NAME, SERVICE))
    say("    This does NOT put the data source back. After --drop-readonly-db, or after the override is deleted, the data source in Grafana's database stays")
    say("    %s with editable false: a provisioned data source is removed only by `deleteDatasources` or by `prune: true` in a provisioning file (%s;" % (RO_USER, "https://grafana.com/docs/grafana/latest/administration/provisioning/"))
    say("    the file of this repo sets neither), and DevLake's start script keeps an existing data source (404/409, entrypoint.sh lines")
    say("    226-233). Going back to merico is not covered by this script and not described in the docs that were read: a person has to change the data source first,")
    say("    and only then drop the database user %s." % RO_USER)
    say("    After apply, check with: python tools/grafana_install.py status --compose-dir %s --wait 120%s" % (args.compose_dir, " --readonly-db" if opt["readonly_db"] else ""))
    bad = [t for ok, t in checks if not ok]
    say()
    say("plan: %s" % ("all checks passed" if not bad else "%d check(s) FAILED, apply would stop without changing anything" % len(bad)))
    return 0 if not bad else 1


def cmd_apply(args):
    opt = options(args)
    say("grafana_install apply")
    checks, st = preconditions(args.compose_dir, args.repo_dir, args.custom_tools, **opt)
    print_checks(checks)
    bad = [t for ok, t in checks if not ok]
    if bad:
        say("apply: stopped. %d check(s) failed. Nothing was changed." % len(bad))
        return 1
    if st["existing"] is None or st["replace"]:
        with open(st["override"], "w", encoding="utf-8", newline="\n") as f:
            f.write(st["text"])
        say("  %s %s" % ("replaced" if st["replace"] else "wrote", st["override"]))
    else:
        say("  %s already has this content" % st["override"])
    say("  running: docker compose up -d --no-deps --force-recreate %s   (in %s)" % (SERVICE, args.compose_dir))
    rc, out, err = docker(["compose", "up", "-d", "--no-deps", "--force-recreate", SERVICE], cwd=args.compose_dir)
    for line in (out + "\n" + err).strip().splitlines()[-6:]:
        say("    " + line)
    if rc != 0:
        if opt["readonly_db"] and RO_ENV in (out + err):
            # Docker Compose could not read the .env line: `docker compose up` of the folder would stop with this override, so the old state is put back
            if st["existing"] is None:
                os.remove(st["override"])
            else:
                with open(st["override"], "w", encoding="utf-8", newline="\n") as f:
                    f.write(st["existing"])
            say("apply: docker compose stopped because %s is not set in the .env of the compose folder (exit code %d). The override file was put back as it was." % (RO_ENV, rc))
            say("       Run: python tools/grafana_readonly_user.py apply --compose-dir %s   and then this apply again." % args.compose_dir)
            return 1
        say("apply: docker compose failed (exit code %d). The override file stays; remove it to undo." % rc)
        return 1
    say("apply: done. Check with: python tools/grafana_install.py status --compose-dir %s --wait 120%s" % (args.compose_dir, " --readonly-db" if opt["readonly_db"] else ""))
    return 0


# ------------------------------------------------------------------ status
def container_id(compose_dir):
    rc, out, err = docker(["compose", "ps", "-q", SERVICE], cwd=compose_dir)
    cid = out.strip().splitlines()[0] if out.strip() else ""
    if rc != 0 or not cid:
        raise Stop("no running `%s` container in %s (%s)" % (SERVICE, compose_dir, err.strip()[:120] or "docker compose ps -q is empty"))
    return cid


def check_mounts(mounts, readonly_db=False):
    """[(ok, text)] for the two targets (three with readonly_db). `mounts` is the decoded `docker inspect --format {{json .Mounts}}`."""
    result = []
    by_target = {m.get("Destination"): m for m in mounts or []}
    for target in (PROVIDER_TARGET, DASHBOARD_TARGET) + ((DATASOURCE_TARGET,) if readonly_db else ()):
        m = by_target.get(target)
        if m is None:
            result.append((False, "mount %s is NOT in the container" % target))
        elif m.get("Type") != "bind" or m.get("RW") is not False:
            result.append((False, "mount %s is there but %s" % (target, "not a bind mount" if m.get("Type") != "bind" else "not read-only")))
        else:
            result.append((True, "mount %s is a read-only bind mount" % target))
    return result


def log_checks(log_text):
    """[(ok, text)] from the log of the container since it was created."""
    lines = log_text.splitlines()
    finished = [l for l in lines if "logger=provisioning.dashboard" in l and FINISHED in l]
    errors = [l for l in lines if "logger=provisioning" in l and ("level=error" in l or "level=warn" in l) and "ai-impact" in l]
    return [(len(finished) >= 1, "the log has `%s` from logger provisioning.dashboard (%d time(s); one line for all providers)" % (FINISHED, len(finished))),
            (len(errors) == 0, "the log has no provisioning level=warn or level=error line that contains ai-impact (%d found)" % len(errors))], errors


def cmd_status(args):
    say("grafana_install status   (changes nothing)")
    try:
        cid = container_id(args.compose_dir)
    except Stop as e:
        say("  [FAIL] %s" % e)
        return 1
    results = []
    rc, out, err = docker(["inspect", "--format", "{{json .Mounts}}", cid])
    try:
        mounts = json.loads(out) if rc == 0 else None
    except ValueError:
        mounts = None
    if mounts is None:
        say("  [FAIL] docker inspect (Mounts) failed: %s" % err.strip()[:120])
        return 1
    mount_results = check_mounts(mounts, getattr(args, "readonly_db", False))
    results += mount_results
    for ok, text in mount_results:
        say("  [%s] %s" % ("ok" if ok else "FAIL", text))
    if not all(ok for ok, _ in mount_results):
        say("status: a mount is missing, so the override file was not read by Docker Compose (Docker's page https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/ says that")
        say("        `compose.override.yaml` is read; the old name %s is not on that page). Nothing was changed and no other file name" % OVERRIDE_NAME)
        say("        or procedure is tried. Report this.")
        return 1
    want = hashlib.sha256((Path(args.repo_dir) / "dashboards" / "json" / "ai-impact.json").read_bytes()).hexdigest()
    rc, out, err = docker(["compose", "exec", "-T", SERVICE, "sha256sum", JSON_IN_CONTAINER], cwd=args.compose_dir)
    have = out.split()[0] if rc == 0 and out.split() else ""
    ok = have == want
    results.append((ok, "sha256 of %s in the container%s the repo file (%s)" % (JSON_IN_CONTAINER, " equals" if ok else " DIFFERS from", want[:12])))
    say("  [%s] %s" % ("ok" if ok else "FAIL", results[-1][1]))
    rc, started, err = docker(["inspect", "--format", "{{.State.StartedAt}}", cid])
    since = started.strip() if rc == 0 else ""
    deadline = time.time() + max(0, args.wait)
    while True:
        rc, out, err = docker(["logs", "--since", since, cid] if since else ["logs", cid])
        checks, errors = log_checks(out + "\n" + err)
        if checks[0][0] or time.time() >= deadline:
            break
        time.sleep(3)
    say("  (log of the container since it was started: %s)" % (since or "its start"))
    for ok, text in checks:
        say("  [%s] %s" % ("ok" if ok else "FAIL", text))
    for l in errors[:5]:
        say("      " + re.sub(r"\s+", " ", l)[:300])
    results += checks
    bad = [t for ok, t in results if not ok]
    say("status: %s" % ("all %d checks passed" % len(results) if not bad else "%d of %d check(s) FAILED" % (len(bad), len(results))))
    return 0 if not bad else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name, helptext in (("plan", "change nothing; show the checks, the override file and the commands"),
                           ("apply", "write the override file and recreate the grafana container"),
                           ("status", "change nothing; check the mounts, the sha256 and the log")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--compose-dir", required=True, help="the folder of DevLake's docker-compose.yml")
        p.add_argument("--repo-dir", default=str(ROOT), help="this repo (default: the folder of this script's parent)")
        if name == "status":
            p.add_argument("--wait", type=int, default=0, help="seconds to wait for the log line `%s`" % FINISHED)
            p.add_argument("--readonly-db", action="store_true", help="also check the mount of %s" % DATASOURCE_TARGET)
        else:
            p.add_argument("--custom-tools", help="the json file that dashboards/json/ai-impact.json was built with (tools/build_dashboard.py --custom-tools)")
            p.add_argument("--readonly-db", action="store_true",
                           help="the data source of Grafana is the read-only user %s (mount of %s; environment %s, MYSQL_USER, MYSQL_PASSWORD)" % (RO_USER, DATASOURCE_FILE, RO_ENV))
            p.add_argument("--drop-readonly-db", action="store_true",
                           help="allow an override without the read-only database lines to replace one that has them (without it the command stops); the data source in Grafana is not changed by this")
            p.add_argument("--anonymous-viewer", action="store_true",
                           help="only with --readonly-db: the screen can be seen without a login (role Viewer) while it is on, for a recording")
    args = ap.parse_args(argv)
    if getattr(args, "anonymous_viewer", False) and not args.readonly_db:
        print("STOP: --anonymous-viewer is accepted only together with --readonly-db (a screen without a login must not run on the user that can write)", file=sys.stderr)
        return 2
    if getattr(args, "drop_readonly_db", False) and args.readonly_db:
        print("STOP: --drop-readonly-db and --readonly-db contradict each other", file=sys.stderr)
        return 2
    if not Path(args.compose_dir).is_dir():
        print("STOP: --compose-dir %s is not a folder" % args.compose_dir, file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        return {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status}[args.command](args)
    except Stop as e:
        print("STOP: %s" % e, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
