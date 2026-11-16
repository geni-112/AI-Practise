// Product scope checked against Huawei Cloud documentation on 2026-11-13.
// These are capability candidates, not a claim of regional availability or equivalence.
const bigData='https://support.huaweicloud.com/intl/en-us/usermanual-caf/caf_01_0113.html';
const products='https://www.huaweicloud.com/intl/en-us/product/index.html';
const databases='https://www.huaweicloud.com/intl/en-us/securecenter/security/security_features.html';
export const SERVICE_CATALOG=[
 ['obs','Object Storage Service (OBS)','对象存储 / Object storage',bigData],
 ['mrs','MapReduce Service (MRS)','Hadoop / Spark 等大数据集群 / Big data clusters',bigData],
 ['dli','Data Lake Insight (DLI)','流批处理与 SQL 分析 / Stream, batch and SQL analytics',bigData],
 ['dws','GaussDB(DWS)','MPP 数据仓库 / MPP data warehouse','https://www.huaweicloud.com/intl/en-us/product/dws/architecture.html'],
 ['dataarts','DataArts Studio','数据集成、开发与治理 / Integration, development and governance',bigData],
 ['rds-mysql','RDS for MySQL','MySQL 关系数据库 / MySQL relational database',databases],
 ['rds-postgresql','RDS for PostgreSQL','PostgreSQL 关系数据库 / PostgreSQL relational database',databases],
 ['taurusdb','TaurusDB','MySQL 兼容数据库 / MySQL-compatible database',databases],
 ['gaussdb','GaussDB','分布式关系数据库 / Distributed relational database',databases],
 ['drs','Data Replication Service (DRS)','数据库迁移与同步 / Database migration and replication',databases],
 ['dds','Document Database Service (DDS)','MongoDB 兼容文档数据库 / MongoDB-compatible documents',databases],
 ['geminidb','GeminiDB','按 API 选择的 NoSQL 数据库 / API-specific NoSQL database',databases],
 ['css','Cloud Search Service (CSS)','搜索与日志分析 / Search and log analytics',bigData],
 ['kafka','DMS for Kafka','托管 Kafka 消息流 / Managed Kafka messaging',products],
 ['cce','Cloud Container Engine (CCE)','容器应用运行 / Container workloads',products],
 ['ecs','Elastic Cloud Server (ECS)','虚拟机与自建软件 / Virtual machines and self-managed software',products],
 ['vpc','Virtual Private Cloud (VPC)','网络隔离与连接 / Network isolation and connectivity',products],
 ['iam','Identity and Access Management (IAM)','身份与访问权限 / Identity and access',databases],
 ['dew','Data Encryption Workshop (DEW)','密钥管理与加密 / Keys and encryption',databases]
].map(([id,name,scope,url])=>({id,name,scope,url,verifiedOn:'2026-11-13',availability:'verify-in-target-region'}));
export const LAYERS=['source','ingestion','storage','processing','serving','governance','operations','network'];
