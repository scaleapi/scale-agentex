"""Dump the FastAPI app's OpenAPI schema to a YAML file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ALLOWED_ORIGINS", "*")


def main() -> int:
    package_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        default=str(package_root / "openapi.yaml"),
        help="Path to write the OpenAPI YAML spec (default: ./openapi.yaml).",
    )
    args = parser.parse_args()

    import yaml
    from src.api.app import fastapi_app

    spec = fastapi_app.openapi()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        yaml.dump(spec, f, sort_keys=False, allow_unicode=True)

    print(f"Wrote OpenAPI spec to {output_path} ({output_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
