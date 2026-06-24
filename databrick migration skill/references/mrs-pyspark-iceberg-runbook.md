# MRS PySpark + Iceberg Runbook

Use this reference when a migration needs runnable MRS client commands for PySpark scripts that use Iceberg tables.

## Environment Preparation

- Prepare an MRS cluster with Python 3 support, an MRS client host, and a test user.
- Do not assume the cluster built-in Python environment is sufficient for business PySpark jobs.
- Use Python 3.7 or later when the source workload requires modern Python packages.
- Package the Python runtime/dependencies and upload the archive to HDFS when the job depends on custom packages.
- Source the MRS client environment and authenticate before running Spark:

```bash
source /opt/client/bigdata_env
kinit <user>
```

## Iceberg Spark SQL Session

Use this pattern for manual DDL and smoke checks:

```bash
spark-sql \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkSessionCatalog \
  --conf spark.sql.catalog.spark_catalog.type=hive \
  --conf spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.local.type=hadoop \
  --conf spark.sql.catalog.local.warehouse=/tmp/iceberg \
  --conf spark.sql.storeAssignmentPolicy=ANSI
```

For Hive-catalog Iceberg demos, create the target database explicitly:

```sql
CREATE DATABASE IF NOT EXISTS sat;
```

Create HDFS directories before DDL when using explicit `LOCATION`, for example `/sat/MVP` and `/sat/Datos_idc`.

## Demo DDL Pattern

Use explicit Iceberg DDL for every source table the Databricks code assumed already existed:

```sql
CREATE TABLE IF NOT EXISTS sat.MVP_REC_PADRON_BASE_PERIODO (
  EJERCICIO INT COMMENT 'Ejercicio',
  PERIODO INT COMMENT 'Periodo',
  C_IDC_RFCEEOG1 STRING COMMENT 'RFC del contribuyente'
) USING iceberg
LOCATION 'hdfs://hacluster/sat/MVP/ICEBERG/MVP_REC_PADRON_BASE_PERIODO';
```

Keep table and location names parameterized when turning the demo into a reusable artifact.

## Generate Mock Data

If the source code lacks DDL or seed data, create a `generate_mock_data.py` style helper that inserts representative records into all required Iceberg tables. Submit it with the same Iceberg configuration used by the main job:

```bash
spark-submit \
  --master yarn-cluster \
  --archives hdfs:///tmp/python.zip#test_python \
  --conf spark.pyspark.python=/usr/bin/python3 \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkSessionCatalog \
  --conf spark.sql.catalog.spark_catalog.type=hive \
  --conf spark.sql.storeAssignmentPolicy=ANSI \
  /opt/sattest/generate_mock_data.py
```

After generating data, query key source tables and target tables before running the migrated ETL.

## Package Migrated PySpark Code

When notebook code is converted into Python modules, keep a clear package shape:

```text
padron_base/main.py                         # core ETL entry such as run_padron_base
funcion_utils/funcion_utils2.py             # shared helpers such as carga_tablas
funciones_mvp_padron_base/                  # business functions
Lanzador_Packages/main.py                   # launcher/orchestration entry
```

Package modules for Spark with:

```bash
zip -r code.zip funcion_utils/ Lanzador_Packages/ padron_base/ funciones_mvp_padron_base/
```

Upload source configuration files such as `Fuentes_mvp.csv` to the expected HDFS/OBS location. When migrating to Iceberg, store table references as `database.table` where possible instead of raw paths.

## Submit Main Job

Use this baseline submit command for migrated MRS PySpark jobs:

```bash
spark-submit \
  --master yarn-cluster \
  --py-files code.zip \
  --archives hdfs:///tmp/python.zip#test_python \
  --conf spark.pyspark.python=/usr/bin/python3 \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkSessionCatalog \
  --conf spark.sql.catalog.spark_catalog.type=hive \
  --conf spark.sql.storeAssignmentPolicy=ANSI \
  Lanzador_Packages/main.py \
  --ubicacion NPSI \
  --ejercicio_analisis 2023 \
  --cve_regimenes 601 \
  --cve_rol 300590 \
  --prefijo_ruta_salida sat \
  --rango PADRON_BASE \
  --cve_regimen_resico 626
```

Adjust the business parameters for each demo and document their meaning in the runbook.

## Validation

- Check the Yarn task status after submit.
- Query all core output tables, for example `mvp_rec_padron_base`, `mvp_rec_padron_base_annual`, `mvp_rec_padron_base_periodo`, `padron_base_resico`, and `padron_base_resico_marcas`.
- Confirm source configuration files such as `Fuentes_mvp.csv` were updated to Iceberg table references.
- Include at least row counts and a small data sample in demo evidence.
