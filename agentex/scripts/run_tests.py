#!/usr/bin/env python3
"""
Flexible test runner for AgentEx.
Automatically detects Docker environment and runs tests with pytest.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def ensure_test_dependencies():
    """Ensure test dependencies are installed."""
    print("📦 Checking test dependencies...")

    try:
        # Check if we can import pytest and testcontainers
        import pytest  # noqa: F401
        import testcontainers  # noqa: F401

        print("✅ Test dependencies are available")
        return True
    except ImportError:
        print("📥 Installing test dependencies...")
        try:
            subprocess.run(
                ["uv", "sync", "--group", "test"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("✅ Test dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install test dependencies: {e}")
            print("💡 Make sure 'uv' is installed and you're in the project root")
            return False


def detect_target_type(target):
    """Detect what type of test target was provided."""
    if not target:
        return "all"

    target_path = Path(target)
    if target_path.exists():
        if target_path.is_file():
            return "file"
        elif target_path.is_dir():
            return "directory"

    # If it contains :: it's likely a test class/method
    if "::" in target:
        return "test_method"

    # Otherwise treat as keyword pattern
    return "pattern"


def build_pytest_command(args):
    """Build pytest command from parsed arguments."""
    cmd = ["uv", "run", "--group", "test", "pytest"]

    # Add test target (file/directory) if specified
    if args.target:
        target_type = detect_target_type(args.target)
        if target_type in ["file", "directory"]:
            cmd.append(args.target)
        elif target_type == "test_method":
            cmd.append(args.target)
        elif target_type == "pattern":
            cmd.extend(["-k", args.target])

    # Add marker filter
    if args.marker:
        cmd.extend(["-m", args.marker])

    # Add keyword filter (this can be combined with target)
    if args.keyword:
        cmd.extend(["-k", args.keyword])

    # Add coverage options
    if args.cov:
        cmd.append(f"--cov={args.cov}")
        if args.cov_report:
            for report in args.cov_report:
                cmd.append(f"--cov-report={report}")
        else:
            # Default coverage reports
            cmd.extend(["--cov-report=term", "--cov-report=html"])

    # Add verbosity (default to some verbosity for better UX)
    if not any(arg.startswith("-v") or arg.startswith("--verbose") for arg in cmd):
        cmd.append("-v")

    # Add any additional pytest args
    if args.pytest_args:
        # Split the pytest_args string and add to command
        additional_args = args.pytest_args.split()
        cmd.extend(additional_args)

    return cmd


def setup_docker_environment():
    """Set up Docker environment using the test_setup script."""
    script_dir = Path(__file__).parent

    try:
        # Import and run the setup function directly to get env vars in this process
        import sys

        sys.path.insert(0, str(script_dir))
        from test_setup import detect_docker_environment
        from test_setup import setup_docker_environment as setup_docker_env

        environment = detect_docker_environment()
        if environment == "unknown":
            print("❌ Could not detect Docker environment")
            return False

        return setup_docker_env(environment)
    except Exception as e:
        print(f"❌ Docker environment setup failed: {e}")
        print("💡 Try running 'make test-docker-check' for detailed diagnostics")
        return False


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run tests with automatic Docker setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Run all tests
  %(prog)s tests/unit/                  # Run all unit tests
  %(prog)s tests/unit/test_foo.py       # Run specific file
  %(prog)s -k crud                      # Run tests matching 'crud'
  %(prog)s -m unit                      # Run tests with 'unit' marker
  %(prog)s --cov=src                    # Run with coverage
  %(prog)s tests/unit/ -k create        # Combine file and keyword filter
  %(prog)s --pytest-args="-s --tb=short" # Pass additional pytest args
        """,
    )

    # Positional argument for file/directory/pattern
    parser.add_argument(
        "target", nargs="?", help="Test file, directory, or test pattern to run"
    )

    # Test selection options
    parser.add_argument(
        "-m",
        "--marker",
        choices=["unit", "integration"],
        help="Run tests with specific marker only",
    )
    parser.add_argument("-k", "--keyword", help="Run tests matching keyword pattern")

    # Coverage options
    parser.add_argument(
        "--cov", help="Enable coverage for specified module (e.g., src)"
    )
    parser.add_argument(
        "--cov-report",
        action="append",
        choices=["term", "html", "xml", "json"],
        help="Coverage report format (can specify multiple)",
    )

    # Additional pytest arguments
    parser.add_argument(
        "--pytest-args", help="Additional pytest arguments (as quoted string)"
    )

    # Utility options
    parser.add_argument(
        "--no-docker-setup", action="store_true", help="Skip Docker environment setup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what command would be run without executing",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    # Ensure we're in the right directory (project root)
    if not Path("pyproject.toml").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)

    # Set up Docker environment unless explicitly skipped
    if not args.no_docker_setup:
        if not setup_docker_environment():
            sys.exit(1)

    # Ensure test dependencies are available
    if not ensure_test_dependencies():
        sys.exit(1)

    # Build the pytest command
    cmd = build_pytest_command(args)

    if args.dry_run:
        print("🔍 Would run command:")
        print("  " + " ".join(cmd))
        return

    # Display what we're about to run
    print("🧪 Running tests...")
    if args.target:
        target_type = detect_target_type(args.target)
        if target_type == "file":
            print(f"   Target: {args.target} (file)")
        elif target_type == "directory":
            print(f"   Target: {args.target} (directory)")
        elif target_type == "test_method":
            print(f"   Target: {args.target} (specific test)")
        elif target_type == "pattern":
            print(f"   Pattern: {args.target}")
    else:
        print("   Target: All tests")

    if args.marker:
        print(f"   Marker: {args.marker}")
    if args.keyword:
        print(f"   Keyword: {args.keyword}")
    if args.cov:
        print(f"   Coverage: {args.cov}")

    print()

    # Run the pytest command with current environment (including Docker env vars)
    try:
        # Pass current environment to subprocess so Docker env vars are inherited
        result = subprocess.run(cmd, env=os.environ.copy())
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
