from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

MAX_TURNS = 10

@dataclass
class Turn:
    role: str
    content: str
    sql: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

_sessions: dict[str, list[Turn]] = {}

def get_history(session_id: str) -> list[Turn]:
    return _sessions.get(session_id, [])

def add_turn(session_id: str, role: str, content: str, sql: str | None = None) -> None:
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append(Turn(role=role, content=content, sql=sql))
    if len(_sessions[session_id]) > MAX_TURNS * 2:
        _sessions[session_id] = _sessions[session_id][-MAX_TURNS * 2:]

def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)

def format_history(session_id: str) -> str:
    turns = get_history(session_id)
    if not turns:
        return "（无历史对话）"
    lines = []
    for t in turns[-6:]:
        if t.role == "user":
            lines.append(f"用户：{t.content}")
        else:
            lines.append(f"助手：{t.content[:100]}...")
    return "\n".join(lines)
