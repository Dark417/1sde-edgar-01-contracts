"""L1: the landing envelope model (data contracts §1).

Repo 3 never writes a bare API response to landing. Every record is wrapped so that
bronze can answer "where did this byte come from, when, under which logical date, and
did it arrive intact" without re-deriving any of it from a file path.

Landing files are gzipped newline-delimited JSON: one envelope per line.

**Why ``payload_json`` is a string.** The three streams disagree about the payload's
shape, and two of them (``company_submissions``, ``company_concept``) are deeply nested
documents whose shape the SEC changes without notice. Typing the payload here would
coerce bronze into a shape we do not control and destroy the replay property: landing
is the system of record, so it stores the bytes the SEC actually returned, verbatim.
Silver parses; bronze and landing do not.

**Versioning.** ``envelope_version`` is written on every record and *read* by bronze
rather than assumed, so a future version 2 fails loudly at parse time instead of
silently mis-parsing. Only version 1 exists.

Does not handle: writing envelopes anywhere — repo 3 does that.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_serializer

__all__ = [
    "ENVELOPE_FIELDS",
    "ENVELOPE_VERSION",
    "SOURCE_SYSTEM",
    "LandingEnvelope",
    "canonical_payload_json",
    "content_sha256",
    "envelope_json_schema_ddl",
]

ENVELOPE_VERSION: Final[str] = "1"
SOURCE_SYSTEM: Final[str] = "sec_edgar"

#: Envelope field -> Spark SQL type. This mapping is the wire contract between repo 3
#: (writer) and repo 4 (reader). Order is significant only for readability; bronze
#: matches on name. Keep in sync with :class:`LandingEnvelope`.
ENVELOPE_FIELDS: Final[dict[str, str]] = {
    "envelope_version": "STRING",
    "source_system": "STRING",
    "stream": "STRING",
    "resource_id": "STRING",
    "logical_date": "STRING",
    "batch_id": "STRING",
    "fetched_at": "STRING",
    "request_url": "STRING",
    "http_status": "INT",
    "content_sha256": "STRING",
    "payload_json": "STRING",
}


def canonical_payload_json(payload: Any) -> str:
    """Serialize a payload to the exact string form that goes on the wire.

    ``sort_keys`` and the tight separators are load-bearing, not style. The same
    payload must serialize to the same bytes on every run and in every process, or
    :func:`content_sha256` stops being a stable identity and the "run it twice"
    guarantee breaks. ``ensure_ascii=False`` keeps company names with non-ASCII
    characters readable rather than escaped.

    Does not handle: validating the payload's shape — verbatim is the point.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_sha256(payload_json: str) -> str:
    """Return the sha256 of the canonical payload string.

    This is an integrity check *and* a change-detection key: bronze can tell a
    genuine update from a re-fetch of identical bytes without diffing documents.
    """
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


class LandingEnvelope(BaseModel):
    """One landing record: provenance metadata plus the verbatim source payload.

    Frozen because an envelope describes something that already happened. Mutating
    one after construction would let ``content_sha256`` disagree with ``payload_json``.
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    envelope_version: str = Field(default=ENVELOPE_VERSION)
    source_system: str = Field(default=SOURCE_SYSTEM)
    stream: str
    #: The natural id of the thing fetched: an accession number, a padded CIK, or
    #: "<padded cik>/<concept tag>". Lets bronze dedupe without parsing the payload.
    resource_id: str
    logical_date: date
    batch_id: str
    fetched_at: datetime
    request_url: str
    http_status: int
    content_sha256: str
    payload_json: str

    @field_serializer("logical_date")
    def _serialize_logical_date(self, value: date) -> str:
        """Serialize as YYYY-MM-DD, never as a datetime (data contracts §1)."""
        return value.isoformat()

    @field_serializer("fetched_at")
    def _serialize_fetched_at(self, value: datetime) -> str:
        """Serialize as RFC3339 with a trailing Z.

        ``isoformat()`` renders UTC as "+00:00"; bronze parses a literal "Z". Emitting
        whichever one ``datetime`` happens to produce is how a timestamp column becomes
        half-null.
        """
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def build(
        cls,
        *,
        stream: str,
        resource_id: str,
        logical_date: date,
        batch_id: str,
        fetched_at: datetime,
        request_url: str,
        http_status: int,
        payload: Any,
    ) -> LandingEnvelope:
        """Construct an envelope from a decoded payload, deriving the hash.

        Prefer this over the constructor: it is the only path that guarantees
        ``content_sha256`` actually describes ``payload_json``.
        """
        payload_json = canonical_payload_json(payload)
        return cls(
            stream=stream,
            resource_id=resource_id,
            logical_date=logical_date,
            batch_id=batch_id,
            fetched_at=fetched_at,
            request_url=request_url,
            http_status=http_status,
            content_sha256=content_sha256(payload_json),
            payload_json=payload_json,
        )

    def to_json_line(self) -> str:
        """Return the canonical single-line JSON form used in NDJSON landing files.

        Keys are sorted so two runs producing the same envelope produce identical
        bytes — the same reason :func:`canonical_payload_json` sorts.

        Does not handle: gzip, newlines between records, or file layout.
        """
        return json.dumps(
            json.loads(self.model_dump_json()),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def envelope_json_schema_ddl() -> str:
    """DDL string for ``from_json`` when reading landing as raw text.

    Used by repo 4's local batch reader. On Databricks, Auto Loader infers the envelope
    and routes anything unexpected into ``_rescued_data``; the DDL here is the same
    shape, so the two readers agree on column names and types.
    """
    return ", ".join(f"{name} {type_sql}" for name, type_sql in ENVELOPE_FIELDS.items())
