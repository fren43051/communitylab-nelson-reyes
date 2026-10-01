import os
import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path para resolución de módulos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.ingestion.models import (
    InteraccionCruda,
    LoteInteraccionesCrudo,
    Interaccion,
    LoteInteracciones,
    AnalisisInteraccion,
    PaqueteDistribucion,
)
from src.ingestion.validador import validar_lote_crudo
from src.graph.nodes import enrutar_categorias
from api.main import app

# =====================================================================
# 1. PRUEBAS DE MODELOS Y VALIDACIÓN PYDANTIC
# =====================================================================

def test_lote_crudo_valido_y_rechazos():
    """Valida que los registros con texto sean aceptados y los vacíos rechazados."""
    datos = {
        "schema_version": "1.0.0",
        "origen_comunidad": "discord",
        "periodo_referencia": "2026-10-01",
        "interacciones": [
            {
                "id": "int-001",
                "autor": "Mariana Souza",
                "canal": "discord",
                "tipo": "testimonio",
                "texto": "Quedé contratada como Dev Jr gracias al curso de IA!",
            },
            {
                "id": "int-002",
                "autor": "Usuario Vacío",
                "canal": "discord",
                "tipo": "otro",
                "texto": "   ",  # Solo espacios en blanco -> debe rechazarse
            },
        ],
    }

    lote_crudo = LoteInteraccionesCrudo.model_validate(datos)
    assert len(lote_crudo.interacciones) == 2

    lote_valido, rechazados = validar_lote_crudo(lote_crudo)
    assert len(lote_valido.interacciones) == 1
    assert lote_valido.interacciones[0].id == "int-001"
    assert len(rechazados) == 1
    assert rechazados[0]["id"] == "int-002"


def test_esquema_paquete_distribucion_completo():
    """Valida la integridad de la estructura de salida PaqueteDistribucion."""
    paquete_dict = {
        "schema_version": "1.2.0",
        "status": "exito",
        "fecha_generacion": datetime.now(timezone.utc).isoformat(),
        "resumen_comunidad": {
            "total_interacciones_procesadas": 1,
            "registros_validos": 1,
            "registros_rechazados": 0,
            "sentimiento_predominante": "Muy Positivo",
            "temas_principales": ["Contratación", "LangGraph"],
            "alertas_soporte": [],
        },
        "activos_distribucion_generados": {
            "post_linkedin": {
                "titulo": "De la comunidad al mercado laboral",
                "cuerpo": "Felicitaciones a Mariana...",
                "canal_recomendado": "LinkedIn Oficial",
                "potencial_engagement": "Alto",
                "source_ids": ["int-001"],
            },
            "destaque_newsletter_semanal": {
                "seccion": "Logro de la Semana",
                "titular": "Estudiante contratada en IA",
                "resumen": "Mariana comparte su experiencia...",
                "source_ids": ["int-001"],
            },
            "sugerencia_contenido_faq": None,
        },
        "control_revision_humana": {
            "numero_revision": 1,
            "estado_decision": "pendiente",
            "revisor": None,
            "fecha_decision": None,
            "comentarios": None,
        },
        "almacenamiento_oci": {
            "bucket": "communitylab-activos-marketing",
            "ruta_objeto": "activos/2026-10-01/paquete-distribucion.json",
            "status": "guardado_con_exito",
            "comprobacion_lectura": True,
        },
        "metadatos_ejecucion": {
            "modelo": "claude-haiku-4-5-20251001",
            "latencia_ms": 1200,
        },
    }

    paquete = PaqueteDistribucion.model_validate(paquete_dict)
    assert paquete.status == "exito"
    assert paquete.resumen_comunidad.total_interacciones_procesadas == 1
    assert paquete.control_revision_humana.estado_decision == "pendiente"


# =====================================================================
# 2. PRUEBAS DEL ROUTER CONDICIONAL DE LANGGRAPH
# =====================================================================

def test_router_enrutar_caso_exito():
    """Valida que interacciones de caso de éxito enruten a generar_caso_exito."""
    estado = {
        "analisis": [
            {
                "id": "test-01",
                "sentimiento": "Muy Positivo",
                "puntuacion_relevancia": 0.95,
                "temas": ["Logro"],
                "categoria_accion": "caso_exito",
                "motivo_seleccion": "Testimonio relevante de contratación",
                "resumen_ejecutivo": "Testimonio de contratación",
            }
        ]
    }
    destino = enrutar_categorias(estado)
    assert "generar_caso_exito" in destino


def test_router_enrutar_faq():
    """Valida que preguntas técnicas enruten a generar_faq."""
    estado = {
        "analisis": [
            {
                "id": "test-02",
                "sentimiento": "Neutral",
                "puntuacion_relevancia": 0.85,
                "temas": ["LangGraph"],
                "categoria_accion": "faq_tip",
                "motivo_seleccion": "Pregunta técnica recurrente",
                "resumen_ejecutivo": "Duda sobre router en LangGraph",
            }
        ]
    }
    destino = enrutar_categorias(estado)
    assert "generar_faq" in destino


# =====================================================================
# 3. PRUEBAS DEL ENDPOINT WEBHOOK FASTAPI
# =====================================================================

client = TestClient(app)

def test_webhook_rechaza_sin_secreto():
    """Valida que una petición sin X-Webhook-Secret responda 401 Unauthorized."""
    payload = {
        "schema_version": "1.0.0",
        "origen_comunidad": "linkedin",
        "periodo_referencia": "2026-10-01",
        "interacciones": [],
    }
    response = client.post("/api/webhooks/linkedin", json=payload)
    assert response.status_code == 401


def test_webhook_rechaza_secreto_incorrecto():
    """Valida que un secreto erróneo sea rechazado con 401."""
    payload = {
        "schema_version": "1.0.0",
        "origen_comunidad": "linkedin",
        "periodo_referencia": "2026-10-01",
        "interacciones": [],
    }
    headers = {"X-Webhook-Secret": "clave-falsa-12345"}
    response = client.post("/api/webhooks/linkedin", json=payload, headers=headers)
    assert response.status_code == 401


def test_health_check_endpoint():
    """Valida que el endpoint /health responda status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "communitylab-api"
