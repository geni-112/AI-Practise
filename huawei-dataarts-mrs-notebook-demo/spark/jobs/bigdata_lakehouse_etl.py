import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    current_timestamp,
    lit,
    regexp_extract,
    round as spark_round,
    sha2,
    sum as spark_sum,
    to_date,
    when,
)


def conf(spark, key, default=None):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


def read_raw(spark, input_format, raw_path):
    fmt = input_format.lower()
    if fmt == "csv":
        return spark.read.option("header", True).option("multiLine", False).csv(raw_path)
    if fmt == "json":
        return spark.read.json(raw_path)
    if fmt == "parquet":
        return spark.read.parquet(raw_path)
    raise ValueError(f"Unsupported input format: {input_format}")


def parse_args():
    parser = argparse.ArgumentParser(description="OBS raw-to-curated Spark ETL for the Huawei DataArts + MRS demo.")
    parser.add_argument("--raw-path")
    parser.add_argument("--clean-path")
    parser.add_argument("--reject-path")
    parser.add_argument("--curated-path")
    parser.add_argument("--event-path")
    parser.add_argument("--input-format", default=None)
    parser.add_argument("--biz-date", default=None)
    parser.add_argument("--shuffle-partitions", default=None)
    parser.add_argument("--curated-table", default=None)
    return parser.parse_args()


def pick(cli_value, spark, conf_key, default=None):
    return cli_value or conf(spark, conf_key, default)


def main():
    args = parse_args()
    spark = (
        SparkSession.builder.appName("dataarts-mrs-bigdata-lakehouse-etl")
        .enableHiveSupport()
        .getOrCreate()
    )

    raw_path = pick(args.raw_path, spark, "demo.raw_path")
    clean_path = pick(args.clean_path, spark, "demo.clean_path")
    reject_path = pick(args.reject_path, spark, "demo.reject_path")
    curated_path = pick(args.curated_path, spark, "demo.curated_path")
    event_path = pick(args.event_path, spark, "demo.event_path", f"{curated_path.rstrip('/')}/_events")
    input_format = pick(args.input_format, spark, "demo.input_format", "csv")
    biz_date = pick(args.biz_date, spark, "demo.biz_date", "2026-06-07")
    shuffle_partitions = pick(args.shuffle_partitions, spark, "demo.shuffle_partitions", "200")
    curated_table = pick(args.curated_table, spark, "demo.curated_table", "demo_daily_channel_metrics")

    required = {
        "demo.raw_path": raw_path,
        "demo.clean_path": clean_path,
        "demo.reject_path": reject_path,
        "demo.curated_path": curated_path,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing required Spark conf: {', '.join(missing)}")

    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.shuffle.partitions", shuffle_partitions)

    raw = read_raw(spark, input_format, raw_path).withColumn("biz_date", lit(biz_date))
    parsed = (
        raw.withColumn("amount_number", col("amount").cast("double"))
        .withColumn("event_date", to_date(lit(biz_date)))
        .withColumn("member_hash", sha2(col("member_id").cast("string"), 256))
    )

    valid = (
        parsed.filter(col("order_id").isNotNull())
        .filter(col("amount_number").isNotNull())
        .filter(col("amount_number") > 0)
        .dropDuplicates(["order_id"])
    )

    clean = valid.select(
        "biz_date",
        "event_date",
        "order_id",
        "channel",
        "store_id",
        col("amount_number").alias("amount"),
        "status",
        regexp_extract(col("member_hash"), r"^(.{16})", 1).alias("member_hash_prefix"),
    )

    rejects = (
        parsed.withColumn(
            "reject_reason",
            when(col("order_id").isNull(), lit("missing_order_id"))
            .when(col("amount_number").isNull(), lit("invalid_amount"))
            .when(col("amount_number") <= 0, lit("non_positive_amount"))
            .otherwise(lit(None)),
        )
        .filter(col("reject_reason").isNotNull())
        .select("biz_date", "order_id", "channel", "store_id", "amount", "status", "reject_reason")
    )

    clean.repartition("biz_date", "channel").write.mode("overwrite").partitionBy("biz_date", "channel").parquet(clean_path)
    rejects.repartition("biz_date").write.mode("overwrite").partitionBy("biz_date").parquet(reject_path)

    metrics = (
        clean.groupBy("biz_date", "channel")
        .agg(
            count("*").alias("orders"),
            spark_round(spark_sum(when(col("status") != "refunded", col("amount")).otherwise(0)), 2).alias("revenue"),
            spark_sum(when(col("status") == "refunded", 1).otherwise(0)).alias("refunds"),
        )
        .withColumn("quality_status", when(col("refunds") > 0, lit("review")).otherwise(lit("passed")))
        .withColumn("published_at", current_timestamp())
    )

    metrics.repartition("biz_date").write.mode("overwrite").partitionBy("biz_date").parquet(curated_path)

    spark.sql("CREATE DATABASE IF NOT EXISTS demo_lakehouse")
    metrics.write.mode("overwrite").saveAsTable(f"demo_lakehouse.{curated_table}")

    event = metrics.select(
        "biz_date",
        "channel",
        "orders",
        "revenue",
        "quality_status",
        lit("dataarts-mrs-bigdata-lakehouse-etl").alias("pipeline"),
        current_timestamp().alias("event_time"),
    )
    event.coalesce(1).write.mode("overwrite").json(event_path)
    spark.stop()


if __name__ == "__main__":
    main()
