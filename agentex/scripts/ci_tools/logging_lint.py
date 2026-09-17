"""Reject new Ruff G001–G004 violations while existing calls are cleaned up."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

RULES = ("G001", "G002", "G003", "G004")
BASELINE = Path("agentex/scripts/ci_tools/logging_baseline.json")


@dataclass(frozen=True)
class Finding:
    key: str
    path: str
    row: int
    code: str
    message: str


def _contains(node: ast.AST, start: tuple[int, int], end: tuple[int, int]) -> bool:
    return (node.lineno, node.col_offset) <= start and (
        node.end_lineno,
        node.end_col_offset,
    ) >= end


def _fingerprint(source: str, diagnostic: dict) -> str:
    lines = source.splitlines()

    def position(location: dict) -> tuple[int, int]:
        row, column = location["row"], location["column"]
        return row, len(lines[row - 1][: column - 1].encode("utf-8"))

    start = position(diagnostic["location"])
    end = position(diagnostic["end_location"])
    matches = []

    def visit(node: ast.AST, scope: tuple[str, ...] = ()) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = (*scope, node.name)
        if isinstance(node, ast.Call) and any(
            _contains(arg, start, end)
            for arg in [*node.args, *(keyword.value for keyword in node.keywords)]
        ):
            matches.append((node, scope))
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(ast.parse(source))
    if not matches:
        raise RuntimeError("Could not locate the logging call for a Ruff diagnostic")
    call, scope = min(
        matches,
        key=lambda match: (
            match[0].end_lineno - match[0].lineno,
            match[0].end_col_offset - match[0].col_offset,
        ),
    )
    payload = json.dumps([scope, ast.dump(call, include_attributes=False)])
    return hashlib.sha256(payload.encode()).hexdigest()


def scan(root: Path, ruff: str = "ruff") -> list[Finding]:
    root = root.resolve()
    result = subprocess.run(
        [
            ruff,
            "check",
            "--isolated",
            "--no-cache",
            "--no-respect-gitignore",
            "--ignore-noqa",
            "--target-version=py312",
            "--select=" + ",".join(RULES),
            "--output-format=json",
            "agentex",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Ruff failed: {result.stderr.strip()}")
    findings = []
    sources = {}
    for diagnostic in json.loads(result.stdout):
        if diagnostic["code"] not in RULES:
            raise RuntimeError(
                f"Ruff could not check the backend: {diagnostic['message']}"
            )
        filename = Path(diagnostic["filename"])
        path = filename.relative_to(root).as_posix()
        if path not in sources:
            sources[path] = filename.read_text()
        digest = _fingerprint(sources[path], diagnostic)
        code = diagnostic["code"]
        findings.append(
            Finding(
                key=f"{path}:{code}:{digest}",
                path=path,
                row=diagnostic["location"]["row"],
                code=code,
                message=diagnostic["message"],
            )
        )
    return findings


def counts(findings: list[Finding]) -> Counter[str]:
    return Counter(finding.key for finding in findings)


def read_baseline(path: Path) -> Counter[str]:
    data = json.loads(path.read_text())
    if data.get("version") != 1 or not isinstance(data.get("violations"), dict):
        raise ValueError("Invalid logging baseline format")
    if any(
        type(value) is not int or value < 1 for value in data["violations"].values()
    ):
        raise ValueError("Baseline counts must be positive integers")
    return Counter(data["violations"])


def write_baseline(path: Path, violations: Counter[str]) -> None:
    path.write_text(
        json.dumps(
            {"version": 1, "violations": dict(violations)}, indent=2, sort_keys=True
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--ruff", default="ruff")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Remove resolved violations; never add new ones",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline_path = root / args.baseline
    try:
        baseline = read_baseline(baseline_path)
        findings = scan(root, args.ruff)
        current = counts(findings)
        unexpected = current - baseline
        if unexpected:
            for finding in findings:
                if unexpected[finding.key]:
                    print(
                        f"{finding.path}:{finding.row}: {finding.code} {finding.message}",
                        file=sys.stderr,
                    )
                    unexpected[finding.key] -= 1
            print(
                "Use a constant log message with arguments or extra fields.",
                file=sys.stderr,
            )
            return 1
        if args.update_baseline:
            write_baseline(baseline_path, current)
        elif baseline - current:
            print(
                "Resolved logging violations: run this command with --update-baseline.",
                file=sys.stderr,
            )
            return 1
        print(
            f"Logging guard passed; {sum(current.values())} existing violations remain."
        )
        return 0
    except (OSError, ValueError, RuntimeError, SyntaxError) as error:
        print(f"Logging guard failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
