"""Lint Alembic migration files for dangerous Postgres patterns.

Companion to the runtime guardrails in
``agentex/database/migrations/alembic/env.py`` (default
``lock_timeout``/``statement_timeout``/``idle_in_transaction_session_timeout``).
Runtime timeouts catch lock contention and runaway statements at execution
time, but they do not catch patterns that finish inside the timeout on a quiet
hour while still taking a write outage — e.g. ``CREATE INDEX`` on an idle
window acquires its ``ShareLock`` instantly, holds it for the whole build, and
finishes cleanly while every writer queues. This linter catches those at PR
review.

The rule names mirror `squawk <https://github.com/sbdchd/squawk>`_'s rules so
reviewers can map the linter output to the broader Postgres-migration-safety
literature, but the implementation is a regex-level inspection of the Python
migration source — Alembic migrations are Python, so we stay at that level
rather than reconstructing the SQL.

Rules
-----

- ``prefer-robust-stmts``: ``op.create_index`` without
  ``postgresql_concurrently=True`` and ``op.create_foreign_key`` without
  ``postgresql_not_valid=True`` on populated tables block writers for the
  duration of the operation. Also catches the raw-SQL escape hatches
  ``op.execute("CREATE INDEX ...")`` (without ``CONCURRENTLY``) and
  ``op.execute("ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ...")``
  (without ``NOT VALID``).
- ``disallowed-unique-constraint``: ``op.create_unique_constraint`` builds the
  supporting index while blocking writes; create the index concurrently first
  and attach the constraint with ``USING INDEX``.
- ``adding-required-field``: ``op.add_column`` with ``nullable=False`` and
  ``server_default=`` rewrites the table to populate the value. Add the
  column nullable, backfill out of band, then add ``NOT NULL``.
- ``transaction-nesting``: a migration that calls
  ``postgresql_concurrently=True`` outside ``op.get_context().autocommit_block``
  will fail at runtime; a migration that mixes long DDL and concurrent index
  ops in a single transaction stacks locks.
- ``no-timeout-overrides`` (custom): forbids ``SET lock_timeout``,
  ``SET statement_timeout``, ``SET idle_in_transaction_session_timeout``, and
  ``RESET`` of those, so a migration cannot quietly disable the runtime
  guardrails. Narrow exception: ``SET statement_timeout`` is permitted
  *inside* an ``autocommit_block`` span — that is the supported escape valve
  for long ``CREATE INDEX CONCURRENTLY`` builds, since the default 30s
  session-level ``statement_timeout`` would otherwise abort the build and
  leave an INVALID index behind. ``RESET statement_timeout`` is **not**
  exempted: ``RESET`` falls back to the database / role / server default
  (typically ``0``, i.e. no timeout), which strips the runner's 30s ceiling
  for every later migration in the batch instead of restoring it. Authors
  must restore the ceiling with an explicit ``SET statement_timeout = '30s'``
  at the end of the block.
- ``in-band-backfill``: ``op.execute("UPDATE ...")`` or ``DELETE FROM`` inside
  a migration holds row locks for the entire transaction and prevents
  autovacuum from cleaning up. Move data backfills to an out-of-band
  operator runbook and keep migrations schema-only.

Escape hatch
------------

Per-finding bypass: add ``# noqa: migration-lint`` on the offending line. The
linter respects the marker and emits no finding for that line.

Wholesale bypass: set ``MIGRATION_UNSAFE_ACK=1`` in the environment running
the linter. The script then prints findings but exits 0. The
``migration-unsafe-ack`` PR label is the documented governance signal that
the suppression is approved — reviewers should treat it as a contract that
the PR description documents the maintenance window plan, expected blast
radius, and how the migration will be operated. Use it when the safe shape
genuinely cannot apply, not to ship faster.

Usage
-----

::

    # Lint changed migrations vs. origin/main:
    python agentex/scripts/ci_tools/migration_lint.py

    # Lint a specific file:
    python agentex/scripts/ci_tools/migration_lint.py --files path/to/migration.py

    # Lint every migration in the tree (sanity-check the corpus):
    python agentex/scripts/ci_tools/migration_lint.py --all
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations" / "alembic" / "versions"
ESCAPE_HATCH_ENV_VAR = "MIGRATION_UNSAFE_ACK"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str

    def format(self) -> str:
        rel: Path | str = self.path
        if self.path.is_absolute():
            try:
                rel = self.path.relative_to(REPO_ROOT.parent)
            except ValueError:
                rel = self.path
        return f"{rel}:{self.line}: [{self.rule}] {self.message}"


# Regex helpers --------------------------------------------------------------
#
# These intentionally over-flag rather than under-flag — false positives are
# resolved with ``# noqa: migration-lint`` on the offending line, or by
# applying the ``migration-unsafe-ack`` PR label when the unsafe shape is
# truly required.

_NOQA = re.compile(r"#\s*noqa:\s*migration-lint", re.IGNORECASE)
_OP_CREATE_TABLE = re.compile(r"\bop\.create_table\s*\(")
_OP_CREATE_INDEX = re.compile(r"\bop\.create_index\s*\(")
_OP_CREATE_FK = re.compile(r"\bop\.create_foreign_key\s*\(")
_OP_CREATE_UNIQUE = re.compile(r"\bop\.create_unique_constraint\s*\(")
_OP_ADD_COLUMN = re.compile(r"\bop\.add_column\s*\(")
_OP_EXECUTE = re.compile(r"\bop\.execute\s*\(")
_AUTOCOMMIT_BLOCK = re.compile(r"autocommit_block\s*\(")
_QUOTED_NAME = re.compile(r"""['"]([A-Za-z_][A-Za-z0-9_]*)['"]""")
_SET_TIMEOUT = re.compile(
    r"\bSET\s+(LOCAL\s+)?"
    r"(lock_timeout|statement_timeout|idle_in_transaction_session_timeout)\b",
    re.IGNORECASE,
)
_RESET_TIMEOUT = re.compile(
    r"\bRESET\s+"
    r"(lock_timeout|statement_timeout|idle_in_transaction_session_timeout)\b",
    re.IGNORECASE,
)
_DATA_BACKFILL = re.compile(
    # ``UPDATE\s+(?!SET\b)\w`` skips the ``UPDATE SET`` clause that appears
    # inside ``INSERT ... ON CONFLICT DO UPDATE SET`` upserts (a legitimate
    # schema-init pattern that should not flag in-band-backfill).
    r"\b(?:UPDATE\s+(?!SET\b)\w|DELETE\s+FROM\b)",
    re.IGNORECASE,
)
_RAW_BLOCKING_INDEX = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b(?!\s+CONCURRENTLY)",
    re.IGNORECASE,
)
_RAW_VALIDATING_FK = re.compile(
    r"\bADD\s+CONSTRAINT\b(?:[^;]*?\bFOREIGN\s+KEY\b)(?![^;]*?\bNOT\s+VALID\b)",
    re.IGNORECASE | re.DOTALL,
)
_RAW_CONCURRENT_INDEX = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\b",
    re.IGNORECASE,
)
# Extract the target table from raw-SQL ``CREATE INDEX … ON tbl`` and
# ``ALTER TABLE tbl ADD CONSTRAINT …`` so the fresh-tables exclusion that
# already applies to the helper-call paths also covers raw-SQL escape
# hatches. Strips optional schema-qualification quotes / backticks; bare
# identifiers only (matches the helper-path behavior).
_RAW_INDEX_TARGET = re.compile(
    r"\bON\s+(?:ONLY\s+)?[\"`]?([A-Za-z_][A-Za-z0-9_]*)[\"`]?",
    re.IGNORECASE,
)
_RAW_FK_TARGET = re.compile(
    r"\bALTER\s+TABLE\s+(?:ONLY\s+)?[\"`]?([A-Za-z_][A-Za-z0-9_]*)[\"`]?",
    re.IGNORECASE,
)
# Extract the target table from raw-SQL ``UPDATE tbl …`` and
# ``DELETE FROM tbl …`` so the fresh-tables exclusion covers data backfills
# on tables created in the same migration (a seed/cleanup pattern that has
# no writers to block). Skips ``UPDATE SET`` (the upsert clause), matching
# the behavior of ``_DATA_BACKFILL``.
_RAW_BACKFILL_TARGET = re.compile(
    r"\b(?:UPDATE\s+(?!SET\b)|DELETE\s+FROM\s+)(?:ONLY\s+)?[\"`]?([A-Za-z_][A-Za-z0-9_]*)[\"`]?",
    re.IGNORECASE,
)
# Kwarg detection regexes — tolerate whitespace around ``=`` so a migration
# author who writes ``postgresql_concurrently = True`` doesn't get a spurious
# finding. The previous literal-substring checks (``"x=True" in call``) would
# silently fail on the spaced form.
_KWARG_CONCURRENTLY_TRUE = re.compile(r"\bpostgresql_concurrently\s*=\s*True\b")
_KWARG_NOT_VALID_TRUE = re.compile(r"\bpostgresql_not_valid\s*=\s*True\b")
_KWARG_NULLABLE_FALSE = re.compile(r"\bnullable\s*=\s*False\b")
_KWARG_SERVER_DEFAULT = re.compile(r"\bserver_default\s*=")


