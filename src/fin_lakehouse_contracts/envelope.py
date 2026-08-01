"""L1: the landing envelope model (data contracts §1).

Does not handle: writing envelopes anywhere — repo 3 does that.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

ENVELOPE_SCHEMA_VERSION = "1"


class LandingEnvelope(BaseModel):
    """One landing record: metadata fields plus the verbatim source payload.

    JSON keys carry leading underscores, which are not valid Python field
    names — hence the aliases. Serialize with ``by_alias=True``.

    Does not handle: payload validation. `payload` is verbatim by design;
    typing it here would destroy the replay property (design doc §5.1).
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    stream: str = Field(alias="_stream")
    logical_date: date = Field(alias="_logical_date")
    batch_id: str = Field(alias="_batch_id")
    fetched_at: datetime = Field(alias="_fetched_at")
    source_url: str = Field(alias="_source_url")
    schema_version: str = Field(alias="_schema_version", default=ENVELOPE_SCHEMA_VERSION)
    payload: dict[str, Any] | list[Any] = Field(alias="payload")

    @field_serializer("logical_date")
    def _serialize_logical_date(self, value: date) -> str:
        """Serialize as YYYY-MM-DD, never as a datetime (data contracts §1)."""
        return value.isoformat()

    def to_json_line(self) -> str:
        """Return the canonical single-line JSON form used in NDJSON landing files.

        Does not handle: gzip, newlines between records, or file layout.
        """
        return self.model_dump_json(by_alias=True)
