# Bitácora de Desarrollo — CommunityLab
**Hackathon ONE Grupo 10 — Oracle Next Education & Alura**
**Autor:** Nelson Enrique Reyes Fabián
**Repositorio:** [communitylab-nelson-reyes](https://github.com/fren43051/communitylab-nelson-reyes)
**Fecha:** 22 de septiembre de 2026

---

## 1. Contexto

Este documento registra el proceso de construcción del MVP de **CommunityLab**, motor inteligente de transformación y distribución de contenido para comunidades digitales, incluyendo las decisiones de arquitectura, los problemas técnicos encontrados durante la integración con LLMs reales y OCI Object Storage, y las mejoras adoptadas a partir de la revisión cruzada con el equipo del **Grupo 34**.

## 2. Arquitectura implementada

El pipeline sigue el flujo obligatorio del brief del hackathon:

```
JSON/CSV (interacciones crudas)
      │
      ▼
Ingesta permisiva (LoteInteraccionesCrudo)
      │
      ▼
Validación estricta (validador.py) ──► registros rechazados (auditoría)
      │
      ▼
LangGraph: nodo_analizar (LLM: sentimiento, temas, rúbrica de relevancia)
      │
      ├──► generar_caso_exito (post LinkedIn + newsletter)
      └──► generar_faq (sugerencia FAQ)
      │
      ▼
nodo_consolidar (resumen + alertas de soporte)
      │
      ▼
nodo_guardar_oci (persistencia + verificación de lectura)
      │
      ▼
Panel Streamlit (curaduría y aprobación)
```

Stack: Python, LangGraph para orquestación, Pydantic para contratos de datos, soporte intercambiable de LLM (Gemini / OpenAI / Claude vía variable de entorno), OCI Object Storage (capa Always Free) para persistencia, Streamlit para la interfaz de curaduría.

## 3. Mejoras adoptadas del Grupo 34

Tras revisar el repositorio del equipo compañero (`esquemas.py`, `validador.py`), se identificaron y adoptaron cuatro patrones de ingeniería de datos que fortalecieron el contrato original:

| Mejora | Antes | Después |
|---|---|---|
| Validación de ingesta | Una sola capa estricta; un registro corrupto tumbaba el lote completo | Dos capas: admisión permisiva (`LoteInteraccionesCrudo`) + validación estricta (`validar_lote_crudo`) que aísla registros inválidos en una lista de auditoría sin bloquear el resto |
| Puntuación de relevancia | Score único arbitrario devuelto por el LLM | Rúbrica de 3 criterios explicables (`evidencia_explicita`, `utilidad_comunitaria`, `claridad_contexto`, 0–2 cada uno) más justificación textual obligatoria (`motivo_seleccion`) |
| Trazabilidad de activos | Los posts generados no referenciaban su origen | Cada activo (`PostLinkedIn`, `DestaqueNewsletter`, `SugerenciaFAQ`) incluye `source_ids` con el ID del mensaje que lo originó |
| Verificación de persistencia OCI | Se confiaba en que `put_object` no lanzara excepción | Tras subir el objeto, se relee (`get_object`) y se compara el contenido antes de marcar `comprobacion_lectura: true` |

## 4. Incidentes técnicos y resolución

Durante la integración con un LLM real y OCI real se presentaron los siguientes problemas, documentados para referencia del equipo:

### 4.1 Pérdida de cambios por conflicto de merge
Al resolver un conflicto de `git merge` en PyCharm (asistido por Junie), la resolución manual descartó las clases de validación en dos capas recién incorporadas. **Causa:** selección de una versión anterior del archivo durante la resolución del conflicto. **Resolución:** reconstrucción manual de `models.py`, `validador.py`, `loader.py` y `nodes.py`, integrando las mejoras del Grupo 34 con el soporte multi-proveedor de LLM ya presente en `llm_provider.py`.

### 4.2 Campo con nombre reservado en Pydantic
El campo `copy` en el modelo `PostLinkedIn` generaba un `UserWarning` por colisionar con el método `BaseModel.copy()`. **Resolución:** renombrado a `cuerpo`.

### 4.3 Respuesta del LLM con estructura inesperada
Al cambiar de proveedor LLM (prueba con Anthropic Claude), el modelo devolvió un objeto/diccionario en el campo `origen` de `SugerenciaFAQ`, donde el esquema esperaba una cadena de texto simple, provocando un `ValidationError` de Pydantic. **Causa raíz:** el prompt no especificaba de forma suficientemente estricta el tipo de dato esperado por campo. **Resolución:** (a) se reescribieron los prompts de generación de activos exigiendo explícitamente "string plano, nunca un objeto" con ejemplos correctos e incorrectos; (b) se añadió una función de normalización defensiva (`_forzar_string`) que extrae el contenido textual relevante de un dict inesperado como salvaguarda adicional.

### 4.4 Error de escritura concurrente en el grafo (`InvalidUpdateError`)
Al procesar un lote con interacciones de distintas categorías (`caso_exito` y `faq_tip` simultáneamente), LangGraph ejecuta las ramas condicionales `generar_caso_exito` y `generar_faq` en paralelo dentro del mismo "superstep". Los nodos devolvían el estado completo (incluyendo la clave `lote`, sin cambios), y LangGraph no pudo resolver la escritura concurrente sobre esa clave, lanzando `InvalidUpdateError: Can receive only one value per step`.

**Resolución:**
- Cada nodo del grafo se modificó para devolver únicamente un diccionario parcial con las claves que efectivamente modifica, en lugar del estado completo.
- La clave `activos_generados` se declaró con un *reducer* (`Annotated[list[dict], operator.add]`) en el `TypedDict` del estado, indicándole a LangGraph que debe concatenar las listas devueltas por nodos paralelos en lugar de fallar.
- El grafo se reestructuró para que ambas ramas condicionales conduzcan directamente al nodo `consolidar`, reflejando que son independientes entre sí.

### 4.5 Warnings de serialización Pydantic
Los activos generados se asignaban como diccionarios (`.model_dump()`) a campos tipados como modelos Pydantic (`Optional[PostLinkedIn]`, etc.), generando `PydanticSerializationUnexpectedValue` al serializar el paquete final. **Resolución:** se asignan directamente las instancias tipadas (`PostLinkedIn(**datos)`) en lugar de su representación en diccionario.

### 4.6 Exposición accidental de credencial
Durante las pruebas de integración con Gemini se pegó accidentalmente una API key real en el flujo de trabajo. **Acción inmediata:** revocación de la credencial en Google AI Studio y generación de una nueva antes de continuar. **Lección para el equipo:** las credenciales deben configurarse únicamente en archivos `.env` locales (excluidos del control de versiones vía `.gitignore`) y nunca compartirse en texto plano en ningún canal.

### 4.7 Resolución de importación en Streamlit (`ModuleNotFoundError: No module named 'src'`)
Al ejecutar el panel interactivo mediante `streamlit run app/streamlit_app.py`, Streamlit establece el directorio de trabajo o el contexto de ejecución en `app/`, lo que provocaba que las importaciones absolutas del paquete raíz `src` fallaran. **Resolución:** se incorporó la resolución dinámica del directorio raíz del proyecto mediante `Path(__file__).resolve().parent.parent` y su inyección en `sys.path.insert(0, ...)` al inicio del script `app/streamlit_app.py`.

### 4.8 Incorporación del flujo de curaduría y revisión humana (Human-in-the-loop)
Se integró el modelo `HumanReviewControl` en el paquete de distribución (`PaqueteDistribucion`), permitiendo que el curador humano apruebe o rechace los activos generados, agregue comentarios de feedback e incremente el número de revisión, persistiendo automáticamente el estado actualizado tanto en la interfaz de Streamlit como en OCI Object Storage.

## 5. Validación end-to-end

Tras aplicar las correcciones anteriores, se ejecutó el pipeline completo (`python main.py` y `streamlit run app/streamlit_app.py`) contra el lote de datos de ejemplo, confirmando:

- Aislamiento correcto de 1 registro inválido (texto vacío) de un total de 7, sin bloquear el procesamiento de los 6 restantes.
- Análisis de sentimiento y categorización exitoso vía Anthropic Claude (y configurable con Gemini u OpenAI).
- Generación simultánea de post LinkedIn, resumen de newsletter y sugerencia de FAQ, cada uno con `source_ids` trazables.
- Detección de una alerta de soporte sobre un registro con dificultad técnica no resuelta.
- Persistencia exitosa en OCI Object Storage con verificación de lectura confirmada (`comprobacion_lectura: true`).
- Panel interactivo en Streamlit funcional con métricas en tiempo real, edición de copys y módulo de aprobación/rechazo humano.

## 6. Estado frente al checklist del hackathon

| Requisito mínimo | Estado |
|---|---|
| Ingestión funcional de interacciones (JSON/CSV) | ✅ Cumplido, con validación en dos capas |
| Análisis de sentimiento y extracción de temas con LLM | ✅ Cumplido (Claude, intercambiable con Gemini/OpenAI) |
| Generación de al menos 2 formatos de activos de marketing | ✅ Cumplido (LinkedIn + newsletter + FAQ) |
| Orquestación con LangGraph/Python | ✅ Cumplido, con bifurcación condicional validada |
| Integración con OCI Object Storage (Always Free) | ✅ Cumplido, con verificación de lectura |
| Panel Streamlit con control de revisión humana | ✅ Cumplido (aprobación/rechazo, trazabilidad y edición) |
| Mínimo 3 ejemplos de transformación demostrados | ✅ Cumplido |
| Repositorio en GitHub con documentación | ✅ Cumplido |

## 7. Próximos pasos

- Explorar despliegue en OCI Compute Instance (Always Free) como diferencial.
- Evaluar integración de un webhook real (Discord/Slack) para ingesta en tiempo real.
- Incorporar generación de banners o creatividades gráficas multimodales para los posts generados.
