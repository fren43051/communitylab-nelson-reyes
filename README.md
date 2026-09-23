# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

Proyecto del **Hackathon ONE Grupo 10** (Oracle Next Education & Alura).  
CommunityLab ingiere interacciones de comunidades digitales (Discord, Slack, foros, redes sociales, LinkedIn), las analiza y clasifica mediante un modelo LLM orquestado con **LangGraph**, y genera automáticamente activos de marketing listos para publicar (posts de LinkedIn, destacados para newsletter semanal y sugerencias de FAQ), persistiendo el resultado en **Oracle Cloud Infrastructure (OCI) Object Storage** (capa Always Free).

Además del modo de ejecución manual (CLI/Streamlit), el proyecto incluye una **API HTTP con webhook** que permite disparar el pipeline automáticamente desde plataformas externas o herramientas de automatización como **n8n**, habilitando un flujo de ingesta en tiempo real sin intervención manual.

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

### Flujo de automatización con n8n (validado end-to-end)

```text
Webhook de n8n (n8n Cloud)
   POST /webhook/linkedin-events
              │
              ▼
   Nodo Code: normaliza el payload
   al contrato LoteInteraccionesCrudo
              │
              ▼
   Nodo HTTP Request ──► túnel ngrok (dominio dev fijo)
              │
              ▼
   POST /api/webhooks/linkedin  ──► reutiliza el pipeline LangGraph descrito arriba
              │
              ▼
   Respuesta con el PaqueteDistribucion completo, de vuelta a n8n
```

Esta integración fue implementada y **probada con una ejecución real** que
recorrió las dos rutas (Streamlit/CLI y webhook/n8n) hasta OCI. Ver detalles
completos en [`INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`](./INTEGRACION_WEBHOOK_N8N_LINKEDIN.md).

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
│   └── interacciones_ejemplo.json # Lote de datos de prueba
├── src/
│   ├── ingestion/
│   │   ├── models.py          # Esquemas Pydantic de entrada y salida
│   │   └── loader.py          # Carga y validación desde JSON/CSV
│   ├── graph/
│   │   ├── state.py           # Estado tipado para LangGraph
│   │   ├── llm_provider.py    # Factory multi-proveedor (Gemini, OpenAI, Claude)
│   │   ├── nodes.py           # Nodos de procesamiento y generación
│   │   └── build_graph.py     # Construcción y compilación del grafo
│   ├── prompts/
│   │   └── canal_prompts.py   # Prompts estructurados por canal
│   └── storage/
│       └── oci_client.py      # Cliente de subida a OCI Object Storage
├── tests/                     # Suite de pruebas
├── main.py                    # Script de ejecución por consola (CLI)
├── requirements.txt           # Dependencias del proyecto
├── .env.example               # Plantilla de variables de entorno
├── INTEGRACION_WEBHOOK_N8N_LINKEDIN.md  # Guía e implementación del webhook + n8n + ngrok
├── BITACORA.md                # Bitácora de avance del proyecto
└── README.md                  # Documentación del proyecto
```

---

## ⚙️ Requisitos Previos

- **Python 3.10 o superior** (probado en Python 3.10, 3.11 y 3.12).
- Clave de API de al menos un proveedor LLM soportado:
  - **Google Gemini** (`GOOGLE_API_KEY`)
  - **OpenAI** (`OPENAI_API_KEY`)
  - **Anthropic Claude** (`ANTHROPIC_API_KEY`)
- (Opcional para guardado en la nube) Cuenta en **Oracle Cloud Infrastructure (OCI)** con credenciales configuradas en `~/.oci/config`.
- (Opcional, solo para el modo webhook/automatización) **n8n** (Cloud o self-hosted) y **ngrok** (o un despliegue público equivalente) si se desea exponer la API local a internet.

---

## 🚀 Instalación y Despliegue

### 1. Clonar el repositorio y preparar el entorno virtual

```bash
git clone https://github.com/fren43051/communitylab-nelson-reyes.git
cd communitylab-nelson-reyes

# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows (PowerShell):
venv\Scripts\Activate.ps1
# En Windows (CMD):
venv\Scripts\activate.bat
# En Linux / macOS:
source venv/bin/activate

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

Edita el archivo `.env` según el proveedor LLM que vayas a utilizar:

```env
# Proveedor activo: gemini | openai | anthropic
LLM_PROVIDER=gemini

# Google Gemini
GOOGLE_API_KEY=tu_api_key_de_gemini
GEMINI_MODEL=gemini-1.5-flash

# OpenAI
OPENAI_API_KEY=tu_api_key_de_openai
OPENAI_MODEL=gpt-4o-mini

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
WEBHOOK_SECRET=cambia-esta-clave-por-una-segura
WEBHOOK_MAX_ITEMS=100
```

### 3. Configurar OCI Object Storage (Always Free)

1. Inicia sesión en la consola de [Oracle Cloud Infrastructure](https://cloud.oracle.com/).
2. Crea un Bucket en **Storage > Object Storage & Archive Storage** (por ejemplo: `communitylab-activos-marketing`).
3. Ve a tu perfil de usuario en OCI > **API Keys** > **Add API Key**, descarga la clave privada y genera el archivo de configuración `~/.oci/config`.
4. Copia tu `Tenancy OCID`, `User OCID`, `Fingerprint` y `Region` en `~/.oci/config`.
5. Asegúrate de configurar `OCI_NAMESPACE`, `OCI_BUCKET_NAME` y `OCI_REGION` en tu archivo `.env`.

> *Nota:* Si no configuras OCI o las credenciales no están disponibles, el pipeline continuará ejecutándose y registrará el estado localmente sin detener la aplicación.

---

## 💻 Modos de Ejecución

### Opción A: Ejecución por Terminal (CLI)

Ejecuta el pipeline completo sobre el lote de interacciones de ejemplo (`data/interacciones_ejemplo.json`):

```bash
python main.py
```

El resultado final estructurado en JSON (con el resumen y los activos generados) se imprimirá en la consola.

### Opción B: Panel Interactivo Web (Streamlit)

Inicia el dashboard web para cargar archivos, visualizar el análisis de sentimiento y aprobar/editar los activos generados:

```bash
streamlit run app/streamlit_app.py
```

Abre tu navegador en `http://localhost:8501`. Desde el panel podrás:
- Subir lotes en formato JSON o utilizar los datos de ejemplo incluidos.
- Visualizar métricas globales (interacciones procesadas, sentimiento, temas frecuentes).
- Revisar y editar copys de LinkedIn, titulares de newsletter y preguntas frecuentes.
- Consultar el estado de persistencia en OCI Object Storage.

### Opción C: API HTTP con Webhook (automatización con n8n)

Además del CLI y Streamlit, el proyecto expone una **API HTTP con FastAPI**
que permite disparar el pipeline completo mediante una petición POST, ideal
para conectarse con herramientas de automatización como n8n, Zapier o
Make, o directamente con la API oficial de LinkedIn.

Levantar la API localmente:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Verificar que está activa:

```bash
curl http://localhost:8000/health
# {"status": "ok", "service": "communitylab-api"}
```

La documentación interactiva (Swagger) está disponible en `http://localhost:8000/docs`.

Enviar un lote de prueba al endpoint principal:

```bash
curl -X POST http://localhost:8000/api/webhooks/linkedin \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: <tu_WEBHOOK_SECRET>" \
  -d '{
    "schema_version": "1.0.0",
    "origen_comunidad": "linkedin",
    "periodo_referencia": "2026-09-23",
    "interacciones": [{
      "id": "linkedin-comment-001",
      "autor": "Maria Lopez",
      "canal": "linkedin",
      "tipo": "feedback",
      "texto": "Excelente publicacion, me ayudo mucho a entender LangGraph",
      "metadata_origen": {
        "plataforma": "linkedin",
        "identificador_original": "urn:li:comment:123456",
        "fecha": "2026-09-23T14:00:00Z"
      }
    }]
  }'
```

La respuesta incluye el `PaqueteDistribucion` completo generado por LangGraph
(post de LinkedIn, destacado de newsletter, sugerencia de FAQ y estado de
persistencia en OCI), listo para revisión humana desde Streamlit.

#### Automatización con n8n (validada con n8n Cloud)

El flujo recomendado usa tres nodos en n8n: **Webhook** (recibe el evento
externo) → **Code** (normaliza el payload al contrato `LoteInteraccionesCrudo`)
→ **HTTP Request** (llama a `/api/webhooks/linkedin`). Si n8n corre en la nube
y la API en tu máquina local, se necesita exponerla con un túnel como
**ngrok** (`ngrok http --url=<tu-dominio-dev> 8000`) o desplegarla en un
entorno público.

La guía completa, con la configuración exacta de cada nodo y la evidencia de
una ejecución exitosa real, está en
[`INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`](./INTEGRACION_WEBHOOK_N8N_LINKEDIN.md).

---

## ❓ Preguntas Frecuentes y Solución de Problemas

### 1. Mensaje `ANTHROPIC_API_KEY is set and takes precedence over...`
Es un aviso informativo del SDK de Anthropic notificando que se está usando la clave de API configurada en `.env` en lugar del autodescubrimiento de perfiles de nube. No afecta el funcionamiento del pipeline.

### 2. Cambiar de modelo LLM en caliente
Puedes cambiar entre **Google Gemini**, **OpenAI** o **Anthropic Claude** modificando únicamente la variable `LLM_PROVIDER` en tu archivo `.env`, sin necesidad de alterar el código del proyecto.

### 3. Los acentos se ven corruptos al imprimir JSON en PowerShell (`Ã³` en vez de `ó`)
Es un problema de la codificación de la consola de PowerShell, no del archivo generado ni de la API (el JSON ya se guarda correctamente en UTF-8). Se soluciona ejecutando antes de la petición:
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

### 4. n8n en la nube no puede llamar a `http://localhost:8000`
Si n8n corre en n8n Cloud (no self-hosted en tu misma máquina), `localhost`
en ese contexto apunta al servidor de n8n, no a tu computadora. Es necesario
exponer la API local con un túnel público como **ngrok**, o desplegarla en un
entorno accesible desde internet (ver sección de Próximos Pasos).

---

## 📋 Requisitos Mínimos Cubiertos (Checklist Hackathon)

- [x] Ingestión funcional de interacciones (JSON/CSV) validada vía Pydantic.
- [x] Análisis de sentimiento y extracción de temas con LLM intercambiable (Gemini, OpenAI, Claude).
- [x] Generación de múltiples formatos de activos: Post de LinkedIn, Newsletter semanal y Sugerencias FAQ.
- [x] Orquestación de agentes y flujo mediante **LangGraph** con bifurcación y edge condicional.
- [x] Integración con **OCI Object Storage** (Always Free) para almacenamiento de activos.
- [x] Dashboard interactivo en **Streamlit** para visualización, edición y aprobación.
- [x] API HTTP con webhook (**FastAPI**) para disparar el pipeline desde herramientas externas.
- [x] Automatización probada de extremo a extremo con **n8n** (Webhook → Code → HTTP Request) y **ngrok** como túnel público.

---

## 🌟 Próximos Pasos Sugeridos

- Despliegue automatizado de la API en una instancia VM Compute Always Free de OCI, para eliminar la dependencia de un túnel temporal (ngrok) durante la automatización con n8n.
- Conexión con la API oficial de LinkedIn (OAuth2) para reemplazar los payloads simulados por eventos reales.
- Deduplicación e idempotencia de eventos recibidos por webhook (evitar procesar el mismo comentario dos veces).
- Autenticación reforzada en el nodo Webhook de n8n (Header Auth) y manejo de errores con nodos IF/Switch/Error Trigger.
- Generación automatizada de imágenes o banners promocionales mediante modelos multimodales.
