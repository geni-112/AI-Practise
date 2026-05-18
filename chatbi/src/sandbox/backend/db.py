import duckdb
import os
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "retail.duckdb")
_conn: duckdb.DuckDBPyConnection | None = None

def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        if not os.path.exists(DB_PATH):
            raise RuntimeError(
                f"数据库文件不存在: {DB_PATH}\n请先运行: python backend/data/seed.py"
            )
        _conn = duckdb.connect(DB_PATH, read_only=True)
    return _conn

def execute_query(sql: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rel = conn.execute(sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchmany(1000)
        result = [dict(zip(cols, row)) for row in rows]
        for row in result:
            for k, v in row.items():
                if hasattr(v, 'isoformat'):
                    row[k] = v.isoformat()
                elif hasattr(v, '__float__'):
                    row[k] = float(v)
        return result
    except Exception as e:
        raise ValueError(str(e))
