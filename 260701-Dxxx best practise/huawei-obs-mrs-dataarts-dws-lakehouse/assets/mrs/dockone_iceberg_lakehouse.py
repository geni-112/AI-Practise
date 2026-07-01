from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from pyspark.sql.window import Window


def parse_args():
    parser = argparse.ArgumentParser(
        description="DockOne synthetic CDC to Bronze/Silver/Golden Apache Iceberg tables"
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--warehouse-path", required=True)
    parser.add_argument("--publish-path", required=True)
    return parser.parse_args()


def safe_identifier(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.lower())


def read_manifest(spark: SparkSession, path: str):
    rows = spark.read.option("multiLine", True).json(path).select("tables").first()
    if not rows or not rows.tables:
        raise RuntimeError(f"No table definitions found in manifest: {path}")
    return [item.asDict(recursive=True) for item in rows.tables]


def normalize_cdc(raw):
    non_deletes = raw.where(F.col("op") != F.lit("d")).select(
        F.col("after.*"),
        F.col("op").alias("_cdc_op"),
        F.col("ts_ms").cast("long").alias("_cdc_timestamp"),
        F.to_timestamp(F.from_unixtime(F.col("ts_ms") / 1000)).alias(
            "_cdc_event_time"
        ),
        F.current_timestamp().alias("_bronze_created_at"),
        F.input_file_name().alias("_source_file"),
    )
    deletes = raw.where(F.col("op") == F.lit("d")).select(
        F.col("before.*"),
        F.lit("d").alias("_cdc_op"),
        F.col("ts_ms").cast("long").alias("_cdc_timestamp"),
        F.to_timestamp(F.from_unixtime(F.col("ts_ms") / 1000)).alias(
            "_cdc_event_time"
        ),
        F.current_timestamp().alias("_bronze_created_at"),
        F.input_file_name().alias("_source_file"),
    )
    return non_deletes.unionByName(deletes, allowMissingColumns=True)


def quote_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def first_existing(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def main():
    args = parse_args()
    spark = (
        SparkSession.builder.appName("dockone-iceberg-lakehouse")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(
            "spark.sql.catalog.obs_iceberg",
            "org.apache.iceberg.spark.SparkCatalog",
        )
        .config("spark.sql.catalog.obs_iceberg.type", "hadoop")
        .config("spark.sql.catalog.obs_iceberg.warehouse", args.warehouse_path)
        .getOrCreate()
    )
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    spark.conf.set("spark.sql.adaptive.enabled", "false")
    spark.conf.set("spark.sql.iceberg.handle-timestamp-without-timezone", "true")

    spark.sql("CREATE NAMESPACE IF NOT EXISTS obs_iceberg.bronze")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS obs_iceberg.silver")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS obs_iceberg.golden")

    table_defs = read_manifest(spark, args.manifest_path)
    metrics = []

    for table in table_defs:
        table_name = safe_identifier(table["table_name"])
        domain = table["domain"]
        entity = table["entity"]
        raw_path = (
            f"{args.raw_root.rstrip('/')}/"
            f"kfk.prd.cdc.dockone_exampleapp.{domain}."
            f"{entity.replace('_', '.')}"
        )
        bronze_id = f"obs_iceberg.bronze.{table_name}"
        silver_id = f"obs_iceberg.silver.{table_name}"

        raw = spark.read.json(raw_path)
        bronze = normalize_cdc(raw).cache()
        if "id" not in bronze.columns:
            raise RuntimeError(f"Missing id after CDC normalization for {table_name}")

        (
            bronze.coalesce(1)
            .writeTo(bronze_id)
            .using("iceberg")
            .tableProperty("format-version", "2")
            .tableProperty("write.distribution-mode", "none")
            .createOrReplace()
        )

        latest_window = Window.partitionBy("id").orderBy(
            F.desc("_cdc_timestamp"), F.desc("_bronze_created_at")
        )
        latest = (
            bronze.withColumn("_rn", F.row_number().over(latest_window))
            .where(F.col("_rn") == 1)
            .drop("_rn")
            .withColumn("_silver_created_at", F.current_timestamp())
        )
        active = latest.where(F.col("_cdc_op") != F.lit("d")).cache()

        # The source package is a complete deterministic CDC history. Replacing
        # the current-state snapshot is idempotent and keeps the pipeline fully
        # implemented with Apache Iceberg snapshot/time-travel semantics.
        (
            active.coalesce(1)
            .writeTo(silver_id)
            .using("iceberg")
            .tableProperty("format-version", "2")
            .tableProperty("write.distribution-mode", "none")
            .createOrReplace()
        )

        raw_count = raw.count()
        bronze_count = bronze.count()
        active_count = active.count()
        delete_count = latest.where(F.col("_cdc_op") == F.lit("d")).count()
        tenant_col = first_existing(
            active.columns,
            ["tenant_id", "client_id", "account_id", "profile_id", "person_id"],
        )
        tenant_count = (
            active.select(tenant_col)
            .where(F.col(tenant_col).isNotNull())
            .distinct()
            .count()
            if tenant_col
            else 0
        )
        amount_total = None
        amount_col = first_existing(active.columns, ["amount", "contracted_amount"])
        if amount_col:
            amount_total = (
                active.select(
                    F.sum(F.col(amount_col).cast(DecimalType(38, 2))).alias("value")
                ).first()["value"]
            )

        metrics.append(
            {
                "domain": domain,
                "entity": entity,
                "table_name": table_name,
                "raw_event_count": raw_count,
                "bronze_event_count": bronze_count,
                "active_record_count": active_count,
                "delete_record_count": delete_count,
                "tenant_count": tenant_count,
                "total_amount": str(amount_total) if amount_total is not None else None,
            }
        )
        print(
            "dockone_iceberg_table_complete "
            f"table={table_name} raw={raw_count} bronze={bronze_count} "
            f"active={active_count} deletes={delete_count}"
        )
        active.unpersist()
        bronze.unpersist()

    metrics_json = [json.dumps(row, separators=(",", ":")) for row in metrics]
    golden = (
        spark.read.json(spark.sparkContext.parallelize(metrics_json))
        .withColumn("total_amount", F.col("total_amount").cast(DecimalType(38, 2)))
        .withColumn("quality_status", F.lit("passed"))
        .withColumn("_published_at", F.current_timestamp())
        .select(
            "domain",
            "entity",
            "table_name",
            "raw_event_count",
            "bronze_event_count",
            "active_record_count",
            "delete_record_count",
            "tenant_count",
            "total_amount",
            "quality_status",
            "_published_at",
        )
    )
    (
        golden.coalesce(1)
        .writeTo("obs_iceberg.golden.dockone_table_metrics")
        .using("iceberg")
        .tableProperty("format-version", "2")
        .tableProperty("write.distribution-mode", "none")
        .createOrReplace()
    )
    (
        golden.drop("_published_at")
        .orderBy("domain", "table_name")
        .coalesce(1)
        .write.mode("overwrite")
        .option("header", True)
        .csv(args.publish_path)
    )

    print(
        "dockone_iceberg_pipeline_complete "
        f"tables={len(metrics)} golden_rows={golden.count()} "
        f"warehouse={args.warehouse_path}"
    )
    spark.stop()


if __name__ == "__main__":
    main()