def _slice_call(source: str, start: int) -> str:
    """Return the substring from ``start`` to the matching closing paren.

    Naive paren-balance walker — sufficient for the structurally-simple call
    sites Alembic autogenerate produces. If a migration uses a more exotic
    construction, the linter may over-flag; suppress with
    ``# noqa: migration-lint``.
    """
    depth = 0
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    return source[start:]


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _has_noqa(source: str, line: int) -> bool:
    lines = source.splitlines()
    if 0 < line <= len(lines):
        return bool(_NOQA.search(lines[line - 1]))
    return False


def _is_in_python_comment(source: str, pos: int) -> bool:
    """Return True if ``pos`` falls after a ``#`` on the same source line.

    Naive — does not account for ``#`` appearing inside a string literal — but
    Alembic migrations rarely embed ``#`` in SQL, and any false negative here
    just leaves the previous behavior unchanged. Used to keep regex-level
    rules from flagging text inside Python comments (e.g. a comment referencing
    a forbidden ``SET lock_timeout`` for documentation purposes).
    """
    line_start = source.rfind("\n", 0, pos) + 1
    return "#" in source[line_start:pos]


def _tables_created(source: str) -> set[str]:
    """Return the set of table names created via ``op.create_table`` in this
    migration.

    Indexes / foreign keys on freshly-created tables are inherently safe —
    there are no writers to block — so the rules that flag those operations
    skip targets in this set.
    """
    names: set[str] = set()
    for match in _OP_CREATE_TABLE.finditer(source):
        # Skip ``# op.create_table(...)`` shapes — a commented-out create_table
        # would otherwise pollute fresh_tables and silently mask findings on
        # the real table elsewhere in the file (false negative).
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        first = _QUOTED_NAME.search(call)
        if first:
            names.add(first.group(1))
    return names


