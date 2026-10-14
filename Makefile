.PHONY: test fix jev

# Runs a command with every GIT_* variable unset. The agent shell exports
# GIT_EDITOR and git rebase -x sets GIT_DIR; a test that runs git in a temp
# repo inherits them, and one once corrupted this repo's .git that way.
NO_GIT_ENV := env $(addprefix -u ,$(filter GIT_%,$(.VARIABLES)))

# Lint, format check, unit tests. Run before every commit.
test:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	$(NO_GIT_ENV) .venv/bin/python -m pytest -q
	$(NO_GIT_ENV) .venv/bin/python -m pytest -m data -q

# Apply what ruff can fix (lint autofixes and formatting).
fix:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

# Ask Jev for one pstack decision: make jev KIND=<kind> INPUT=<path.json>
# Kinds and their input formats: scripts/jev_decide.py --help
jev:
	PYTHONPATH=. .venv/bin/python scripts/jev_decide.py $(KIND) $(INPUT)
