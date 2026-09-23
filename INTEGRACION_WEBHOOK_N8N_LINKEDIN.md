# Integración de CommunityLab con Webhooks, n8n y LinkedIn

Este documento describe cómo conectar CommunityLab con n8n para recibir datos de
LinkedIn (o de un proveedor autorizado), transformarlos al formato del proyecto,
procesarlos con LangGraph y almacenar el resultado en OCI Object Storage.

> **Estado actual (actualizado 2026-09-23):** la integración fue implementada y
> **validada end-to-end en una ejecución real** usando n8n Cloud + ngrok + la API
> local de CommunityLab. El flujo completo Webhook → Code → HTTP Request → API →
> LangGraph/Claude → OCI quedó demostrado con una ejecución exitosa. Ver la
> sección 17 con la evidencia de esa corrida.

## 1. Arquitectura implementada

```text
Cliente de prueba (PowerShell / cURL / formulario)
                    |
                    v
        Webhook de n8n (n8n Cloud)
        POST /webhook-test/linkedin-events
                    |
                    v
        Code (n8n): normaliza el payload
        al contrato LoteInteraccionesCrudo
                    |
                    v
        HTTP Request (n8n) -> tunel ngrok
        https://<dominio-dev>.ngrok-free.app
                    |
                    v
        ngrok reenvia a http://localhost:8000
                    |
                    v
        POST /api/webhooks/linkedin
        API HTTP de CommunityLab (FastAPI)
                    |
                    v
      Pydantic + validacion de ingesta
                    |
                    v
              LangGraph + LLM (Claude)
                    |
                    v
       OCI Object Storage + respuesta JSON
                    |
                    v
       Streamlit para curaduria humana
```

La responsabilidad de cada componente:

| Componente | Responsabilidad |
|---|---|
| LinkedIn | Fuente de datos, únicamente mediante APIs y permisos autorizados (pendiente de conectar; hoy se simula el payload) |
| n8n (Cloud) | Recepción del evento vía Webhook, transformación con Code, envío con HTTP Request |
| ngrok | Expone la API local de CommunityLab a una URL pública HTTPS que n8n Cloud puede alcanzar |
| API de CommunityLab | Autenticación del webhook, validación y ejecución del grafo |
| LangGraph | Análisis, clasificación y generación de activos |
| OCI | Persistencia del paquete generado |
| Streamlit | Revisión, edición, aprobación o rechazo humano |

## 2. Contrato de datos que ya utiliza CommunityLab

El endpoint recibe un lote compatible con `LoteInteraccionesCrudo`.
El JSON mínimo es:

```json
{
  "schema_version": "1.0.0",
  "origen_comunidad": "linkedin",
  "periodo_referencia": "2026-09-22",
  "interacciones": [
    {
      "id": "linkedin-comment-001",
      "autor": "Nombre del usuario",
      "canal": "linkedin",
      "tipo": "feedback",
      "texto": "El contenido fue muy útil para nuestra comunidad.",
      "metadata_origen": {
        "plataforma": "linkedin",
        "identificador_original": "urn:li:comment:123456",
        "fecha": "2026-09-22T21:30:00Z"
      }
    }
  ]
}
```

Los valores válidos para `tipo` son:

```text
testimonio
pregunta_tecnica
feedback
otro
sin_clasificar
```

La primera capa de ingesta admite registros incompletos y
`validar_lote_crudo` aísla los registros rechazados. Los registros que llegan
al análisis estricto necesitan un `texto` no vacío.

### Campos recomendados

| Campo | Obligatorio | Descripción |
|---|---:|---|
| `schema_version` | No | Versión del contrato; usar `1.0.0` |
| `origen_comunidad` | Sí | En este caso, `linkedin` |
| `periodo_referencia` | Sí | Fecha o periodo del lote |
| `interacciones` | Sí | Lista con una o más interacciones |
| `interacciones[].id` | Sí | ID estable del evento |
| `interacciones[].autor` | No | Nombre o identificador disponible |
| `interacciones[].canal` | Sí | `linkedin` |
| `interacciones[].tipo` | No | Clasificación inicial; se puede usar `sin_clasificar` |
| `interacciones[].texto` | No en la admisión | Texto del comentario o publicación |
| `metadata_origen` | No | Trazabilidad del evento original |

