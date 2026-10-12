# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orquestación-LangGraph-FF4F00?style=for-the-badge&logo=diagram&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Oracle Cloud Infrastructure](https://img.shields.io/badge/Oracle_Cloud-Always_Free-F80000?style=for-the-badge&logo=oracle&logoColor=white)](https://cloud.oracle.com/)
[![OCI Vault](https://img.shields.io/badge/Security-OCI_Vault_AES--256-blue?style=for-the-badge&logo=oracle&logoColor=white)](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)
[![Autonomous Database](https://img.shields.io/badge/Database-Oracle_Autonomous_DB-orange?style=for-the-badge&logo=oracle&logoColor=white)](https://www.oracle.com/autonomous-database/)
[![Docker & n8n](https://img.shields.io/badge/n8n-Docker%20Automated-FF6D5A?style=for-the-badge&logo=n8n&logoColor=white)](https://n8n.io/)
[![Tests Passing](https://img.shields.io/badge/Pytest-47_Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)

**Proyecto del Hackathon ONE Grupo 10 (Oracle Next Education & Alura)**  
**CommunityLab** ingiere interacciones de comunidades digitales (Discord, Slack, foros, redes sociales, LinkedIn), las analiza y clasifica mediante un modelo LLM orquestado con **LangGraph**, y genera automáticamente activos de marketing listos para publicar (posts de LinkedIn, destacados para newsletter semanal y sugerencias de FAQ).

El proyecto implementa una arquitectura empresarial en **Oracle Cloud Infrastructure (OCI)**:
1. 🔐 **OCI Vault (KMS):** Gestión centralizada y cifrada de todos los secretos y credenciales (API keys de LLM, llaves OCI, tokens de webhook y contraseñas de BD), eliminando credenciales en texto plano del `.env`.
2. 🗄️ **Oracle Autonomous Database Serverless (Always Free):** Persistencia relacional de interacciones y paquetes curados mediante `python-oracledb` en modo *Thin TLS*.
3. 📦 **OCI Object Storage:** Almacenamiento inmutable de paquetes de distribución JSON como Data Lake (versiones `borrador`, `aprobado` y `rechazado`).
4. ⚡ **API HTTP con Webhooks:** Ingesta automática en tiempo real integrada con **n8n Cloud / Docker**.
5. 🧑‍⚖️ **Human-in-the-Loop (HITL):** Panel interactivo en Streamlit para curaduría, edición y aprobación/rechazo humano antes de publicar.

---

## 🎬 Flujo y Demostración

El pipeline integra las siguientes capacidades:

* 🎬 **Recorrido:** Ingesta por webhook o Streamlit ➔ validación con Pydantic ➔ LangGraph con bifurcación condicional ➔ generación de activos ➔ persistencia en Autonomous DB y Object Storage ➔ revisión humana.
* ☁️ **Evidencia OCI:** El bucket `communitylab-activos-marketing` (namespace `axv2uguhheq1`, región `us-phoenix-1`) almacena versiones `borrador`, `aprobado` o `rechazado`; cada escritura se verifica con una lectura posterior. Asimismo, la base de datos `communitylabdb` mantiene el histórico relacional.
* 🧪 **Verificación automatizada:** **39 pruebas unitarias pasando**, incluyendo validación de contratos, seguridad HMAC con OCI Vault, reintentos del LLM, persistencia de OCI DB y degradación controlada.
* 📁 **Guía técnica detallada:** Consulta [`INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`](./INTEGRACION_WEBHOOK_N8N_LINKEDIN.md) para ver la arquitectura y evidencia del despliegue.

---

## 🏗️ Arquitectura del Pipeline y Almacenamiento Híbrido

```text
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
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
  ┌─────────────────────────────┐               ┌─────────────────────────────┐
  │ 🗄️ ORACLE AUTONOMOUS DB    │               │ 📦 OCI OBJECT STORAGE       │
  │ - communitylab_interacciones│               │ - Bucket: communitylab-     │
  │ - communitylab_paquetes     │               │   activos-marketing         │
  │ - Consultas SQL & Auditoría │               │ - Paquetes JSON inmutables  │
  └──────────────┬──────────────┘               └──────────────┬──────────────┘
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        │
                                        ▼
                 ┌─────────────────────────────────────────────┐
                 │           app/streamlit_app.py              │
                 │      (Curaduría Humana y Aprobación)        │
                 └──────────────────────▲──────────────────────┘
                                        │
           🔐 [src/config/secrets.py] ◄── OCI Vault (communitylab-secrets)
```

---

## 🔐 Seguridad y Gestión de Secretos con OCI Vault

CommunityLab sigue el principio de **Zero Secrets on Disk**:
* **Ningún secreto en claro en `.env`:** Claves de API (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`), tokens (`WEBHOOK_SECRET`) y credenciales de base de datos (`DB_USER`, `DB_PASSWORD`, `DB_CONNECT_STRING`) residen exclusivamente en **OCI Vault**.
* **Caché ultrarrápida en memoria:** Las llamadas a `obtener_secreto()` consultan OCI Vault y mantienen una caché en memoria (TTL 300s) que reduce la latencia de acceso a **~1.8 microsegundos**, alcanzando más de 300 req/s en endpoints protegidos.
* **Soporte para Instance Principal:** Al desplegar en Compute Instances de OCI, la máquina se autentica de forma nativa mediante IAM sin necesidad de archivos `~/.oci/` en disco.

---

## 📁 Estructura del Repositorio

```text
communitylab-nelson-reyes/
├── api/
│   ├── __init__.py
│   ├── main.py                 # App FastAPI (expone /health y webhooks)
│   └── webhooks.py             # Endpoint POST /api/webhooks/linkedin protegido con Vault
├── app/
│   └── streamlit_app.py       # Panel interactivo en Streamlit con control de revisión HITL
├── data/
│   ├── interacciones_ejemplo.json     # Lote canónico de pruebas del brief
│   ├── demo_01_contratacion.json      # Caso canónico: Contratación / Éxito
│   ├── demo_02_faq_langgraph.json     # Caso canónico: Duda técnica LangGraph
│   └── demo_03_mixto_invalido.json    # Caso mixto con descarte de corruptos
├── docs/
│   ├── INTEGRACION_WEBHOOK_N8N_LINKEDIN.md # Guía técnica de integración con n8n
│   └── n8n_workflow_communitylab.json      # Flujo exportado de n8n para importar
├── scripts/
│   ├── benchmark_vault.py     # Medición de latencia y throughput de Vault y DB
│   ├── oci_db_setup.py        # Aprovisionamiento de Oracle Autonomous DB y guardado en Vault
│   ├── oci_vault_check.py     # Verificación de salud de Vault, Storage y DB
│   └── oci_vault_setup.py     # Migración de secretos locales a OCI Vault
├── src/
│   ├── config/
│   │   ├── oci_auth.py        # Autenticación unificada OCI (API Key e Instance Principal)
│   │   └── secrets.py         # Gestor centralizado de secretos con OCI Vault y caché
│   ├── ingestion/
│   │   ├── loader.py          # Carga de datos JSON
│   │   ├── models.py          # Modelos Pydantic de entrada y salida
│   │   └── validador.py       # Aislamiento y validación de registros crudos
│   ├── graph/
│   │   ├── state.py           # Estado tipado para LangGraph
│   │   ├── llm_provider.py    # Factory multi-proveedor (Gemini, OpenAI, Claude) con Vault
│   │   ├── nodes.py           # Nodos de procesamiento, router y generadores
│   │   └── build_graph.py     # Grafo compilado de LangGraph
│   ├── prompts/
│   │   └── canal_prompts.py   # Prompts estructurados por canal
│   └── storage/
│       ├── oci_client.py      # Almacenamiento versionado en OCI Object Storage
│       ├── oci_db.py          # Persistencia en Oracle Autonomous Database (Always Free)
│       └── revision.py        # Control de revisión humana y versionado
├── tests/
│   ├── conftest.py            # Fixtures de pruebas aisladas
│   ├── test_oci_db.py         # Pruebas del conector de base de datos OCI
│   ├── test_pipeline.py       # Pruebas del pipeline LangGraph y validaciones
│   └── test_secrets.py        # Pruebas unitarias de OCI Vault y caché
├── main.py                    # Script de ejecución por consola (CLI)
├── requirements.txt           # Dependencias del proyecto (incluye oracledb)
├── .env.example               # Plantilla de variables no sensibles
├── BITACORA.md                # Bitácora detallada de avances y arquitectura
└── README.md                  # Documentación principal
```

---

## ⚙️ Requisitos Previos

- **Python 3.11** o superior.
- Cuenta en **Oracle Cloud Infrastructure (OCI)** con credenciales configuradas en `~/.oci/config` (o permisos de Instance Principal en Compute).
- API Key de al menos un proveedor LLM (Anthropic Claude, OpenAI o Gemini) almacenada en **OCI Vault**.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar el repositorio y preparar el entorno

```bash
git clone https://github.com/fren43051/communitylab-nelson-reyes.git
cd communitylab-nelson-reyes

# Crear y activar entorno virtual
python -m venv .venv

# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# En Linux / macOS:
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia la plantilla `.env.example` para crear tu `.env`:

```bash
cp .env.example .env
```

Configura únicamente los parámetros no sensibles y el backend de Vault en `.env`:

```env
# Proveedor LLM y modelo
LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Oracle Cloud Infrastructure
OCI_CONFIG_FILE=~/.oci/config
OCI_CONFIG_PROFILE=DEFAULT
OCI_NAMESPACE=axv2uguhheq1
OCI_BUCKET_NAME=communitylab-activos-marketing
OCI_REGION=us-phoenix-1

# Backend de secretos vía OCI Vault
SECRETS_BACKEND=oci-vault
OCI_VAULT_ID=ocid1.vault.oc1...
```

### 3. Verificar estado de OCI Vault, Storage y Base de Datos

Ejecuta la herramienta de diagnóstico de punta a punta:

```bash
python scripts/oci_vault_check.py --storage --db
```

Para medir la latencia y rendimiento de lectura:

```bash
python scripts/benchmark_vault.py
```

---

## 💻 Modos de Ejecución

### Opción A: API HTTP con Webhook (Producción / n8n)
Levanta el servidor FastAPI para recepción automatizada:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```
* **Swagger UI / Documentación interactiva:** `http://localhost:8000/docs`
* **Health Check:** `http://localhost:8000/health`
* **Endpoint Webhook:** `POST http://localhost:8000/api/webhooks/linkedin` (requiere cabecera `X-Webhook-Secret`).

### Opción B: Panel Interactivo Web (Streamlit HITL)
Inicia la interfaz de curaduría humana con edición y control de aprobación:
```bash
streamlit run app/streamlit_app.py
```

El grafo guarda la salida inicial como `borrador`. Las decisiones humanas crean objetos separados con sufijo `aprobado` o `rechazado`, sin reemplazar el borrador, y registran el evento en Oracle Autonomous DB.

### Opción C: Ejecución por Terminal (CLI)
Procesa el lote canónico de ejemplo (`data/interacciones_ejemplo.json`):
```bash
python main.py
```

### Opción D: Automatización con n8n en Docker
El repositorio incluye el flujo oficial exportado en **`docs/n8n_workflow_communitylab.json`**:
1. Abre n8n en tu navegador (`http://localhost:5678`).
2. Importa el archivo JSON del flujo.
3. El webhook de n8n recibirá eventos externos, los normalizará mediante JavaScript y disparará la API de FastAPI con persistencia automática en OCI.

---

## 🧪 Pruebas Automatizadas (Pytest)

El proyecto cuenta con una suite completa de pruebas unitarias construida con `pytest`:

```bash
pytest -v
```

Cobertura de pruebas (**47 tests pasando**):
* **Validación de Datos:** Aislamiento y filtrado de registros corruptos con Pydantic.
* **Router de LangGraph:** Bifurcación condicional (`caso_exito` vs `faq`).
* **Seguridad Webhook:** Validación de cabecera HMAC contra OCI Vault y rechazo HTTP 401.
* **Gestor de Secretos:** Comprobación de caché TTL, degradación controlada y Vault mock.
* **Conector OCI DB:** Pruebas de conexión e inserción en Oracle Autonomous DB.
* **Resiliencia LLM:** Reintentos ante respuestas corruptas y errores limpios.

---

## 📋 Requisitos Cubiertos (Checklist Hackathon 100%)

- [x] **Ingestión funcional** validada vía Pydantic (admite lotes crudos y aísla registros corruptos).
- [x] **Análisis cognitivo multimodelo** con LLM intercambiable (Gemini, OpenAI, Claude).
- [x] **Generación de 3 activos canónicos:** Post de LinkedIn, Newsletter semanal y Sugerencias FAQ.
- [x] **Orquestación mediante LangGraph** con estado tipado y router condicional.
- [x] **Seguridad Empresarial con OCI Vault:** Claves cifradas con AES-256 sin secretos en disco.
- [x] **Persistencia en Oracle Autonomous Database (Always Free):** Tablas operativas relacionales y consultas de métricas.
- [x] **Almacenamiento en OCI Object Storage Always Free** con verificación de lectura inmediata y versionado (`borrador`, `aprobado`, `rechazado`).
- [x] **Dashboard interactivo en Streamlit** para curaduría, edición y aprobación humana con trazabilidad.
- [x] **API RESTful (FastAPI)** con webhook seguro para ingesta automatizada.
- [x] **Integración n8n Cloud + ngrok** probada y validada end-to-end con video de demostración.
- [x] **Suite de pruebas automatizadas (`pytest`):** 47 tests unitarios pasando.
