#!/usr/bin/env python3
"""Test of tools/grafana_readonly_user.py against a fake docker (the function `docker` of the module is replaced; no container is touched, and
the .env files are throw-away files in a scratch folder): (1) the password is never in the standard output, the standard error or an argument of a
command; (2) a fake mysql that writes its standard input to its standard error still gives only `ERROR nnnn`; (3) a .env line is used as it is, a
missing one is made (hex digits) and added after the newline check; (4) the SQL has the form of the MySQL 8.4 manual (CREATE USER, ALTER USER, GRANT
SELECT ON lake.*); (5) status: SHOW GRANTS has exactly the two lines in backtick form, and the processlist from the IP of the grafana container has
grafana_ro 1 or more and merico 0. The expected values are written by hand.

Usage: python tests/tools/test_grafana_readonly_user.py     (the last line is "N checks, M failures"; exit code 0 = no failure)
"""
import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("grafana_readonly_user", ROOT / "tools" / "grafana_readonly_user.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

rows, bad = [], []


def check(name, got, want=True):
    rows.append(name)
    if got != want:
        bad.append("%s: got %r, want %r" % (name, got, want))


PW = "c0ffee1234567890abcdef1234567890abcdef1234567890"          # a value that is in a .env of the tests only
GRANTS_OK = "GRANT USAGE ON *.* TO `grafana_ro`@`%`\nGRANT SELECT ON `lake`.* TO `grafana_ro`@`%`\n"
GRAFANA_IP = "172.18.0.4"
PROCESS_OK = ("5\troot\tlocalhost\tlake\tQuery\t0\tstarting\tSHOW PROCESSLIST\n"
              "9\tmerico\t172.18.0.5:51000\tlake\tSleep\t3\t\tNULL\n"            # devlake, not the grafana container
              "21\tgrafana_ro\t%s:40100\tlake\tSleep\t1\t\tNULL\n"
              "22\tgrafana_ro\t%s:40102\tlake\tSleep\t1\t\tNULL\n" % (GRAFANA_IP, GRAFANA_IP))
COMPOSE = "services:\n  mysql:\n    image: mysql:8\n  grafana:\n    image: x\n"


class Fake:
    """Records every docker call (arguments, folder, standard input) and answers from a script."""

    def __init__(self, exec_mode="ok", grants=GRANTS_OK, process=PROCESS_OK, grafana_ps="gid\n", mysql_ps="mid\n", info_rc=0,
                 logs=("Datasource created successfully\nDatasource already exists; keeping existing one\n"
                       'logger=context t=2026-10-21T10:00:05Z level=info msg="Request Completed" method=POST path=/api/datasources status=409 remote_addr=[::1]\n'
                       'logger=context t=2026-10-21T10:00:03Z level=info msg="Request Completed" method=DELETE path=/api/datasources/1 status=404 remote_addr=[::1]\n'
                       'logger=context level=info msg="Request Completed" method=GET path=/api/datasources status=409\n')):
        self.calls = []
        self.exec_mode, self.grants, self.process = exec_mode, grants, process
        self.grafana_ps, self.mysql_ps, self.info_rc, self.logs = grafana_ps, mysql_ps, info_rc, logs

    def __call__(self, args, cwd=None, input_text=None, timeout=600):
        self.calls.append((list(args), cwd, input_text))
        if args[0] == "info":
            return self.info_rc, "29.8.0\n", ""
        if args[:3] == ["compose", "ps", "-q"]:
            return 0, self.mysql_ps if args[3] == "mysql" else self.grafana_ps, ""
        if args[:4] == ["compose", "exec", "-T", "mysql"]:
            sql = input_text or ""
            if "CREATE USER" in sql:
                if self.exec_mode == "ok":
                    return 0, "", "mysql: [Warning] Using a password on the command line interface can be insecure.\n"
                if self.exec_mode == "echo":      # a mysql that writes the statement into its error message
                    return 1, "", "ERROR 1396 (HY000) at line 2: Operation ALTER USER failed for 'grafana_ro'@'%' near: " + sql
                if self.exec_mode == "echo_no_number":     # an error without a number; the standard input comes back in it
                    return 1, "", "mysql: could not run: " + sql
                if self.exec_mode == "error_rc0":          # mysql run with --force: the error is in the text, the exit code is 0
                    return 0, "", "ERROR 1007 (HY000) at line 3: " + sql
                if self.exec_mode == "echo_rc0":           # a warning that repeats the statement while the exit code is 0
                    return 0, "", "Warning (Code 1287): " + sql
                if self.exec_mode == "root_refused":
                    return 1, "", "ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: YES)"
            if sql.startswith("SHOW GRANTS"):
                if isinstance(self.grants, tuple):
                    return 1, "", "ERROR %d (42000): There is no such grant defined for user 'grafana_ro' on host '%%'" % self.grants[0]
                return 0, self.grants, ""
            if sql.startswith("SHOW PROCESSLIST"):
                return 0, self.process, ""
            return 1, "", "unexpected statement"
        if args[0] == "inspect" and "{{.State.StartedAt}}" in args:
            return 0, "2026-10-21T08:21:44.1775251Z\n", ""
        if args[0] == "inspect" and any("NetworkSettings.Networks" in a for a in args):
            return 0, GRAFANA_IP + " \n", ""
        if args[0] == "logs":
            return 0, self.logs, ""
        return 1, "", "unexpected call"

    def mysql_inputs(self):
        return [c[2] for c in self.calls if c[0][:4] == ["compose", "exec", "-T", "mysql"]]


def run(command, compose_dir, fake):
    R.docker = fake
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = R.main([command, "--compose-dir", str(compose_dir)])
        except Exception as e:      # a crash is a failed check, not the end of the test
            rc = "exception " + type(e).__name__
    return rc, out.getvalue(), err.getvalue()


def folder(tmp, name, env_bytes=b"", with_env=True):
    d = Path(tmp) / name
    d.mkdir()
    (d / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    if with_env:
        (d / ".env").write_bytes(env_bytes)
    return d


def env_of(d):
    return (Path(d) / ".env").read_bytes()


def no_secret(secret, out, err, fake):
    """True when the secret is in none of: standard output, standard error, an argument or the folder of a docker command."""
    argv = " ".join(" ".join(c[0]) + " " + str(c[1]) for c in fake.calls)
    return secret not in out and secret not in err and secret not in argv


SQL_FOR = ("CREATE USER IF NOT EXISTS 'grafana_ro'@'%%' IDENTIFIED BY '%s';\n"
           "ALTER USER 'grafana_ro'@'%%' IDENTIFIED BY '%s';\n"
           "GRANT SELECT ON lake.* TO 'grafana_ro'@'%%';\n")

# ---------------------------------------------------------------- 4: the SQL has the form of the manual
check("the SQL: CREATE USER IF NOT EXISTS, ALTER USER, GRANT SELECT ON lake.*, line by line", R.sql_text("PWD"), SQL_FOR % ("PWD", "PWD"))
check("the SQL has SELECT as the only right and no ALL / WITH GRANT OPTION", ("ALL" in R.sql_text("x"), "GRANT OPTION" in R.sql_text("x"), R.sql_text("x").count("GRANT")), (False, False, 1))
check("the host part is '%' and the database part is lake.* (MySQL 8.4 manual: ON db_name.*)", ("'grafana_ro'@'%'" in R.sql_text("x"), "ON lake.* TO" in R.sql_text("x")), (True, True))
check("the root password is expanded inside the container (no value in the command text)", ('-p"$MYSQL_ROOT_PASSWORD"' in R.MYSQL_ROOT_CMD, "-uroot" in R.MYSQL_ROOT_CMD), (True, True))
check("the mysql command line, written out: --batch --skip-column-names (the status parser reads rows without a header), the database lake",
      R.MYSQL_ROOT_CMD, 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 --batch --skip-column-names lake')

with tempfile.TemporaryDirectory() as tmp:
    # ---------------------------------------------------------------- plan
    d = folder(tmp, "p1", b"A=1\n" + ("GRAFANA_DB_RO_PASSWORD=%s\n" % PW).encode())
    before = env_of(d)
    fake = Fake()
    rc, out, err = run("plan", d, fake)
    check("plan, .env with the line: exit 0, names the line, user, right", (rc, "GRAFANA_DB_RO_PASSWORD" in out, "'grafana_ro'@'%'" in out, "SELECT ON lake.*" in out), (0, True, True, True))
    check("plan never shows the value (not in the output, not in a command)", no_secret(PW, out, err, fake), True)
    check("plan says the line also reaches devlake and config-ui (env_file), without line numbers of a compose file that is not in this repository",
          ("devlake" in out and "config-ui" in out and "env_file" in out, "L60" in out or "L72" in out), (True, False))
    check("plan changes nothing: .env unchanged, no statement sent to mysql", (env_of(d) == before, fake.mysql_inputs()), (True, []))
    check("plan with the SQL shows <password>, not a value", "IDENTIFIED BY '<password>'" in out, True)
    rc, out, err = run("plan", folder(tmp, "p2", with_env=False), Fake())
    check("plan: no .env file is a FAIL", (rc, "no .env file" in out), (1, True))
    rc, out, err = run("plan", folder(tmp, "p3", b"X=1\n"), Fake())
    check("plan: .env without the line is fine (apply makes it)", (rc, "has no GRAFANA_DB_RO_PASSWORD line yet" in out), (0, True))
    rc, out, err = run("plan", folder(tmp, "p4", b"GRAFANA_DB_RO_PASSWORD=a$b\n"), Fake())
    check("plan: a value with a `$` is a FAIL and the value is not shown", (rc, "a$b" in out, "other than a letter" in out), (1, False, True))
    rc, out, err = run("plan", folder(tmp, "p5", b"X=1\n"), Fake(info_rc=1))
    check("plan: Docker not answering is a FAIL", rc, 1)
    rc, out, err = run("plan", folder(tmp, "p6", b"X=1\n"), Fake(mysql_ps=""))
    check("plan: no running mysql service is a FAIL", (rc, "`mysql` is running" in out and "[FAIL]" in out), (1, True))

    # ---------------------------------------------------------------- 3 and 4 and 1: apply with the line in .env
    d = folder(tmp, "a1", ("A=1\nGRAFANA_DB_RO_PASSWORD=%s\nB=2\n" % PW).encode())
    before = env_of(d)
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply with the line: exit 0, last line says done", (rc, out.strip().splitlines()[-1].startswith("apply: done.")), (0, True))
    check("apply with the line: the SQL sent is the manual's form with the value of the line", fake.mysql_inputs(), [SQL_FOR % (PW, PW)])
    check("apply with the line: .env is not changed at all", env_of(d), before)
    check("apply: the value is in none of the output, the error output, the arguments, the folder", no_secret(PW, out, err, fake), True)
    check("apply: the command text that reaches docker has --batch and --skip-column-names and no value",
          [("--batch" in c[0][-1], "--skip-column-names" in c[0][-1], PW in c[0][-1]) for c in fake.calls if c[0][:4] == ["compose", "exec", "-T", "mysql"]], [(True, True, False)])
    check("apply runs: docker compose exec -T mysql sh -c <root command>, in the compose folder",
          [(c[0], c[1]) for c in fake.calls if c[0][0] == "compose" and c[0][1] == "exec"], [(["compose", "exec", "-T", "mysql", "sh", "-c", R.MYSQL_ROOT_CMD], str(d))])
    check("apply says that the value was not shown", "(value not shown)" in out, True)

    # a second run gives the same
    fake2 = Fake()
    rc, out, err = run("apply", d, fake2)
    check("apply again: the same SQL (the database gets the same password as .env), .env still unchanged", (rc, fake2.mysql_inputs(), env_of(d)), (0, [SQL_FOR % (PW, PW)], before))

    # no line: made and added
    d = folder(tmp, "a2", b"A=1\nB=2\n")
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    text = env_of(d).decode("utf-8")
    m = re.fullmatch(r"A=1\nB=2\nGRAFANA_DB_RO_PASSWORD=([0-9a-f]{48})\n", text)
    check("apply without the line: one line GRAFANA_DB_RO_PASSWORD=<48 hex digits> is added after the old lines", (rc, m is not None), (0, True))
    made = m.group(1) if m else "?"
    check("apply without the line: the SQL has the value that was written to .env", fake.mysql_inputs(), [SQL_FOR % (made, made)])
    check("apply without the line: the made value is in no output, no argument", no_secret(made, out, err, fake), True)
    check("the made value has no `$` (Grafana and Docker Compose would read it as a variable)", "$" in made, False)
    fake2 = Fake()
    rc, out, err = run("apply", d, fake2)
    check("second apply: the line is used again, .env has still one line of it, the same SQL",
          (rc, text == env_of(d).decode("utf-8"), env_of(d).count(b"GRAFANA_DB_RO_PASSWORD"), fake2.mysql_inputs()), (0, True, 1, [SQL_FOR % (made, made)]))

    # no newline at the end of .env
    d = folder(tmp, "a3", b"A=1\nLAST=2")
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    m = re.fullmatch(r"A=1\nLAST=2\nGRAFANA_DB_RO_PASSWORD=([0-9a-f]{48})\n", env_of(d).decode("utf-8"))
    check("apply: .env that does not end with a newline: the newline is added first, the last line is not glued to the new one", (rc, m is not None), (0, True))
    d = folder(tmp, "a4", b"A=1\r\nLAST=2")
    rc, out, err = run("apply", d, Fake())
    m = re.fullmatch(rb"A=1\r\nLAST=2\r\nGRAFANA_DB_RO_PASSWORD=[0-9a-f]{48}\r\n", env_of(d))
    check("apply: a .env with CRLF keeps CRLF", (rc, m is not None), (0, True))
    d = folder(tmp, "a5", b"")
    rc, out, err = run("apply", d, Fake())
    check("apply: an empty .env gets just the line", (rc, re.fullmatch(rb"GRAFANA_DB_RO_PASSWORD=[0-9a-f]{48}\n", env_of(d)) is not None), (0, True))

    # the value forms of an existing line
    d = folder(tmp, "a6", ('GRAFANA_DB_RO_PASSWORD="%s"\n' % PW).encode())
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply: a value in double quotes is used without the quotes", (rc, fake.mysql_inputs()), (0, [SQL_FOR % (PW, PW)]))
    d = folder(tmp, "a7", ("GRAFANA_DB_RO_PASSWORD=%s\nGRAFANA_DB_RO_PASSWORD=%s\n" % ("o" * 20, PW)).encode())
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply: when the line is twice in .env the last one is used (as in a dotenv file)", (rc, fake.mysql_inputs()), (0, [SQL_FOR % (PW, PW)]))
    d = folder(tmp, "a8", b"GRAFANA_DB_RO_PASSWORD=it's$x\nZ=1\n")
    before = env_of(d)
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply: a value with a quote or `$` stops before anything is sent, .env not changed, the value not shown",
          (rc, fake.mysql_inputs(), env_of(d) == before, "it's" in out), (1, [], True, False))
    d = folder(tmp, "a9", b"GRAFANA_DB_RO_PASSWORD=short\n")
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply: a value shorter than 16 characters stops", (rc, fake.mysql_inputs()), (1, []))

    # ---------------------------------------------------------------- the syntax of the .env file (docker_variable_interpolation.md, section `.env` file syntax)
    cases = [
        ("export prefix", "export GRAFANA_DB_RO_PASSWORD=%s\n" % PW, True),
        ("single quotes", "GRAFANA_DB_RO_PASSWORD='%s'\n" % PW, True),
        ("single quotes, then a comment", "GRAFANA_DB_RO_PASSWORD='%s' # c\n" % PW, True),
        ("double quotes, then a comment", 'GRAFANA_DB_RO_PASSWORD="%s" # c\n' % PW, True),
        ("unquoted, a space, then # comment", "GRAFANA_DB_RO_PASSWORD=%s # c\n" % PW, True),
        ("unquoted, several spaces, then # comment", "GRAFANA_DB_RO_PASSWORD=%s    # c\n" % PW, True),
        ("colon as the delimiter", "GRAFANA_DB_RO_PASSWORD: %s\n" % PW, True),
        ("spaces around = and after the value", "GRAFANA_DB_RO_PASSWORD = %s   \n" % PW, True),
        ("a UTF-8 byte order mark before the first line", "\ufeffGRAFANA_DB_RO_PASSWORD=%s\n" % PW, True),
        ("a tab before # (Compose keeps the tab and the comment as the value)", "GRAFANA_DB_RO_PASSWORD=%s\t# c\n" % PW, False),
        ("# glued to the value (not a comment)", "GRAFANA_DB_RO_PASSWORD=%s# c\n" % PW, False),
        ("text after the closing quote", 'GRAFANA_DB_RO_PASSWORD="%s"x\n' % PW, False),
        ("a # inside the quotes is part of the value", 'GRAFANA_DB_RO_PASSWORD="%s # c"\n' % PW, False),
        ("no closing quote", 'GRAFANA_DB_RO_PASSWORD="%s\n' % PW, False),
        ("a name that only starts like ours is another variable", "GRAFANA_DB_RO_PASSWORD_X=%s\n" % PW, "other"),
    ]
    for n, (label, line, expect) in enumerate(cases):
        d = folder(tmp, "e%d" % n, line.encode("utf-8"))
        before = env_of(d)
        fake = Fake()
        rc, out, err = run("apply", d, fake)
        if expect is True:
            check("the .env line is used: " + label, (rc, fake.mysql_inputs(), env_of(d) == before), (0, [SQL_FOR % (PW, PW)], True))
        elif expect is False:
            check("the .env line is refused, nothing sent, .env unchanged, value not shown: " + label, (rc, fake.mysql_inputs(), env_of(d) == before, PW in out + err), (1, [], True, False))
        else:
            check("a line of another variable is not ours (a new line is added): " + label, (rc, len(fake.mysql_inputs()), env_of(d).count(b"\nGRAFANA_DB_RO_PASSWORD=")), (0, 1, 1))
    for n_chars, ok in ((15, False), (16, True), (128, True), (129, False)):
        d = folder(tmp, "len%d" % n_chars, ("GRAFANA_DB_RO_PASSWORD=%s\n" % ("a" * n_chars)).encode())
        fake = Fake()
        rc, out, err = run("apply", d, fake)
        check("a value of %d characters is %s" % (n_chars, "used" if ok else "refused"), (rc, len(fake.mysql_inputs())), (0, 1) if ok else (1, 0))
    d = folder(tmp, "len_ds", ("GRAFANA_DB_RO_PASSWORD=%s\n" % ("A1_-" * 8)).encode())
    rc, out, err = run("apply", d, Fake())
    check("letters, digits, _ and - are allowed in a value", rc, 0)

    # the shell environment beats .env in Docker Compose (docker_variable_interpolation.md L64-L72)
    d = folder(tmp, "sh1", ("GRAFANA_DB_RO_PASSWORD=%s\n" % PW).encode())
    before = env_of(d)
    os.environ["GRAFANA_DB_RO_PASSWORD"] = "shell-value-%s" % PW[:12]
    try:
        fake = Fake()
        rc, out, err = run("plan", d, fake)
        check("plan: GRAFANA_DB_RO_PASSWORD set in the shell is a FAIL, and the value is not shown", (rc, "IS set" in out, "shell-value" in out + err, PW in out + err), (1, True, False, False))
        fake = Fake()
        rc, out, err = run("apply", d, fake)
        check("apply: GRAFANA_DB_RO_PASSWORD set in the shell stops before anything is sent or written", (rc, fake.mysql_inputs(), env_of(d) == before, "shell-value" in out + err), (1, [], True, False))
    finally:
        del os.environ["GRAFANA_DB_RO_PASSWORD"]
    rc, out, err = run("plan", d, Fake())
    check("plan: not set in the shell is fine", (rc, "is not set in the shell environment" in out), (0, True))

    # stops before a change
    d = folder(tmp, "b1", b"X=1\n")
    before = env_of(d)
    fake = Fake(info_rc=1)
    rc, out, err = run("apply", d, fake)
    check("apply: Docker not answering stops before .env or mysql is touched", (rc, env_of(d) == before, fake.mysql_inputs()), (1, True, []))
    fake = Fake(mysql_ps="")
    rc, out, err = run("apply", d, fake)
    check("apply: no running mysql stops before .env or mysql is touched", (rc, env_of(d) == before, fake.mysql_inputs()), (1, True, []))
    d = folder(tmp, "b2", with_env=False)
    fake = Fake()
    rc, out, err = run("apply", d, fake)
    check("apply: no .env file stops (no file is created, nothing is sent)", (rc, (d / ".env").exists(), fake.mysql_inputs()), (1, False, []))

    # ---------------------------------------------------------------- 2: errors print only the number
    d = folder(tmp, "c1", ("GRAFANA_DB_RO_PASSWORD=%s\n" % PW).encode())
    fake = Fake(exec_mode="echo")
    rc, out, err = run("apply", d, fake)
    check("a mysql that writes the statement into its error: exit 1, only `ERROR 1396` is printed", (rc, "ERROR 1396" in out), (1, True))
    check("... and the value is in no output, no error output, no argument", no_secret(PW, out, err, fake), True)
    check("... and no part of the statement is printed (CREATE USER / IDENTIFIED / Operation)", any(w in out + err for w in ("IDENTIFIED", "Operation", "near:", "ALTER USER")), False)
    fake = Fake(exec_mode="echo_no_number")
    rc, out, err = run("apply", d, fake)
    check("an error without a number whose text is the standard input: exit 1, nothing of the text is printed", (rc, no_secret(PW, out, err, fake), "could not run" in out + err, "IDENTIFIED" in out + err), (1, True, False, False))
    fake = Fake(exec_mode="echo_rc0")
    rc, out, err = run("apply", d, fake)
    check("a warning that repeats the statement while the exit code is 0 is not printed", (rc, no_secret(PW, out, err, fake)), (0, True))
    fake = Fake(exec_mode="error_rc0")
    rc, out, err = run("apply", d, fake)
    check("an ERROR line in the error output while the exit code is 0 is an error too: exit 1, only the number", (rc, "ERROR 1007" in out, no_secret(PW, out, err, fake)), (1, True, True))
    fake = Fake(exec_mode="root_refused")
    rc, out, err = run("apply", d, fake)
    check("root refused: only `ERROR 1045` is printed, not the message of mysql", (rc, "ERROR 1045" in out, "Access denied" in out + err), (1, True, False))
    check("after a mysql error the .env line stays (the next apply uses it)", env_of(d), ("GRAFANA_DB_RO_PASSWORD=%s\n" % PW).encode())
    d = folder(tmp, "c2", b"A=1\n")
    fake = Fake(exec_mode="echo")
    rc, out, err = run("apply", d, fake)
    mm = re.search(rb"GRAFANA_DB_RO_PASSWORD=([0-9a-f]+)", env_of(d))
    made = mm.group(1).decode() if mm else "?"
    check("an error after a made value: the made value is in no output, no argument", (rc, no_secret(made, out, err, fake)), (1, True))

    # ---------------------------------------------------------------- 5: status
    d = folder(tmp, "s1", ("GRAFANA_DB_RO_PASSWORD=%s\n" % PW).encode())
    before = env_of(d)
    fake = Fake()
    rc, out, err = run("status", d, fake)
    check("status, all good: exit 0 and the last line", (rc, out.strip().splitlines()[-1]), (0, "status: all 2 checks passed"))
    check("status prints the counts: grafana_ro 2, merico 0, and the records of the start script", ("grafana_ro 2 (want 1 or more), merico 0 (want 0)" in out,
          "`Datasource created successfully` 1" in out, "`Datasource already exists; keeping existing one` 1" in out, "`POST /api/datasources status=409` 1" in out), (True,) * 4)
    check("status counts the request-log lines by method and path (a GET with status 409 is not counted) and the DELETE with 404",
          ("`DELETE /api/datasources/<id> status=404` 1" in out, "start script" in out and "request log" in out), (True, True))
    check("status changes nothing: .env unchanged, no CREATE / ALTER / GRANT, no compose up", (env_of(d) == before, [s for s in fake.mysql_inputs() if not s.startswith("SHOW")],
          [c for c in fake.calls if c[0][:2] == ["compose", "up"]]), (True, [], []))
    check("status sends exactly SHOW GRANTS FOR 'grafana_ro'@'%' and SHOW PROCESSLIST", fake.mysql_inputs(), ["SHOW GRANTS FOR 'grafana_ro'@'%';\n", "SHOW PROCESSLIST;\n"])
    check("status: inspect only with --format and a Go-template field (never the environment of the container)",
          [c[0] for c in fake.calls if c[0][0] == "inspect"], [["inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", "gid"],
                                                              ["inspect", "--format", "{{.State.StartedAt}}", "gid"]])
    check("status never prints a row of the processlist (the Info column can hold a statement)", "SHOW PROCESSLIST" in out or "Sleep" in out or "root" in out, False)
    check("status: the value is in no output", no_secret(PW, out, err, fake), True)

    def status_with(**kw):
        return run("status", d, Fake(**kw))

    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO `grafana_ro`@`%`\nGRANT SELECT ON `lake`.* TO `grafana_ro`@`%`\nGRANT INSERT ON `lake`.* TO `grafana_ro`@`%`\n")
    check("status: a third grant line (INSERT) is a FAIL", (rc, "got 3 line(s)" in out), (1, True))
    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO `grafana_ro`@`%`\nGRANT SELECT, INSERT ON `lake`.* TO `grafana_ro`@`%`\n")
    check("status: SELECT, INSERT in the second line is a FAIL", rc, 1)
    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO `grafana_ro`@`%`\n")
    check("status: only the USAGE line is a FAIL", rc, 1)
    rc, out, err = status_with(grants="GRANT SELECT ON `lake`.* TO `grafana_ro`@`%`\n")
    check("status: only the SELECT line is a FAIL", rc, 1)
    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO 'grafana_ro'@'%'\nGRANT SELECT ON lake.* TO 'grafana_ro'@'%'\n")
    check("status: the lines in the form with plain quotes (not the form that MySQL prints) are a FAIL", rc, 1)
    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO `grafana_ro`@`%`\nGRANT SELECT ON `lake`.* TO `grafana_ro`@`%`\nGRANT ALL PRIVILEGES ON *.* TO `grafana_ro`@`%`\n")
    check("status: ALL PRIVILEGES in addition is a FAIL", rc, 1)
    rc, out, err = status_with(grants="GRANT USAGE ON *.* TO `grafana_ro`@`%`\nGRANT SELECT ON `other`.* TO `grafana_ro`@`%`\n")
    check("status: SELECT on another database is a FAIL", rc, 1)
    rc, out, err = status_with(grants=(1141,))
    check("status: the user does not exist (ERROR 1141): a FAIL that prints the number", (rc, "ERROR 1141" in out), (1, True))
    rc, out, err = status_with(process="21\tgrafana_ro\t%s:40100\tlake\tSleep\t1\t\tNULL\n9\tmerico\t%s:40101\tlake\tSleep\t1\t\tNULL\n" % (GRAFANA_IP, GRAFANA_IP))
    check("status: a merico connection from the grafana container is a FAIL", (rc, "merico 1 (want 0)" in out, "grafana_ro 1" in out), (1, True, True))
    rc, out, err = status_with(process="9\tmerico\t%s:40101\tlake\tSleep\t1\t\tNULL\n" % GRAFANA_IP)
    check("status: no grafana_ro connection is a FAIL and says to open the screen first", (rc, "open the screen" in out), (1, True))
    rc, out, err = status_with(process="21\tgrafana_ro\t172.18.0.9:40100\tlake\tSleep\t1\t\tNULL\n")
    check("status: a grafana_ro connection from another IP does not count", (rc, "grafana_ro 0" in out), (1, True))
    rc, out, err = status_with(process="21\tgrafana_ro\t%s:40100\tlake\tSleep\t1\t\tNULL\n9\tmerico\t172.18.0.5:51000\tlake\tSleep\t3\t\tNULL\n" % GRAFANA_IP)
    check("status: a merico connection from another container (devlake) does not count; one grafana_ro connection is enough", rc, 0)
    rc, out, err = status_with(grafana_ps="")
    check("status: no running grafana container is a FAIL", (rc, "no running `grafana` container" in out), (1, True))
    rc, out, err = status_with(logs="nothing\n")
    check("status: the start-script lines are a record, zero counts are not a FAIL", (rc, "`POST /api/datasources status=409` 0" in out, "`Datasource already exists; keeping existing one` 0" in out), (0, True, True))
    rc, out, err = status_with(logs="some other already exists line\nPOST status=409\n")
    check("status: a line that only has `already exists` or `status=409` somewhere is not counted as the start script's", (rc, "`Datasource already exists; keeping existing one` 0" in out, "`POST /api/datasources status=409` 0" in out), (0, True, True))

for b in bad:
    print("FAIL " + b)
print("%d checks, %d failures" % (len(rows), len(bad)))
sys.exit(1 if bad else 0)
