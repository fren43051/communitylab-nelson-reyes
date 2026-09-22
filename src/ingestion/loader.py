"""
Carga de lotes de interacciones desde JSON o CSV, seguida de validacion en dos capas.
"""
import json
import pandas as pd

from src.ingestion.models import LoteInteraccionesCrudo, InteraccionCruda, LoteInteracciones
from src.ingestion.validador import validar_lote_crudo


def cargar_json_crudo(ruta: str) -> LoteInteraccionesCrudo:
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    return LoteInteraccionesCrudo(**data)


def cargar_csv_crudo(ruta: str, origen_comunidad: str, periodo_referencia: str) -> LoteInteraccionesCrudo:
    """
    Espera columnas: id, autor, canal, tipo, texto
    """
    df = pd.read_csv(ruta)
    interacciones = [InteraccionCruda(**row) for row in df.to_dict(orient="records")]
    return LoteInteraccionesCrudo(
        origen_comunidad=origen_comunidad,
        periodo_referencia=periodo_referencia,
        interacciones=interacciones,
    )


def cargar_json(ruta: str) -> tuple[LoteInteracciones, list[dict]]:
    """
    Carga un JSON y aplica validacion en dos capas.
    Devuelve (lote_validado, rechazados) - nunca lanza excepcion por un registro corrupto.
    """
    crudo = cargar_json_crudo(ruta)
    return validar_lote_crudo(crudo)


def cargar_csv(ruta: str, origen_comunidad: str, periodo_referencia: str) -> tuple[LoteInteracciones, list[dict]]:
    crudo = cargar_csv_crudo(ruta, origen_comunidad, periodo_referencia)
    return validar_lote_crudo(crudo)
