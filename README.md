# 🚀 CommunityLab — Motor Inteligente de Transformación y Distribución para Comunidades Digitales

Proyecto del **Hackathon ONE Grupo 10** (Oracle Next Education & Alura). Ingiere interacciones de una
comunidad digital (Discord, Slack, foros), las analiza con un LLM y genera automáticamente activos de
marketing listos para publicar (posts de LinkedIn, resúmenes de newsletter, sugerencias de FAQ), guardando
el resultado en OCI Object Storage (capa Always Free).

## Arquitectura del pipeline

```
   JSON/CSV interacciones (crudo)
            |
            v
   [ingestion/loader.py]  --> LoteInteraccionesCrudo (admision permisiva)
            |
            v
   [ingestion/validador.py]  --> validar_lote_crudo()
            |                       |
      validos (Interaccion)    rechazados (aislados en auditoria)
            |
            v
   =========== LangGraph ===========
   [nodo_analizar]            --> LLM: sentimiento, temas, rubrica de relevancia, categoria_accion
            |
   (edge condicional: enrutar_categorias)
      /            \
     v              v
[generar_caso_exito]  [generar_faq]
  post LinkedIn         sugerencia FAQ
  + newsletter          (con source_ids)
  (con source_ids)
      \            /
       v          v
      [nodo_consolidar]  --> arma PaqueteDistribucion (incluye resumen + alertas)
            |
            v
      [nodo_guardar_oci]  --> sube JSON a OCI, RELEE para verificar (comprobacion_lectura)
   ==================================
            |
            v
   [app/streamlit_app.py]  --> panel de curaduría, rechazados y aprobación
```

## Contratos de datos (Pydantic)

Siguiendo el patrón de validación en dos capas adoptado del equipo compañero (Grupo 34):

- **Capa 1 — Admisión permisiva** (`InteraccionCruda`, `LoteInteraccionesCrudo`): acepta lotes con
  campos faltantes o texto vacío sin bloquear la ingestión completa.
- **Capa 2 — Validación estricta** (`Interaccion`, aplicada por `validar_lote_crudo`): exige texto no
  vacío y aísla cada registro inválido en una lista de `rechazados` con su motivo de fallo, sin tumbar
  el resto del lote.
- **Rúbrica de relevancia explicable** (`PuntuacionRelevancia`): 3 criterios de 0 a 2 puntos
  (`evidencia_explicita`, `utilidad_comunitaria`, `claridad_contexto`) más un `motivo_seleccion`
  obligatorio, en lugar de un score arbitrario del LLM.
- **Trazabilidad de activos** (`source_ids` en `PostLinkedIn`, `DestaqueNewsletter`, `SugerenciaFAQ`):
  cada activo generado referencia el/los ID(s) de los mensajes originales que lo respaldan.
- **Verificación de persistencia OCI** (`comprobacion_lectura` en `AlmacenamientoOCI`): el cliente
  relee el objeto subido al bucket para confirmar que la escritura persistió correctamente, en lugar
  de confiar solo en la respuesta de `put_object`.

## Estructura del repositorio

```
communitylab-nelson-reyes/
├── app/
│   └── streamlit_app.py
├── data/
│   └── interacciones_ejemplo.json
├── src/
│   ├── ingestion/
│   │   ├── models.py       # Esquemas Pydantic en dos capas
│   │   ├── validador.py    # Aislamiento de registros invalidos
│   │   └── loader.py       # Carga JSON/CSV + validacion
│   ├── graph/
│   │   ├── state.py
│   │   ├── llm_provider.py
│   │   ├── nodes.py
│   │   └── build_graph.py
│   ├── prompts/
│   │   └── canal_prompts.py
│   └── storage/
│       └── oci_client.py   # Sube y RELEE para verificar persistencia
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

Los registros inválidos del batch de ejemplo (`msg-007`, texto vacío) se muestran en consola como
aislados antes de continuar el análisis con los registros válidos.

### 5. Ejecutar el panel Streamlit

```bash
streamlit run app/streamlit_app.py
```

## Requisitos mínimos cubiertos (checklist del hackathon)

- Ingestión funcional de interacciones (JSON/CSV) vía Pydantic, con validación en dos capas.
- Análisis de sentimiento y extracción de temas con LLM (Gemini/OpenAI/Claude, intercambiable).
- Generación de al menos 2 formatos de activos: post LinkedIn + newsletter, o FAQ, según bifurcación.
- Orquestación del flujo con LangGraph, incluyendo edge condicional según `categoria_accion`.
- Integración con OCI Object Storage (capa Always Free), con verificación de lectura tras la escritura.
- Panel Streamlit para visualización de rechazados, análisis y aprobación de activos.

## Próximos pasos sugeridos (diferenciales)

- Despliegue en una VM Compute Always Free de OCI.
- Webhook real conectando Discord/Slack al pipeline.
- Generación de imágenes/banners para los posts con un modelo multimodal.
- Panel de `HumanReviewControl` con historial de revisiones (numero_revision, revisor, comentarios).
