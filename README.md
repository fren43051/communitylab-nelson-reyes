# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

Proyecto del **Hackathon ONE Grupo 10** (Oracle Next Education & Alura).  
CommunityLab ingiere interacciones de comunidades digitales (Discord, Slack, foros, redes sociales), las analiza y clasifica mediante un modelo LLM orquestado con **LangGraph**, y genera automáticamente activos de marketing listos para publicar (posts de LinkedIn, destacados para newsletter semanal y sugerencias de FAQ), persistiendo el resultado en **Oracle Cloud Infrastructure (OCI) Object Storage** (capa Always Free).

---

## 🏗️ Arquitectura del Pipeline

```text
   JSON/CSV de Interacciones
              │
              ▼
   [src/ingestion/loader.py]  ──► Validación con Pydantic (LoteInteracciones)
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

---

## ❓ Preguntas Frecuentes y Solución de Problemas

### 1. Mensaje `ANTHROPIC_API_KEY is set and takes precedence over...`
Es un aviso informativo del SDK de Anthropic notificando que se está usando la clave de API configurada en `.env` en lugar del autodescubrimiento de perfiles de nube. No afecta el funcionamiento del pipeline.

### 2. Cambiar de modelo LLM en caliente
Puedes cambiar entre **Google Gemini**, **OpenAI** o **Anthropic Claude** modificando únicamente la variable `LLM_PROVIDER` en tu archivo `.env`, sin necesidad de alterar el código del proyecto.

---

## 📋 Requisitos Mínimos Cubiertos (Checklist Hackathon)

- [x] Ingestión funcional de interacciones (JSON/CSV) validada vía Pydantic.
- [x] Análisis de sentimiento y extracción de temas con LLM intercambiable (Gemini, OpenAI, Claude).
- [x] Generación de múltiples formatos de activos: Post de LinkedIn, Newsletter semanal y Sugerencias FAQ.
- [x] Orquestación de agentes y flujo mediante **LangGraph** con bifurcación y edge condicional.
- [x] Integración con **OCI Object Storage** (Always Free) para almacenamiento de activos.
- [x] Dashboard interactivo en **Streamlit** para visualización, edición y aprobación.

---

## 🌟 Próximos Pasos Sugeridos

- Despliegue automatizado en una instancia VM Compute Always Free de OCI.
- Integración de Webhooks en tiempo real para ingesta directa desde Discord o Slack.
- Generación automatizada de imágenes o banners promocionales mediante modelos multimodales.
