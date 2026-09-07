"""The in-dashboard documentation.

Guarded like every other dashboard page, but with no permission requirement:
documentation a ReadOnly operator cannot open is documentation withheld from
the person most likely to need it. Signing in is still required — these pages
describe this installation's own conventions.
"""

from __future__ import annotations

from typing import Any

from sillo.core.http import HttpContext
from sillo.responses import not_found
from sillo_inertia import render

from app.docs import DOCS, doc_by_slug, navigation, neighbours, search
from routes.web._kit import page

__all__ = ["docs_index", "docs_page", "docs_search"]


@page()
async def docs_index(ctx: HttpContext) -> Any:
    return await render("docs/Index", {"navigation": navigation(), "total": len(DOCS)}, ctx=ctx)


@page()
async def docs_page(ctx: HttpContext, slug: str) -> Any:
    doc = doc_by_slug(slug)
    if doc is None:
        return not_found()
    previous, following = neighbours(slug)
    return await render(
        "docs/Page",
        {
            "navigation": navigation(),
            "doc": doc,
            "previous": previous,
            "next": following,
            "contents": [
                {"text": block["text"], "id": _anchor(block["text"])}
                for block in doc["blocks"]
                if block["type"] == "h" and block.get("level", 2) == 2
            ],
        },
        ctx=ctx,
    )


@page()
async def docs_search(ctx: HttpContext) -> Any:
    query = (ctx.query_params.get("q") or "").strip()
    return await render(
        "docs/Search",
        {"navigation": navigation(), "query": query, "results": search(query)},
        ctx=ctx,
    )


def _anchor(text: str) -> str:
    """A URL fragment for a heading — must match `views/ui/docs.tsx::anchor`."""
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
