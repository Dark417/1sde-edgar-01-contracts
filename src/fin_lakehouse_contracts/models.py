"""L1: raw record models (data contracts §2).

Does not handle: typing or cleaning values — these are *raw* records; typing
happens in silver (repo 4).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FilingIndexRecord(BaseModel):
    """One row of the EDGAR daily form index, all fields as-published strings.

    All str by design: this is the raw record. cik stays a string — leading
    zeros are semantically meaningful in EDGAR URLs (never make it an int).

    Does not handle: date parsing, CIK padding, accession normalization.
    """

    model_config = ConfigDict(frozen=True)

    company_name: str
    form_type: str
    cik: str
    date_filed: str
    file_name: str
