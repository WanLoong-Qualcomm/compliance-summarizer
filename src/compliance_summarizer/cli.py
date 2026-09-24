"""Command-line entry point for the compliance summarizer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from . import __version__
from .settings import SettingsError, create_default_settings, load_settings


def build_parser() -> argparse.ArgumentParser:
    """Build the baseline command-line parser."""

    return argparse.ArgumentParser(
        prog="compliance-summarizer",
        description="Generate deterministic compliance summaries.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the baseline command-line application."""

    parser = build_parser()
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    settings_path = Path("settings.json")
    created = create_default_settings(settings_path)
    if created:
        print(f"Created settings template at {settings_path}.")
        print("Complete the file before continuing with a compliance run.")
    else:
        print(f"Using existing settings file at {settings_path}.")
        try:
            load_settings(settings_path)
        except SettingsError as error:
            print(f"Settings error: {error}", file=sys.stderr)
            return 2
        print("Settings loaded successfully.")
    print(f"compliance-summarizer {__version__} (baseline)")
    return 0
