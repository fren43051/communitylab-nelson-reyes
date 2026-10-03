# 📖 Bitácora de Desarrollo — CommunityLab
**Proyecto:** CommunityLab – Motor Inteligente de Transformación y Distribución para Comunidades Digitales  
**Iniciativa:** Hackathon ONE Grupo 10 — Oracle Next Education & Alura  
**Autor:** Nelson Reyes  
**Rol:** Backend & Cloud Architect / Lead Data & AI Engineer  

---

## 🎯 Resumen Ejecutivo del Proyecto
CommunityLab es un motor inteligente diseñado para procesar flujos de interacción orgánica desde comunidades tecnológicas (Discord, Slack, foros y formularios) y convertirlos sistemáticamente en activos de marketing institucional, contenidos educativos y resúmenes de métricas comunitarias. 

La arquitectura integra:
1. **Ingesta y Validación de Dos Capas (Pydantic V2):** Admisión flexible y tipado estricto que aísla registros vacíos para optimizar consumo de tokens.
2. **Orquestación Cognitiva con LangGraph:** Grafo multicapa con routers condicionales para bifurcación entre casos de éxito (`generar_caso_exito`) y soporte recurrente (`generar_faq`).
3. **Persistencia en la Nube con Oracle Cloud Infrastructure (OCI):** Almacenamiento y comprobación de integridad en OCI Object Storage en la capa Always Free.
4. **Interfaces de Consumo Dual:** API REST desacoplada en FastAPI para webhooks en tiempo real y panel interactivo en Streamlit para curaduría humana (*Human-in-the-Loop*).

---

## 📅 Hito 1: Fundaciones y Arquitectura del MVP (2026-09-22)
* **Diseño del Pipeline:** Definición del flujo desacoplado en capas (Ingesta Pydantic ➔ Orquestación LangGraph ➔ Persistencia OCI ➔ Streamlit UI).
* **Modelado de Dominio (`src/ingestion/models.py`):** Creación de esquemas tipados para `InteraccionCruda`, `LoteInteraccionesCrudo`, `AnalisisInteraccion`, `PuntuacionRelevancia` y el contrato final `PaqueteDistribucion` (versión 1.2.0).
* **Validador de Ingesta (`src/ingestion/validador.py`):** Lógica de separación automática: admite registros con contenido y descarta registros vacíos sin interrumpir el lote.

---

## 📅 Hito 2: Automatización en Tiempo Real con Webhook y n8n (2026-09-23)
* **Backend FastAPI (`api/`):** Construcción del servicio REST con endpoint `/health` y `POST /api/webhooks/linkedin`.
* **Seguridad Criptográfica:** Validación mediante cabecera `X-Webhook-Secret` con `hmac.compare_digest` para mitigar ataques de temporización.
* **Túnel y Pruebas:** Conexión validada entre n8n y la API mediante túnel seguro (ngrok / reverse proxy) documentado en `INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`.

---

## 📅 Hito 3: Acuerdos de Coordinación y Transferencia Técnica (2026-09-24)
* **Reunión de Equipo:** Acuerdos para estandarizar el entorno en **Python 3.11** y definir el prototipo de Enrique como referencia de integración.
* **Documentación para el Equipo:** Elaboración de la guía técnica y matriz de resolución de dudas frecuentes para LangGraph, OCI y FastAPI.

---

## 📅 Hito 4: Calidad de Ingeniería y Suite Automatizada 100% (2026-10-01)
* **Suite de Pruebas Automatizadas (`tests/test_pipeline.py`):**
  1. *Validación Pydantic:* Comprobación de admisión de registros válidos y aislamiento de textos vacíos en `validador.py`.
  2. *Contrato Estricto:* Test de integridad sobre el modelo `PaqueteDistribucion`.
  3. *Router de LangGraph:* Verificación unitaria de bifurcación condicional (`enrutar_categorias` hacia `generar_caso_exito` o `generar_faq`).
  4. *Seguridad de Endpoints:* Pruebas con `TestClient` para rechazo HTTP 401 sin secreto o token erróneo y diagnóstico en `/health`.
* **Resultado:** 7 de 7 pruebas aprobadas (`7 passed in 0.29s`).

---

## 📅 Hito 5: Despliegue en la Nube (OCI Compute), n8n Docker y Persistencia Real (2026-10-03)
* **Despliegue Completo en la Nube (Diferencial Oficial OCI Compute):**
  * Puesta en marcha de una máquina virtual **`VM.Standard.A4.Flex` (Ubuntu Linux ARM)** en Oracle Cloud Infrastructure (Región Phoenix).
  * Configuración del firewall de red (OCI VCN Ingress Rules) y reglas locales `iptables` en los puertos `8000` (FastAPI), `8501` (Streamlit) y `5678` (n8n).
* **Persistencia Verificada en OCI Object Storage (Always Free):**
  * Creación y autenticación con API Keys del bucket `communitylab-activos-marketing` (Namespace `axv2uguhheq1`).
  * Validación de ciclo completo de escritura y lectura de paquetes JSON (`comprobacion_lectura: true`).
* **Automatización con n8n en Contenedor Docker:**
  * Despliegue del contenedor `n8nio/n8n` en la misma instancia de OCI.
  * Configuración del flujo de 3 nodos (`Webhook` ➔ `Code JS normalizador` ➔ `HTTP Request a FastAPI`).
  * Exportación oficial del workflow en `docs/n8n_workflow_communitylab.json`.
* **Prueba End-to-End en Producción Cloud:**
  * Recepción de eventos desde Webhook n8n ➔ Ingesta y validación en FastAPI ➔ Generación de copys para LinkedIn y FAQs con LLM ➔ Persistencia automática en el bucket de OCI y visualización en el panel de Streamlit.

---

## 🛠️ Stack Tecnológico Integrado
* **Lenguaje & Entorno:** Python 3.11 / Python 3.14 / uv
* **Orquestación Cognitiva:** LangChain, LangGraph
* **Validación de Datos:** Pydantic V2
* **Backend API:** FastAPI, Uvicorn
* **Frontend Web:** Streamlit
* **Infraestructura Cloud:** Oracle Cloud Infrastructure (OCI Compute + OCI Object Storage Always Free)
* **Automatización & Contenedores:** Docker, n8n
* **Testing:** Pytest (100% Passing)
