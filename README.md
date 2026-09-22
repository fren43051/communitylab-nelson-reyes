# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

Proyecto del **Hackathon ONE Grupo 10** (Oracle Next Education & Alura). Ingiere interacciones de una
comunidad digital (Discord, Slack, foros), las analiza con un LLM y genera automáticamente activos de
marketing listos para publicar (posts de LinkedIn, resúmenes de newsletter, sugerencias de FAQ), guardando
el resultado en OCI Object Storage (capa Always Free).

## Arquitectura del pipeline

```
   JSON/CSV interacciones
            |
            v
   [ingestion/loader.py]  --> valida con Pydantic (LoteInteracciones)
            |
            v
   =========== LangGraph ===========
   [nodo_analizar]            --> LLM: sentimiento, temas, score, categoria_accion
            |
   (edge condicional: enrutar_categorias)
      /            \
     v              v
[generar_caso_exito]  [generar_faq]
  post LinkedIn         sugerencia FAQ
  + newsletter
      \            /
       v          v
      [nodo_consolidar]  --> arma PaqueteDistribucion
            |
            v
      [nodo_guardar_oci]  --> sube JSON a OCI Object Storage (Always Free)
   ==================================
            |
            v
   [app/streamlit_app.py]  --> panel de curaduría y aprobación
```

## Estructura del repositorio

```
communitylab-nelson-reyes/
├── app/
│   └── streamlit_app.py
├── data/
│   └── interacciones_ejemplo.json
├── src/
│   ├── ingestion/
│   │   ├── models.py
│   │   └── loader.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── llm_provider.py
│   │   ├── nodes.py
│   │   └── build_graph.py
│   ├── prompts/
│   │   └── canal_prompts.py
│   └── storage/
│       └── oci_client.py
├── tests/
├── main.py
├── requirements.txt
├── .env.example
└── .gitignore
```

## Cómo desplegar y correr

### 1. Clonar y preparar entorno

```bash
git clone https://github.com/fren43051/communitylab-nelson-reyes.git
cd communitylab-nelson-reyes
python -m venv venv
source venv/bin/activate    # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Completa tu API key del LLM elegido (Gemini, OpenAI o Claude) y los datos de tu bucket OCI.

### 3. Configurar OCI Object Storage (Always Free)

1. Crea una cuenta OCI Always Free si no la tienes.
2. Crea un bucket (ej. `communitylab-activos-marketing`) en Object Storage.
3. Genera tu API Key desde la consola de OCI y descarga el archivo `~/.oci/config`.
4. Completa `OCI_NAMESPACE`, `OCI_BUCKET_NAME` y `OCI_REGION` en tu `.env`.

### 4. Ejecutar el pipeline por consola

```bash
python main.py
```

### 5. Ejecutar el panel Streamlit

```bash
streamlit run app/streamlit_app.py
```

## Requisitos mínimos cubiertos (checklist del hackathon)

- Ingestión funcional de interacciones (JSON/CSV) vía Pydantic.
- Análisis de sentimiento y extracción de temas con LLM (Gemini/OpenAI/Claude, intercambiable).
- Generación de al menos 2 formatos de activos: post LinkedIn + newsletter, o FAQ, según bifurcación.
- Orquestación del flujo con LangGraph, incluyendo edge condicional según `categoria_accion`.
- Integración con OCI Object Storage (capa Always Free) para persistir los paquetes generados.
- Panel Streamlit para visualización y aprobación de los activos.

## Próximos pasos sugeridos (diferenciales)

- Despliegue en una VM Compute Always Free de OCI.
- Webhook real conectando Discord/Slack al pipeline.
- Generación de imágenes/banners para los posts con un modelo multimodal.
