"""The documentation pages, assembled.

Content lives in `app/docs/pages/`, one module per section. This module orders
the sections, flattens the pages and provides the lookups the routes use.
"""

from __future__ import annotations

from typing import Any

from app.docs.pages import foundations, integrate, operate, quickstart, realtime

__all__ = ["DOCS", "SECTIONS", "doc_by_slug", "navigation", "neighbours", "search"]

#: Section order — the docs sidebar and reading order both follow this.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("foundations", "Foundations"),
    ("quickstart", "Getting started"),
    ("realtime", "Realtime"),
    ("integrate", "Integrating"),
    ("operate", "Operating"),
)

DOCS: tuple[dict[str, Any], ...] = (
    *foundations.PAGES,
    *quickstart.PAGES,
    *realtime.PAGES,
    *integrate.PAGES,
    *operate.PAGES,
)


def doc_by_slug(slug: str) -> dict[str, Any] | None:
    return next((doc for doc in DOCS if doc["slug"] == slug), None)


def navigation() -> list[dict[str, Any]]:
    """The docs sidebar: sections in order, each with its pages in order."""
    return [
        {
            "key": key,
            "label": label,
            "pages": [
                {"slug": d["slug"], "title": d["title"], "summary": d["summary"]}
                for d in DOCS
                if d["section"] == key
            ],
        }
        for key, label in SECTIONS
    ]


def neighbours(slug: str) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    """The previous and next page, in reading (section) order."""
    ordered = [d for key, _ in SECTIONS for d in DOCS if d["section"] == key]
    index = next((i for i, d in enumerate(ordered) if d["slug"] == slug), None)
    if index is None:
        return None, None

    def brief(doc: dict[str, Any]) -> dict[str, str]:
        return {"slug": doc["slug"], "title": doc["title"]}

    return (
        brief(ordered[index - 1]) if index > 0 else None,
        brief(ordered[index + 1]) if index + 1 < len(ordered) else None,
    )


def search(query: str, limit: int = 14) -> list[dict[str, Any]]:
    """Substring search over titles, summaries and body text.

    Not an index. This many pages is small enough that scanning them beats
    maintaining something that can fall out of date.
    """
    needle = (query or "").strip().lower()
    if len(needle) < 2:
        return []

    hits: list[tuple[int, dict[str, Any]]] = []
    for doc in DOCS:
        haystack = " ".join([doc["title"], doc["summary"], *_text_of(doc)]).lower()
        if needle not in haystack:
            continue
        score = (
            0 if needle in doc["title"].lower()
            else 1 if needle in doc["summary"].lower()
            else 2
        )
        hits.append(
            (score, {"slug": doc["slug"], "title": doc["title"], "summary": doc["summary"]})
        )

    hits.sort(key=lambda pair: pair[0])
    return [doc for _, doc in hits[:limit]]


def all_internal_links() -> list[tuple[str, str]]:
    """Every `/docs/<slug>` referenced from a page body, as (source_slug, target_slug).

    `tests/test_docs.py` uses this to assert no page links to a slug that does
    not exist.
    """
    import re

    pattern = re.compile(r"\]\(/docs/([a-z0-9-]+)")
    out: list[tuple[str, str]] = []
    for doc in DOCS:
        for text in _text_of(doc):
            for match in pattern.finditer(text):
                out.append((doc["slug"], match.group(1)))
    return out


def _text_of(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for block in doc["blocks"]:
        if "text" in block:
            out.append(str(block["text"]))
        if "code" in block:
            out.append(str(block["code"]))
        for item in block.get("items", []):
            out.append(
                item if isinstance(item, str)
                else " ".join(str(v) for v in item.values())
            )
        for row in block.get("rows", []):
            out.extend(str(cell) for cell in row)
    return out
