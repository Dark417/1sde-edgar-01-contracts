"""L1: the XBRL concept set and canonical mapping (data contracts §0.2-§0.3).

Coalescing ``Revenues`` and
``RevenueFromContractWithCustomerExcludingAssessedTax`` into ``revenue_total``
is best-effort: filers switch tags across years and the two are not perfectly
interchangeable. The as-filed ``concept`` is therefore always retained
alongside ``concept_canonical`` in silver and gold.

Does not handle: fetching concepts from EDGAR or validating filer usage.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

CONCEPT_SET: Final[tuple[str, ...]] = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "OperatingIncomeLoss",
    "GrossProfit",
    "CostOfRevenue",
    "Assets",
    "AssetsCurrent",
    "Liabilities",
    "LiabilitiesCurrent",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "NetCashProvidedByUsedInOperatingActivities",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
)

CONCEPT_CANONICAL_MAP: Final[Mapping[str, str]] = {
    "Revenues": "revenue_total",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue_total",
}
