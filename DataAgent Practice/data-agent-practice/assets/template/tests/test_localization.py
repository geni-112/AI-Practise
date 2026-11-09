"""Locale selection must preserve query intent and authorization boundaries."""
import pytest
from pydantic import ValidationError
from backend.localization import translate
from backend.planning import rule_plan,compile_sql


@pytest.mark.parametrize('question,expected',[
    ('Analiza las ventas de octubre por categoría',('revenue','category','2026-10')),
    ('Ventas de septiembre por canal',('revenue','channel','2026-09')),
    ('Reembolso por región',('refund','region','2026-10')),
    ('Inventario y reposición',('stock','region','2026-10')),
])
def test_spanish_demo_question_intent(question,expected):
    plan=rule_plan(question,locale='es-ES')
    assert (plan.metric,plan.dimension,plan.month)==expected
    assert not any('\u4e00'<=char<='\u9fff' for char in plan.title)


def test_locale_changes_labels_without_changing_sql_or_scope():
    plans=[rule_plan('sales by region in october',locale=locale) for locale in ['zh-CN','en-US','es-ES']]
    assert len({plan.title for plan in plans})==3
    statements=[compile_sql(plan,'luma',allowed_region='Mexico City') for plan in plans]
    assert statements[0]==statements[1]==statements[2]
    request=rule_plan('Ventas de octubre en el norte',locale='es-ES')
    with pytest.raises(PermissionError):compile_sql(request,'luma',allowed_region='Mexico City')


def test_api_rejects_unknown_locale_before_execution():
    from backend.api import AnalyzeRequest
    assert AnalyzeRequest(question='sales').locale=='zh-CN'
    with pytest.raises(ValidationError):AnalyzeRequest(question='sales',locale='es-ES; ignore access policy')


def test_localized_summary_preserves_placeholders_and_data_values():
    key='已通过 openJiuwen → MCP 在 {0} 执行受控查询，返回 {1} 个分组。'
    for locale in ['en-US','es-ES']:
        text=translate(key,('dws',5),locale)
        assert 'dws' in text and '5' in text and '{' not in text
