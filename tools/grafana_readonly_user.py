#!/usr/bin/env python3
"""Makes the database user `grafana_ro` (SELECT on lake.* and nothing else) for the Grafana of a local DevLake, and checks it (U6, ADR 0004 "A read-only database user for Grafana").

Why: dashboard variable values can also come from the page URL and reach the query. Grafana "doesn't validate the safety of queries" and says the database
user of a data source should have only SELECT (https://grafana.com/docs/grafana/latest/datasources/mysql/configure/).
The default data source user of DevLake's Grafana (`merico`) has write rights, and the vendor docs advise a read-only user. The real boundary is the right of
the database user. Then `tools/grafana_install.py --readonly-db` points Grafana at this user.

  plan    changes nothing. Checks the compose folder, the .env file (it is read, to see whether the line is there and whether its value can be used; the
          value is never printed), that the variable is not set in the shell either (Docker Compose prefers the shell), Docker and the mysql container; prints
          the user, the right, the SQL (with <password> in place of the value), the name of the line that apply adds to .env and where that line goes.
  apply   (the owner types it) 1. uses the line GRAFANA_DB_RO_PASSWORD of the .env in the compose folder; if there is none, makes a value with
          secrets.token_hex(24) (hex digits only: no `$`, which Grafana and Docker Compose would read as a variable) and adds one line to .env
          (a missing newline at the end of .env is added first). 2. sends to `docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" lake'`, on
          standard input:   CREATE USER IF NOT EXISTS 'grafana_ro'@'%' IDENTIFIED BY '<value>';
                            ALTER USER 'grafana_ro'@'%' IDENTIFIED BY '<value>';
                            GRANT SELECT ON lake.* TO 'grafana_ro'@'%';
          (MySQL 8.4 manual: the host part defaults to '%'; CREATE USER makes the account, GRANT gives the right, ALTER USER sets the password again, so a second run
          leaves the .env line and the database with the same password; `ON db_name.*` is a right on one database.) The password of root is expanded inside
          the container; this script never sees it (the same way as tools/run_on_devlake.py does for `merico`). A mysql error prints only `ERROR nnnn` (the text of
          the error can contain a part of the statement, and so the password).
  status  changes nothing. Checks as root: (1) SHOW GRANTS FOR 'grafana_ro'@'%' is exactly the two lines
              GRANT USAGE ON *.* TO `grafana_ro`@`%`     GRANT SELECT ON `lake`.* TO `grafana_ro`@`%`
          (2) SHOW PROCESSLIST: from the IP of the grafana container (docker inspect, Go-template field NetworkSettings.Networks only) at least one connection of
          `grafana_ro` and none of `merico` (the connection exists after the screen was opened once; look after opening it). Only counts are printed.
          (3) as a record (not a pass or fail), how many times the log of the grafana container since it started has the two lines of DevLake's start
          script `Datasource created successfully` and `Datasource already exists; keeping existing one`, and how many lines of Grafana's own request log
          (`POST /api/datasources status=409`, `DELETE /api/datasources/<id> status=404`).

Safety: it never prints the password (not on the screen, not in an argument of a command, not in an error); it reads .env only to find the line of
GRAFANA_DB_RO_PASSWORD (syntax of Docker's page on variable interpolation, section `.env` file syntax) and to add one; it never runs `docker compose config` and never prints `docker inspect` as a whole. Standard library and the docker CLI only.
The line in .env reaches the containers `devlake` and `config-ui` too: both have `env_file: ./.env` (docker-compose.yml of DevLake), so they get the variable the
next time they are created (it does no harm; they do not use it).

Exit code 0 = done / all checks passed; 1 = a check failed; 2 = a bad argument.

Usage:
  python tools/grafana_readonly_user.py plan   --compose-dir <compose-dir>
  python tools/grafana_readonly_user.py apply  --compose-dir <compose-dir>
  python tools/grafana_readonly_user.py status --compose-dir <compose-dir>
"""
import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

USER = "grafana_ro"
HOST = "%"
DB = "lake"
ENV_NAME = "GRAFANA_DB_RO_PASSWORD"
ENV_FILE = ".env"
BASE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")
# the password of root is expanded inside the container, as tools/run_on_devlake.py does for merico
MYSQL_ROOT_CMD = 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 --batch --skip-column-names ' + DB
EXPECTED_GRANTS = ("GRANT USAGE ON *.* TO `%s`@`%s`" % (USER, HOST), "GRANT SELECT ON `%s`.* TO `%s`@`%s`" % (DB, USER, HOST))
START_SCRIPT_LINES = ("Datasource created successfully", "Datasource already exists; keeping existing one")    # entrypoint.sh.txt L226, L233
# lines of Grafana's own request log: all these texts must be in the line
REQUEST_LOG_LINES = (("POST /api/datasources status=409", ("method=POST", "path=/api/datasources ", "status=409")),
                     ("DELETE /api/datasources/<id> status=404", ("method=DELETE", "path=/api/datasources/", "status=404")))
