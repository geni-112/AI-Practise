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


def main():
    spark = (
        SparkSession.builder.appName("dataarts-mrs-bigdata-lakehouse-etl")
        .enableHiveSupport()
        .getOrCreate()
    )

    raw_path = conf(spark, "demo.raw_path")
    clean_path = conf(spark, "demo.clean_path")
    reject_path = conf(spark, "demo.reject_path")
    curated_path = conf(spark, "demo.curated_path")
    event_path = conf(spark, "demo.event_path", f"{curated_path.rstrip('/')}/_events")
    input_format = conf(spark, "demo.input_format", "csv")
    biz_date = conf(spark, "demo.biz_date", "2026-06-07")
    shuffle_partitions = conf(spark, "demo.shuffle_partitions", "200")
    curated_table = conf(spark, "demo.curated_table", "demo_daily_channel_metrics")

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
