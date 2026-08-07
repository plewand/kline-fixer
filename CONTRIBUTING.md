# Contributing to Kline Fixer

Thank you for helping improve Kline Fixer.

## Before you start

- Search existing issues before opening a new one.
- Use a bug report for reproducible defects and a feature request for proposed behavior.
- For substantial changes, open an issue first so the design can be discussed.
- Never include API keys, private market data, or other secrets in issues or commits.

## Development setup

```bash
git clone <repository-url>
cd KlineFixer
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Run the quality checks before submitting changes:

```bash
python -m pytest
ruff check .
```

## Pull requests

1. Create a focused branch from the default branch.
2. Add or update tests for behavior changes.
3. Update documentation and `CHANGELOG.md` when user-visible behavior changes.
4. Keep commits clear and avoid unrelated formatting changes.
5. Complete the pull-request template and ensure CI passes.

By contributing, you agree that your contribution is licensed under the repository's MIT License and that you will follow the Code of Conduct.
