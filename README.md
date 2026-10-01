# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orquestación-LangGraph-FF4F00?style=for-the-badge&logo=diagram&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Oracle Cloud Infrastructure](https://img.shields.io/badge/Oracle_Cloud-Always_Free-F80000?style=for-the-badge&logo=oracle&logoColor=white)](https://cloud.oracle.com/)
[![Tests Passing](https://img.shields.io/badge/Pytest-Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)

Proyecto del **Hackathon ONE Grupo 10** (Oracle Next Education & Alura).  
CommunityLab ingiere interacciones de comunidades digitales (Discord, Slack, foros, redes sociales, LinkedIn), las analiza y clasifica mediante un modelo LLM orquestado con **LangGraph**, y genera automáticamente activos de marketing listos para publicar (posts de LinkedIn, destacados para newsletter semanal y sugerencias de FAQ), persistiendo el resultado en **Oracle Cloud Infrastructure (OCI) Object Storage** (capa Always Free).

Además del modo de ejecución manual (CLI/Streamlit), el proyecto incluye una **API HTTP con webhook** que permite disparar el pipeline automáticamente desde plataformas externas o herramientas de automatización como **n8n**, habilitando un flujo de ingesta en tiempo real sin intervención manual.

---

## 📺 Demostración en Video y Evidencia

El flujo de integración completa fue grabado y verificado en tiempo real:
* **Recorrido:** Webhook externo (PowerShell) ➔ Normalización en **n8n Cloud** ➔ Túnel **ngrok** (dominio dev fijo) ➔ Backend **FastAPI** ➔ Orquestación con **LangGraph + Claude** ➔ Persistencia en **OCI Object Storage (Región Monterrey)**.
* **Evidencia OCI:** Verificación directa en la consola web de Oracle Cloud del archivo `paquete-distribucion.json` creado en el bucket `communitylab-activos-marketing`.
* 📁 **Guía de integración técnica detallada:** Consulta [`INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`](./INTEGRACION_WEBHOOK_N8N_LINKEDIN.md) para ver la arquitectura y evidencia fotográfica del despliegue.

---

## 🏗️ Arquitectura del Pipeline

```text
   JSON/CSV de Interacciones          Webhook externo (n8n, LinkedIn, etc.)
              │                                    │
              │                                    ▼
              │                    POST /api/webhooks/linkedin (FastAPI)
              │                                    │
              ▼                                    ▼
   [src/ingestion/loader.py]  ──►  Validación con Pydantic (LoteInteracciones)
              │
              ▼
   ═══════════════════════════ LangGraph ═══════════════════════════
   [nodo_analizar]            ──► LLM: sentimiento, temas, score, categoria_accion
              │
              ▼
   (Edge condicional: enrutar_categorias)
        ╱            ╲
       ▼              ▼
   [generar_caso_exito]  [generar_faq]
   • Post LinkedIn       • Sugerencia FAQ
   • Newsletter
        ╲            ╱
         ▼          ▼
   [nodo_consolidar]          ──► Ensambla PaqueteDistribucion
              │
              ▼
   [nodo_guardar_oci]         ──► Almacena JSON en OCI Object Storage (Always Free)
   ═════════════════════════════════════════════════════════════════
              │
              ▼
   [app/streamlit_app.py]     ──► Panel interactivo de curaduría y aprobación
```

---

## 📁 Estructura del Repositorio

```text
communitylab-nelson-reyes/
├── api/
│   ├── __init__.py
│   ├── main.py                 # App FastAPI (expone /health y el router de webhooks)
│   └── webhooks.py             # Endpoint POST /api/webhooks/linkedin con validación de secreto
├── app/
│   └── streamlit_app.py       # Panel interactivo en Streamlit
├── data/
│   └── interacciones_ejemplo.json # Lote de 3 casos canónicos del brief (Testimonio, FAQ, Feedback)
├── src/
│   ├── ingestion/
│   │   ├── models.py          # Esquemas Pydantic de entrada y salida
│   │   └── validador.py       # Aislamiento y validación de registros crudos
│   ├── graph/
│   │   ├── state.py           # Estado tipado para LangGraph
│   │   ├── llm_provider.py    # Factory multi-proveedor (Gemini, OpenAI, Claude)
│   │   ├── nodes.py           # Nodos de procesamiento, router y generadores
│   │   └── build_graph.py     # Construcción y compilación del grafo
│   ├── prompts/
│   │   └── canal_prompts.py   # Prompts estructurados por canal
│   └── storage/
│       └── oci_client.py      # Cliente de subida a OCI Object Storage
├── tests/
│   └── test_pipeline.py       # Suite automatizada con pytest (Pydantic, Router, Webhooks)
├── main.py                    # Script de ejecución por consola (CLI)
├── requirements.txt           # Dependencias del proyecto
├── .env.example               # Plantilla de variables de entorno
├── INTEGRACION_WEBHOOK_N8N_LINKEDIN.md  # Documento técnico de integración con n8n y OCI
├── BITACORA.md                # Bitácora detallada de avances y arquitectura
└── README.md                  # Documentación principal
```

---

## ⚙️ Requisitos Previos

- **Python 3.11** (entorno estandarizado para compatibilidad con OCI SDK).
- Clave de API de al menos un proveedor LLM soportado:
  - **Google Gemini** (`GOOGLE_API_KEY`)
  - **OpenAI** (`OPENAI_API_KEY`)
  - **Anthropic Claude** (`ANTHROPIC_API_KEY`)
- (Opcional para guardado en la nube) Cuenta en **Oracle Cloud Infrastructure (OCI)** con credenciales configuradas en `~/.oci/config`.
- (Opcional para modo automatización) **n8n** (Cloud o self-hosted) y **ngrok** para exponer la API local.

---

## 🚀 Instalación y Despliegue

### 1. Clonar el repositorio y preparar el entorno virtual

```bash
git clone https://github.com/fren43051/communitylab-nelson-reyes.git
cd communitylab-nelson-reyes

# Crear entorno virtual con Python 3.11
python -m venv .venv

# Activar entorno virtual
# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# En Linux / macOS:
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia la plantilla `.env.example` para crear tu archivo `.env`:

```bash
# En Windows (PowerShell):
Copy-Item .env.example .env
# En Linux / macOS:
cp .env.example .env
```

Edita el archivo `.env` según tu proveedor LLM y credenciales de OCI:

```env
# Proveedor activo: gemini | openai | anthropic
LLM_PROVIDER=anthropic

# Anthropic Claude
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Oracle Cloud Infrastructure (OCI) Object Storage
OCI_CONFIG_FILE=~/.oci/config
OCI_CONFIG_PROFILE=DEFAULT
OCI_NAMESPACE=tu_namespace_oci
OCI_BUCKET_NAME=communitylab-activos-marketing
OCI_REGION=mx-monterrey-1

# --- Webhooks (modo automatización con n8n) ---
WEBHOOK_SECRET=tu_secreto_seguro_para_webhook
WEBHOOK_MAX_ITEMS=100
```

---

## 💻 Modos de Ejecución

### Opción A: Ejecución por Terminal (CLI)
Procesa el lote canónico de ejemplo (`data/interacciones_ejemplo.json`) directamente:
```bash
python main.py
```

### Opción B: Panel Interactivo Web (Streamlit)
Inicia la interfaz de curaduría humana y edición de activos:
```bash
streamlit run app/streamlit_app.py
```

### Opción C: API HTTP con Webhook (Automatización n8n)
Levanta el servidor FastAPI para recibir eventos externos:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## 🧪 Pruebas Automatizadas

El proyecto incluye una suite completa de pruebas unitarias y de integración construida con `pytest`:

```bash
pytest tests/test_pipeline.py -v
```

Cobertura de pruebas:
* **Validación de Datos:** Prueba de aislamiento de registros incompletos o vacíos vía Pydantic.
* **Integridad de Salida:** Verificación del contrato estricto de `PaqueteDistribucion`.
* **Router de LangGraph:** Comprobación del enrutamiento condicional (`generar_caso_exito` vs `generar_faq`).
* **Seguridad Webhook:** Verificación de rechazo HTTP 401 por cabecera ausente o token erróneo y diagnóstico en `/health`.

---

## 📋 Requisitos Cubiertos (Checklist Hackathon 1000%)

- [x] **Ingestión funcional** validada vía Pydantic (admite lotes crudos y aísla registros corruptos).
- [x] **Análisis cognitivo multimodelo** con LLM intercambiable (Gemini, OpenAI, Claude).
- [x] **Generación de 3 activos canónicos:** Post de LinkedIn, Newsletter semanal y Sugerencias FAQ.
- [x] **Orquestación mediante LangGraph** con estado tipado y router condicional.
- [x] **Integración con OCI Object Storage** Always Free con validación de lectura inmediata.
- [x] **Dashboard interactivo en Streamlit** para curaduría, edición y aprobación humana.
- [x] **API RESTful (FastAPI)** con webhook seguro para ingesta automatizada.
- [x] **Integración n8n Cloud + ngrok** probada y validada end-to-end con video de demostración.
- [x] **Suite de pruebas automatizadas (`pytest`)** en `tests/test_pipeline.py`.
- [x] **Datos de prueba con los 3 casos mínimos** exigidos por el brief del challenge.
