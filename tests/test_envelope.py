"""Round-trip tests for the landing envelope (data contracts §1)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from edgar_lakehouse_contracts.envelope import LandingEnvelope
from edgar_lakehouse_contracts.models import FilingIndexRecord


def _sample() -> LandingEnvelope:
    return LandingEnvelope(
        _stream="filing_index",
        _logical_date=date(2026, 7, 29),
        _batch_id="filing_index-20260729-eb4807cfccc9",
        _fetched_at=datetime(2026, 7, 29, 22, 5, 1, tzinfo=UTC),
        _source_url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260729.idx",
        payload={"company_name": "APPLE INC", "cik": "320193"},
    )


class TestRoundTrip:
    def test_model_json_model_is_byte_identical(self) -> None:
        original = _sample()
        line = original.to_json_line()
        reparsed = LandingEnvelope.model_validate_json(line)
        assert reparsed.to_json_line() == line

    def test_logical_date_serializes_as_date_not_datetime(self) -> None:
        raw = json.loads(_sample().to_json_line())
        assert raw["_logical_date"] == "2026-07-29"

    def test_aliases_carry_leading_underscores(self) -> None:
        raw = json.loads(_sample().to_json_line())
        assert set(raw) == {
            "_stream",
            "_logical_date",
            "_batch_id",
            "_fetched_at",
            "_source_url",
            "_schema_version",
            "payload",
        }

    def test_payload_verbatim(self) -> None:
        payload = {"z": 1, "a": {"nested": [3, 2, 1]}, "date": "07/29/2026"}
        env = _sample().model_copy(update={"payload": payload})
        raw = json.loads(env.to_json_line())
        assert raw["payload"] == payload

    def test_schema_version_default(self) -> None:
        assert _sample().schema_version == "1"


class TestFilingIndexRecord:
    def test_all_fields_are_raw_strings(self) -> None:
        record = FilingIndexRecord(
            company_name="APPLE INC",
            form_type="10-K",
            cik="320193",
            date_filed="2026-07-29",
            file_name="edgar/data/320193/0000320193-26-000123.txt",
        )
        assert record.cik == "320193"  # stays a string: leading zeros matter
        assert record.date_filed == "2026-07-29"  # typing happens in silver
