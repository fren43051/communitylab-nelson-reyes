"""
Estado compartido del grafo LangGraph.

'activos_generados' usa un reducer (Annotated + operator.add) porque
generar_caso_exito y generar_faq pueden ejecutarse en el mismo superstep
(en paralelo) y ambos escriben en esa clave: el reducer le indica a LangGraph
que debe CONCATENAR las listas devueltas en vez de fallar por escritura concurrente.
"""
import operator
from typing import TypedDict, Optional, Annotated
from src.ingestion.models import LoteInteracciones, AnalisisInteraccion, PaqueteDistribucion


class CommunityLabState(TypedDict):
    lote: LoteInteracciones
    rechazados: list[dict]
    analisis: list[AnalisisInteraccion]
    activos_generados: Annotated[list[dict], operator.add]
    paquete_final: Optional[PaqueteDistribucion]
    oci_resultado: Optional[dict]
