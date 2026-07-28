from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SAT taxpayer registry ETL for Huawei Cloud MRS Spark.")
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--gold-path", required=True)
    parser.add_argument("--audit-path", required=True)
    parser.add_argument("--iceberg-warehouse", required=True)
    parser.add_argument("--iceberg-table", default="tax_gold.taxpayer_regime_year")
    parser.add_argument("--year", default="2025")
    return parser.parse_args()


def validated_table_name(value: str) -> tuple[str, str]:
    parts = value.split(".")
    if len(parts) != 2 or any(not IDENTIFIER_PATTERN.fullmatch(part) for part in parts):
        raise ValueError("--iceberg-table must use the form namespace.table with safe identifiers")
    return parts[0], parts[1]


def schema_metadata(dataframe) -> list[dict[str, object]]:
    return [
        {
            "name": field.name,
            "type": field.dataType.simpleString(),
            "nullable": field.nullable,
            "classification": (
                "business_dimension"
                if field.name in {"year", "region", "regime", "resico_flag"}
                else "aggregate_metric"
            ),
        }
        for field in dataframe.schema.fields
    ]


def write_audit(spark: SparkSession, path: str, payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    spark.createDataFrame([(text,)], ["value"]).coalesce(1).write.mode("overwrite").text(path)


def publish_unhandled_failure(exc_type, exc_value, exc_traceback) -> None:
    try:
        args = parse_args()
        spark = SparkSession.getActiveSession()
        if spark is not None:
            write_audit(
                spark,
                args.audit_path,
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "error_type": exc_type.__name__,
                    "error": str(exc_value)[:4000],
                    "traceback": "".join(
                        traceback.format_exception(exc_type, exc_value, exc_traceback)
                    )[-12000:],
                },
            )
    except Exception as audit_error:
        print(f"Unable to publish failure audit: {audit_error}", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback)


def main() -> None:
    args = parse_args()
    namespace, table = validated_table_name(args.iceberg_table)
    qualified_table = f"spark_catalog.{namespace}.{table}"
    table_location = (
        f"{args.iceberg_warehouse.rstrip('/')}/{namespace}/{table}"
    )
    spark = (
        SparkSession.builder.appName("sat-agentic-taxpayer-etl")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.iceberg.spark.SparkSessionCatalog",
        )
        .config("spark.sql.catalog.spark_catalog.type", "hive")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.storeAssignmentPolicy", "ANSI")
        .enableHiveSupport()
        .getOrCreate()
    )

    raw = (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .csv(args.raw_path)
    )

    allowed_regions = ["CDMX", "Jalisco", "Nuevo Leon", "Puebla", "Yucatan"]
    cleaned = (
        raw.filter(F.col("year").cast("string") == F.lit(args.year))
        .filter(F.col("region").isin(allowed_regions))
        .withColumn("rfc_hash", F.sha2(F.col("rfc"), 256))
        .withColumn("masked_rfc", F.concat(F.substring(F.col("rfc"), 1, 3), F.lit("***"), F.substring(F.col("rfc"), -3, 3)))
        .drop("rfc")
    )

    gold = (
        cleaned.groupBy("year", "region", "regime", "resico_flag")
        .agg(
            F.count("*").alias("taxpayer_count"),
            F.sum(F.col("annual_income")).alias("annual_income_total"),
            F.avg(F.col("annual_income")).alias("annual_income_avg"),
        )
        .select(
            F.col("year").cast("string").alias("year"),
            F.col("region").cast("string").alias("region"),
            F.col("regime").cast("string").alias("regime"),
            F.col("resico_flag").cast("boolean").alias("resico_flag"),
            F.col("taxpayer_count").cast("long").alias("taxpayer_count"),
            F.col("annual_income_total").cast("long").alias("annual_income_total"),
            F.col("annual_income_avg").cast("double").alias("annual_income_avg"),
        )
        .orderBy("year", "region", "regime", "resico_flag")
    )

    spark.sql(f"CREATE DATABASE IF NOT EXISTS spark_catalog.{namespace}")
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table} (
            year STRING NOT NULL,
            region STRING NOT NULL,
            regime STRING NOT NULL,
            resico_flag BOOLEAN NOT NULL,
            taxpayer_count BIGINT NOT NULL,
            annual_income_total BIGINT,
            annual_income_avg DOUBLE
        )
        USING iceberg
        PARTITIONED BY (year)
        LOCATION '{table_location}'
        TBLPROPERTIES ('format-version'='2')
        """
    )
    gold.createOrReplaceTempView("sat_gold_stage")
    spark.sql(
        f"""
        INSERT OVERWRITE TABLE {qualified_table}
        SELECT
            year,
            region,
            regime,
            resico_flag,
            taxpayer_count,
            annual_income_total,
            annual_income_avg
        FROM sat_gold_stage
        """
    )

    iceberg_gold = spark.table(qualified_table).orderBy(
        "year", "region", "regime", "resico_flag"
    )
    iceberg_gold.coalesce(1).write.mode("overwrite").option("header", True).csv(
        args.gold_path
    )

    snapshot_rows = spark.sql(
        f"""
        SELECT snapshot_id, committed_at, operation, manifest_list, summary
        FROM {qualified_table}.snapshots
        ORDER BY committed_at DESC
        LIMIT 20
        """
    ).collect()
    snapshots = []
    for row in snapshot_rows:
        summary = dict(row["summary"] or {})
        snapshots.append(
            {
                "snapshot_id": str(row["snapshot_id"]),
                "committed_at": str(row["committed_at"]),
                "operation": str(row["operation"]),
                "manifest_list": str(row["manifest_list"]),
                "total_records": summary.get("total-records", ""),
            }
        )
    current_snapshot = snapshots[0] if snapshots else {}

    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_path": args.raw_path,
        "gold_path": args.gold_path,
        "year": args.year,
        "input_rows": raw.count(),
        "cleaned_rows": cleaned.count(),
        "gold_rows": iceberg_gold.count(),
        "direct_rfc_in_gold": False,
        "iceberg": {
            "verified": bool(snapshots),
            "format": "iceberg",
            "format_version": 2,
            "catalog": "spark_catalog",
            "namespace": namespace,
            "table": table,
            "qualified_name": qualified_table,
            "warehouse": args.iceberg_warehouse,
            "table_location": table_location,
            "metadata_location": current_snapshot.get("manifest_list", ""),
            "current_snapshot_id": current_snapshot.get("snapshot_id", ""),
            "partitioning": ["identity(year)"],
            "schema": schema_metadata(iceberg_gold),
            "snapshots": snapshots,
        },
    }
    write_audit(spark, args.audit_path, audit)
    spark.stop()


if __name__ == "__main__":
    sys.excepthook = publish_unhandled_failure
    main()
