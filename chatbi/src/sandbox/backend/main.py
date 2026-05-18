import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from nl2sql import generate_sql, generate_insight
from db import execute_query
from session import add_turn, clear_session, format_history
from chart_advisor import advise_chart
from cache import get as cache_get, set as cache_set

app = FastAPI(title="ChatBI Sandbox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str
    session_id: str

class ChatResponse(BaseModel):
    sql: str
    result: list[dict]
    chart: dict | None
    insight: str
    cached: bool
    error: str | None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    cached = cache_get(question)
    if cached:
        return {**cached, "cached": True}

    history_text = format_history(req.session_id)
    sql = ""
    rows = []
    error_msg = None

    for attempt in range(3):
        try:
            error_context = error_msg if attempt > 0 else ""
            sql = await generate_sql(question, history_text, error_context)
            rows = execute_query(sql)
            error_msg = None
            break
        except Exception as e:
            error_msg = str(e)
            if attempt == 2:
                add_turn(req.session_id, "user", question)
                add_turn(req.session_id, "assistant", f"查询失败：{error_msg}", sql)
                return ChatResponse(
                    sql=sql,
                    result=[],
                    chart=None,
                    insight=f"抱歉，无法生成准确的查询，请换一种描述方式。（{error_msg[:100]}）",
                    cached=False,
                    error=error_msg,
                )

    chart = advise_chart(sql, rows)
    insight = await generate_insight(question, sql, rows)

    add_turn(req.session_id, "user", question)
    add_turn(req.session_id, "assistant", insight, sql)

    response_data = {
        "sql": sql,
        "result": rows,
        "chart": chart,
        "insight": insight,
        "cached": False,
        "error": None,
    }
    cache_set(question, response_data)
    return ChatResponse(**response_data)

@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    clear_session(session_id)
    return {"status": "cleared"}
