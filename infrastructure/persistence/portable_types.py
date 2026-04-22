"""Portable SQLAlchemy types — work on both PostgreSQL and SQLite.

GUID: Stores UUID as CHAR(36) on SQLite, native UUID on PostgreSQL.
PortableJSON: Uses JSONB on PostgreSQL, JSON on SQLite.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID or CHAR(36) on other dialects.
    Transparently converts between Python ``uuid.UUID`` and database string.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID

            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(value))

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# PortableJSON: JSONB on PG (binary, indexable), JSON on SQLite/others
PortableJSON = JSON().with_variant(JSONB(), "postgresql")
