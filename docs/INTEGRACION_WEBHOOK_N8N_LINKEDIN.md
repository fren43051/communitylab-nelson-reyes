# Integración de CommunityLab con Webhooks, n8n y LinkedIn

Este documento describe cómo conectar CommunityLab con n8n para recibir datos de
LinkedIn (o de un proveedor autorizado), transformarlos al formato del proyecto,
procesarlos con LangGraph y almacenar el resultado en OCI Object Storage.

> **Estado actual:** esta guía es de implementación. Leerla no modifica el
> proyecto. Actualmente CommunityLab recibe archivos JSON desde Streamlit; no
> incluye todavía una API HTTP ni un endpoint webhook.

## 1. Arquitectura propuesta

```text
LinkedIn API oficial o proveedor autorizado
                    |
                    v
             n8n (OAuth / HTTP)
                    |
                    v
        POST /api/webhooks/linkedin
                    |
                    v
        API HTTP de CommunityLab
                    |
                    v
      Pydantic + validacion de ingesta
                    |
                    v
              LangGraph + LLM
                    |
                    v
       OCI Object Storage + respuesta JSON
                    |
                    v
       Streamlit para curaduria humana
```

La responsabilidad de cada componente sería:

| Componente | Responsabilidad |
|---|---|
| LinkedIn | Fuente de datos, únicamente mediante APIs y permisos autorizados |
| n8n | OAuth, consulta o recepción de eventos, transformación y reintentos |
| API de CommunityLab | Autenticación del webhook, validación y ejecución del grafo |
| LangGraph | Análisis, clasificación y generación de activos |
| OCI | Persistencia del paquete generado |
| Streamlit | Revisión, edición, aprobación o rechazo humano |

## 2. Contrato de datos que ya utiliza CommunityLab

El endpoint debe recibir un lote compatible con `LoteInteraccionesCrudo`.
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

## 3. Cambios que habría que realizar en el proyecto

Estos son los cambios de referencia. **No se aplican automáticamente al leer
este documento.**

### 3.1 Dependencias

Agregar a `requirements.txt`:

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
```

Instalar después:

```powershell
pip install -r requirements.txt
```

### 3.2 Variables de entorno

Agregar a `.env.example`:

```env
# --- Webhooks ---
WEBHOOK_SECRET=cambia-esta-clave-por-una-segura
WEBHOOK_MAX_ITEMS=100
```

En el `.env` local usar una clave real, larga y privada:

```env
WEBHOOK_SECRET=una-clave-larga-y-privada
WEBHOOK_MAX_ITEMS=100
```

El archivo `.env` ya está excluido por `.gitignore` y no debe subirse al
repositorio.

### 3.3 Estructura nueva

Crear:

```text
api/
├── __init__.py
├── main.py
└── webhooks.py
```

No sería necesario modificar inicialmente los módulos existentes de ingesta,
grafo, almacenamiento u Streamlit porque el endpoint reutilizaría esas piezas.

## 4. API HTTP de referencia

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

Puede permanecer vacío:

```python
```

## 5. Ejecutar y probar la API

Desde la raíz del proyecto:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Comprobar el servicio:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8000/health"
```

La documentación interactiva de FastAPI estaría en:

```text
http://localhost:8000/docs
```

El endpoint de negocio sería:

```text
http://localhost:8000/api/webhooks/linkedin
```

### Prueba directa con PowerShell

```powershell
$body = @{
    schema_version = "1.0.0"
    origen_comunidad = "linkedin"
    periodo_referencia = "2026-09-22"
    interacciones = @(
        @{
            id = "test-001"
            autor = "Usuario de prueba"
            canal = "linkedin"
            tipo = "feedback"
            texto = "Este contenido fue muy útil."
            metadata_origen = @{
                plataforma = "linkedin"
                identificador_original = "test-001"
                fecha = "2026-09-22T22:00:00Z"
            }
        }
    )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/webhooks/linkedin" `
  -Headers @{
      "X-Webhook-Secret" = "una-clave-larga-y-privada"
  } `
  -ContentType "application/json" `
  -Body $body
