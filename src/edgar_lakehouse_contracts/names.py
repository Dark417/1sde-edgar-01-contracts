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

# ---------------------------------------------------------------------------
# SSM Parameter Store keys — the cross-repo config interface.
#
# These live here because nothing owned them before, and it showed. Repo 2
# published ``/edgar-lakehouse/dbx/volume_path``; repo 3 read that name; repo 4
# independently invented ``/edgar-lakehouse/dbx/landing_volume`` for the same
# value and read a key that was never published. Nothing failed loudly, because
# repo 4's config falls back to a default when the lookup misses — so the two
# repos simply disagreed in silence.
#
# A parameter name is a name, which makes it this module's business exactly like
# the catalog and bucket names above. Producer and consumers now import one
# constant instead of each spelling it out.
#
# Adding a constant breaks nobody: repos adopt these on their next version bump
# rather than all at once.
# ---------------------------------------------------------------------------
SSM_PREFIX: Final[str] = "/edgar-lakehouse"

SSM_DBX_HOST: Final[str] = f"{SSM_PREFIX}/dbx/host"
SSM_DBX_VOLUME_PATH: Final[str] = f"{SSM_PREFIX}/dbx/volume_path"
SSM_DBX_WAREHOUSE_ID: Final[str] = f"{SSM_PREFIX}/dbx/warehouse_id"
SSM_S3_RAW_BUCKET: Final[str] = f"{SSM_PREFIX}/s3/raw_bucket"
SSM_S3_SERVING_BUCKET: Final[str] = f"{SSM_PREFIX}/s3/serving_bucket"
SSM_ECR_INGEST_REPO: Final[str] = f"{SSM_PREFIX}/ecr/ingest_repo"
SSM_ECS_TASK_FAMILY: Final[str] = f"{SSM_PREFIX}/ecs/task_family"
SSM_CONTRACTS_VERSION: Final[str] = f"{SSM_PREFIX}/contracts/version"
SSM_LANDING_MODE: Final[str] = f"{SSM_PREFIX}/landing_mode"

#: Every key repo 2 publishes. Repo 2 asserts it publishes exactly this set, so
#: a key added here without a publisher — or published without being declared —
#: fails that repo's build instead of surfacing as a runtime ParameterNotFound.
SSM_PUBLISHED: Final[frozenset[str]] = frozenset(
    {
        SSM_DBX_HOST,
        SSM_DBX_VOLUME_PATH,
        SSM_DBX_WAREHOUSE_ID,
        SSM_S3_RAW_BUCKET,
        SSM_S3_SERVING_BUCKET,
        SSM_ECR_INGEST_REPO,
        SSM_ECS_TASK_FAMILY,
        SSM_CONTRACTS_VERSION,
        SSM_LANDING_MODE,
    }
)


def ssm_oidc_role_arn(repo: str) -> str:
    """Return the SSM key holding *repo*'s GitHub Actions OIDC role ARN.

    Per-repo rather than a constant, since the set of repos changes. Does not
    handle: checking the parameter exists, or that the repo is one of the five.
    """
    return f"{SSM_PREFIX}/iam/oidc_role_arn/{repo}"


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
    # The partition key is `logical_date=`, not `dt=`. Auto Loader derives a column
    # named after the key, and repo 4's bronze reads `logical_date` -- with `dt=` it
    # would silently get no partition column at all and every row would carry a null
    # logical date. The name is part of the contract, not cosmetic.
    partition = f"logical_date={logical_date.isoformat()}"
    suffix = f"edgar/{stream_value}/{partition}/{filename}"
    if mode == "s3":
        return f"s3://{raw_bucket}/{suffix}"
    return f"{VOLUME_LANDING}/{stream_value}/{partition}/{filename}"


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