def _second_quoted_name(call: str) -> str | None:
    """Return the second quoted identifier in a call snippet.

    For ``op.create_index("ix_foo", "foo", [...])`` this returns ``"foo"``.
    For ``op.create_foreign_key("fk", "child", "parent", ...)`` this returns
    ``"child"`` — the *child* table is the one taking the lock.
    """
    matches = _QUOTED_NAME.findall(call)
    return matches[1] if len(matches) >= 2 else None


# Individual rules -----------------------------------------------------------


def _check_prefer_robust_stmts(path: Path, source: str) -> Iterable[Finding]:
    fresh_tables = _tables_created(source)

    for match in _OP_CREATE_INDEX.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        if _KWARG_CONCURRENTLY_TRUE.search(call):
            continue
        target = _second_quoted_name(call)
        if target and target in fresh_tables:
            continue
        yield Finding(
            path=path,
            line=line,
            rule="prefer-robust-stmts",
            message=(
                "op.create_index without postgresql_concurrently=True takes "
                "ShareLock for the whole build and blocks writes. Use "
                "postgresql_concurrently=True inside an "
                "op.get_context().autocommit_block()."
            ),
        )

    for match in _OP_CREATE_FK.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        if _KWARG_NOT_VALID_TRUE.search(call):
            continue
        target = _second_quoted_name(call)
        if target and target in fresh_tables:
            continue
        yield Finding(
            path=path,
            line=line,
            rule="prefer-robust-stmts",
            message=(
                "op.create_foreign_key without postgresql_not_valid=True "
                "takes ShareRowExclusiveLock and full-scans the child "
                "table to validate. Add with postgresql_not_valid=True, "
                "then VALIDATE CONSTRAINT in a follow-up migration."
            ),
        )

    # Catch the raw-SQL escape hatches: developers copying ``CREATE INDEX`` /
    # ``ADD CONSTRAINT FOREIGN KEY`` from a DBA runbook into ``op.execute(...)``
    # would otherwise bypass every helper-level check above.
    for match in _OP_EXECUTE.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        # Skip ``# op.execute(...)`` shapes — a Python comment isn't executed,
        # so a finding here would force a `# noqa` on a line that does nothing.
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        if _RAW_BLOCKING_INDEX.search(call):
            target_match = _RAW_INDEX_TARGET.search(call)
            target = target_match.group(1) if target_match else None
            if not (target and target in fresh_tables):
                yield Finding(
                    path=path,
                    line=line,
                    rule="prefer-robust-stmts",
                    message=(
                        'op.execute("CREATE INDEX ...") without CONCURRENTLY '
                        "takes ShareLock for the whole build and blocks writes. "
                        "Use CREATE INDEX CONCURRENTLY inside an "
                        "op.get_context().autocommit_block()."
                    ),
                )
        if _RAW_VALIDATING_FK.search(call):
            target_match = _RAW_FK_TARGET.search(call)
            target = target_match.group(1) if target_match else None
            if not (target and target in fresh_tables):
                yield Finding(
                    path=path,
                    line=line,
                    rule="prefer-robust-stmts",
                    message=(
                        'op.execute("ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ...") '
                        "without NOT VALID takes ShareRowExclusiveLock and "
                        "full-scans the child table to validate. Add NOT VALID, "
                        "then VALIDATE CONSTRAINT in a follow-up migration."
                    ),
                )


