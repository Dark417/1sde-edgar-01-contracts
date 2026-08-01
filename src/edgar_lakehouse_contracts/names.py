"""L0: pure constants and deterministic name/path builders.

Imports nothing from this package. Does not handle: I/O, config resolution,
existence checks — it only builds strings.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from enum import StrEnum
from typing import Final, Literal

CATALOG: Final[str] = "edgar"
SCHEMA_LANDING: Final[str] = "landing"
SCHEMA_BRONZE: Final[str] = "bronze"
SCHEMA_SILVER: Final[str] = "silver"
SCHEMA_GOLD: Final[str] = "gold"

RAW_BUCKET_DEFAULT: Final[str] = "edgar-lake-raw"
SERVING_BUCKET_DEFAULT: Final[str] = "edgar-lake-serving"
VOLUME_LANDING: Final[str] = "/Volumes/edgar/landing/edgar"

_ACCESSION_CANONICAL: Final[re.Pattern[str]] = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_ACCESSION_BARE: Final[re.Pattern[str]] = re.compile(r"^\d{18}$")


class Stream(StrEnum):
    """The three ingest streams. Values are used in paths and batch ids."""

    FILING_INDEX = "filing_index"
    COMPANY_SUBMISSIONS = "company_submissions"
    COMPANY_CONCEPT = "company_concept"


def table(schema: str, name: str) -> str:
    """Return the fully qualified table name ``edgar.<schema>.<name>``.

    Does not handle: validating that the table exists or that the schema is one
    of the four known schemas.
    """
    return f"{CATALOG}.{schema}.{name}"


def batch_id(stream: str | Stream, logical_date: date) -> str:
    """Return the deterministic batch id for a (stream, logical_date) pair.

    sha256 over an explicitly '|'-delimited string — never Python ``hash()``,
    which is randomized per process. Same inputs always produce the same id, so
    re-runs overwrite instead of duplicating (design doc §8.1).

    Does not handle: uniqueness across re-runs — sameness across re-runs is the
    entire point.
    """
    stream_value = str(Stream(stream).value)
    digest = hashlib.sha256(f"{stream_value}|{logical_date.isoformat()}".encode()).hexdigest()
    return f"{stream_value}-{logical_date.strftime('%Y%m%d')}-{digest[:12]}"


def landing_path(
    mode: Literal["s3", "volume"],
    stream: str | Stream,
    logical_date: date,
    raw_bucket: str = RAW_BUCKET_DEFAULT,
) -> str:
    """Return the full landing object path for one batch.

    The filename is identical in both modes; only the prefix differs — this is
    what makes an S3 replay reproduce the live Volume path exactly (ADR-001).

    Does not handle: creating the object, checking bucket/volume existence.
    """
    stream_value = str(Stream(stream).value)
    filename = f"{batch_id(stream_value, logical_date)}.json.gz"
    suffix = f"edgar/{stream_value}/dt={logical_date.isoformat()}/{filename}"
    if mode == "s3":
        return f"s3://{raw_bucket}/{suffix}"
    return f"{VOLUME_LANDING}/{stream_value}/dt={logical_date.isoformat()}/{filename}"


def pad_cik(cik: str | int) -> str:
    """Return the CIK as a 10-character zero-padded string.

    cik is a STRING everywhere in this project — leading zeros are semantically
    meaningful in EDGAR URLs; any code that makes it an int is a bug.

    Does not handle: verifying the CIK exists in EDGAR.
    """
    digits = str(cik).strip()
    if not digits.isdigit() or len(digits) > 10:
        raise ValueError(f"not a valid CIK: {cik!r}")
    return digits.zfill(10)


def normalize_accession(raw: str) -> str:
    """Return the accession number in canonical ``0001234567-26-000123`` form.

    Accepts the canonical dashed form or the bare 18-digit form; anything else
    raises ValueError. Does not handle: checking the accession exists on EDGAR.
    """
    candidate = raw.strip()
    if _ACCESSION_CANONICAL.match(candidate):
        return candidate
    if _ACCESSION_BARE.match(candidate):
        return f"{candidate[:10]}-{candidate[10:12]}-{candidate[12:]}"
    raise ValueError(f"not a valid accession number: {raw!r}")
