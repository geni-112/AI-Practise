# Delta Table to Hudi Replacement

| Databricks / Delta behavior | Hudi replacement in this demo |
| --- | --- |
| `DeltaTable.createIfNotExists(...).location(path)` | Hudi table created on first Spark write to `obs://.../lake/{bronze,silver}/...` |
| Bronze `mode=append` | Hudi COW table with `operation=upsert`, preserving latest per record key |
| Silver `merge` by `id` | Hudi `recordkey.field=id` and `operation=upsert` |
| `sequence_by=_cdc_timestamp` | Hudi `precombine.field=_cdc_timestamp` |
| `whenMatchedDelete(source_._cdc_op = 'd')` | Hudi `operation=delete` for latest delete records |
| Delta checkpoints / schema tracking | Self-built manifest/checkpoint/schema-log plus Hudi commit timeline |
| Unity Catalog table name | DataArts catalog / Hive sync / Hudi metadata path |

The important implementation detail is to split latest CDC events into upserts and deletes after deduplication. This avoids treating delete envelopes as ordinary rows.