def _check_disallowed_unique_constraint(path: Path, source: str) -> Iterable[Finding]:
    fresh_tables = _tables_created(source)
    for match in _OP_CREATE_UNIQUE.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        target = _second_quoted_name(call)
        if target and target in fresh_tables:
            continue
        yield Finding(
            path=path,
            line=line,
            rule="disallowed-unique-constraint",
            message=(
                "op.create_unique_constraint builds the index while blocking "
                "writes. Create a unique index concurrently and attach with "
                "ADD CONSTRAINT ... USING INDEX in a follow-up migration."
            ),
        )


def _check_adding_required_field(path: Path, source: str) -> Iterable[Finding]:
    fresh_tables = _tables_created(source)
    for match in _OP_ADD_COLUMN.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        # ``op.add_column("foo", sa.Column("x", ...))`` — the *first* quoted
        # name is the target table; second is the column. New tables have no
        # writers to block, so a NOT NULL + server_default add is safe there.
        target_match = _QUOTED_NAME.search(call)
        if target_match and target_match.group(1) in fresh_tables:
            continue
        if _KWARG_NULLABLE_FALSE.search(call) and _KWARG_SERVER_DEFAULT.search(call):
            yield Finding(
                path=path,
                line=line,
                rule="adding-required-field",
                message=(
                    "op.add_column with nullable=False and a server_default "
                    "rewrites the whole table. Add the column nullable, "
                    "backfill out of band, then ALTER ... SET NOT NULL in a "
                    "follow-up migration."
                ),
            )