## 3. Cambios realizados en el proyecto

### 3.1 Dependencias

Agregadas a `requirements.txt`:

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
```

Instalación:

```powershell
pip install -r requirements.txt
```

### 3.2 Variables de entorno

En `.env.example`:

```env
# --- Webhooks ---
WEBHOOK_SECRET=cambia-esta-clave-por-una-segura
WEBHOOK_MAX_ITEMS=100
```

En el `.env` local se usa una clave real, larga y privada. El archivo `.env`
ya está excluido por `.gitignore` y no debe subirse al repositorio.

### 3.3 Estructura creada

```text
api/
├── __init__.py
├── main.py
└── webhooks.py
```

No fue necesario modificar los módulos existentes de ingesta, grafo,
almacenamiento o Streamlit porque el endpoint reutiliza esas piezas.

## 4. API HTTP (implementada)

### 4.1 `api/webhooks.py`

```python
import hmac
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import ValidationError

from src.graph.build_graph import construir_grafo
from src.ingestion.models import LoteInteraccionesCrudo
from src.ingestion.validador import validar_lote_crudo

load_dotenv()

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
GRAFO = construir_grafo()


def validar_secreto_webhook(
    x_webhook_secret: str | None,
) -> None:
    secreto_configurado = os.getenv("WEBHOOK_SECRET")

    if not secreto_configurado:
        raise RuntimeError(
            "WEBHOOK_SECRET no esta configurado en las variables de entorno"
        )

    if not x_webhook_secret or not hmac.compare_digest(
        x_webhook_secret,
        secreto_configurado,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secreto de webhook invalido",
        )


@router.get("/linkedin/health")
def comprobar_estado_webhook() -> dict:
    return {
        "status": "ok",
        "service": "communitylab",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/linkedin")
def recibir_datos_linkedin(
    payload: dict,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    validar_secreto_webhook(x_webhook_secret)

    try:
        lote_crudo = LoteInteraccionesCrudo.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error.errors(),
        ) from error

    limite_items = int(os.getenv("WEBHOOK_MAX_ITEMS", "100"))

    if len(lote_crudo.interacciones) > limite_items:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El lote no puede superar {limite_items} interacciones",
        )

    lote_validado, rechazados = validar_lote_crudo(lote_crudo)

    if not lote_validado.interacciones:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "mensaje": "No hay interacciones validas para procesar",
                "rechazados": rechazados,
            },
        )

    estado_inicial = {
        "lote": lote_validado,
        "rechazados": rechazados,
        "analisis": [],
        "activos_generados": [],
        "paquete_final": None,
        "oci_resultado": None,
    }

    try:
        resultado = GRAFO.invoke(estado_inicial)
    except Exception as error:
        # Registrar el error en un sistema de logs antes de desplegar a producción.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo procesar el lote recibido",
        ) from error

    paquete_final = resultado["paquete_final"]

    return {
        "status": "procesado",
        "origen_comunidad": lote_crudo.origen_comunidad,
        "periodo_referencia": lote_crudo.periodo_referencia,
        "registros_recibidos": len(lote_crudo.interacciones),
        "registros_rechazados": len(rechazados),
        "paquete": paquete_final.model_dump(mode="json"),
    }
```

> Antes de usar este ejemplo en producción, conviene reemplazar el comentario
> de logging por el sistema de logs del despliegue. No se deben registrar
> tokens, secretos ni respuestas que contengan datos privados.

### 4.2 `api/main.py`

```python
from fastapi import FastAPI

from api.webhooks import router as webhooks_router

