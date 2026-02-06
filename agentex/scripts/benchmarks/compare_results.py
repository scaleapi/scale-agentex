#!/usr/bin/env python3
"""
Compare benchmark results between MongoDB and PostgreSQL.

Usage:
    python scripts/benchmarks/compare_results.py results/mongodb.json results/postgres.json
"""

import argparse
import json
import sys
from pathlib import Path


def load_results(path: Path) -> dict:
    """Load benchmark results from JSON file."""
    with open(path) as f:
        return json.load(f)


def find_scenario(
    scenarios: list[dict], concurrency: int, state_size: int
) -> dict | None:
    """Find a scenario matching the given parameters."""
    for s in scenarios:
        if s["concurrency"] == concurrency and s["state_size"] == state_size:
            return s
    return None


def format_percent_diff(base: float, comparison: float) -> str:
    """Format percentage difference with indicator."""
    if base == 0:
        return "N/A"
    diff = ((comparison - base) / base) * 100
    indicator = "+" if diff > 0 else ""
    return f"{indicator}{diff:.1f}%"


def generate_comparison_report(mongodb_results: dict, postgres_results: dict) -> str:
    """Generate a markdown comparison report."""
    lines = []
    lines.append("# Task State Storage Benchmark Comparison")
    lines.append("")
    lines.append(
        f"**MongoDB timestamp**: {mongodb_results.get('metadata', {}).get('timestamp', 'N/A')}"
    )
    lines.append(
        f"**PostgreSQL timestamp**: {postgres_results.get('metadata', {}).get('timestamp', 'N/A')}"
    )
    lines.append("")

    # Get all unique concurrency and state size combinations
    mongo_scenarios = mongodb_results.get("scenarios", [])
    postgres_scenarios = postgres_results.get("scenarios", [])

    concurrencies = sorted({s["concurrency"] for s in mongo_scenarios})
    state_sizes = sorted({s["state_size"] for s in mongo_scenarios})

    # Summary section
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | MongoDB | PostgreSQL | Winner |")
    lines.append("|--------|---------|------------|--------|")

    # Calculate overall averages
    mongo_p50_avg = 0
    postgres_p50_avg = 0
    mongo_throughput_avg = 0
    postgres_throughput_avg = 0
    count = 0

    for s in mongo_scenarios:
        for _op, metrics in s.get("operations", {}).items():
            mongo_p50_avg += metrics.get("p50_ms", 0)
            count += 1
        mongo_throughput_avg += s.get("ops_per_second", 0)

    for s in postgres_scenarios:
        for _op, metrics in s.get("operations", {}).items():
            postgres_p50_avg += metrics.get("p50_ms", 0)
        postgres_throughput_avg += s.get("ops_per_second", 0)

    if count > 0:
        mongo_p50_avg /= count
        postgres_p50_avg /= count
        mongo_throughput_avg /= len(mongo_scenarios) if mongo_scenarios else 1
        postgres_throughput_avg /= len(postgres_scenarios) if postgres_scenarios else 1

    p50_winner = "MongoDB" if mongo_p50_avg < postgres_p50_avg else "PostgreSQL"
    throughput_winner = (
        "MongoDB" if mongo_throughput_avg > postgres_throughput_avg else "PostgreSQL"
    )

    lines.append(
        f"| Avg P50 Latency | {mongo_p50_avg:.2f} ms | {postgres_p50_avg:.2f} ms | **{p50_winner}** |"
    )
    lines.append(
        f"| Avg Throughput | {mongo_throughput_avg:.0f} ops/s | {postgres_throughput_avg:.0f} ops/s | **{throughput_winner}** |"
    )
    lines.append("")

    # Detailed comparison per state size
    for state_size in state_sizes:
        lines.append(f"## State Size: {state_size} bytes")
        lines.append("")

        # Throughput table
        lines.append("### Throughput (ops/sec)")
        lines.append("")
        lines.append("| Concurrency | MongoDB | PostgreSQL | Diff |")
        lines.append("|-------------|---------|------------|------|")

        for conc in concurrencies:
            mongo_s = find_scenario(mongo_scenarios, conc, state_size)
            postgres_s = find_scenario(postgres_scenarios, conc, state_size)

            mongo_ops = mongo_s.get("ops_per_second", 0) if mongo_s else 0
            postgres_ops = postgres_s.get("ops_per_second", 0) if postgres_s else 0
            diff = format_percent_diff(mongo_ops, postgres_ops)

            lines.append(f"| {conc} | {mongo_ops:.0f} | {postgres_ops:.0f} | {diff} |")

        lines.append("")

        # Per-operation latency comparison
        lines.append("### Latency by Operation (P50 ms)")
        lines.append("")

        # Get all operations
        operations = set()
        for s in mongo_scenarios + postgres_scenarios:
            operations.update(s.get("operations", {}).keys())
        operations = sorted(operations)

        for conc in concurrencies:
            lines.append(f"#### Concurrency: {conc}")
            lines.append("")
            lines.append("| Operation | MongoDB | PostgreSQL | Diff |")
            lines.append("|-----------|---------|------------|------|")

            mongo_s = find_scenario(mongo_scenarios, conc, state_size)
            postgres_s = find_scenario(postgres_scenarios, conc, state_size)

            for op in operations:
                mongo_metrics = (mongo_s or {}).get("operations", {}).get(op, {})
                postgres_metrics = (postgres_s or {}).get("operations", {}).get(op, {})

                mongo_p50 = mongo_metrics.get("p50_ms", 0)
                postgres_p50 = postgres_metrics.get("p50_ms", 0)
                diff = format_percent_diff(mongo_p50, postgres_p50)

                # Highlight the winner
                if mongo_p50 < postgres_p50 and mongo_p50 > 0:
                    mongo_cell = f"**{mongo_p50:.2f}**"
                    postgres_cell = f"{postgres_p50:.2f}"
                elif postgres_p50 < mongo_p50 and postgres_p50 > 0:
                    mongo_cell = f"{mongo_p50:.2f}"
                    postgres_cell = f"**{postgres_p50:.2f}**"
                else:
                    mongo_cell = f"{mongo_p50:.2f}"
                    postgres_cell = f"{postgres_p50:.2f}"

                lines.append(f"| {op} | {mongo_cell} | {postgres_cell} | {diff} |")

            lines.append("")

    # P99 latency comparison (important for production)
    lines.append("## P99 Latency Comparison")
    lines.append("")
    lines.append(
        "High-percentile latencies are critical for production. Lower is better."
    )
    lines.append("")

    for state_size in state_sizes:
        lines.append(f"### State Size: {state_size} bytes")
        lines.append("")
        lines.append(
            "| Concurrency | Operation | MongoDB P99 | PostgreSQL P99 | Winner |"
        )
        lines.append(
            "|-------------|-----------|-------------|----------------|--------|"
        )

        for conc in concurrencies:
            mongo_s = find_scenario(mongo_scenarios, conc, state_size)
            postgres_s = find_scenario(postgres_scenarios, conc, state_size)

            for op in operations:
                mongo_metrics = (mongo_s or {}).get("operations", {}).get(op, {})
                postgres_metrics = (postgres_s or {}).get("operations", {}).get(op, {})

                mongo_p99 = mongo_metrics.get("p99_ms", 0)
                postgres_p99 = postgres_metrics.get("p99_ms", 0)

                if mongo_p99 < postgres_p99 and mongo_p99 > 0:
                    winner = "MongoDB"
                elif postgres_p99 < mongo_p99 and postgres_p99 > 0:
                    winner = "PostgreSQL"
                else:
                    winner = "Tie"

                lines.append(
                    f"| {conc} | {op} | {mongo_p99:.2f} | {postgres_p99:.2f} | {winner} |"
                )

        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")

    if mongo_p50_avg < postgres_p50_avg * 0.9:
        lines.append(
            "- **MongoDB shows significantly better latency.** Consider staying with MongoDB unless PostgreSQL offers other benefits (consistency, transactions)."
        )
    elif postgres_p50_avg < mongo_p50_avg * 0.9:
        lines.append(
            "- **PostgreSQL shows significantly better latency.** Migration to PostgreSQL is recommended."
        )
    else:
        lines.append(
            "- **Performance is comparable.** Decision should be based on other factors (operational simplicity, data consistency requirements)."
        )

    if mongo_throughput_avg > postgres_throughput_avg * 1.2:
        lines.append(
            "- **MongoDB has higher throughput.** Important for high-scale scenarios."
        )
    elif postgres_throughput_avg > mongo_throughput_avg * 1.2:
        lines.append(
            "- **PostgreSQL has higher throughput.** Better for high-scale scenarios."
        )

    lines.append("")
    lines.append("---")
    lines.append("*Report generated by compare_results.py*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Compare MongoDB and PostgreSQL benchmark results"
    )
    parser.add_argument(
        "mongodb_results",
        type=str,
        help="Path to MongoDB benchmark results JSON",
    )
    parser.add_argument(
        "postgres_results",
        type=str,
        help="Path to PostgreSQL benchmark results JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: print to stdout)",
    )

    args = parser.parse_args()

    # Load results
    mongodb_path = Path(args.mongodb_results)
    postgres_path = Path(args.postgres_results)

    if not mongodb_path.exists():
        print(f"Error: MongoDB results file not found: {mongodb_path}")
        sys.exit(1)
    if not postgres_path.exists():
        print(f"Error: PostgreSQL results file not found: {postgres_path}")
        sys.exit(1)

    mongodb_results = load_results(mongodb_path)
    postgres_results = load_results(postgres_path)

    # Generate report
    report = generate_comparison_report(mongodb_results, postgres_results)

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)
        print(f"Report saved to {output_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
