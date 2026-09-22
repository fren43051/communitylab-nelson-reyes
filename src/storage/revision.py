"""
Gestion del ciclo de revision humana sobre un PaqueteDistribucion.
Aplica la decision del curador (aprobar/rechazar) y actualiza el paquete,
re-persistiendo en OCI para dejar registro de auditoria de la decision.
"""
from datetime import datetime, timezone

from src.ingestion.models import PaqueteDistribucion, HumanReviewControl
from src.storage.oci_client import subir_paquete_a_oci


def aplicar_decision_revision(
    paquete: PaqueteDistribucion,
    estado_decision: str,
    revisor: str,
    comentarios: str | None = None,
) -> PaqueteDistribucion:
    """
    Aplica una decision de revision humana (aprobado/rechazado) sobre el paquete,
    incrementando el numero de revision si ya habia una decision previa.
    """
    revision_anterior = paquete.control_revision_humana.numero_revision
    nueva_revision = revision_anterior + 1 if paquete.control_revision_humana.estado_decision != "pendiente" else revision_anterior

    paquete.control_revision_humana = HumanReviewControl(
        numero_revision=nueva_revision,
        estado_decision=estado_decision,
        revisor=revisor,
        fecha_decision=datetime.now(timezone.utc),
        comentarios=comentarios,
    )
    return paquete


def persistir_decision_en_oci(paquete: PaqueteDistribucion, periodo_referencia: str) -> dict:
    """
    Re-sube el paquete actualizado (con la decision de revision aplicada) a OCI,
    dejando trazabilidad de que la version final incluye la aprobacion/rechazo humano.
    """
    resultado = subir_paquete_a_oci(paquete, periodo_referencia=periodo_referencia)
    return resultado