app = FastAPI(
    title="CommunityLab API",
    version="1.0.0",
)

app.include_router(webhooks_router)


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "communitylab-api",
    }
```

### 4.3 `api/__init__.py`

Vacío.

## 5. Ejecutar y probar la API localmente

Desde la raíz del proyecto:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Comprobación validada:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/health"
```

Respuesta real obtenida:

```text
status service
------ -------
ok     communitylab-api
```

Documentación interactiva: `http://localhost:8000/docs`.
Endpoint de negocio: `http://localhost:8000/api/webhooks/linkedin`.

### Prueba directa con PowerShell (validada con Claude generando contenido real)

```powershell
$body = @{
    schema_version = "1.0.0"
    origen_comunidad = "linkedin"
    periodo_referencia = "2026-09-23"
    interacciones = @(
        @{
            id = "linkedin-comment-001"
            autor = "Maria Lopez"
            canal = "linkedin"
            tipo = "feedback"
            texto = "Excelente publicacion, me ayudo mucho a entender LangGraph"
            metadata_origen = @{
                plataforma = "linkedin"
                identificador_original = "urn:li:comment:123456"
                fecha = "2026-09-23T14:00:00Z"
            }
        }
    )
} | ConvertTo-Json -Depth 5

$respuesta = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/webhooks/linkedin" `
  -Headers @{ "X-Webhook-Secret" = "<tu-clave-larga-y-privada>" } `
  -ContentType "application/json" `
  -Body $body

