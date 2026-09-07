"""The documentation shipped inside the control plane.

Docs live here as structured blocks rather than Markdown files, so they render
with the same component library as the rest of the dashboard — a note, a table
and a code block look like BEACN, not like a README pasted into a panel — and
there is no Markdown parser or HTML sanitiser in the path to an authenticated
page.

Authoring is a little more verbose in exchange. That is worth paying for a
fixed set of pages that ship with the product.

Every page is checked by `tests/test_docs.py`: slugs unique, sections known,
internal `/docs/...` links resolving, every page rendering.
"""

from app.docs.content import (
    DOCS,
    SECTIONS,
    all_internal_links,
    doc_by_slug,
    navigation,
    neighbours,
    search,
)

__all__ = [
    "DOCS",
    "SECTIONS",
    "all_internal_links",
    "doc_by_slug",
    "navigation",
    "neighbours",
    "search",
]
