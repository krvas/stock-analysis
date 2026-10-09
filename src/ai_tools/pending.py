"""List open Claude Code requests: ``python -m src.ai_tools.pending``.

Logs one line per request: request path, ticker, task, workspace, response path.
"""

from __future__ import annotations

import json
import logging

from src.ai_tools.claude_code import RESPONSE_SUFFIX
from src.config import AI_REQUESTS_DIR

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    requests = sorted(
        path
        for path in AI_REQUESTS_DIR.glob("*.json")
        if not path.name.endswith(RESPONSE_SUFFIX)
    )
    if not requests:
        logger.info("No pending AI requests in %s", AI_REQUESTS_DIR)
    for path in requests:
        request = json.loads(path.read_text(encoding="utf-8"))
        logger.info(
            "%s\t%s\t%s\t%s\t%s",
            path,
            request["ticker"],
            request["task"],
            request["workspace"],
            request["response_path"],
        )


if __name__ == "__main__":
    main()
