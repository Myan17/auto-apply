# auto-apply

Automated job application tool.

## Requirements

- Python 3.9+
- Git
- Browsers for Playwright (see below)

## Install

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

2. Install the package in editable mode (installs dependencies from pyproject.toml):

```bash
pip install -e .
```

3. Install Playwright browsers (required if using browser automation):

```bash
python -m playwright install
```

4. (Optional) Install dev dependencies for tests:

```bash
pip install -e .[dev]
```

## Configuration

- Copy or create a `.env` file (project uses `python-dotenv`) and provide required credentials and API keys (e.g., Anthropic, Google service account JSON path, etc.).
- Check `config/settings.yaml` for app-specific configuration.

## Running

- Show CLI help:

```bash
auto-apply --help
# or
python -m src.cli --help
```

- Run typical command (example):

```bash
auto-apply run
# or an appropriate subcommand per `--help`
```

## Tests

Run tests with pytest:

```bash
pytest
```

## Verify repository Git status (see everything tracked)

- Show working tree status (untracked files will appear):

```bash
git status --short
```

- List only untracked files:

```bash
git ls-files --others --exclude-standard
```

- List all tracked files in the repo:

```bash
git ls-files
```

- To ensure all files are added to git (review before running):

```bash
git add -A
git status --short
# then commit when ready
git commit -m "Add project files"
```

## Where to look in the code

- CLI entrypoint: `src/cli.py` (installed as the `auto-apply` console script from `pyproject.toml`).
- Main package code: `src/` (see `src/ai`, `applicator`, `scraper`, `documents`, `sheets`).
- Configuration: `config/settings.yaml`.

## Notes

- This README is minimal. If you want, I can add step-by-step examples for common flows (e.g., authenticating Google Sheets, setting API keys, or a sample run).
