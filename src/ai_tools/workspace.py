"""Per-ticker workspace: the latest 10-Ks' narrative sections as markdown files.

Layout: ``AI_WORKSPACE_DIR/{TICKER}/{fiscal_year}_{accession}/{section}.md``,
one subfolder per filing. A run reads all of the ticker folder's subfolders
together, so backends get the ticker folder as their workspace root.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from edgar import Company, Filing

from src.api.edgartools.source import setup_edgartools
from src.config import AI_ANNUAL_REPORTS, AI_WORKSPACE_DIR

logger = logging.getLogger(__name__)

# Workspace file stem -> TenK item.
SECTION_ITEMS: dict[str, str] = {
    "business": "Item 1",
    "risk_factors": "Item 1A",
    "mdna": "Item 7",
    "market_risk": "Item 7A",
}

# Told to the agent (OpenRouter system prompt, Claude Code request).
WORKSPACE_LAYOUT = (
    "The workspace holds one subfolder per annual report (10-K), named "
    "{fiscal_year}_{accession}. Each subfolder has business.md (Item 1), "
    "risk_factors.md (Item 1A), mdna.md (Item 7, MD&A) and market_risk.md "
    "(Item 7A). Use all the years, not only the latest."
)


def latest_10ks(ticker: str) -> list[Filing]:
    """``ticker``'s latest ``AI_ANNUAL_REPORTS`` original (non-amended) 10-Ks,
    newest first."""
    setup_edgartools()
    filings = list(
        Company(ticker)
        .get_filings(form="10-K", amendments=False)
        .head(AI_ANNUAL_REPORTS)
    )
    if not filings:
        raise ValueError(f"No 10-K filings found for {ticker}")
    return filings


def filing_folder_name(filing: Filing) -> str:
    """``{fiscal_year}_{accession}``: period-of-report year, else filing year."""
    period = filing.period_of_report
    year = str(period)[:4] if period else str(filing.filing_date)[:4]
    return f"{year}_{filing.accession_number}"


def workspace_dir(ticker: str) -> Path:
    return AI_WORKSPACE_DIR / ticker.upper()


def build_workspace(ticker: str, filings: list[Filing]) -> Path:
    """Write each filing's sections under :func:`workspace_dir`; return it.

    Subfolders that already hold every section file are skipped, and
    subfolders of filings not in ``filings`` are deleted so the agent reads
    exactly these years. A section the filing parser cannot find is written as
    a one-line "unavailable" note so every subfolder has the same files.
    """
    root = workspace_dir(ticker)
    current = {filing_folder_name(filing) for filing in filings}
    if root.is_dir():
        for stale in (p for p in root.iterdir() if p.name not in current):
            logger.info("Removing stale AI workspace %s", stale)
            shutil.rmtree(stale)
    for filing in filings:
        folder = root / filing_folder_name(filing)
        paths = {stem: folder / f"{stem}.md" for stem in SECTION_ITEMS}
        if all(path.is_file() for path in paths.values()):
            continue
        tenk = filing.obj()
        folder.mkdir(parents=True, exist_ok=True)
        for stem, item in SECTION_ITEMS.items():
            text = tenk[item]
            if not text or not text.strip():
                logger.warning("%s %s: %s not found", ticker, folder.name, item)
                text = f"{item} is unavailable for this filing."
            paths[stem].write_text(f"# {item}\n\n{text.strip()}\n", encoding="utf-8")
        logger.info("Built AI workspace %s", folder)
    return root
