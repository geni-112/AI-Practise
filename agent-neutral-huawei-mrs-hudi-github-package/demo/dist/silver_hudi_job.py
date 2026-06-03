from __future__ import annotations

import argparse
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def parse_args():
    parser = argparse.ArgumentParser(description="Bronze Hudi to silver Hudi with CDC merge semantics")
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument("--silver-path", required=True)
    parser.add_argument("--hudi-table-name", required=True)
    return parser.parse_args()


def base_options(args, operation):
    return {
        "hoodie.table.name": args.hudi_table_name,
        "hoodie.datasource.write.table.type": "COPY_ON_WRITE",
        "hoodie.datasource.write.operation": operation,
        "hoodie.datasource.write.recordkey.field": "id",
        "hoodie.datasource.write.precombine.field": "_cdc_timestamp",
        "hoodie.datasource.write.partitionpath.field": "tenant_id",
        "hoodie.datasource.write.hive_style_partitioning": "true",
        "hoodie.datasource.hive_sync.enable": "false",
        "hoodie.datasource.hive_sync.table": args.hudi_table_name,
        "hoodie.datasource.hive_sync.partition_fields": "tenant_id",
        "hoodie.upsert.shuffle.parallelism": "2",
        "hoodie.delete.shuffle.parallelism": "2",
    }


def main():
    args = parse_args()
    spark = SparkSession.builder.appName(f"silver-hudi-{args.table_name}").getOrCreate()
    bronze = spark.read.format("hudi").load(args.bronze_path)
    window = Window.partitionBy("id").orderBy(F.desc_nulls_first("_cdc_timestamp"))
    latest = bronze.withColumn("_rn", F.row_number().over(window)).where("_rn = 1").drop("_rn")
    business_cols = [c for c in latest.columns if not c.startswith("_hoodie_")]
    latest = latest.select(*business_cols, F.current_timestamp().alias("_silver_created_at"))

    upserts = latest.where(F.col("_cdc_op") != F.lit("d"))
    deletes = latest.where(F.col("_cdc_op") == F.lit("d")).select("id", "_cdc_timestamp", "tenant_id")

    if upserts.take(1):
        upserts.write.format("hudi").options(**base_options(args, "upsert")).mode("append").save(args.silver_path)
    if deletes.take(1):
        deletes.write.format("hudi").options(**base_options(args, "delete")).mode("append").save(args.silver_path)

    print(
        "silver_hudi_complete "
        f"table={args.table_name} path={args.silver_path} "
        f"upserts={upserts.count()} deletes={deletes.count()}"
    )


if __name__ == "__main__":
    main()
