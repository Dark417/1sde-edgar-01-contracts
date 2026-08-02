"""Round-trip tests for the landing envelope (data contracts §1).

The envelope is the wire contract between repo 3 (writer) and repo 4 (bronze reader).
Both sides are separate codebases, so the tests that matter here are the ones that pin
the *serialized* form: field names, types on the wire, and byte-stability. A change
that keeps the Python model happy but renames a JSON key silently breaks bronze.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from edgar_lakehouse_contracts.envelope import (
    ENVELOPE_FIELDS,
    LandingEnvelope,
    canonical_payload_json,
    content_sha256,
    envelope_json_schema_ddl,
)
from edgar_lakehouse_contracts.models import FilingIndexRecord

PAYLOAD = {"company_name": "APPLE INC", "cik": "320193"}


def _sample(**overrides: object) -> LandingEnvelope:
    kwargs: dict[str, object] = {
        "stream": "filing_index",
        "resource_id": "0000320193-26-000123",
        "logical_date": date(2026, 7, 29),
        "batch_id": "filing_index-20260729-eb4807cfccc9",
        "fetched_at": datetime(2026, 7, 29, 22, 5, 1, tzinfo=UTC),
        "request_url": (
            "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260729.idx"
        ),
        "http_status": 200,
        "payload": PAYLOAD,
    }
    kwargs.update(overrides)
    return LandingEnvelope.build(**kwargs)  # type: ignore[arg-type]


class TestWireFormat:
    def test_json_keys_are_exactly_the_declared_envelope_fields(self) -> None:
        """The JSON keys ARE the contract -- bronze matches on these names."""
        raw = json.loads(_sample().to_json_line())
        assert set(raw) == set(ENVELOPE_FIELDS)

    def test_no_key_carries_a_leading_underscore(self) -> None:
        """Guards the exact regression that made repo 4 unable to read repo 3."""
        raw = json.loads(_sample().to_json_line())
        assert [k for k in raw if k.startswith("_")] == []

    def test_logical_date_serializes_as_date_not_datetime(self) -> None:
        raw = json.loads(_sample().to_json_line())
        assert raw["logical_date"] == "2026-07-29"

    def test_fetched_at_serializes_with_a_trailing_z(self) -> None:
        """Not "+00:00": bronze parses a literal Z."""
        raw = json.loads(_sample().to_json_line())
        assert raw["fetched_at"] == "2026-07-29T22:05:01Z"

    def test_http_status_stays_an_int_on_the_wire(self) -> None:
        raw = json.loads(_sample().to_json_line())
        assert raw["http_status"] == 200
        assert isinstance(raw["http_status"], int)

    def test_payload_json_is_a_string_not_an_object(self) -> None:
        """Landing stores bytes, not a shape the SEC can change under us."""
        raw = json.loads(_sample().to_json_line())
        assert isinstance(raw["payload_json"], str)
        assert json.loads(raw["payload_json"]) == PAYLOAD


class TestRoundTrip:
    def test_to_json_line_is_stable_through_a_reparse(self) -> None:
        original = _sample()
        line = original.to_json_line()
        assert LandingEnvelope.model_validate_json(line).to_json_line() == line

    def test_same_inputs_produce_identical_bytes(self) -> None:
        """Byte-identity is what makes an S3 replay reproduce the Volume path."""
        assert _sample().to_json_line() == _sample().to_json_line()

    def test_payload_key_order_does_not_change_the_bytes(self) -> None:
        """Canonical serialization sorts keys, so dict ordering cannot leak in."""
        a = _sample(payload={"a": 1, "z": 2})
        b = _sample(payload={"z": 2, "a": 1})
        assert a.to_json_line() == b.to_json_line()
        assert a.content_sha256 == b.content_sha256

    def test_payload_survives_verbatim(self) -> None:
        payload = {"z": 1, "a": {"nested": [3, 2, 1]}, "date": "07/29/2026"}
        raw = json.loads(_sample(payload=payload).to_json_line())
        assert json.loads(raw["payload_json"]) == payload

    def test_non_ascii_is_preserved_not_escaped(self) -> None:
        payload = {"company_name": "Société Générale"}
        raw = json.loads(_sample(payload=payload).to_json_line())
        assert json.loads(raw["payload_json"])["company_name"] == "Société Générale"


class TestIntegrity:
    def test_content_sha256_describes_the_payload_json(self) -> None:
        env = _sample()
        assert env.content_sha256 == content_sha256(env.payload_json)

    def test_different_payloads_hash_differently(self) -> None:
        assert _sample(payload={"a": 1}).content_sha256 != _sample(payload={"a": 2}).content_sha256

    def test_canonical_payload_json_is_compact_and_sorted(self) -> None:
        assert canonical_payload_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


class TestDefaults:
    def test_envelope_version_default(self) -> None:
        assert _sample().envelope_version == "1"

    def test_source_system_default(self) -> None:
        assert _sample().source_system == "sec_edgar"


class TestSparkDdl:
    def test_ddl_names_every_envelope_field(self) -> None:
        ddl = envelope_json_schema_ddl()
        for name in ENVELOPE_FIELDS:
            assert name in ddl

    def test_ddl_types_match_the_declared_mapping(self) -> None:
        assert "http_status INT" in envelope_json_schema_ddl()
        assert "payload_json STRING" in envelope_json_schema_ddl()


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
