"""Compatibility entry point for the packaged CLI."""

from kline_fixer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
