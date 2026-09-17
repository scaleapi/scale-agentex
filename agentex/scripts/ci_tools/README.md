# Logging message check

The CI logging guard runs Ruff G001–G004 across backend Python files. These rules
reject `.format()`, `%` interpolation, string concatenation, and f-strings inside
logging calls. Use a constant message with separate fields:

```python
logger.info("Request completed", extra={"request_id": request_id})
```

Parameterized messages are also accepted:

```python
logger.info("Request %s completed", request_id)
```

Keep sensitive values out of the message, even when using parameters. A formatter
can remove structured fields; it cannot remove values already in message text.

Run the guard and its tests from the repository root:

```sh
uv run --frozen python agentex/scripts/ci_tools/logging_lint.py
uv run --frozen python -m unittest discover -s agentex/scripts/ci_tools -p test_logging_lint.py
```

`logging_baseline.json` records existing violations for gradual cleanup. Each
entry identifies the file, rule, enclosing function or class, and complete
logging call, with a count for repeated identical calls. It does not exempt
whole files. New or changed interpolated calls fail, including duplicates of an
existing call. Moving a call to a different function also requires fixing it;
formatting and line-number changes do not affect the check.

After replacing existing interpolation, remove the resolved entries:

```sh
uv run --frozen python agentex/scripts/ci_tools/logging_lint.py --update-baseline
```

The update command can only remove entries. Commit the smaller baseline with the
logging changes. Do not add entries to accept new interpolation. CI ignores Ruff
exclusions, per-file rule ignores, `noqa`, and `.gitignore` for this check. Ruff's
normal exclusions for generated and virtual-environment directories still apply.

CI uses Python 3.12 and Ruff 0.13.2, matching the backend's Python version and the
workspace lock. Update the CI pin together with the lock when updating Ruff.
