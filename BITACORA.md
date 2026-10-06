# ðŸ“– BitÃ¡cora de Desarrollo â€” CommunityLab
**Proyecto:** CommunityLab â€“ Motor Inteligente de TransformaciÃ³n y DistribuciÃ³n para Comunidades Digitales  
**Iniciativa:** Hackathon ONE Grupo 10 â€” Oracle Next Education & Alura  
**Autor:** Nelson Reyes  
**Rol:** Backend & Cloud Architect / Lead Data & AI Engineer  

---

## ðŸŽ¯ Resumen Ejecutivo del Proyecto
CommunityLab es un motor inteligente diseÃ±ado para procesar flujos de interacciÃ³n orgÃ¡nica desde comunidades tecnolÃ³gicas (Discord, Slack, foros y formularios) y convertirlos sistemÃ¡ticamente en activos de marketing institucional, contenidos educativos y resÃºmenes de mÃ©tricas comunitarias. 

La arquitectura integra:
1. **Ingesta y ValidaciÃ³n de Dos Capas (Pydantic V2):** AdmisiÃ³n flexible y tipado estricto que aÃ­sla registros vacÃ­os para optimizar consumo de tokens.
2. **OrquestaciÃ³n Cognitiva con LangGraph:** Grafo multicapa con routers condicionales para bifurcaciÃ³n entre casos de Ã©xito (`generar_caso_exito`) y soporte recurrente (`generar_faq`).
3. **Persistencia en la Nube con Oracle Cloud Infrastructure (OCI):** Almacenamiento y comprobaciÃ³n de integridad en OCI Object Storage en la capa Always Free.
4. **Interfaces de Consumo Dual:** API REST desacoplada en FastAPI para webhooks en tiempo real y panel interactivo en Streamlit para curadurÃ­a humana (*Human-in-the-Loop*).

---

## ðŸ“… Hito 1: Fundaciones y Arquitectura del MVP (2026-09-22)
* **DiseÃ±o del Pipeline:** DefiniciÃ³n del flujo desacoplado en capas (Ingesta Pydantic âž” OrquestaciÃ³n LangGraph âž” Persistencia OCI âž” Streamlit UI).
* **Modelado de Dominio (`src/ingestion/models.py`):** CreaciÃ³n de esquemas tipados para `InteraccionCruda`, `LoteInteraccionesCrudo`, `AnalisisInteraccion`, `PuntuacionRelevancia` y el contrato final `PaqueteDistribucion` (versiÃ³n 1.2.0).
* **Validador de Ingesta (`src/ingestion/validador.py`):** LÃ³gica de separaciÃ³n automÃ¡tica: admite registros con contenido y descarta registros vacÃ­os sin interrumpir el lote.

---

## ðŸ“… Hito 2: AutomatizaciÃ³n en Tiempo Real con Webhook y n8n (2026-09-23)
* **Backend FastAPI (`api/`):** ConstrucciÃ³n del servicio REST con endpoint `/health` y `POST /api/webhooks/linkedin`.
* **Seguridad CriptogrÃ¡fica:** ValidaciÃ³n mediante cabecera `X-Webhook-Secret` con `hmac.compare_digest` para mitigar ataques de temporizaciÃ³n.
* **TÃºnel y Pruebas:** ConexiÃ³n validada entre n8n y la API mediante tÃºnel seguro (ngrok / reverse proxy) documentado en `INTEGRACION_WEBHOOK_N8N_LINKEDIN.md`.

---

## ðŸ“… Hito 3: Acuerdos de CoordinaciÃ³n y Transferencia TÃ©cnica (2026-09-24)
* **ReuniÃ³n de Equipo:** Acuerdos para estandarizar el entorno en **Python 3.11** y definir el prototipo de Enrique como referencia de integraciÃ³n.
* **DocumentaciÃ³n para el Equipo:** ElaboraciÃ³n de la guÃ­a tÃ©cnica y matriz de resoluciÃ³n de dudas frecuentes para LangGraph, OCI y FastAPI.

---

## ðŸ“… Hito 4: Calidad de IngenierÃ­a y Suite Automatizada 100% (2026-10-01)
* **Suite de Pruebas Automatizadas (`tests/test_pipeline.py`):**
  1. *ValidaciÃ³n Pydantic:* ComprobaciÃ³n de admisiÃ³n de registros vÃ¡lidos y aislamiento de textos vacÃ­os en `validador.py`.
  2. *Contrato Estricto:* Test de integridad sobre el modelo `PaqueteDistribucion`.
  3. *Router de LangGraph:* VerificaciÃ³n unitaria de bifurcaciÃ³n condicional (`enrutar_categorias` hacia `generar_caso_exito` o `generar_faq`).
  4. *Seguridad de Endpoints:* Pruebas con `TestClient` para rechazo HTTP 401 sin secreto o token errÃ³neo y diagnÃ³stico en `/health`.
* **Resultado:** 7 de 7 pruebas aprobadas (`7 passed in 0.29s`).

---

