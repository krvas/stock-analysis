.PHONY: test fix jev

# Lint, format check, unit tests. Run before every commit. tests/conftest.py
# drops every GIT_* variable, so pytest needs no env scrub here.
test:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/python -m pytest -q
	.venv/bin/python -m pytest -m data -q

# Apply what ruff can fix (lint autofixes and formatting).
fix:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

# Ask Jev for one pstack decision: make jev KIND=<kind> INPUT=<path.json>
# Kinds and their input formats: scripts/jev_decide.py --help
jev:
	PYTHONPATH=. .venv/bin/python scripts/jev_decide.py $(KIND) $(INPUT)
