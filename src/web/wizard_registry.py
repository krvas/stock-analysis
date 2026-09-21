"""Single source of truth for wizard page and sub-page identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PageGroup = Literal["business", "people", "price", "red_flags"]

GROUP_LABELS: Final[dict[PageGroup, str]] = {
    "business": "Business",
    "people": "People",
    "price": "Price",
    "red_flags": "Red Flags",
}

GROUP_ORDER: Final[tuple[PageGroup, ...]] = (
    "business",
    "people",
    "price",
    "red_flags",
)


@dataclass(frozen=True)
class SubPage:
    slug: str
    title: str
    order: int


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    order: int
    group: PageGroup
    subpages: list[SubPage]


WIZARD_PAGES: list[Page] = [
    Page(
        slug="business-understanding",
        title="Business Understanding",
        order=1,
        group="business",
        subpages=[
            SubPage(slug="one-line-answers", title="One-line Answers", order=1),
        ],
    ),
    Page(
        slug="adjustments",
        title="Adjustments",
        order=2,
        group="business",
        subpages=[
            SubPage(slug="look-through-earnings", title="Look-through Earnings", order=1),
        ],
    ),
    Page(
        slug="business-quality",
        title="Business Quality",
        order=3,
        group="business",
        subpages=[
            SubPage(slug="moats", title="Moats", order=1),
        ],
    ),
    Page(
        slug="management-quality",
        title="Management Quality",
        order=4,
        group="people",
        subpages=[
            SubPage(slug="compensation", title="Compensation", order=1),
        ],
    ),
    Page(
        slug="valuation",
        title="Valuation",
        order=5,
        group="price",
        subpages=[
            SubPage(slug="growth-estimation", title="Growth Estimation", order=1),
        ],
    ),
    Page(
        slug="red-flags",
        title="Red Flags",
        order=6,
        group="red_flags",
        subpages=[
            SubPage(slug="automated-checks", title="Automated Checks", order=1),
        ],
    ),
]


def get_page(slug: str) -> Page | None:
    for page in WIZARD_PAGES:
        if page.slug == slug:
            return page
    return None


def get_subpage(page_slug: str, subpage_slug: str) -> SubPage | None:
    page = get_page(page_slug)
    if page is None:
        return None
    for subpage in page.subpages:
        if subpage.slug == subpage_slug:
            return subpage
    return None


def grouped_pages() -> list[tuple[PageGroup, str, list[Page]]]:
    """Pages clustered by group, in canonical group order."""
    buckets: dict[PageGroup, list[Page]] = {}
    for page in WIZARD_PAGES:
        buckets.setdefault(page.group, []).append(page)
    return [
        (group, GROUP_LABELS[group], buckets[group])
        for group in GROUP_ORDER
        if group in buckets
    ]


def first_subpage(page: Page) -> SubPage | None:
    if not page.subpages:
        return None
    return min(page.subpages, key=lambda subpage: subpage.order)
