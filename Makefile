.PHONY: test fix triage

# Lint, format check, unit tests. Run before every commit.
test:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/python -m pytest -q

# Apply what ruff can fix (lint autofixes and formatting).
fix:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

# Score review findings with Jev: make triage FINDINGS=<scratch>/findings-1.json
triage:
	PYTHONPATH=. .venv/bin/python scripts/triage_findings.py $(FINDINGS)