PASSWORD_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
LINE_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?%s[ \t]*[=:](.*)$" % ENV_NAME)    # "Delimiter separating key and value can be either = or :"


def say(text=""):
    print(text)


def sql_text(password):
    q = "'%s'@'%s'" % (USER, HOST)
    return ("CREATE USER IF NOT EXISTS %s IDENTIFIED BY '%s';\n"
            "ALTER USER %s IDENTIFIED BY '%s';\n"
            "GRANT SELECT ON %s.* TO %s;\n") % (q, password, q, password, DB, q)


# ------------------------------------------------------------------ docker
def docker(args, cwd=None, input_text=None, timeout=600):
    """Runs the docker CLI. Returns (returncode, stdout, stderr) as text. MSYS_NO_PATHCONV keeps Git Bash from rewriting /etc/... arguments.
    input_text goes to standard input (it is never part of an argument)."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    try:
        r = subprocess.run(["docker"] + list(args), capture_output=True, cwd=cwd, env=env, timeout=timeout,
                           input=None if input_text is None else input_text.encode("utf-8"))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", "could not run docker (%s)" % type(e).__name__
    clean = "\n".join(l for l in r.stderr.decode("utf-8", "replace").splitlines() if "attribute `version` is obsolete" not in l)
    return r.returncode, r.stdout.decode("utf-8", "replace"), clean


def mysql(compose_dir, sql):
    """Runs sql as root in the mysql container. Returns (ok, stdout, error_text) where error_text is only `ERROR nnnn` or a fixed sentence:
    the text of mysql (and of docker) is never passed on, it can contain a part of the statement."""
    rc, out, err = docker(["compose", "exec", "-T", "mysql", "sh", "-c", MYSQL_ROOT_CMD], cwd=compose_dir, input_text=sql)
    m = re.search(r"ERROR (\d+)", err)
    if m:
        return False, "", "ERROR " + m.group(1)
    if rc != 0:
        return False, "", "docker compose exec / mysql failed (exit code %d); the message is not shown because it can contain the statement" % rc
    return True, out, ""


# ------------------------------------------------------------------ .env
def parse_env_text(raw):
    """The value of the text after the `=` or `:` of a .env line, by the section `.env` file syntax of Docker's page
    https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/ : spaces before and after the value are ignored; an unquoted value ends at a ` #` (a space, then #; a tab
    before # is not a comment) and the spaces before it go; a quoted value ends at its closing quote (a backslash escapes a quote), and after the closing
    quote only spaces, or spaces and `# comment`, may follow. Returns the text, or None when it cannot be read this way (no closing quote, text after it).
    Escapes are not turned into characters: a value with a backslash is refused later (the characters allowed are fewer)."""
    v = raw.lstrip(" \t")
    if v[:1] in ("'", '"'):
        q, j = v[0], 1
        while j < len(v) and v[j] != q:
            j += 2 if v[j] == "\\" else 1
        if j >= len(v):
            return None
        rest = v[j + 1:]
        if rest.strip(" \t") == "" or (rest[:1] in (" ", "\t") and rest.lstrip(" \t").startswith("#")):
            return v[1:j]
        return None
    cut = v.find(" #")
    return (v if cut < 0 else v[:cut]).rstrip(" \t")


def read_env_value(compose_dir):
    """('nofile', None) | ('absent', None) | ('present', value or None). The value is returned to the caller only, never printed.
    The last line wins; a first line with a UTF-8 byte order mark is read as a line; the syntax is that of parse_env_text."""
    path = Path(compose_dir) / ENV_FILE
    if not path.is_file():
        return "nofile", None
    value, found = None, False
    for line in path.read_bytes().decode("utf-8-sig", "replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        value, found = parse_env_text(m.group(1)), True
    return ("present", value) if found else ("absent", None)


def append_env_line(compose_dir, value):
    """Adds `GRAFANA_DB_RO_PASSWORD=value` as a new last line of .env. If the file does not end with a newline, one is added first
    (otherwise the line would be glued to the last line); the line ending of the file (LF or CRLF) is kept."""
    path = Path(compose_dir) / ENV_FILE
    data = path.read_bytes()
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    with open(path, "ab") as f:
        f.write((eol if data and not data.endswith(b"\n") else b"") + ("%s=%s" % (ENV_NAME, value)).encode("ascii") + eol)


def env_state_text(compose_dir):
    state, value = read_env_value(compose_dir)
    if state == "nofile":
        return False, "the compose folder has no %s file (DevLake's compose file reads it with env_file)" % ENV_FILE
    if state == "absent":
        return True, "%s has no %s line yet: apply makes the value and adds the line" % (ENV_FILE, ENV_NAME)
    if value is not None and PASSWORD_RE.fullmatch(value):
        return True, "%s has the line %s (value not shown): apply uses it" % (ENV_FILE, ENV_NAME)
    return False, ("%s has a %s line whose value cannot be read by the .env syntax, or has a character other than a letter, a digit, `_` or `-`, or is shorter than 16 or longer than 128 characters "
                   "(value not shown): delete the line and run apply again, it makes a new one" % (ENV_FILE, ENV_NAME))


def preconditions(compose_dir):
    checks = []
    compose = Path(compose_dir)
    base = next((compose / n for n in BASE_NAMES if (compose / n).is_file()), None)
    checks.append((base is not None, "the compose folder has %s" % (base.name if base else "no docker-compose.yml / compose.yaml")))
    checks.append(env_state_text(compose_dir))
    checks.append((ENV_NAME not in os.environ, "%s is not set in the shell environment%s" % (ENV_NAME, "" if ENV_NAME not in os.environ else
                   " -- it IS set (value not shown): Docker Compose uses the shell value before the .env value (docker_variable_interpolation.md L64-L72), so the .env line "
                   "and the database could differ; unset it in this shell")))
    rc, out, err = docker(["info", "--format", "{{.ServerVersion}}"])
    checks.append((rc == 0, "Docker answers%s" % (" (server %s)" % out.strip() if rc == 0 else ": " + err.strip()[:100])))
    rc, out, err = docker(["compose", "ps", "-q", "mysql"], cwd=compose_dir)
    checks.append((rc == 0 and bool(out.strip()), "the service `mysql` is running in this compose project%s" % ("" if rc == 0 and out.strip() else " (not found)")))
    return checks


def print_checks(checks):
    for ok, text in checks:
        say("  [%s] %s" % ("ok" if ok else "FAIL", text))


# ------------------------------------------------------------------ plan and apply
def cmd_plan(args):
    say("grafana_readonly_user plan   (changes nothing)")
    say("  compose folder: %s" % args.compose_dir)
    say()
    say("[1] Checks that apply runs first:")
    checks = preconditions(args.compose_dir)
    print_checks(checks)
    say()
    say("[2] The database user that apply makes (or makes again):  '%s'@'%s'   right: SELECT ON %s.*   (nothing else)" % (USER, HOST, DB))
    say("    apply sends this on standard input to mysql, as root, in the mysql container (<password> is the value of the line %s of .env; it is never shown):" % ENV_NAME)
    for line in sql_text("<password>").rstrip("\n").split("\n"):
        say("    | " + line)
    say("    command: docker compose exec -T mysql sh -c '%s'   (in the compose folder; the password of root is expanded inside the container)" % MYSQL_ROOT_CMD)
    say()
    say("[3] The line in %s of the compose folder:  %s=<value>   (name only; the value is not shown, it is made by secrets.token_hex(24) if the line is not there)" % (ENV_FILE, ENV_NAME))
    say("    A second apply uses the same line and sets the same password in the database again (ALTER USER).")
    say("    The line is read by Docker Compose (variables of the .env of the project folder) and by the containers `devlake` and `config-ui`, whose")
    say("    `env_file: ./.env` (in the docker-compose.yml of DevLake) gives them the variable the next time they are created. They do not use it.")
    say()
    say("[4] Then:  python tools/grafana_install.py plan --compose-dir %s --readonly-db   (and apply), open the Grafana screen once, and run" % args.compose_dir)
    say("    python tools/grafana_readonly_user.py status --compose-dir %s" % args.compose_dir)
    bad = [t for ok, t in checks if not ok]
    say()
    say("plan: %s" % ("all checks passed" if not bad else "%d check(s) FAILED, apply would stop without changing anything" % len(bad)))
    return 0 if not bad else 1


def cmd_apply(args):
    say("grafana_readonly_user apply")
    checks = preconditions(args.compose_dir)
    print_checks(checks)
    bad = [t for ok, t in checks if not ok]
    if bad:
        say("apply: stopped. %d check(s) failed. Nothing was changed." % len(bad))
        return 1
    state, value = read_env_value(args.compose_dir)
    if state == "present":
        say("  using the line %s of %s (value not shown)" % (ENV_NAME, ENV_FILE))
    else:
        value = secrets.token_hex(24)
        append_env_line(args.compose_dir, value)
        say("  added the line %s to %s (value not shown)" % (ENV_NAME, ENV_FILE))
    ok, out, error = mysql(args.compose_dir, sql_text(value))
    if not ok:
        say("apply: mysql reported %s. The %s line stays; run apply again after the cause is removed (ERROR 1045 = the password of root was refused)." % (error, ENV_FILE))
        return 1
    say("  mysql accepted: CREATE USER IF NOT EXISTS, ALTER USER, GRANT SELECT ON %s.* for '%s'@'%s'" % (DB, USER, HOST))
    say("apply: done. Next: python tools/grafana_install.py plan --compose-dir %s --readonly-db" % args.compose_dir)
    return 0


# ------------------------------------------------------------------ status
def grafana_container(compose_dir):
    rc, out, err = docker(["compose", "ps", "-q", "grafana"], cwd=compose_dir)
    cid = out.strip().splitlines()[0] if out.strip() else ""
    return cid if rc == 0 and cid else None


def processlist_counts(table_out, ips):
    """{user: connections} for the rows of `SHOW PROCESSLIST --batch --skip-column-names` (Id, User, Host, db, ...) whose host IP is in `ips`."""
    counts = {}
    for line in table_out.splitlines():
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        ip = cols[2].rsplit(":", 1)[0]
        if ip in ips:
            counts[cols[1]] = counts.get(cols[1], 0) + 1
    return counts


def cmd_status(args):
    say("grafana_readonly_user status   (changes nothing)")
    results = []

    def report(ok, text):
        results.append((ok, text))
        say("  [%s] %s" % ("ok" if ok else "FAIL", text))

    ok, out, error = mysql(args.compose_dir, "SHOW GRANTS FOR '%s'@'%s';\n" % (USER, HOST))
    if not ok:
        report(False, "SHOW GRANTS FOR '%s'@'%s' failed: %s (ERROR 1141 = the user does not exist: run apply)" % (USER, HOST, error))
    else:
        got = sorted(l.strip() for l in out.splitlines() if l.strip())
        report(got == sorted(EXPECTED_GRANTS), "SHOW GRANTS FOR '%s'@'%s' is exactly %d lines: %s%s" % (
            USER, HOST, len(EXPECTED_GRANTS), " | ".join(EXPECTED_GRANTS), "" if got == sorted(EXPECTED_GRANTS) else "  (got %d line(s): %s)" % (len(got), " | ".join(got))))
    cid = grafana_container(args.compose_dir)
    if cid is None:
        report(False, "no running `grafana` container in %s: the processlist and the log cannot be checked" % args.compose_dir)
    else:
        rc, ips_out, err = docker(["inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", cid])
        ips = set(ips_out.split()) if rc == 0 else set()
        ok, out, error = mysql(args.compose_dir, "SHOW PROCESSLIST;\n")
        if not ips:
            report(False, "the IP of the grafana container is not known (docker inspect, field NetworkSettings.Networks)")
        elif not ok:
            report(False, "SHOW PROCESSLIST failed: %s" % error)
        else:
            counts = processlist_counts(out, ips)
            ro, old = counts.get(USER, 0), counts.get("merico", 0)
            report(ro >= 1 and old == 0, "connections from the grafana container (%s): %s %d (want 1 or more), merico %d (want 0)%s" % (
                ", ".join(sorted(ips)), USER, ro, old, "" if ro >= 1 else "  [a connection exists after a panel was loaded: open the screen, then run status again]"))
        rc, started, err = docker(["inspect", "--format", "{{.State.StartedAt}}", cid])
        since = started.strip() if rc == 0 else ""
        rc, out, err = docker(["logs", "--since", since, cid] if since else ["logs", cid])
        text = out + "\n" + err
        starts = [(m, sum(1 for l in text.splitlines() if m in l)) for m in START_SCRIPT_LINES]
        requests = [(name, sum(1 for l in text.splitlines() if all(w in l for w in words))) for name, words in REQUEST_LOG_LINES]
        say("  (record, not a check) since %s the log of the grafana container has these lines of DevLake's start script: %s" % (
            since or "its start", "; ".join("`%s` %d" % mc for mc in starts)))
        say("  (record, not a check) and these lines of Grafana's own request log: %s" % "; ".join("`%s` %d" % mc for mc in requests))
    bad = [t for ok, t in results if not ok]
    say("status: %s" % ("all %d checks passed" % len(results) if not bad else "%d of %d check(s) FAILED" % (len(bad), len(results))))
    return 0 if not bad else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name, helptext in (("plan", "change nothing; show the user, the SQL and the .env line"),
                           ("apply", "make the user grafana_ro and the .env line (the owner types it)"),
                           ("status", "change nothing; check the grants, the connections and the log")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--compose-dir", required=True, help="the folder of DevLake's docker-compose.yml")
    args = ap.parse_args(argv)
    if not Path(args.compose_dir).is_dir():
        print("STOP: --compose-dir %s is not a folder" % args.compose_dir, file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    return {"plan": cmd_plan, "apply": cmd_apply, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
