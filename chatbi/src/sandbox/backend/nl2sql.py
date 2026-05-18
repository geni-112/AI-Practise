import os
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv
from schema_registry import get_relevant_schema

load_dotenv()

_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "https://api-ap-southeast-1.modelarts-maas.com/openai/v1")
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client

MODEL = os.getenv("LLM_MODEL", "glm-5.1")

SYSTEM_PROMPT = """你是一个专业的数据分析师，擅长将自然语言问题转换为 DuckDB SQL 查询。

{schema}

## 规则
1. 只返回 SQL 语句，不要任何解释，不要 markdown 代码块（不要```sql）
2. 使用 DuckDB 语法：DATE_TRUNC('month', order_date)、STRFTIME('%Y-%m', order_date)
3. 默认只统计 status='completed' 的订单，除非用户明确要求其他状态
4. 金额字段保留2位小数：ROUND(SUM(total_amount), 2) as sales_amount
5. 结果默认按金额或数量降序排列，加 LIMIT 100
6. 季度用 DATE_TRUNC('quarter', order_date)
7. "上季度"指相对当前日期的上一个自然季度，用 CURRENT_DATE 计算
8. 多表查询时写完整 JOIN 条件

## 对话历史
{history}
"""

def _extract_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```', '', text)
    text = text.split(';')[0].strip() + ';'
    return text

async def generate_sql(question: str, history_text: str, error_context: str = "") -> str:
    schema = get_relevant_schema(question)
    system = SYSTEM_PROMPT.format(schema=schema, history=history_text)

    user_content = question
    if error_context:
        user_content = f"""上次生成的SQL执行报错：{error_context}

请修正后重新生成SQL，只返回修正后的SQL语句。
原始问题：{question}"""

    client = get_client()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content or ""
    return _extract_sql(raw)

async def generate_insight(question: str, sql: str, rows: list[dict]) -> str:
    if not rows:
        return "查询结果为空，可能没有符合条件的数据。"

    preview = str(rows[:5])
    total = len(rows)

    client = get_client()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是数据分析助手，用简洁的中文解读查询结果，2-3句话，突出关键数字和洞察，不要重复问题。"},
            {"role": "user", "content": f"问题：{question}\n结果（共{total}行，前5行）：{preview}\n请解读这个结果。"},
        ],
        temperature=0.3,
        max_tokens=256,
    )
    return response.choices[0].message.content or "数据已返回，请查看图表。"