```

## 6. Webhook de n8n y configuración del flujo

El webhook es el punto de entrada que recibe los datos externos y los entrega
al flujo de transformación de n8n.

Hay dos formas de iniciar el flujo:

### Opción A: consulta periódica

Útil cuando la API de LinkedIn no ofrece el evento que necesitas:

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

### Opción B: recepción de eventos

Útil si LinkedIn o un proveedor autorizado puede llamar un webhook:

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
Respond to Webhook
```

### Nodo Webhook de n8n

Configuración sugerida:

```text
HTTP Method: POST
Path: linkedin-events
Response Mode: Using Respond to Webhook node
Authentication: Header Auth o una credencial equivalente
```

n8n generará URLs parecidas a:

```text
https://n8n.tudominio.com/webhook-test/linkedin-events
https://n8n.tudominio.com/webhook/linkedin-events
```

La URL `webhook-test` se utiliza durante pruebas. La URL `webhook` se usa
cuando el workflow está activo.

El webhook de n8n no concede permisos de LinkedIn por sí mismo: solamente
recibe una petición HTTP.

## 7. Transformar datos en un nodo Code de n8n

Suponiendo que el nodo anterior devuelve elementos como:

```json
{
  "id": "urn:li:comment:123456",
  "authorName": "María López",
  "comment": "Excelente publicación",
  "createdAt": "2026-09-22T21:30:00Z"
}
```

El nodo **Code** de n8n puede devolver el contrato de CommunityLab:

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

El filtro evita enviar textos vacíos al análisis estricto.

## 8. Nodo HTTP Request de n8n

Configurar un nodo **HTTP Request**:

```text
Method: POST
URL: https://tu-dominio.com/api/webhooks/linkedin
Send Body: Yes
Body Content Type: JSON
```

Headers:

```text
Content-Type: application/json
X-Webhook-Secret: una-clave-larga-y-privada
```

Como cuerpo JSON se puede utilizar la expresión:

```javascript
{{ $json }}
```

Si n8n y la API corren en el mismo equipo, la URL de prueba puede ser:

```text
http://localhost:8000/api/webhooks/linkedin
```

Si n8n corre en la nube, `localhost` apunta al servidor de n8n, no a la
computadora local. En ese caso CommunityLab necesita una URL pública HTTPS.

## 9. Configurar LinkedIn

La vía recomendada es:

1. Crear una aplicación en LinkedIn Developers.
2. Configurar `Client ID` y `Client Secret`.
3. Registrar la URL de redirección OAuth que proporciona n8n.
4. Solicitar los productos y permisos necesarios.
5. Crear en n8n una credencial OAuth2 o utilizar una credencial HTTP adecuada.
6. Consultar únicamente endpoints que LinkedIn haya autorizado.
7. Transformar la respuesta al contrato de CommunityLab.

La configuración conceptual OAuth2 es:

```text
Authorization URL:
https://www.linkedin.com/oauth/v2/authorization

Access Token URL:
https://www.linkedin.com/oauth/v2/accessToken

Client ID:
el-client-id-de-linkedin

Client Secret:
el-client-secret-de-linkedin

Scope:
los-permisos-aprobados-para-tu-aplicacion
```

Los scopes y endpoints disponibles dependen del producto y de la aprobación
de la aplicación. OAuth no implica acceso general a perfiles, publicaciones,
comentarios o analíticas.

No se debe implementar scraping para evadir límites o permisos de LinkedIn.
Además del riesgo de bloqueo, puede incumplir los términos de la plataforma.
Si la API oficial no cubre el caso, se debe evaluar un proveedor autorizado y
sus condiciones de uso.

## 10. Exposición pública de la API

Para desarrollo local se puede usar:

```text
http://localhost:8000
```

Para n8n alojado fuera de la computadora se necesita publicar la API mediante,
por ejemplo:

- Oracle Cloud Compute.
- Render.
- Railway.
- Una VM con dominio.
- Docker detrás de Nginx o Caddy.
- Un túnel temporal como ngrok o Cloudflare Tunnel.

La URL de producción debería ser similar a:

```text
https://api.tudominio.com/api/webhooks/linkedin
```

Usar HTTPS, nunca enviar tokens o secretos por HTTP plano.

## 11. Respuestas y manejo de errores

