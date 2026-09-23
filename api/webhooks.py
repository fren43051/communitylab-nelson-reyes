"""
Endpoint webhook que recibe lotes de interacciones (ej. desde n8n / LinkedIn)
y los procesa a traves del pipeline existente de CommunityLab, reutilizando
los modelos, validador y grafo ya construidos sin modificarlos.
"""
import hmac
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import ValidationError

from src.graph.build_graph import construir_grafo
from src.ingestion.models import LoteInteraccionesCrudo
from src.ingestion.validador import validar_lote_crudo

load_dotenv()

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
GRAFO = construir_grafo()


def validar_secreto_webhook(x_webhook_secret: str | None) -> None:
    secreto_configurado = os.getenv("WEBHOOK_SECRET")

    if not secreto_configurado:
        raise RuntimeError("WEBHOOK_SECRET no esta configurado en las variables de entorno")

    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, secreto_configurado):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secreto de webhook invalido",
        )


@router.get("/linkedin/health")
def comprobar_estado_webhook() -> dict:
    return {
        "status": "ok",
        "service": "communitylab",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/linkedin")
def recibir_datos_linkedin(
    payload: dict,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    validar_secreto_webhook(x_webhook_secret)

    try:
        lote_crudo = LoteInteraccionesCrudo.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.errors(),
        ) from error

    limite_items = int(os.getenv("WEBHOOK_MAX_ITEMS", "100"))

    if len(lote_crudo.interacciones) > limite_items:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El lote no puede superar {limite_items} interacciones",
        )

    lote_validado, rechazados = validar_lote_crudo(lote_crudo)

    if not lote_validado.interacciones:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"mensaje": "No hay interacciones validas para procesar", "rechazados": rechazados},
        )

    estado_inicial = {
        "lote": lote_validado,
        "rechazados": rechazados,
        "analisis": [],
        "activos_generados": [],
        "paquete_final": None,
        "oci_resultado": None,
    }

    try:
        resultado = GRAFO.invoke(estado_inicial)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo procesar el lote recibido",
        ) from error

    paquete_final = resultado["paquete_final"]

    return {
        "status": "procesado",
        "origen_comunidad": lote_crudo.origen_comunidad,
        "periodo_referencia": lote_crudo.periodo_referencia,
        "registros_recibidos": len(lote_crudo.interacciones),
        "registros_rechazados": len(rechazados),
        "paquete": paquete_final.model_dump(mode="json"),
    }
