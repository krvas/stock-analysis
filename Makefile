.PHONY: test test-data-long fix jev

# Lint, format check, unit tests. Run before every commit.
test:
	python3 scripts/link_worktree_files.py
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/python -m pytest -q
	REQUIRE_DATA_TESTS=1 .venv/bin/python -m pytest -m data -q

# Data tests only, over tests/data_test_tickers_long.txt.
test-data-long:
	python3 scripts/link_worktree_files.py
	REQUIRE_DATA_TESTS=1 DATA_TICKERS=long .venv/bin/python -m pytest -m data -q

# Apply what ruff can fix (lint autofixes and formatting).
fix:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

# Ask Jev for one pstack decision: make jev KIND=<kind> INPUT=<path.json>
# Kinds and their input formats: scripts/jev_decide.py --help
jev:
	PYTHONPATH=. .venv/bin/python scripts/jev_decide.py $(KIND) $(INPUT)
