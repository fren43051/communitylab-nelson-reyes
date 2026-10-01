# 📓 Bitácora de Desarrollo — CommunityLab (Nelson Enrique Reyes)

Bitácora técnica de decisiones de arquitectura, implementación y validación experimental para el **Hackathon ONE Grupo 10** (Oracle Next Education & Alura).

---

## 📅 Hito 1: Fundaciones y Arquitectura del MVP (2026-09-22)
* **Diseño del Pipeline:** Definición del flujo desacoplado en capas (Ingesta Pydantic ➔ Orquestación LangGraph ➔ Persistencia OCI ➔ Streamlit UI).
* **Multi-LLM Provider:** Construcción de `src/graph/llm_provider.py` con soporte en caliente para Google Gemini (`gemini-1.5-flash`), OpenAI (`gpt-4o-mini`) y Anthropic Claude (`claude-haiku-4-5-20251001`).
* **Conector OCI Object Storage:** Implementación del cliente `src/storage/oci_client.py` con autenticación mediante API Key y verificación de lectura inmediata en la región Monterrey (`mx-monterrey-1`).

---

## 📅 Hito 2: Automatización en Tiempo Real con Webhook y n8n (2026-09-23)
* **Backend FastAPI (`api/`):** Construcción del servicio REST con endpoint `/health` y `POST /api/webhooks/linkedin`.
* **Seguridad Criptográfica:** Validación de cabecera `X-Webhook-Secret` mediante comparación de digests en memoria (`hmac.compare_digest`).
* **Integración n8n Cloud + ngrok:** 
  * Configuración del flujo visual: `Webhook (n8n)` ➔ `Code (Transformación JavaScript a Pydantic)` ➔ `HTTP Request`.
  * Exposición de la API local mediante túnel permanente de ngrok (`vocal-sharing-tahr.ngrok-free.app`).
* **Validación End-to-End con Video:** Ejecución y grabación de prueba en vivo con evento simulado, confirmando generación del post de LinkedIn y persistencia de `paquete-distribucion.json` en OCI.

---

## 📅 Hito 3: Acuerdos de Coordinación y Transferencia Técnica (2026-09-24)
* **Reunión de Equipo:** Acuerdos para estandarizar el entorno en **Python 3.11** y definir el prototipo de Enrique como referencia de integración.
* **Documentación para el Equipo:** Elaboración de la guía técnica y matriz de resolución de dudas frecuentes para LangGraph, OCI y FastAPI.

---

## 📅 Hito 4: Calidad de Ingeniería y Preparación Final 1000% (2026-10-01)
* **Suite de Pruebas Automatizadas (`tests/test_pipeline.py`):**
  1. *Validación Pydantic:* Comprobación de admisión de registros válidos y aislamiento de textos vacíos en `validador.py`.
  2. *Contrato Estricto:* Test de integridad sobre el modelo `PaqueteDistribucion`.
  3. *Router de LangGraph:* Verificación unitaria de bifurcación condicional (`enrutar_categorias` hacia `generar_caso_exito` o `generar_faq`).
  4. *Seguridad de Endpoints:* Pruebas con `TestClient` para rechazo HTTP 401 sin secreto o token erróneo y diagnóstico en `/health`.
* **Casos Canónicos del Challenge (`data/interacciones_ejemplo.json`):**
  * Caso 1 (Testimonio / Contratación): Mariana Souza ➔ Generación de post inspirador de LinkedIn y destaque de newsletter.
  * Caso 2 (Pregunta Técnica / Router): Lucas Albuquerque ➔ Generación de tip rápido / sugerencia FAQ.
  * Caso 3 (Feedback / OCI Always Free): Carlos Mendoza ➔ Resumen semanal de métricas.
  * Caso 4 (Control de Errores): Registro vacío para certificar el descarte automático.
* **Documentación y Badges:** Incorporación de insignias oficiales en el `README.md` (Python 3.11, LangGraph, FastAPI, OCI Always Free, Pytest Passing) y sección de evidencia audiovisual.
