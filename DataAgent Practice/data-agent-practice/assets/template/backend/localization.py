"""Shared UI/agent copy. Locale changes display text, never execution identifiers."""
from __future__ import annotations
import json,re,unicodedata
from typing import Literal
from .config import ROOT

Locale=Literal['zh-CN','en-US','es-ES']
LANGUAGES={'zh-CN':'Simplified Chinese','en-US':'American English','es-ES':'Spanish'}
MESSAGES=json.loads((ROOT/'src/messages.json').read_text())


def translate(message:str,values=(),locale:Locale='zh-CN')->str:
    translations=MESSAGES.get(message)
    text=message if not translations else (translations[2] if len(translations)>2 else message) if locale=='zh-CN' else translations[0 if locale=='en-US' else 1]
    return re.sub(r'\{(\d+)\}',lambda match:str(values[int(match[1])]) if int(match[1])<len(values) else match[0],text)


def normalize_question(question:str)->str:
    text=''.join(c for c in unicodedata.normalize('NFD',question) if not unicodedata.combining(c))
    replacements=[
        ('ciudad de mexico','Mexico City'),('numero de pedidos|cantidad de pedidos','order count'),
        ('valor medio del pedido|valor promedio del pedido','aov'),('todos los meses|todo el periodo','all months'),
        ('todas las regiones','all regions'),('reembolsos?|devolucion(?:es)?','refund'),
        ('publicidad|publicitari[oa]s?|campanas?','advertising'),('inventario|existencias|reposicion','inventory'),
        ('resenas?|comentarios?|sentimiento','review'),('competencia|competidor(?:es)?','competitor'),
        ('ventas?|ingresos?','sales'),('categorias?','category'),('canal(?:es)?','channel'),
        ('regiones?|regional','region'),('tendencias?|mensual|meses','trend'),
        ('octubre','october'),('septiembre','september'),('norte','north'),('sur','south'),
    ]
    for pattern,replacement in replacements:text=re.sub(pattern,replacement,text,flags=re.I)
    return text
