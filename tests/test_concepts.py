"""Tests for the concept set and canonical map (data contracts §0.2-§0.3)."""

from __future__ import annotations

from edgar_lakehouse_contracts.concepts import CONCEPT_CANONICAL_MAP, CONCEPT_SET


def test_exactly_fifteen_concepts() -> None:
    assert len(CONCEPT_SET) == 15
    assert len(set(CONCEPT_SET)) == 15


def test_every_map_key_is_in_concept_set() -> None:
    missing = set(CONCEPT_CANONICAL_MAP) - set(CONCEPT_SET)
    assert not missing, f"canonical map keys not in CONCEPT_SET: {sorted(missing)}"


def test_mvp2_has_exactly_one_canonical_target() -> None:
    assert set(CONCEPT_CANONICAL_MAP.values()) == {"revenue_total"}
    assert set(CONCEPT_CANONICAL_MAP) == {
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    }
