"""Command-line interface for the deterministic v0.2 application."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .app import run
from .config import create_settings_template
from .errors import ComplianceSummarizerError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compliance-summarizer",
        description="Generate a deterministic SIGPATH GAIN compliance report.",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path("settings.json"),
        help="settings.json path (default: ./settings.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("compliance-summary.html"),
        help="HTML report path (default: ./compliance-summary.html)",
    )
    parser.add_argument(
        "--init-settings",
        action="store_true",
        help="create a v0.2 settings template and exit",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output report",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.init_settings:
            created = create_settings_template(args.settings)
            print(f"Created settings template: {created.resolve()}")
            return 0
        analysis, output = run(
            args.settings,
            args.output,
            overwrite=args.overwrite,
        )
    except ComplianceSummarizerError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    main_stats = next(
        item
        for item in analysis.statistics.pivot_statistics
        if item.pivot == analysis.statistics.main_pivot
    )
    print(f"Processed {analysis.statistics.case_count} GAIN row(s).")
    print(
        f"{analysis.statistics.main_pivot} failures: {main_stats.failure_rate.numerator}/"
        f"{main_stats.failure_rate.denominator}."
    )
    print(f"Coverage warnings: {len(analysis.parsed.warnings)}.")
    print("AI generation: bypassed.")
    print(f"Report written to: {output}")
    return 0