def _is_autocommit_call(node: ast.expr) -> bool:
    """Return True if ``node`` is a call to ``autocommit_block``.

    Matches both attribute access (``op.get_context().autocommit_block()``)
    and bare name access (``autocommit_block()``) — the call site is the
    relevant signal, not the receiver chain.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "autocommit_block":
        return True
    if isinstance(func, ast.Name) and func.id == "autocommit_block":
        return True
    return False


def _autocommit_spans(source: str) -> list[tuple[int, int]]:
    """Return (start, end) byte-offset ranges enclosed by ``with ... autocommit_block():`` blocks.

    Uses the AST so the body boundary is the parser's view of the block —
    not an indentation heuristic that breaks on triple-quoted strings whose
    content starts at column 0 (e.g. ``op.execute(\"\"\"\\nCREATE TABLE...\"\"\")``)
    and would otherwise terminate the span early. Also handles the PEP 617
    parenthesized ``with`` form correctly.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    line_starts: list[int] = []
    pos = 0
    for ln in source.splitlines(keepends=True):
        line_starts.append(pos)
        pos += len(ln)
    line_starts.append(pos)  # sentinel: end-of-file offset

    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        if not any(_is_autocommit_call(item.context_expr) for item in node.items):
            continue
        if not node.body:
            continue
        first = node.body[0]
        last = node.body[-1]
        start_lineno = first.lineno  # 1-based
        end_lineno = getattr(last, "end_lineno", last.lineno) or last.lineno
        start_offset = (
            line_starts[start_lineno - 1]
            if start_lineno - 1 < len(line_starts)
            else pos
        )
        end_offset = line_starts[end_lineno] if end_lineno < len(line_starts) else pos
        spans.append((start_offset, end_offset))
    return spans


def _check_transaction_nesting(path: Path, source: str) -> Iterable[Finding]:
    """Flag each ``postgresql_concurrently=True`` call site that is not inside an
    ``autocommit_block``.

    Scans every concurrent-index occurrence individually rather than just
    asking whether ``autocommit_block`` appears anywhere in the file — a
    migration with two concurrent indexes where only one is wrapped would
    otherwise pass the linter and fail at runtime.
    """
    spans = _autocommit_spans(source)
    for match in _KWARG_CONCURRENTLY_TRUE.finditer(source):
        line = _line_of(source, match.start())
        if _is_in_python_comment(source, match.start()):
            continue
        if _has_noqa(source, line):
            continue
        if any(start <= match.start() < end for start, end in spans):
            continue
        yield Finding(
            path=path,
            line=line,
            rule="transaction-nesting",
            message=(
                "postgresql_concurrently=True must run inside "
                "`with op.get_context().autocommit_block():` — "
                "CREATE INDEX CONCURRENTLY cannot run inside a transaction."
            ),
        )

    # Raw-SQL escape hatch: ``op.execute("CREATE INDEX CONCURRENTLY ...")``
    # outside an autocommit_block also fails at runtime. The
    # ``prefer-robust-stmts`` raw-SQL check correctly excludes CONCURRENTLY
    # (since CONCURRENTLY is the *safe* form), so we'd otherwise miss it
    # entirely.
    for match in _OP_EXECUTE.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        if not _RAW_CONCURRENT_INDEX.search(call):
            continue
        if any(start <= match.start() < end for start, end in spans):
            continue
        yield Finding(
            path=path,
            line=line,
            rule="transaction-nesting",
            message=(
                'op.execute("CREATE INDEX CONCURRENTLY ...") must run inside '
                "`with op.get_context().autocommit_block():` — "
                "CREATE INDEX CONCURRENTLY cannot run inside a transaction."
            ),
        )


def _check_no_timeout_overrides(path: Path, source: str) -> Iterable[Finding]:
    spans = _autocommit_spans(source)

    def _inside_autocommit_block(offset: int) -> bool:
        return any(start <= offset < end for start, end in spans)

    for match in _SET_TIMEOUT.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        # `statement_timeout` may be overridden inside an autocommit_block —
        # that is the supported escape valve for long CREATE INDEX
        # CONCURRENTLY builds (the default 30s session ceiling applies inside
        # autocommit blocks too, since `autocommit_block` only changes the
        # transaction isolation, not session-level GUCs). Authors must
        # restore the ceiling with an explicit `SET statement_timeout = '30s'`
        # at the end of the block — RESET is intentionally not exempted
        # because it falls back to the database / role default (typically 0).
        timeout_name = (match.group(2) or "").lower()
        if timeout_name == "statement_timeout" and _inside_autocommit_block(
            match.start()
        ):
            continue
        yield Finding(
            path=path,
            line=line,
            rule="no-timeout-overrides",
            message=(
                "Migrations must not SET lock_timeout / statement_timeout / "
                "idle_in_transaction_session_timeout — those are configured "
                "by the migration runner. Apply the migration-unsafe-ack PR "
                "label if a maintenance window genuinely requires it. "
                "(Exception: SET statement_timeout is permitted inside an "
                "autocommit_block for long CREATE INDEX CONCURRENTLY builds.)"
            ),
        )

    for match in _RESET_TIMEOUT.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        yield Finding(
            path=path,
            line=line,
            rule="no-timeout-overrides",
            message=(
                "Migrations must not RESET lock_timeout / statement_timeout / "
                "idle_in_transaction_session_timeout — runtime guardrails "
                "must remain in effect for the whole migration. RESET falls "
                "back to the database / role / server default (typically 0, "
                "i.e. no timeout), so it does not restore the runner's 30s "
                "ceiling. Inside an autocommit_block, restore the ceiling "
                "with an explicit `SET statement_timeout = '30s'` instead."
            ),
        )


def _check_in_band_backfill(path: Path, source: str) -> Iterable[Finding]:
    """Flag ``op.execute(...)`` calls whose SQL contains an UPDATE or DELETE FROM.

    Data backfills run inside the migration transaction, hold row locks for
    its full duration, and prevent autovacuum from reclaiming dead tuples.
    They belong in an out-of-band operator runbook, not in the migration.

    Skips backfills targeting tables created in the same migration (seed-data
    or staging-cleanup patterns) — there are no other writers to block, and
    the autovacuum concern is negligible on a fresh table.
    """
    fresh_tables = _tables_created(source)
    for match in _OP_EXECUTE.finditer(source):
        line = _line_of(source, match.start())
        if _has_noqa(source, line):
            continue
        if _is_in_python_comment(source, match.start()):
            continue
        call = _slice_call(source, match.start())
        if _DATA_BACKFILL.search(call):
            target_match = _RAW_BACKFILL_TARGET.search(call)
            target = target_match.group(1) if target_match else None
            if target and target in fresh_tables:
                continue
            yield Finding(
                path=path,
                line=line,
                rule="in-band-backfill",
                message=(
                    "op.execute() containing UPDATE / DELETE FROM holds row "
                    "locks for the entire migration transaction and prevents "
                    "autovacuum from cleaning up. Move data backfills to an "
                    "out-of-band operator runbook and keep the migration "
                    "schema-only."
                ),
            )


_RULES = (
    _check_prefer_robust_stmts,
    _check_disallowed_unique_constraint,
    _check_adding_required_field,
    _check_transaction_nesting,
    _check_no_timeout_overrides,
    _check_in_band_backfill,
)


def lint_file(path: Path) -> list[Finding]:
    source = path.read_text()
    findings: list[Finding] = []
    for rule in _RULES:
        findings.extend(rule(path, source))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


# File discovery ------------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _changed_migrations(base: str) -> list[Path]:
    """Migration files changed vs ``base`` (added or modified)."""
    try:
        # Three-dot diff matches what reviewers see on the PR.
        out = _git("diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD")
    except subprocess.CalledProcessError:
        # Fall back to two-dot diff if the merge base cannot be computed
        # (e.g. shallow clone in CI without that history).
        out = _git("diff", "--name-only", "--diff-filter=AM", base)
    # `git diff --name-only` returns paths relative to the actual git
    # top-level, not REPO_ROOT (which is the package root). Resolve the
    # toplevel explicitly so this keeps working if the package is moved
    # within the repo (instead of silently producing nonexistent
    # candidates and linting nothing).
    git_toplevel = Path(_git("rev-parse", "--show-toplevel").strip())
    paths: list[Path] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        candidate = (git_toplevel / line).resolve()
        if not candidate.exists():
            continue
        try:
            rel = candidate.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if (
            rel.parts[:4]
            == (
                "database",
                "migrations",
                "alembic",
                "versions",
            )
            and rel.suffix == ".py"
        ):
            paths.append(candidate)
    return paths


def _all_migrations() -> list[Path]:
    return sorted(p for p in MIGRATIONS_DIR.glob("*.py") if p.name != "__init__.py")


# CLI -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--base",
        default=os.environ.get("MIGRATION_LINT_BASE", "origin/main"),
        help="Git ref to diff against when discovering changed migrations.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Lint every migration in the versions/ directory.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Lint specific migration files instead of computing the diff.",
    )
    args = parser.parse_args(argv)

    if args.all:
        paths = _all_migrations()
    elif args.files:
        paths = [Path(p).resolve() for p in args.files]
    else:
        paths = _changed_migrations(args.base)

    if not paths:
        print("migration_lint: no changed migration files to inspect.")
        return 0

    findings: list[Finding] = []
    for path in paths:
        findings.extend(lint_file(path))

    if not findings:
        print(f"migration_lint: {len(paths)} migration(s) inspected, no findings.")
        return 0

    ack = os.environ.get(ESCAPE_HATCH_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    header = (
        "migration_lint: findings (escape hatch active — migration-unsafe-ack)"
        if ack
        else "migration_lint: findings"
    )
    print(header, file=sys.stderr)
    for finding in findings:
        print(finding.format(), file=sys.stderr)

    if ack:
        print(
            "\nmigration_lint: migration-unsafe-ack acknowledged; not failing.",
            file=sys.stderr,
        )
        return 0

    print(
        "\nmigration_lint: failing build. Fix the issues above, suppress with "
        "`# noqa: migration-lint` on the offending line, or apply the "
        "`migration-unsafe-ack` PR label after explaining the maintenance "
        "window in the PR description.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
