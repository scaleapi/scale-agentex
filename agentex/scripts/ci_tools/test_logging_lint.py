"""Exercise the logging guard against real Ruff diagnostics."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import logging_lint


class LoggingLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.backend = self.root / "agentex"
        self.backend.mkdir()
        self.path = self.backend / "example.py"
        self.baseline = self.root / "baseline.json"
        self.ruff = os.environ.get("RUFF", "ruff")

    def write(self, body: str) -> None:
        self.path.write_text(
            "import logging\nlogger = logging.getLogger(__name__)\n" + body
        )

    def scan(self) -> list[logging_lint.Finding]:
        return logging_lint.scan(self.root, self.ruff)

    def save_baseline(self) -> None:
        logging_lint.write_baseline(self.baseline, logging_lint.counts(self.scan()))

    def check(self, *, update: bool = False) -> int:
        args = [
            "--root",
            str(self.root),
            "--baseline",
            str(self.baseline),
            "--ruff",
            self.ruff,
        ]
        if update:
            args.append("--update-baseline")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return logging_lint.main(args)

    def test_all_four_rules_and_parameterized_logging(self) -> None:
        self.write(
            'logger.info("value {}".format(value))\n'
            'logger.info("value %s" % value)\n'
            'logger.info("value " + value)\n'
            'logger.info(f"value {value}")\n'
            'logger.info("value %s", value)\n'
            'logger.info("value", extra={"value": value})\n'
        )
        self.assertEqual(
            {finding.code for finding in self.scan()}, {"G001", "G002", "G003", "G004"}
        )
        self.assertEqual(len(self.scan()), 4)

    def test_new_interpolation_in_existing_file_fails(self) -> None:
        self.write('logger.info(f"old {value}")\n')
        self.save_baseline()
        self.write('logger.info(f"old {value}")\nlogger.info(f"new {value}")\n')
        self.assertEqual(self.check(), 1)

    def test_duplicate_interpolation_fails(self) -> None:
        statement = 'logger.info(f"value {value}")\n'
        self.write(statement)
        self.save_baseline()
        self.write(statement * 2)
        self.assertEqual(self.check(), 1)

    def test_formatting_and_line_shifts_preserve_baseline(self) -> None:
        self.write('def run(value):\n    logger.info(f"value {value}")\n')
        self.save_baseline()
        self.write(
            "\n\ndef run(value):\n    logger.info(\n        f'value {value}'\n    )\n"
        )
        self.assertEqual(self.check(), 0)

    def test_moving_interpolation_to_another_function_fails(self) -> None:
        self.write('def old(value):\n    logger.info(f"value {value}")\n')
        self.save_baseline()
        self.write('def new(value):\n    logger.info(f"value {value}")\n')
        self.assertEqual(self.check(), 1)

    def test_changing_logger_call_fails(self) -> None:
        self.write('logger.info(f"value {value}")\n')
        self.save_baseline()
        self.write('logger.error(f"value {value}")\n')
        self.assertEqual(self.check(), 1)

    def test_baseline_can_shrink_but_cannot_grow(self) -> None:
        self.write('logger.info(f"old {value}")\n')
        self.save_baseline()
        original = self.baseline.read_text()
        self.write('logger.info(f"old {value}")\nlogger.info(f"new {value}")\n')
        self.assertEqual(self.check(update=True), 1)
        self.assertEqual(self.baseline.read_text(), original)
        self.write('logger.info("old %s", value)\n')
        self.assertEqual(self.check(), 1)
        self.assertEqual(self.check(update=True), 0)
        self.assertEqual(json.loads(self.baseline.read_text())["violations"], {})
        self.assertEqual(self.check(), 0)

    def test_ruff_configuration_noqa_and_gitignore_cannot_hide_new_logs(self) -> None:
        self.write('logger.info(f"value {value}")  # noqa: G004\n')
        (self.root / "pyproject.toml").write_text(
            '[tool.ruff]\nexclude = ["agentex"]\n'
        )
        (self.root / ".gitignore").write_text("agentex/\n")
        self.assertEqual(len(self.scan()), 1)

    def test_migrations_and_scripts_are_checked(self) -> None:
        for directory in ("database/migrations", "scripts"):
            path = self.backend / directory / "example.py"
            path.parent.mkdir(parents=True)
            path.write_text('import logging\nlogging.info(f"value {value}")\n')
        self.assertEqual(len(self.scan()), 2)

    def test_unicode_and_log_level_argument(self) -> None:
        self.write(
            'logger.log(logging.INFO, f"value {value}")\nlogger.info(f"café {value}")\n'
        )
        self.save_baseline()
        self.assertEqual(len(self.scan()), 2)
        self.assertEqual(self.check(), 0)

    def test_keyword_message_is_checked(self) -> None:
        self.write('logger.info(msg=f"value {value}")\n')
        self.save_baseline()
        self.assertEqual(len(self.scan()), 1)
        self.assertEqual(self.check(), 0)

    def test_syntax_error_fails_closed(self) -> None:
        self.write("def broken(:\n")
        with self.assertRaises(RuntimeError):
            self.scan()

    def test_missing_baseline_fails_closed(self) -> None:
        self.write('logger.info("value")\n')
        self.assertEqual(self.check(), 2)


if __name__ == "__main__":
    unittest.main()