| Código | Significado |
|---:|---|
| `200` | Lote procesado y paquete generado |
| `401` | `X-Webhook-Secret` ausente o inválido |
| `413` | El lote supera `WEBHOOK_MAX_ITEMS` |
| `422` | JSON inválido o no hay interacciones procesables |
| `500` | Fallo del grafo, LLM u otro componente interno |

Una respuesta exitosa tendría esta forma:

```json
{
  "status": "procesado",
  "origen_comunidad": "linkedin",
  "periodo_referencia": "2026-09-22",
  "registros_recibidos": 1,
  "registros_rechazados": 0,
  "paquete": {
    "schema_version": "1.2.0",
    "status": "exito"
  }
}
```

En n8n se pueden usar nodos **IF**, **Switch** o **Error Trigger** para:

- Reintentar errores temporales.
- Notificar errores permanentes.
- Guardar la respuesta en una base de datos.
- Enviar el paquete a otro workflow.

## 12. Duplicados e idempotencia

LinkedIn, n8n o un proveedor externo pueden reenviar un evento. Para evitar
procesarlo dos veces, se recomienda:

1. Usar un ID estable en `metadata_origen.identificador_original`.
2. Guardar los IDs procesados en n8n Data Store o una base de datos.
3. Consultar el Data Store antes de enviar el lote.
4. Marcar el ID como procesado solo después de recibir una respuesta exitosa.

Para una idempotencia implementada en CommunityLab habría que añadir un
`event_id` o un almacenamiento de eventos procesados. Esa capacidad no existe
actualmente en los modelos del proyecto.

## 13. Lotes grandes y tareas largas

El ejemplo ejecuta `GRAFO.invoke(...)` antes de responder. Esto es sencillo,
pero el análisis de un lote grande puede superar el timeout de n8n o del proxy.

Para producción, la evolución recomendada es:

```text
POST webhook
      |
      v
Validar y registrar evento
      |
      v
Responder 202 Accepted
      |
      v
Cola / worker / tarea en segundo plano
      |
      v
LangGraph + OCI
```

Luego n8n puede consultar un endpoint de estado o recibir una notificación al
terminar. No conviene ocultar un procesamiento largo detrás de una respuesta
`200` si el cliente puede agotarse esperando.

## 14. Seguridad mínima

Antes de producción:

- Mantener `WEBHOOK_SECRET` fuera del código y del repositorio.
- Comparar el secreto con una comparación segura.
- Exigir HTTPS.
- Limitar el tamaño y cantidad de registros.
- Configurar rate limiting.
- Validar el `Content-Type`.
- Evitar logs con tokens, claves o datos privados.
- Rotar el secreto periódicamente.
- Configurar timeouts y reintentos controlados en n8n.
- Validar duplicados.
- Usar OAuth oficial de LinkedIn.
- Revisar retención y privacidad de los datos recibidos.

## 15. Relación con Streamlit

No se recomienda convertir `app/streamlit_app.py` en un endpoint webhook.
La separación más clara es:

```text
FastAPI  -> automatización, recepción de datos y ejecución del pipeline
Streamlit -> inspección, edición y aprobación humana
```

El paquete generado por la API puede persistirse en OCI y después cargarse o
consultarse desde el panel de Streamlit.

## 16. Lista final de implementación

```text
[ ] Agregar FastAPI y Uvicorn a requirements.txt
[ ] Agregar WEBHOOK_SECRET y WEBHOOK_MAX_ITEMS al entorno
[ ] Crear api/__init__.py
[ ] Crear api/main.py
[ ] Crear api/webhooks.py
[ ] Levantar la API con Uvicorn
[ ] Probar /health
[ ] Probar POST /api/webhooks/linkedin con JSON manual
[ ] Crear el workflow de n8n
[ ] Configurar OAuth o el proveedor autorizado de LinkedIn
[ ] Transformar los datos al contrato de CommunityLab
[ ] Configurar X-Webhook-Secret en n8n
[ ] Configurar el HTTP Request de n8n
[ ] Probar primero con datos ficticios
[ ] Publicar la API con HTTPS
[ ] Añadir deduplicación y observabilidad
[ ] Revisar permisos, privacidad y términos de LinkedIn
```

La integración no requiere cambiar inicialmente el pipeline de LangGraph:
la nueva API solo actúa como una entrada HTTP que reutiliza los modelos,
validadores, grafo y almacenamiento que ya existen.
