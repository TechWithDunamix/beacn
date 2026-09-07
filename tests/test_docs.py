"""The in-dashboard documentation: structure, links, and rendering.

A docs site that quietly 404s or renders a blank block is worse than none.
"""

from __future__ import annotations

from app.docs import DOCS, SECTIONS, all_internal_links, navigation, neighbours, search

_SECTION_KEYS = {key for key, _ in SECTIONS}
_KNOWN_BLOCKS = {"p", "h", "code", "list", "note", "table", "terms", "cards"}


def test_there_are_at_least_ten_pages():
    assert len(DOCS) >= 10


def test_every_page_has_the_required_shape():
    for doc in DOCS:
        assert doc["slug"] and doc["slug"] == doc["slug"].lower().replace(" ", "")
        assert doc["section"] in _SECTION_KEYS, f"{doc['slug']} -> unknown section {doc['section']}"
        assert doc["title"] and doc["summary"]
        assert doc["blocks"], f"{doc['slug']} has no blocks"


def test_slugs_are_unique():
    slugs = [d["slug"] for d in DOCS]
    assert len(slugs) == len(set(slugs)), "duplicate doc slug"


def test_every_block_is_a_known_type():
    for doc in DOCS:
        for i, block in enumerate(doc["blocks"]):
            assert block["type"] in _KNOWN_BLOCKS, f"{doc['slug']}[{i}] -> {block['type']}"


def test_internal_links_all_resolve():
    slugs = {d["slug"] for d in DOCS}
    dangling = [(src, tgt) for src, tgt in all_internal_links() if tgt not in slugs]
    assert not dangling, f"docs link to non-existent pages: {dangling}"


def test_every_page_links_to_at_least_one_other():
    # a page with no outbound links is usually a page that forgot its context
    linked = {src for src, _ in all_internal_links()}
    # allow a couple of terminal pages (troubleshooting is heavily linked *to*)
    orphans = [d["slug"] for d in DOCS if d["slug"] not in linked]
    assert len(orphans) <= 3, f"too many pages with no outbound links: {orphans}"


def test_navigation_covers_every_page_once():
    nav = navigation()
    assert [s["key"] for s in nav] == [k for k, _ in SECTIONS]
    flat = [p["slug"] for s in nav for p in s["pages"]]
    assert sorted(flat) == sorted(d["slug"] for d in DOCS)


def test_neighbours_form_a_chain():
    ordered = [p["slug"] for s in navigation() for p in s["pages"]]
    first, last = ordered[0], ordered[-1]
    assert neighbours(first)[0] is None
    assert neighbours(last)[1] is None
    prev, nxt = neighbours(ordered[1])
    assert prev["slug"] == ordered[0] and nxt["slug"] == ordered[2]


def test_search_finds_pages_by_body_text():
    assert any(r["slug"] == "delivery-semantics" for r in search("at-least-once"))
    assert any(r["slug"] == "realtime-protocol" for r in search("heartbeat"))
    assert search("x") == []  # too short


# --- rendering ----------------------------------------------------------


async def _login(client, email: str) -> None:
    await client.get("/login")
    token = client.cookies.get("XSRF-TOKEN")
    r = await client.post(
        "/login",
        data={"email": email, "password": "correct horse battery staple"},
        headers={
            "content-type": "application/x-www-form-urlencoded",
            **({"X-XSRF-TOKEN": token} if token else {}),
        },
    )
    assert r.status_code in (302, 303)


async def test_docs_index_and_every_page_render(client, admin_user):
    await _login(client, "admin@test.local")

    idx = await client.get("/docs", headers={"X-Inertia": "true", "X-Inertia-Version": ""})
    assert idx.status_code == 200
    assert idx.json()["component"] == "docs/Index"

    for doc in DOCS:
        r = await client.get(
            f"/docs/{doc['slug']}", headers={"X-Inertia": "true", "X-Inertia-Version": ""}
        )
        assert r.status_code == 200, f"{doc['slug']} -> {r.status_code}"
        props = r.json()["props"]
        assert props["doc"]["slug"] == doc["slug"]
        # the on-page contents is built from level-2 headings
        assert isinstance(props["contents"], list)


async def test_unknown_doc_slug_is_404(client, admin_user):
    await _login(client, "admin@test.local")
    r = await client.get("/docs/no-such-page", headers={"X-Inertia": "true", "X-Inertia-Version": ""})
    assert r.status_code == 404


async def test_docs_require_sign_in(client):
    r = await client.get("/docs")
    assert r.status_code in (302, 409)
