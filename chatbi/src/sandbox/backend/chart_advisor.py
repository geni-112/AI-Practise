import re
from typing import Any

def advise_chart(sql: str, rows: list[dict[str, Any]]) -> dict:
    if not rows:
        return {"type": "table", "option": {}}

    cols = list(rows[0].keys())
    sql_lower = sql.lower()

    num_cols = [c for c in cols if isinstance(rows[0][c], (int, float))]
    str_cols = [c for c in cols if c not in num_cols]

    time_keywords = ['month', 'year', 'quarter', 'date', 'week', '月', '年', '季度', '日']
    has_time = any(any(kw in c.lower() for kw in time_keywords) for c in str_cols)
    if has_time and num_cols and len(rows) > 2:
        return _line_chart(rows, str_cols[0], num_cols[0])

    proportion_keywords = ['占比', '比例', '份额', '占', 'ratio', 'share', 'percent']
    if any(kw in sql_lower for kw in proportion_keywords) and num_cols:
        return _pie_chart(rows, str_cols[0] if str_cols else cols[0], num_cols[0])

    if len(str_cols) >= 1 and len(num_cols) >= 1 and len(rows) <= 30:
        return _bar_chart(rows, str_cols[0], num_cols[0])

    return {"type": "table", "option": {}}


def _bar_chart(rows, x_col, y_col):
    x_data = [str(r[x_col]) for r in rows]
    y_data = [round(float(r[y_col]), 2) for r in rows]
    return {
        "type": "bar",
        "option": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": x_data, "axisLabel": {"rotate": 30, "interval": 0}},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "data": y_data, "itemStyle": {"color": "#3b82f6"}}],
            "grid": {"left": "10%", "right": "5%", "bottom": "20%"}
        }
    }


def _line_chart(rows, x_col, y_col):
    x_data = [str(r[x_col]) for r in rows]
    y_data = [round(float(r[y_col]), 2) for r in rows]
    return {
        "type": "line",
        "option": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": x_data, "axisLabel": {"rotate": 30}},
            "yAxis": {"type": "value"},
            "series": [{"type": "line", "data": y_data, "smooth": True,
                        "areaStyle": {"opacity": 0.1}, "itemStyle": {"color": "#3b82f6"}}],
            "grid": {"left": "10%", "right": "5%", "bottom": "20%"}
        }
    }


def _pie_chart(rows, name_col, val_col):
    data = [{"name": str(r[name_col]), "value": round(float(r[val_col]), 2)} for r in rows]
    return {
        "type": "pie",
        "option": {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"orient": "vertical", "left": "left"},
            "series": [{"type": "pie", "radius": "60%", "data": data,
                        "emphasis": {"itemStyle": {"shadowBlur": 10}}}]
        }
    }
