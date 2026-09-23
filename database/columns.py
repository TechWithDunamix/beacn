"""Add columns a model gained since its table was created.

`Tortoise.generate_schemas(safe=True)` — what `beacn migrate` used to run
alone — creates missing *tables* only. A field added to an existing model
produces a table that already exists, so nothing is created and nothing
complains, and the first query naming the new column fails at runtime
instead, in production, on whatever request happens to be first. This is
the second step that command was missing, run right after it.

Bounded to the field types this project actually uses (`_SQLITE_TYPES`/
`_POSTGRES_TYPES` below) and skips `ForeignKeyField` outright — a new
relation wants a real, reviewed migration with an index and an `on_delete`
someone chose on purpose, not a column this silently adds a guess for.

**SQLite is the path this has actually been run against** (this project's
own dev database, via `beacn migrate`). The Postgres branch is written from
`information_schema` and standard DDL rather than guessed, but has not been
exercised against a real Postgres server from here — verify it once against
a copy of that database before trusting it in that environment. If the
dialect is anything else, `sync_missing_columns` raises rather than guessing
at syntax it has no basis for.
"""

from __future__ import annotations

import json as jsonlib

from tortoise import Tortoise, fields
from tortoise.fields.relational import ForeignKeyFieldInstance

__all__ = ["sync_missing_columns"]

_SQLITE_TYPES: dict[type, str] = {
    fields.CharField: "VARCHAR({max_length})",
    fields.TextField: "TEXT",
    fields.IntField: "INT",
    fields.BigIntField: "BIGINT",
    fields.FloatField: "REAL",
    fields.BooleanField: "INT",
    fields.DatetimeField: "TIMESTAMP",
    fields.JSONField: "JSON",
}

_POSTGRES_TYPES: dict[type, str] = {
    fields.CharField: "VARCHAR({max_length})",
    fields.TextField: "TEXT",
    fields.IntField: "INT",
    fields.BigIntField: "BIGINT",
    fields.FloatField: "DOUBLE PRECISION",
    fields.BooleanField: "BOOL",
    fields.DatetimeField: "TIMESTAMPTZ",
    fields.JSONField: "JSONB",
}


def _sql_type(field: fields.Field, type_map: dict[type, str]) -> str | None:
    for cls, template in type_map.items():
        if isinstance(field, cls):
            return template.format(max_length=getattr(field, "max_length", None))
    return None


def _default_literal(field: fields.Field, dialect: str) -> str | None:
    """A DDL-safe literal for `field`'s default, or `None` if it has none we
    know how to spell — which is also what makes a NOT NULL field with no
    literal get skipped by the caller rather than sent as invalid SQL."""
    default = field.default
    if callable(default):
        try:
            default = default()
        except TypeError:
            return None
    if default is None:
        return None
    if isinstance(default, bool):
        if dialect == "postgres":
            return "TRUE" if default else "FALSE"
        return "1" if default else "0"
    if isinstance(default, (int, float)):
        return str(default)
    if isinstance(default, (list, dict)):
        encoded = jsonlib.dumps(default).replace("'", "''")
        return f"'{encoded}'::jsonb" if dialect == "postgres" else f"'{encoded}'"
    if isinstance(default, str):
        return "'{}'".format(default.replace("'", "''"))
    return None


async def _existing_columns(conn, dialect: str, table: str) -> set[str]:
    if dialect == "sqlite":
        _, rows = await conn.execute_query(f'PRAGMA table_info("{table}")')
        return {row["name"] for row in rows}
    if dialect == "postgres":
        _, rows = await conn.execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", [table]
        )
        return {row["column_name"] for row in rows}
    raise RuntimeError(
        f"sync_missing_columns does not know how to inspect a {dialect!r} database — "
        "add it to database/columns.py rather than assume SQLite's syntax works there."
    )


async def sync_missing_columns() -> list[str]:
    """Add any column a registered model has that its table does not.

    Returns the columns it added, as `"table.column"` strings, for the
    caller to report — an empty list is the common case (nothing to do) and
    is not itself news.
    """
    conn = Tortoise.get_connection("default")
    dialect = conn.capabilities.dialect
    type_map = _POSTGRES_TYPES if dialect == "postgres" else _SQLITE_TYPES
    added: list[str] = []

    for model in Tortoise.apps.get_models_iterable():
        table = model._meta.db_table
        existing = await _existing_columns(conn, dialect, table)

        for field_name, field in model._meta.fields_map.items():
            if isinstance(field, ForeignKeyFieldInstance):
                continue
            column = field.source_field or field_name
            if column in existing:
                continue

            sql_type = _sql_type(field, type_map)
            if sql_type is None:
                continue  # a field type this helper does not know — skip, never guess

            default_literal = _default_literal(field, dialect)
            if not field.null and default_literal is None:
                # A NOT NULL column with no literal default cannot be added
                # to a table that may already have rows — SQLite refuses
                # this outright, and Postgres would fail every existing
                # row's constraint check the same way.
                continue

            statement = f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'
            if default_literal is not None:
                statement += f" DEFAULT {default_literal}"
            if not field.null:
                statement += " NOT NULL"

            await conn.execute_script(statement + ";")
            added.append(f"{table}.{column}")

    return added
