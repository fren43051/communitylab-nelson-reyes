"""
Estado compartido del grafo LangGraph.
"""
from typing import TypedDict, Optional
from src.ingestion.models import LoteInteracciones, AnalisisInteraccion, PaqueteDistribucion


class CommunityLabState(TypedDict):
    lote: LoteInteracciones
    rechazados: list[dict]
    analisis: list[AnalisisInteraccion]
    activos_generados: list[dict]
    paquete_final: Optional[PaqueteDistribucion]
    oci_resultado: Optional[dict]
