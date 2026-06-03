from __future__ import annotations

import argparse
import os
from pyspark.sql import SparkSession


def parse_args():
    parser = argparse.ArgumentParser(description="Load silver Hudi table to DWS over JDBC")
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--silver-path", required=True)
    parser.add_argument("--dws-table", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    spark = SparkSession.builder.appName(f"dws-load-{args.table_name}").getOrCreate()
    df = spark.read.format("hudi").load(args.silver_path)
    jdbc_url = os.environ["DWS_JDBC_URL"]
    user = os.environ["DWS_USER"]
    password = os.environ["DWS_PASSWORD"]
    (
        df.write.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", args.dws_table)
        .option("user", user)
        .option("password", password)
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )
    print(f"dws_load_complete source={args.silver_path} target={args.dws_table} rows={df.count()}")


if __name__ == "__main__":
    main()
