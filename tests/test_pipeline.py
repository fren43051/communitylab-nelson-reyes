import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

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
    PuntuacionRelevancia,
    PaqueteDistribucion,
    AlmacenamientoOCI,
)
from src.ingestion.validador import validar_lote_crudo
from src.ingestion.loader import cargar_json
from src.graph import nodes
from src.graph.nodes import enrutar_categorias
from src.storage import oci_client
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
            AnalisisInteraccion(
                id="test-01",
                autor="Mariana Souza",
                canal="discord",
                tipo="testimonio",
                texto="Quedé contratada como Dev Jr gracias a la comunidad!",
                sentimiento="Muy Positivo",
                puntuacion_relevancia=PuntuacionRelevancia(
                    evidencia_explicita=2,
                    utilidad_comunitaria=2,
                    claridad_contexto=2,
                    total=6,
                ),
                temas=["Logro", "Contratación"],
                categoria_accion="caso_exito",
                motivo_seleccion="Testimonio relevante de contratación",
                resumen_ejecutivo="Testimonio de contratación",
            )
        ]
    }
    destino = enrutar_categorias(estado)
    assert "generar_caso_exito" in destino


def test_router_enrutar_faq():
    """Valida que preguntas técnicas enruten a generar_faq."""
    estado = {
        "analisis": [
            AnalisisInteraccion(
                id="test-02",
                autor="Lucas Albuquerque",
                canal="discord",
                tipo="pregunta_tecnica",
                texto="¿Cómo estructurar nodos condicionales en LangGraph?",
                sentimiento="Neutral",
                puntuacion_relevancia=PuntuacionRelevancia(
                    evidencia_explicita=2,
                    utilidad_comunitaria=2,
                    claridad_contexto=1,
                    total=5,
                ),
                temas=["LangGraph", "Nodos Condicionales"],
                categoria_accion="faq_tip",
                motivo_seleccion="Pregunta técnica recurrente",
                resumen_ejecutivo="Duda sobre router en LangGraph",
            )
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


@pytest.mark.parametrize(
    ("fixture", "validas", "rechazadas"),
    [
        ("demo_01_contratacion.json", 1, 0),
        ("demo_02_faq_langgraph.json", 1, 0),
        ("demo_03_mixto_invalido.json", 3, 1),
    ],
)
def test_fixtures_demo_validan_y_aislan_invalidos(fixture, validas, rechazadas):
    ruta = Path(__file__).resolve().parent.parent / "data" / fixture
    lote, registros_rechazados = cargar_json(str(ruta))
    assert len(lote.interacciones) == validas
    assert len(registros_rechazados) == rechazadas


def test_llm_json_reintenta_respuesta_json_invalida(monkeypatch):
    class LLMFalso:
        def __init__(self):
            self.llamadas = 0

        def invoke(self, _mensajes):
            self.llamadas += 1
            contenido = "no-json" if self.llamadas == 1 else '{"ok": true}'
            return SimpleNamespace(content=contenido)

    llm = LLMFalso()
    monkeypatch.setattr(nodes, "get_llm", lambda: llm)
    monkeypatch.setattr(nodes.time, "sleep", lambda _segundos: None)

    assert nodes._llm_json("sistema", "usuario") == {"ok": True}
    assert llm.llamadas == 2


def test_llm_json_falla_con_error_legible_despues_de_reintentos(monkeypatch):
    class LLMFalso:
        def invoke(self, _mensajes):
            return SimpleNamespace(content="no-json")

    monkeypatch.setattr(nodes, "get_llm", lambda: LLMFalso())
    monkeypatch.setattr(nodes.time, "sleep", lambda _segundos: None)

    with pytest.raises(RuntimeError, match="tras 2 intentos"):
        nodes._llm_json("sistema", "usuario", intentos=2)


def test_fallo_de_analisis_se_aísla_en_un_registro(monkeypatch):
    from src.ingestion.models import Interaccion, LoteInteracciones

    lote = LoteInteracciones(
        origen_comunidad="discord",
        periodo_referencia="test",
        interacciones=[Interaccion(id="int-1", autor="Ana", canal="general", tipo="otro", texto="Mensaje")],
    )
    monkeypatch.setattr(nodes, "_llm_json", lambda *_args: (_ for _ in ()).throw(RuntimeError("modelo caido")))

    resultado = nodes.nodo_analizar({"lote": lote})

    assert len(resultado["analisis"]) == 1
    assert resultado["analisis"][0].categoria_accion == "descartar"
    assert resultado["analisis"][0].requiere_soporte is True
    assert "modelo caido" in resultado["analisis"][0].motivo_seleccion


def test_subir_paquete_oci_versiona_ruta_y_verifica_lectura(monkeypatch):
    class ClienteOCI:
        def put_object(self, **kwargs):
            self.nombre_objeto = kwargs["object_name"]
            self.contenido = kwargs["put_object_body"]

        def get_object(self, **kwargs):
            assert kwargs["object_name"] == self.nombre_objeto
            return SimpleNamespace(data=SimpleNamespace(content=self.contenido))

    cliente = ClienteOCI()
    modulo_oci = SimpleNamespace(
        config=SimpleNamespace(from_file=lambda **_kwargs: {}),
        object_storage=SimpleNamespace(ObjectStorageClient=lambda _config: cliente),
    )
    monkeypatch.setitem(sys.modules, "oci", modulo_oci)
    monkeypatch.setenv("OCI_NAMESPACE", "namespace-test")

    resultado = oci_client.subir_paquete_a_oci({"status": "exito"}, "demo", "aprobado/!!!")

    assert resultado["status"] == "guardado_con_exito"
    assert resultado["comprobacion_lectura"] is True
    assert cliente.nombre_objeto.endswith("/paquete-distribucion-aprobado.json")
    assert json.loads(cliente.contenido.decode("utf-8")) == {"status": "exito"}


def test_error_oci_mantiene_status_literal_y_detalle(monkeypatch):
    modulo_oci = SimpleNamespace(
        config=SimpleNamespace(from_file=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("sin credenciales"))),
        object_storage=SimpleNamespace(),
    )
    monkeypatch.setitem(sys.modules, "oci", modulo_oci)

    resultado = oci_client.subir_paquete_a_oci({}, "demo", "borrador")
    almacenamiento = AlmacenamientoOCI(**resultado)

    assert almacenamiento.status == "guardado_error"
    assert almacenamiento.detalle_error == "sin credenciales"
