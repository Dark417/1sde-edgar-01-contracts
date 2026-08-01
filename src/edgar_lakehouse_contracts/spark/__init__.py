"""L2 leaf: Spark StructType schemas, behind a lazy import.

Nothing else in this package imports this subpackage. Importing
``edgar_lakehouse_contracts`` must succeed with no pyspark on the path (repos 3
and 5 install the package without Spark); only importing
``edgar_lakehouse_contracts.spark.schemas`` requires pyspark.
"""
