"""
Carga y validacion de lotes de interacciones desde JSON o CSV.
"""
import json
import pandas as pd
from src.ingestion.models import LoteInteracciones, Interaccion


def cargar_json(ruta: str) -> LoteInteracciones:
    with open(ruta, "r", encoding="utf-8") as f:
        data = json.load(f)
    return LoteInteracciones(**data)


def cargar_csv(ruta: str, origen_comunidad: str, periodo_referencia: str) -> LoteInteracciones:
    """
    Espera columnas: autor, canal, tipo, texto
    """
    df = pd.read_csv(ruta)
    interacciones = [Interaccion(**row) for row in df.to_dict(orient="records")]
    return LoteInteracciones(
        origen_comunidad=origen_comunidad,
        periodo_referencia=periodo_referencia,
        interacciones=interacciones,
    )