## ðŸ“… Hito 5: Despliegue en la Nube (OCI Compute), n8n Docker y Persistencia Real (2026-10-03)
* **Despliegue Completo en la Nube (Diferencial Oficial OCI Compute):**
  * Puesta en marcha de una mÃ¡quina virtual **`VM.Standard.A4.Flex` (Ubuntu Linux ARM)** en Oracle Cloud Infrastructure (RegiÃ³n Phoenix).
  * ConfiguraciÃ³n del firewall de red (OCI VCN Ingress Rules) y reglas locales `iptables` en los puertos `8000` (FastAPI), `8501` (Streamlit) y `5678` (n8n).
* **Persistencia Verificada en OCI Object Storage (Always Free):**
  * CreaciÃ³n y autenticaciÃ³n con API Keys del bucket `communitylab-activos-marketing` (Namespace `axv2uguhheq1`).
  * ValidaciÃ³n de ciclo completo de escritura y lectura de paquetes JSON (`comprobacion_lectura: true`).
* **AutomatizaciÃ³n con n8n en Contenedor Docker:**
  * Despliegue del contenedor `n8nio/n8n` en la misma instancia de OCI.
  * ConfiguraciÃ³n del flujo de 3 nodos (`Webhook` âž” `Code JS normalizador` âž” `HTTP Request a FastAPI`).
  * ExportaciÃ³n oficial del workflow en `docs/n8n_workflow_communitylab.json`.
* **Prueba End-to-End en ProducciÃ³n Cloud:**
  * RecepciÃ³n de eventos desde Webhook n8n âž” Ingesta y validaciÃ³n en FastAPI âž” GeneraciÃ³n de copys para LinkedIn y FAQs con LLM âž” Persistencia automÃ¡tica en el bucket de OCI y visualizaciÃ³n en el panel de Streamlit.

---

## ðŸ“… Hito 6: VerificaciÃ³n local de credenciales y suite (2026-10-06)
* **Estado Git:** Rama alineada con `communitylab-nelson-reyes` (`main`); `.env` solo local (gitignored).
* **LLM Anthropic:** `LLM_PROVIDER=anthropic` + `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` â€” invocaciÃ³n de prueba exitosa (sin 401/403/429).
* **Pytest:** `7 passed` en `tests/test_pipeline.py` (validaciÃ³n, contrato, router, webhook, health).
* **OCI regiÃ³n de esta tenancy (fren43051):**
  * Home region real: **`mx-monterrey-1`** (clave `MTY`). Ãšnica suscripciÃ³n `READY`.
  * **`us-phoenix-1` no aplica** a esta cuenta: auth 401 y al intentar suscribir `PHX` â†’ `409 TenantCapacityExceeded` (lÃ­mite de regiones Always Free).
  * El despliegue en Phoenix del Hito 5 corresponde a otra tenancy/namespace (`axv2uguhheq1`), no a `axl02vwdgmxt`.
* **OCI Object Storage (bloqueado por cuota en Monterrey):**
  * Auth API Key OK (`~/.oci/config`, regiÃ³n `mx-monterrey-1`, namespace `axl02vwdgmxt`).
  * LÃ­mites de servicio: `object-storage` â†’ `bucket-count=0`, `storage-bytes=0` (sin capacidad Always Free usable).
  * Por eso `create_bucket` responde 409 y `get`/`put` 404 aunque `list_buckets` muestre un nombre fantasma.
  * AcciÃ³n: en consola OCI (Governance â†’ Limits / Request service limit increase) o verificar elegibilidad Always Free de Object Storage en `mx-monterrey-1`.
* **Seguridad:** no versionar `.env`, `*.pem` ni secretos de webhook.

---

## ðŸ› ï¸ Stack TecnolÃ³gico Integrado
* **Lenguaje & Entorno:** Python 3.11 / Python 3.14 / uv
* **OrquestaciÃ³n Cognitiva:** LangChain, LangGraph
* **ValidaciÃ³n de Datos:** Pydantic V2
* **Backend API:** FastAPI, Uvicorn
* **Frontend Web:** Streamlit
* **Infraestructura Cloud:** Oracle Cloud Infrastructure (OCI Compute + OCI Object Storage Always Free)
* **AutomatizaciÃ³n & Contenedores:** Docker, n8n
* **Testing:** Pytest (100% Passing)

---

## Plan B: resiliencia y curaduria para la demo (2026-10-06)
* La interfaz Streamlit permite editar LinkedIn, newsletter y FAQ; las ediciones se guardan en el paquete antes de aprobar o rechazar.
* La salida automatica se persiste como `borrador`; las decisiones humanas se guardan en rutas OCI separadas `aprobado` y `rechazado`. El rechazo exige un motivo.
* Se agregaron tres fixtures de demo (contratacion, FAQ LangGraph y lote mixto con un registro invalido) y ejemplos few-shot en los cuatro prompts.
* `_llm_json` reintenta hasta tres veces respuestas fallidas y reporta el error; un fallo de analisis individual queda aislado como pendiente de revision/soporte.
* Los errores OCI conservan el estado tipado `guardado_error` y exponen el detalle por separado.
