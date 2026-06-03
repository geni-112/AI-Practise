from __future__ import annotations

import argparse
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def parse_args():
    parser = argparse.ArgumentParser(description="Raw CDC JSON to bronze Hudi")
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument("--checkpoint-path", required=True)
    parser.add_argument("--hudi-table-name", required=True)
    return parser.parse_args()


def hudi_options(args):
    return {
        "hoodie.table.name": args.hudi_table_name,
        "hoodie.datasource.write.table.type": "COPY_ON_WRITE",
        "hoodie.datasource.write.operation": "upsert",
        "hoodie.datasource.write.recordkey.field": "id",
        "hoodie.datasource.write.precombine.field": "_cdc_timestamp",
        "hoodie.datasource.write.partitionpath.field": "_cdc_date",
        "hoodie.datasource.write.hive_style_partitioning": "true",
        "hoodie.datasource.write.keygenerator.class": "org.apache.hudi.keygen.ComplexKeyGenerator",
        "hoodie.datasource.hive_sync.enable": "false",
        "hoodie.datasource.hive_sync.table": args.hudi_table_name,
        "hoodie.datasource.hive_sync.partition_fields": "_cdc_date",
        "hoodie.upsert.shuffle.parallelism": "2",
        "hoodie.insert.shuffle.parallelism": "2",
    }


def main():
    args = parse_args()
    spark = SparkSession.builder.appName(f"bronze-hudi-{args.table_name}").getOrCreate()
    raw = spark.read.json(args.raw_path)

    non_deletes = raw.where(F.col("op") != F.lit("d")).select(
        F.col("after.*"),
        F.col("op").alias("_cdc_op"),
        F.col("ts_ms").alias("_cdc_timestamp"),
        F.to_date(F.from_unixtime(F.col("ts_ms") / 1000)).alias("_cdc_date"),
        F.current_timestamp().alias("_bronze_created_at"),
    )

    deletes = raw.where(F.col("op") == F.lit("d")).select(
        F.col("before.*"),
        F.lit("d").alias("_cdc_op"),
        F.col("ts_ms").alias("_cdc_timestamp"),
        F.to_date(F.from_unixtime(F.col("ts_ms") / 1000)).alias("_cdc_date"),
        F.current_timestamp().alias("_bronze_created_at"),
    )

    bronze = non_deletes.unionByName(deletes, allowMissingColumns=True)
    bronze.write.format("hudi").options(**hudi_options(args)).mode("append").save(args.bronze_path)
    print(f"bronze_hudi_complete table={args.table_name} path={args.bronze_path} rows={bronze.count()}")


if __name__ == "__main__":
    main()
