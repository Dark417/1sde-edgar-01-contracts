"""Tests for L0 names: determinism is the point of every one of these."""

from __future__ import annotations

from datetime import date

import pytest

from fin_lakehouse_contracts import names
from fin_lakehouse_contracts.names import Stream


class TestBatchId:
    def test_hardcoded_expected_value(self) -> None:
        # Determinism across processes is the point: this value must never
        # change for these inputs, or re-runs stop overwriting and start
        # duplicating downstream.
        assert (
            names.batch_id(Stream.FILING_INDEX, date(2026, 7, 29))
            == "filing_index-20260729-eb4807cfccc9"
        )

    def test_accepts_plain_string_stream(self) -> None:
        assert names.batch_id("filing_index", date(2026, 7, 29)) == names.batch_id(
            Stream.FILING_INDEX, date(2026, 7, 29)
        )

    def test_distinct_inputs_distinct_ids(self) -> None:
        a = names.batch_id(Stream.FILING_INDEX, date(2026, 7, 29))
        b = names.batch_id(Stream.FILING_INDEX, date(2026, 7, 30))
        c = names.batch_id(Stream.COMPANY_CONCEPT, date(2026, 7, 29))
        assert len({a, b, c}) == 3

    def test_rejects_unknown_stream(self) -> None:
        with pytest.raises(ValueError):
            names.batch_id("not_a_stream", date(2026, 7, 29))


class TestLandingPath:
    def test_same_filename_both_modes(self) -> None:
        d = date(2026, 7, 29)
        s3 = names.landing_path("s3", Stream.FILING_INDEX, d)
        volume = names.landing_path("volume", Stream.FILING_INDEX, d)
        assert s3.rsplit("/", 1)[1] == volume.rsplit("/", 1)[1]
        assert s3 != volume

    def test_s3_prefix(self) -> None:
        path = names.landing_path("s3", Stream.FILING_INDEX, date(2026, 7, 29))
        assert path.startswith("s3://fin-lake-raw/edgar/filing_index/dt=2026-07-29/")
        assert path.endswith(".json.gz")

    def test_volume_prefix(self) -> None:
        path = names.landing_path("volume", Stream.COMPANY_CONCEPT, date(2026, 7, 29))
        assert path.startswith("/Volumes/fin/landing/edgar/company_concept/dt=2026-07-29/")

    def test_custom_bucket(self) -> None:
        path = names.landing_path("s3", Stream.FILING_INDEX, date(2026, 7, 29), raw_bucket="b")
        assert path.startswith("s3://b/edgar/")


class TestPadCik:
    def test_int_input(self) -> None:
        assert names.pad_cik(320193) == "0000320193"

    def test_string_input_preserves_value(self) -> None:
        assert names.pad_cik("320193") == "0000320193"

    def test_already_padded(self) -> None:
        assert names.pad_cik("0000320193") == "0000320193"

    @pytest.mark.parametrize("bad", ["", "12345678901", "32O193", "-5", "12.3"])
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError):
            names.pad_cik(bad)


class TestNormalizeAccession:
    def test_canonical_passthrough(self) -> None:
        assert names.normalize_accession("0001234567-26-000123") == "0001234567-26-000123"

    def test_bare_digits_equal_canonical(self) -> None:
        assert names.normalize_accession("000123456726000123") == names.normalize_accession(
            "0001234567-26-000123"
        )

    def test_strips_whitespace(self) -> None:
        assert names.normalize_accession(" 0001234567-26-000123 ") == "0001234567-26-000123"

    @pytest.mark.parametrize("bad", ["", "123", "0001234567_26_000123", "00012345672600012"])
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError):
            names.normalize_accession(bad)


class TestTable:
    def test_fully_qualified(self) -> None:
        assert names.table(names.SCHEMA_SILVER, "filing") == "fin.silver.filing"
