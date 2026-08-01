"""Spark-marked tests: the StructTypes work in a real SparkSession."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fin_lakehouse_contracts import names
from fin_lakehouse_contracts.spark import schemas as spark_schemas

pytestmark = pytest.mark.spark


@pytest.fixture(scope="module")
def spark() -> Iterator[object]:
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("contracts-schema-tests")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


def test_every_schema_builds_an_empty_dataframe(spark: object) -> None:
    from pyspark.sql import SparkSession

    assert isinstance(spark, SparkSession)
    for fqn, schema in spark_schemas.SCHEMAS.items():
        df = spark.createDataFrame([], schema)
        assert df.schema == schema, f"round-trip through a real session changed {fqn}"


def test_get_schema_known_table() -> None:
    fqn = names.table(names.SCHEMA_SILVER, "financial_fact")
    schema = spark_schemas.get_schema(fqn)
    assert "accession_number" in schema.fieldNames()


def test_get_schema_unknown_table_names_known_ones() -> None:
    with pytest.raises(KeyError, match=r"fin.silver.filing"):
        spark_schemas.get_schema("fin.silver.nope")
