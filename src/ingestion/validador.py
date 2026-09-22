"""
Modulo de validacion local en dos capas para CommunityLab.
Patron adoptado del Grupo 34: nunca se rechaza el lote completo por un registro
corrupto; los invalidos se aislan en auditoria y el resto sigue procesandose.
"""
from typing import Tuple
from pydantic import ValidationError

from src.ingestion.models import LoteInteraccionesCrudo, Interaccion, LoteInteracciones


def validar_lote_crudo(payload: LoteInteraccionesCrudo) -> Tuple[LoteInteracciones, list[dict]]:
    """
    Recibe un LoteInteraccionesCrudo (admision permisiva) y devuelve:
    - lote_validado: LoteInteracciones con solo los registros que pasan validacion estricta
    - rechazados: lista de dicts con el registro crudo + motivo de fallo, para auditoria
    """
    validos: list[Interaccion] = []
    rechazados: list[dict] = []

    for raw_item in payload.interacciones:
        try:
            validado = Interaccion(
                id=raw_item.id,
                autor=raw_item.autor,
                canal=raw_item.canal,
                tipo=raw_item.tipo,
                texto=raw_item.texto or "",
                metadata_origen=raw_item.metadata_origen,
            )
            validos.append(validado)
        except ValidationError as e:
            rechazados.append({
                "id": raw_item.id,
                "autor": raw_item.autor,
                "canal": raw_item.canal,
                "error": str(e),
                "texto_crudo": raw_item.texto,
                "metadata_origen": raw_item.metadata_origen.model_dump(),
            })

    lote_validado = LoteInteracciones(
        origen_comunidad=payload.origen_comunidad,
        periodo_referencia=payload.periodo_referencia,
        interacciones=validos,
    )
    return lote_validado, rechazados
