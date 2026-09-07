"""The block vocabulary a documentation page is written in.

Small and closed on purpose. Nine block types cover every page BEACN ships, and
a closed set means the renderer (`views/ui/docs.tsx`) is exhaustive — there is
no branch that falls through to "unknown block", and adding a tenth is a
deliberate act in two files rather than something that silently renders nothing.

Inline markup inside any `text` is a tiny four-form subset — `` `code` ``,
`**bold**`, `*italic*`, `[label](/docs/slug)` — parsed in one pass by the
renderer. It is not Markdown; docs are authored in this repository by people
who can read that function.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "cards",
    "code",
    "heading",
    "note",
    "para",
    "steps",
    "table",
    "terms",
]


def para(text: str) -> dict[str, Any]:
    """A paragraph."""
    return {"type": "p", "text": text}


def heading(text: str, level: int = 2) -> dict[str, Any]:
    """A section heading. Level 2 gets an anchor in the on-page contents."""
    return {"type": "h", "text": text, "level": level}


def code(source: str, lang: str = "bash", caption: str = "") -> dict[str, Any]:
    """A fenced code block. `lang` is advisory — the renderer does not highlight
    per language, it just uses one monospace treatment."""
    return {"type": "code", "lang": lang, "code": source.strip("\n"), "caption": caption}


def steps(items: list[str], ordered: bool = False) -> dict[str, Any]:
    """A list. `ordered=True` numbers it — use that only when order matters."""
    return {"type": "list", "items": items, "ordered": ordered}


def note(text: str, *, tone: str = "info", title: str = "") -> dict[str, Any]:
    """A callout. `tone` is one of info, caution, critical, ok. Blank lines in
    `text` become separate paragraphs inside the callout."""
    return {"type": "note", "tone": tone, "title": title, "text": text}


def table(head: list[str], rows: list[list[str]]) -> dict[str, Any]:
    """A table. Cells may contain inline markup."""
    return {"type": "table", "head": head, "rows": rows}


def terms(items: list[tuple[str, str]]) -> dict[str, Any]:
    """A definition list — a term and what it means."""
    return {"type": "terms", "items": [{"term": t, "text": d} for t, d in items]}


def cards(items: list[tuple[str, str]]) -> dict[str, Any]:
    """A grid of small titled cards, for an overview."""
    return {"type": "cards", "items": [{"title": t, "text": d} for t, d in items]}
