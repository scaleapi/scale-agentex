"""Unit tests for the migration safety linter.

Covers each rule in ``scripts/ci_tools/migration_lint.py`` plus the escape
hatch and CLI entry point. Tests exercise the rule-level pure functions
directly so they are fast and deterministic — no git or filesystem state
beyond the temporary file the CLI invocation reads.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "ci_tools" / "migration_lint.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("migration_lint", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["migration_lint"] = module
    spec.loader.exec_module(module)
    return module


migration_lint = _load_module()


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "20260101_test.py"
    path.write_text(textwrap.dedent(source).lstrip())
    return path


# Rules ---------------------------------------------------------------------


def test_create_index_without_concurrently_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index("ix_foo_bar", "foo", ["bar"])
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "prefer-robust-stmts" for f in findings)


def test_create_index_on_fresh_table_passes(tmp_path: Path) -> None:
    """Indexing a table you just created in the same migration is safe."""
    path = _write(
        tmp_path,
        """
        from alembic import op
        import sqlalchemy as sa
        def upgrade():
            op.create_table("foo", sa.Column("id", sa.Integer(), primary_key=True))
            op.create_index("ix_foo_id", "foo", ["id"])
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_create_fk_on_fresh_table_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        import sqlalchemy as sa
        def upgrade():
            op.create_table("foo", sa.Column("bar_id", sa.Integer()))
            op.create_foreign_key(
                "fk_foo_bar", "foo", "bar", ["bar_id"], ["id"]
            )
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_create_unique_constraint_on_fresh_table_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        import sqlalchemy as sa
        def upgrade():
            op.create_table("foo", sa.Column("name", sa.String()))
            op.create_unique_constraint("uq_foo_name", "foo", ["name"])
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_create_index_concurrently_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            with op.get_context().autocommit_block():
                op.create_index(
                    "ix_foo_bar", "foo", ["bar"], postgresql_concurrently=True
                )
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_create_foreign_key_without_not_valid_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_foreign_key(
                "fk_foo_bar", "foo", "bar", ["x"], ["id"]
            )
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "prefer-robust-stmts" for f in findings)


def test_create_foreign_key_not_valid_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_foreign_key(
                "fk_foo_bar",
                "foo",
                "bar",
                ["x"],
                ["id"],
                postgresql_not_valid=True,
            )
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_create_unique_constraint_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_unique_constraint("uq_foo_bar", "foo", ["bar"])
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "disallowed-unique-constraint" for f in findings)


def test_add_column_not_null_with_server_default_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.add_column(
                "foo",
                sa.Column(
                    "baz",
                    sa.String(),
                    nullable=False,
                    server_default="x",
                ),
            )
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "adding-required-field" for f in findings)


def test_add_column_nullable_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.add_column("foo", sa.Column("baz", sa.String(), nullable=True))
        """,
    )
    assert migration_lint.lint_file(path) == []


def test_concurrently_outside_autocommit_block_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index(
                "ix_foo_bar", "foo", ["bar"], postgresql_concurrently=True
            )
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "transaction-nesting" for f in findings)


def test_concurrently_mixed_one_outside_one_inside_flags_only_outside(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index(
                "ix_foo_a", "foo", ["a"], postgresql_concurrently=True
            )
            with op.get_context().autocommit_block():
                op.create_index(
                    "ix_foo_b", "foo", ["b"], postgresql_concurrently=True
                )
        """,
    )
    findings = [
        f for f in migration_lint.lint_file(path) if f.rule == "transaction-nesting"
    ]
    assert len(findings) == 1, findings
    # The flagged occurrence is the one outside the autocommit_block — i.e.
    # the kwarg site of the first op.create_index, which is the lower-numbered
    # of the two postgresql_concurrently=True positions in the source.
    source_lines = path.read_text().splitlines()
    flagged_line = source_lines[findings[0].line - 1]
    assert "postgresql_concurrently=True" in flagged_line
    inside_lines = [
        i
        for i, line in enumerate(source_lines, start=1)
        if "postgresql_concurrently=True" in line
    ]
    assert findings[0].line == min(inside_lines)


def test_in_band_update_backfill_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("UPDATE foo SET x = 1 WHERE y IS NULL")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "in-band-backfill" for f in findings)


def test_in_band_delete_backfill_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("DELETE FROM foo WHERE created_at < now()")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "in-band-backfill" for f in findings)


def test_in_band_backfill_select_not_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("SELECT * FROM foo")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert all(f.rule != "in-band-backfill" for f in findings)


def test_set_lock_timeout_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("SET lock_timeout = '60s'")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "no-timeout-overrides" for f in findings)


def test_set_local_statement_timeout_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("SET LOCAL statement_timeout = '120s'")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "no-timeout-overrides" for f in findings)


def test_reset_lock_timeout_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("RESET lock_timeout")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert any(f.rule == "no-timeout-overrides" for f in findings)


def test_set_other_setting_not_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.execute("SET search_path = public")
        """,
    )
    findings = migration_lint.lint_file(path)
    assert all(f.rule != "no-timeout-overrides" for f in findings)


def test_noqa_suppresses_finding(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index("ix_foo_bar", "foo", ["bar"])  # noqa: migration-lint
        """,
    )
    assert migration_lint.lint_file(path) == []


# CLI -----------------------------------------------------------------------


def test_main_returns_zero_when_no_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(migration_lint, "_changed_migrations", lambda base: [])
    rc = migration_lint.main([])
    assert rc == 0


def test_main_returns_one_on_findings(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index("ix_foo_bar", "foo", ["bar"])
        """,
    )
    rc = migration_lint.main(["--files", str(path)])
    assert rc == 1


def test_main_escape_hatch_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIGRATION_UNSAFE_ACK", "1")
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            op.create_index("ix_foo_bar", "foo", ["bar"])
        """,
    )
    rc = migration_lint.main(["--files", str(path)])
    assert rc == 0


def test_main_specific_files_clean(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        from alembic import op
        def upgrade():
            with op.get_context().autocommit_block():
                op.create_index(
                    "ix_foo_bar", "foo", ["bar"], postgresql_concurrently=True
                )
        """,
    )
    rc = migration_lint.main(["--files", str(path)])
    assert rc == 0


def test_finding_format_relative_path(tmp_path: Path) -> None:
    finding = migration_lint.Finding(
        path=Path("agentex/database/migrations/alembic/versions/x.py"),
        line=42,
        rule="prefer-robust-stmts",
        message="hi",
    )
    assert finding.format().startswith(
        "agentex/database/migrations/alembic/versions/x.py:42:"
    )
