# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Orquestación: LangGraph](https://img.shields.io/badge/orquestacion-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Oracle Cloud](https://img.shields.io/badge/OCI-Always%20Free-red.svg)](https://www.oracle.com/cloud/free/)
[![Pytest](https://img.shields.io/badge/pytest-15%20passed-brightgreen.svg)](https://pytest.org/)
[![Docker & n8n](https://img.shields.io/badge/n8n-Docker%20Automated-FF6D5A.svg)](https://n8n.io/)

**Proyecto del Hackathon ONE Grupo 10 (Oracle Next Education & Alura)**  
**CommunityLab** ingiere interacciones de comunidades digitales (Discord, Slack, foros, redes sociales, LinkedIn), las analiza y clasifica mediante un modelo LLM orquestado con **LangGraph**, y genera automáticamente activos de marketing listos para publicar (posts de LinkedIn, destacados para newsletter semanal y sugerencias de FAQ), persistiendo el resultado en **Oracle Cloud Infrastructure (OCI) Object Storage** (capa Always Free) y desplegado en **OCI Compute**.

Además del modo de ejecución manual (CLI/Streamlit), el proyecto incluye una **API HTTP con Webhook** que permite disparar el pipeline automáticamente desde plataformas externas o herramientas de automatización como **n8n** en contenedor Docker, habilitando un flujo de ingesta en tiempo real sin intervención manual.

---

## 🎬 Flujo y Evidencia

El pipeline integra las siguientes capacidades:

* 🎬 **Recorrido:** Ingesta por webhook o Streamlit ➔ validación ➔ LangGraph con bifurcación condicional ➔ generación de activos ➔ revisión humana.
* ☁️ **Evidencia OCI:** El bucket `communitylab-activos-marketing` (namespace `axv2uguhheq1`, región `us-phoenix-1`) almacena versiones `borrador`, `aprobado` o `rechazado`; cada escritura se verifica con una lectura posterior.
* 🧪 **Verificación automatizada:** `15 passed`, incluyendo validación de las demos, reintentos y error legible del LLM, aislamiento de fallos por interacción y persistencia OCI simulada en tests.

---

## 🏗️ Arquitectura del Sistema

```
                  ┌──────────────────────────────────────────────┐
                  │              FUENTES DE COMUNIDAD            │
                  │   (Discord, Slack, Foros, Webhooks, LinkedIn)│
                  └──────────────────────┬───────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
                 ▼ (Modo Manual)                                 ▼ (Modo Automático)
     ┌───────────────────────┐                       ┌───────────────────────┐
     │  Streamlit UI / CLI   │                       │      n8n Workflow     │
     │  (Curaduría Humana)   │                       │ (Normalizador eventos)│
     └───────────┬───────────┘                       └───────────┬───────────┘
                 │                                               │
                 │ JSON                                          │ POST (X-Webhook-Secret)
                 │                                               ▼
                 │                                   ┌───────────────────────┐
                 │                                   │    FastAPI Endpoint   │
                 │                                   │ (/api/webhooks/...)   │
                 │                                   └───────────┬───────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │         src/ingestion/validador.py            │
                 │  - Validación Pydantic (LoteInteracciones)    │
                 │  - Aislamiento de registros vacíos/inválidos  │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │         LANGGRAPH COGNITIVE PIPELINE          │
                 │                                               │
                 │             [nodo_analizar]                   │
                 │       (Extracción Sentimiento + Temas)        │
                 │                      │                        │
                 │                      ▼                        │
                 │           (enrutar_categorias)                │
                 │                ╱           ╲                  │
                 │               ▼             ▼                 │
                 │    [generar_caso_exito]  [generar_faq]        │
                 │               ╲             ╱                 │
                 │                ▼           ▼                  │
                 │            [nodo_consolidar]                  │
                 │       (Estructura PaqueteDistribucion)        │
                 │                      │                        │
                 │                      ▼                        │
                 │             [nodo_guardar_oci]                │
                 └──────────────────────┬────────────────────────┘
                                        │
                                        ▼
                 ┌───────────────────────────────────────────────┐
                 │          ORACLE CLOUD INFRASTRUCTURE          │
                 │   - VM Compute Always Free (Linux Ubuntu ARM) │
                 │   - Object Storage Bucket:                    │
                 │     communitylab-activos-marketing            │
                 │   - Objeto: paquete-distribucion-{estado}.json│
                 │   - Estados: borrador/aprobado/rechazado     │
                 └───────────────────────────────────────────────┘
```

---

## 🚀 Despliegue y Ejecución Rápida

### 1. Requisitos Previos
* **Python 3.11+**
* Acceso a una cuenta de **Oracle Cloud Infrastructure (OCI)** en capa Always Free.
* API Key de tu proveedor de LLM preferido (Google Gemini, Anthropic Claude o OpenAI).

### 2. Instalación del Entorno
```bash
# Clonar repositorio
git clone https://github.com/fren43051/communitylab-nelson-reyes.git
cd communitylab-nelson-reyes

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configuración de Variables (`.env`)
Copia `.env.example` a `.env` y completa tus credenciales. La configuración de ejemplo usa Anthropic; también puedes elegir `gemini` u `openai` en `LLM_PROVIDER` y proporcionar la API key correspondiente. No subas `.env` ni claves PEM al repositorio.
```ini
# --- Proveedor de Inteligencia Artificial ---
ANTHROPIC_API_KEY=tu_api_key_aqui
LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# --- Oracle Cloud Infrastructure (OCI) Object Storage ---
OCI_CONFIG_FILE=~/.oci/config
OCI_CONFIG_PROFILE=DEFAULT
OCI_NAMESPACE=axv2uguhheq1
OCI_BUCKET_NAME=communitylab-activos-marketing
OCI_REGION=us-phoenix-1

# --- Webhook & API Security ---
WEBHOOK_SECRET=tu-clave-secreta-de-webhook-2026
WEBHOOK_MAX_ITEMS=100
```

---

## ⚙️ Modos de Ejecución

### Opción A: API HTTP con Webhook (Producción / n8n)
Levanta el servidor FastAPI para recepción automatizada:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
* **Swagger UI / Documentación interactiva:** `http://localhost:8000/docs`
* **Health Check:** `http://localhost:8000/health`
* **Endpoint Webhook:** `POST http://localhost:8000/api/webhooks/linkedin` (requiere cabecera `X-Webhook-Secret`).

### Opción B: Panel Interactivo Web (Streamlit)
Inicia la interfaz de curaduría humana. El selector ofrece el ejemplo completo y tres demos; puedes editar LinkedIn, newsletter y FAQ, y aprobar o rechazar el paquete. La aprobación y el rechazo requieren identidad del curador, y el rechazo también requiere motivo.
```bash
streamlit run app/streamlit_app.py
```

El grafo guarda la salida inicial como `borrador`. Las decisiones humanas crean objetos separados con sufijo `aprobado` o `rechazado`, sin reemplazar el borrador.

### Opción C: Automatización con n8n en Docker
El repositorio incluye el flujo oficial exportado en **`docs/n8n_workflow_communitylab.json`**:
1. Abre n8n en tu navegador (`http://localhost:5678`).
2. Importa el archivo JSON del flujo.
3. El webhook de n8n recibirá eventos externos, los normalizará mediante JavaScript y disparará la API de FastAPI con persistencia automática en OCI.

---

## 🧪 Pruebas Automatizadas (Pytest)

El proyecto incluye pruebas de contratos, validación, enrutamiento, seguridad del webhook, resiliencia del LLM y persistencia OCI simulada. La última ejecución registrada obtuvo **15 pruebas aprobadas** (incluye casos parametrizados):

```bash
python -m pytest tests/ -v
```

Cobertura de pruebas certificada:
* `test_lote_crudo_valido_y_rechazos`: Validación de esquemas Pydantic y aislamiento de registros vacíos.
* `test_esquema_paquete_distribucion_completo`: Verificación del contrato estricto de salida `PaqueteDistribucion`.
* `test_router_enrutar_caso_exito`: Bifurcación condicional en LangGraph hacia `generar_caso_exito`.
* `test_router_enrutar_faq`: Bifurcación condicional en LangGraph hacia `generar_faq`.
* `test_webhook_rechaza_sin_secreto`: Seguridad HTTP 401 Unauthorized sin cabecera de autenticación.
* `test_webhook_rechaza_secreto_incorrecto`: Seguridad HTTP 401 Unauthorized ante secretos inválidos.
* `test_health_check_endpoint`: Disponibilidad del servicio en `/health`.
* Validación de las tres demos y aislamiento de interacciones inválidas.
* Reintento ante JSON inválido del LLM, error legible tras agotar intentos y aislamiento de un fallo de análisis por interacción.
* Verificación de la ruta versionada y lectura posterior OCI con cliente simulado; validación del contrato de error.

Las pruebas de OCI usan un cliente simulado; para verificar credenciales, red y permisos reales, ejecuta una corrida de la aplicación contra tu tenancy.

---

## 📄 Contrato de Salida Generado (`PaqueteDistribucion`)

Ejemplo de estructura JSON persistida en OCI Object Storage:
```json
{
  "schema_version": "1.2.0",
  "status": "exito",
  "fecha_generacion": "2026-10-03T10:59:16.447120Z",
  "resumen_comunidad": {
    "total_interacciones_procesadas": 1,
    "registros_validos": 1,
    "registros_rechazados": 0,
    "sentimiento_predominante": "Muy Positivo",
    "temas_principales": ["Oportunidad laboral", "Éxito profesional", "Valor de la comunidad"],
    "alertas_soporte": []
  },
  "activos_distribucion_generados": {
    "post_linkedin": {
      "titulo": "De estudiante a Dev Jr: La historia de éxito de Mariana que inspira 🚀",
      "cuerpo": "Hoy queremos celebrar un logro extraordinario...",
      "canal_recomendado": "LinkedIn Oficial",
      "potencial_engagement": "Alto",
      "source_ids": ["linkedin-1791025146950-0"]
    },
    "destaque_newsletter_semanal": {
      "seccion": "Logro de la Semana",
      "titular": "Mariana Souza consigue su primer trabajo como Dev Jr",
      "resumen": "Mariana logró ser contratada como Desarrolladora Junior gracias al apoyo...",
      "source_ids": ["linkedin-1791025146950-0"]
    },
    "sugerencia_contenido_faq": null
  },
  "control_revision_humana": {
    "numero_revision": 1,
    "estado_decision": "pendiente",
    "revisor": null,
    "fecha_decision": null,
    "comentarios": null
  },
  "almacenamiento_oci": {
    "bucket": "communitylab-activos-marketing",
    "ruta_objeto": "activos/2026-10-06-demo-contratacion-2026/paquete-distribucion-borrador.json",
    "status": "guardado_con_exito",
    "comprobacion_lectura": true,
    "detalle_error": null
  },
  "metadatos_ejecucion": {
    "modelo": "llm-configurado-via-env",
    "latencia_ms": 0
  }
}
```