$respuesta.paquete | ConvertTo-Json -Depth 10
```

> **Nota de encoding en PowerShell 5.x/7.x en Windows:** si los acentos salen
> corruptos (`Ã³` en vez de `ó`) al imprimir en consola, no es un problema del
> archivo ni de la API — el JSON ya se genera y guarda en UTF-8 correctamente.
> Corregir la consola antes de repetir la petición:
> ```powershell
> [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
> $OutputEncoding = [System.Text.Encoding]::UTF8
> ```

## 6. n8n Cloud: configuración usada (no Docker local)

Se optó por **n8n Cloud** (trial de 14 días, 1000 ejecuciones) en vez de una
instalación con Docker local, porque ya estaba disponible y no requiere
configurar infraestructura adicional. Docker local sigue siendo una alternativa
válida sin límite de días si se prefiere control total.

### Opción A: consulta periódica (no usada en esta implementación)

```text
Schedule Trigger
        |
        v
HTTP Request a LinkedIn
        |
        v
Code: normalizar datos
        |
        v
Data Store: evitar duplicados
        |
        v
HTTP Request a CommunityLab
        |
        v
IF / notificacion
```

### Opción B: recepción de eventos (implementada y validada)

```text
Webhook de n8n
        |
        v
Code: normalizar datos
        |
        v
HTTP Request a CommunityLab
        |
        v
Respond to Webhook (implícito via "When Last Node Finishes")
```

### Nodo Webhook — configuración real usada

```text
HTTP Method: POST
Path: linkedin-events
Authentication: None (suficiente para demo; usar Header Auth en producción)
Respond: When Last Node Finishes   <- clave para ver la respuesta real de la API
Response Data: First Entry JSON
```

URLs generadas por n8n Cloud en esta instancia:

```text
Test:       https://fren43051.app.n8n.cloud/webhook-test/linkedin-events
Producción: https://fren43051.app.n8n.cloud/webhook/linkedin-events
```

> Importante: con "Respond: Immediately" (valor por defecto) el webhook
> responde antes de que el Code y el HTTP Request terminen, por lo que nunca
> se ve la respuesta real de la API. Debe cambiarse a **"When Last Node
> Finishes"**.

## 7. Nodo Code de n8n — versión validada

Con el payload de prueba enviado por PowerShell, el body que reciben n8n en
`$input.first().json.body` fue:

```json
{
  "id": "linkedin-n8n-001",
  "autor": "Maria Lopez",
  "tipo": "feedback",
  "texto": "Excelente publicacion, me ayudo mucho a entender LangGraph",
  "identificador_original": "urn:li:comment:999888"
}
```

Código usado en el nodo **Code** (JavaScript, modo "Run Once for All Items"):

```javascript
const item = $input.first().json.body;

return [{
  json: {
    schema_version: "1.0.0",
    origen_comunidad: "linkedin",
    periodo_referencia: new Date().toISOString().slice(0,10),
    interacciones: [{
      id: item.id || `linkedin-${Date.now()}`,
      autor: item.autor,
      canal: "linkedin",
      tipo: item.tipo || "feedback",
      texto: item.texto,
      metadata_origen: {
        plataforma: "linkedin",
        identificador_original: item.identificador_original || "",
        fecha: new Date().toISOString()
      }
    }]
  }
}];
```

Salida real obtenida al ejecutar el paso (`Execute step`):

```json
{
  "schema_version": "1.0.0",
  "origen_comunidad": "linkedin",
  "periodo_referencia": "2026-09-23",
  "interacciones": [{
    "id": "linkedin-n8n-001",
    "autor": "Maria Lopez",
    "canal": "linkedin",
    "tipo": "feedback",
    "texto": "Excelente publicacion, me ayudo mucho a entender LangGraph",
    "metadata_origen": {
      "plataforma": "linkedin",
      "identificador_original": "urn:li:comment:999888",
      "fecha": "2026-09-23T08:15:42.209Z"
    }
  }]
}
```

Este JSON coincide exactamente con el contrato `LoteInteraccionesCrudo` que
espera la API.

### Variante genérica (si el proveedor no manda campos con estos nombres)

Si el nodo anterior a Code devuelve un formato distinto, como:

```json
{
  "id": "urn:li:comment:123456",
  "authorName": "María López",
  "comment": "Excelente publicación",
  "createdAt": "2026-09-22T21:30:00Z"
}
```

Usar esta variante del nodo Code, que soporta múltiples nombres de campo y
filtra textos vacíos:

```javascript
const entradas = $input.all();

return [
  {
    json: {
      schema_version: "1.0.0",
      origen_comunidad: "linkedin",
      periodo_referencia: new Date().toISOString().slice(0, 10),
      interacciones: entradas
        .map((item, index) => {
          const dato = item.json;
          const texto = dato.comment ?? dato.text ?? "";

          return {
            id: dato.id ?? `linkedin-${Date.now()}-${index}`,
            autor: dato.authorName ?? dato.author ?? "Anonimo",
            canal: "linkedin",
            tipo: "sin_clasificar",
            texto,
            metadata_origen: {
              plataforma: "linkedin",
              identificador_original: dato.id ?? null,
              fecha: dato.createdAt ?? new Date().toISOString()
            }
          };
        })
        .filter((interaccion) => interaccion.texto.trim().length > 0)
    }
  }
];
```

## 8. Nodo HTTP Request de n8n — configuración real usada

```text
Method: POST
URL: https://<tu-dominio-dev>.ngrok-free.app/api/webhooks/linkedin
Authentication: None
Send Headers: activado
  Name: X-Webhook-Secret
  Value: <la misma clave configurada en WEBHOOK_SECRET>
Send Body: activado
Body Content Type: JSON
Specify Body: Using JSON
JSON: {{ $json }}
```

Al ejecutar este nodo (`Execute step`) sobre la salida del nodo Code, la
respuesta completa fue capturada con éxito (ver sección 17).

Si n8n y la API corrieran en el mismo equipo sin exposición pública, la URL
de prueba podría ser `http://localhost:8000/api/webhooks/linkedin`. Pero como
se usó **n8n Cloud**, `localhost` en ese contexto apuntaría al servidor de
n8n, no a la máquina local — por eso fue necesario exponer la API con ngrok
(sección 9).

## 9. Exposición pública de la API local con ngrok — implementado

Dado que n8n Cloud corre en servidores externos y la API de CommunityLab
corre en `localhost:8000`, se usó **ngrok** para crear un túnel HTTPS público.

### 9.1 Instalación y autenticación

```powershell
winget install ngrok -s msstore
ngrok config add-authtoken <tu-authtoken-de-ngrok>
```

### 9.2 Dominio dev fijo

La cuenta de ngrok ya contaba con un **dominio dev gratuito y permanente**
(`vocal-sharing-tahr.ngrok-free.app` en esta implementación), visible en
`https://dashboard.ngrok.com/domains`. A diferencia de las URLs aleatorias
que ngrok asigna por defecto en cada sesión, este dominio se mantiene fijo
entre reinicios del túnel, lo cual evita tener que reconfigurar la URL en el
nodo HTTP Request de n8n cada vez.

### 9.3 Levantar el túnel apuntando al dominio fijo

```powershell
ngrok http --url=vocal-sharing-tahr.ngrok-free.app 8000
```

Salida real confirmada:

```text
Session Status                online
Account                        Nelson Enrique Reyes (Plan: Free)
Version                        3.39.9-msix-stable
Region                         United States (us)
Web Interface                  http://127.0.0.1:4040
Forwarding                     https://vocal-sharing-tahr.ngrok-free.app -> http://localhost:8000
```

### 9.4 Verificación del túnel

```powershell
Invoke-RestMethod -Method Get -Uri "https://vocal-sharing-tahr.ngrok-free.app/health"
```

Respuesta real obtenida (idéntica a la de `localhost`, confirmando que el
túnel reenvía correctamente):

```text
status service
------ -------
ok     communitylab-api
```

> Si se usa el plan free de ngrok sin dominio dev reservado, cada reinicio del
> túnel genera una URL nueva y hay que actualizarla en n8n. Reservar y usar un
> dominio dev evita ese problema.

## 10. Configurar LinkedIn (pendiente, no implementado aún)

La vía recomendada sigue siendo:

1. Crear una aplicación en LinkedIn Developers.
2. Configurar `Client ID` y `Client Secret`.
3. Registrar la URL de redirección OAuth que proporciona n8n.
4. Solicitar los productos y permisos necesarios.
5. Crear en n8n una credencial OAuth2 o utilizar una credencial HTTP adecuada.
6. Consultar únicamente endpoints que LinkedIn haya autorizado.
7. Transformar la respuesta al contrato de CommunityLab (sección 7).

```text
Authorization URL: https://www.linkedin.com/oauth/v2/authorization
Access Token URL:   https://www.linkedin.com/oauth/v2/accessToken
Client ID:          el-client-id-de-linkedin
Client Secret:      el-client-secret-de-linkedin
Scope:              los-permisos-aprobados-para-tu-aplicacion
```

No se debe implementar scraping para evadir límites o permisos de LinkedIn.
Mientras esto no esté implementado, el flujo se prueba con payloads
simulados enviados manualmente (como en las secciones 5 y 7), lo cual ya fue
validado exitosamente.

## 11. Despliegue a producción (pendiente)

Para que n8n no dependa de un túnel temporal de ngrok abierto en una laptop,
la API debería publicarse en un entorno permanente, por ejemplo:

- Oracle Cloud Compute Instance.
- Render.
- Railway.
- Una VM con dominio propio.
- Docker detrás de Nginx o Caddy.

La URL de producción resultante sería similar a:

```text
https://api.tudominio.com/api/webhooks/linkedin
```

Usar siempre HTTPS; nunca enviar tokens o secretos por HTTP plano.

## 12. Respuestas y manejo de errores

| Código | Significado |
|---:|---|
| `200` | Lote procesado y paquete generado |
| `401` | `X-Webhook-Secret` ausente o inválido |
| `413` | El lote supera `WEBHOOK_MAX_ITEMS` |
| `422` | JSON inválido o no hay interacciones procesables |
| `500` | Fallo del grafo, LLM u otro componente interno |

En n8n se pueden usar nodos **IF**, **Switch** o **Error Trigger** para
reintentar errores temporales, notificar errores permanentes, guardar la
respuesta en una base de datos, o enviar el paquete a otro workflow. No
implementado todavía en el workflow actual (solo 3 nodos: Webhook, Code,
HTTP Request).

## 13. Duplicados e idempotencia (pendiente)

Para evitar procesar dos veces el mismo evento:

1. Usar un ID estable en `metadata_origen.identificador_original`.
2. Guardar los IDs procesados en n8n Data Store o una base de datos.
3. Consultar el Data Store antes de enviar el lote.
4. Marcar el ID como procesado solo después de recibir una respuesta exitosa.

Para una idempotencia implementada en CommunityLab habría que añadir un
`event_id` o un almacenamiento de eventos procesados. Esa capacidad no existe
actualmente en los modelos del proyecto ni en el workflow de n8n.

## 14. Lotes grandes y tareas largas

El endpoint ejecuta `GRAFO.invoke(...)` antes de responder. Esto es sencillo
y fue suficiente para la demo con 1 interacción, pero el análisis de un lote
grande puede superar el timeout de n8n o del proxy. Para producción, la
evolución recomendada:

```text
POST webhook -> Validar y registrar evento -> Responder 202 Accepted
      -> Cola / worker / tarea en segundo plano -> LangGraph + OCI
```

## 15. Seguridad mínima

Antes de producción:

- Mantener `WEBHOOK_SECRET` fuera del código y del repositorio.
- Comparar el secreto con una comparación segura (ya implementado con `hmac.compare_digest`).
- Exigir HTTPS (cubierto por ngrok/n8n Cloud durante la demo).
- Limitar el tamaño y cantidad de registros (ya implementado con `WEBHOOK_MAX_ITEMS`).
- Configurar rate limiting (pendiente).
- Validar el `Content-Type` (pendiente).
- Evitar logs con tokens, claves o datos privados.
- Rotar el secreto periódicamente.
- Configurar timeouts y reintentos controlados en n8n (pendiente).
- Validar duplicados (pendiente, ver sección 13).
- Usar OAuth oficial de LinkedIn (pendiente, ver sección 10).
- Cambiar `Authentication: None` del nodo Webhook a `Header Auth` antes de un uso más allá de la demo.

## 16. Relación con Streamlit

```text
FastAPI  -> automatización, recepción de datos y ejecución del pipeline
Streamlit -> inspección, edición y aprobación humana
```

El paquete generado por la API se persiste en OCI y después puede cargarse o
consultarse desde el panel de Streamlit para la revisión humana
(`control_revision_humana.estado_decision: "pendiente"` en la respuesta).

## 17. Evidencia de la ejecución end-to-end validada

Fecha de la prueba: 2026-09-23, ~02:28 UTC-6.

Cadena completa ejecutada: **n8n Cloud (Webhook) → Code → HTTP Request → ngrok
→ FastAPI local → LangGraph/Claude → OCI Object Storage → respuesta de vuelta
a n8n**.

Petición disparada manualmente desde PowerShell hacia la URL de test del
Webhook de n8n:

```text
POST https://fren43051.app.n8n.cloud/webhook-test/linkedin-events
```

Respuesta final capturada en el nodo HTTP Request de n8n (`status: 200`,
mostrada con el icono ✓ verde en el canvas):

```json
[
  {
    "status": "procesado",
    "origen_comunidad": "linkedin",
    "periodo_referencia": "2026-09-23",
    "registros_recibidos": 1,
    "registros_rechazados": 0,
    "paquete": {
      "schema_version": "1.2.0",
      "status": "exito",
      "fecha_generacion": "2026-09-23T08:27:07.860802Z",
      "resumen_comunidad": {
        "total_interacciones_procesadas": 1,
        "registros_validos": 1,
        "registros_rechazados": 0,
        "sentimiento_predominante": "Muy Positivo",
        "temas_principales": [
          "LangGraph",
          "Educación técnica",
          "Satisfacción del usuario"
        ],
        "alertas_soporte": []
      },
      "activos_distribucion_generados": {
        "post_linkedin": {
          "titulo": "De la curiosidad al dominio: María López conquista LangGraph 🚀",
          "canal_recomendado": "LinkedIn Oficial",
          "potencial_engagement": "Alto",
          "source_ids": ["linkedin-n8n-001"]
        },
        "destaque_newsletter_semanal": {
          "seccion": "Logro de la Semana",
          "titular": "María López domina LangGraph con nuestra guía",
          "source_ids": ["linkedin-n8n-001"]
        },
        "sugerencia_contenido_faq": null
      },
      "control_revision_humana": {
        "numero_revision": 1,
        "estado_decision": "pendiente",
        "revisor": null,
        "fecha_decision": null,
        "comentarios": null
      },
      "almacenamiento_oci": {
        "bucket": "communitylab-activos-marketing",
        "ruta_objeto": "activos/2026-09-23-2026-09-23/paquete-distribucion.json",
        "status": "guardado_con_exito",
        "comprobacion_lectura": true
      },
      "metadatos_ejecucion": {
        "modelo": "llm-configurado-via-env",
        "latencia_ms": 0
      }
    }
  }
]
```

Puntos que confirma esta ejecución:

- El contenido generado por Claude **no es estático**: el título y cuerpo del
  post de LinkedIn cambiaron respecto a ejecuciones anteriores con el mismo
  comentario de entrada, confirmando generación real en cada llamada.
- `almacenamiento_oci.comprobacion_lectura: true` confirma que, además de
  guardar el archivo en el bucket, se verificó que la lectura posterior fue
  exitosa.
- `control_revision_humana.estado_decision: "pendiente"` confirma que el
  paquete queda esperando aprobación humana antes de publicarse, como diseña
  la arquitectura (sección 16).

## 18. Lista final de implementación (actualizada)

```text
[x] Agregar FastAPI y Uvicorn a requirements.txt
[x] Agregar WEBHOOK_SECRET y WEBHOOK_MAX_ITEMS al entorno
[x] Crear api/__init__.py
[x] Crear api/main.py
[x] Crear api/webhooks.py
[x] Levantar la API con Uvicorn
[x] Probar /health
[x] Probar POST /api/webhooks/linkedin con JSON manual (PowerShell)
[x] Crear el workflow de n8n (n8n Cloud, no Docker local)
[x] Configurar nodo Webhook (Path: linkedin-events, Respond: When Last Node Finishes)
[x] Configurar nodo Code con transformación al contrato LoteInteraccionesCrudo
[x] Instalar y configurar ngrok con dominio dev fijo
[x] Configurar el HTTP Request de n8n apuntando al túnel de ngrok
[x] Configurar X-Webhook-Secret en el header del HTTP Request de n8n
[x] Probar con datos ficticios end-to-end (validado con éxito)
[ ] Configurar OAuth o el proveedor autorizado de LinkedIn
[ ] Publicar la API en un entorno permanente (no depender de ngrok + laptop)
[ ] Añadir deduplicación y observabilidad
[ ] Cambiar Authentication del Webhook de "None" a "Header Auth"
[ ] Añadir nodos IF/Switch/Error Trigger para manejo de errores en n8n
[ ] Revisar permisos, privacidad y términos de LinkedIn
[ ] Publicar (Activate) el workflow para obtener la URL de producción estable
```

La integración no requirió cambiar el pipeline de LangGraph existente: la
API HTTP solo actúa como una entrada nueva que reutiliza los modelos,
validadores, grafo y almacenamiento que ya existían en el proyecto.
