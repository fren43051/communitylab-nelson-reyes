"""
Resolucion centralizada de secretos del proyecto.

Todo modulo que necesite una credencial debe llamar a `obtener_secreto()` en
lugar de leer `os.getenv()` directamente. Ese unico punto de entrada es lo que
permite cambiar de backend (entorno local u OCI Vault) sin tocar el pipeline, y
lo que hara que la mudanza a una Compute Instance no requiera reescribir nada.

Backends:
    SECRETS_BACKEND=env        -> valores del entorno / archivo .env (desarrollo y pruebas)
    SECRETS_BACKEND=oci-vault  -> OCI Vault (Secret Management), con cache en memoria

Las variables de configuracion (region, bucket, namespace, modelos) NO son
secretos y siguen leyendose del entorno.
"""
import base64
import os
import threading
import time

from dotenv import load_dotenv

from src.config.oci_auth import construir_cliente

load_dotenv()

BACKEND_ENV = "env"
BACKEND_OCI_VAULT = "oci-vault"

_BACKENDS_VALIDOS = (BACKEND_ENV, BACKEND_OCI_VAULT)

# Mapa variable de entorno -> nombre del secreto en OCI Vault.
# Solo lo que esta aqui vive en Vault; el resto se lee del entorno.
SECRETS_EN_VAULT = {
    "ANTHROPIC_API_KEY": "communitylab-anthropic-api-key",
    "OPENAI_API_KEY": "communitylab-openai-api-key",
    "GOOGLE_API_KEY": "communitylab-google-api-key",
    "WEBHOOK_SECRET": "communitylab-webhook-secret",
    "OCI_CONFIG": "communitylab-oci-config",
    "OCI_PRIVATE_KEY": "communitylab-oci-private-key",
    "DB_USER": "communitylab-db-user",
    "DB_PASSWORD": "communitylab-db-password",
    "DB_NAME": "communitylab-db-name",
    "DB_CONNECT_STRING": "communitylab-db-connect-string",
}

DEFAULT_CACHE_TTL_SEGUNDOS = 300.0

_cache: dict[str, tuple[float, str]] = {}
_bloqueo = threading.Lock()


class SecretoNoDisponibleError(RuntimeError):
    """El secreto exigido no pudo resolverse con el backend activo."""


def backend_activo() -> str:
    """Backend de secretos declarado en el entorno; por defecto 'env'."""
    backend = (os.getenv("SECRETS_BACKEND") or BACKEND_ENV).strip().lower()

    if backend not in _BACKENDS_VALIDOS:
        raise ValueError(
            f"SECRETS_BACKEND no soportado: {backend!r}. Usa {BACKEND_ENV!r} o {BACKEND_OCI_VAULT!r}."
        )
    return backend


def ttl_cache_segundos() -> float:
    """Segundos de validez de la cache; 0 desactiva la cache."""
    crudo = (os.getenv("SECRETS_CACHE_TTL") or "").strip()
    if not crudo:
        return DEFAULT_CACHE_TTL_SEGUNDOS
    try:
        return max(0.0, float(crudo))
    except ValueError:
        return DEFAULT_CACHE_TTL_SEGUNDOS


def limpiar_cache() -> None:
    """Vacia la cache de secretos (usada al rotar un valor y por las pruebas)."""
    with _bloqueo:
        _cache.clear()


def obtener_vault_id() -> str:
    """OCID del vault del proyecto. No es un secreto, pero es obligatorio en modo Vault."""
    vault_id = (os.getenv("OCI_VAULT_ID") or "").strip()
    if not vault_id:
        raise SecretoNoDisponibleError(
            "SECRETS_BACKEND=oci-vault requiere OCI_VAULT_ID con el OCID del vault. "
            "Ejecuta scripts/oci_vault_setup.py o cambia a SECRETS_BACKEND=env."
        )
    return vault_id


def _leer_desde_vault(nombre: str) -> str:
    """Descarga el bundle del secreto y lo decodifica desde base64."""
    from oci.secrets import SecretsClient

    vault_id = obtener_vault_id()
    cliente = construir_cliente(SecretsClient)
    respuesta = cliente.get_secret_bundle_by_name(SECRETS_EN_VAULT[nombre], vault_id)
    contenido = respuesta.data.secret_bundle_content

    if getattr(contenido, "content_type", "BASE64") != "BASE64":
        raise SecretoNoDisponibleError(
            f"El secreto {SECRETS_EN_VAULT[nombre]!r} no tiene contenido BASE64; "
            f"content_type={getattr(contenido, 'content_type', None)!r}"
        )

    return base64.b64decode(contenido.content).decode("utf-8")


def _leer_con_cache(nombre: str) -> str:
    """Lee desde Vault reutilizando el valor mientras no venza el TTL."""
    ttl = ttl_cache_segundos()
    ahora = time.monotonic()

    if ttl > 0:
        with _bloqueo:
            entrada = _cache.get(nombre)
            if entrada and entrada[0] > ahora:
                return entrada[1]

    valor = _leer_desde_vault(nombre)

    if ttl > 0:
        with _bloqueo:
            _cache[nombre] = (ahora + ttl, valor)
    return valor


def obtener_secreto(nombre: str) -> str | None:
    """
    Devuelve el valor del secreto segun el backend activo, o None si no existe.

    En modo Vault, las variables que no estan mapeadas en SECRETS_EN_VAULT se
    leen del entorno: solo lo que de verdad se aprovisiono en Vault pasa por la
    red. Un 404 de Vault se traduce en None (secreto no aprovisionado, por
    ejemplo un proveedor LLM que no se usa), mientras que cualquier otro fallo
    --red, permisos, OCI_VAULT_ID ausente-- lanza SecretoNoDisponibleError en
    lugar de degradar en silencio a un valor en claro del entorno.
    """
    if backend_activo() == BACKEND_ENV or nombre not in SECRETS_EN_VAULT:
        valor = os.getenv(nombre)
        return valor or None

    try:
        return _leer_con_cache(nombre) or None
    except SecretoNoDisponibleError:
        raise
    except Exception as error:
        if getattr(error, "status", None) == 404:
            return None
        raise SecretoNoDisponibleError(
            f"No se pudo leer {SECRETS_EN_VAULT[nombre]!r} desde OCI Vault "
            f"({type(error).__name__}). Revisa OCI_VAULT_ID, OCI_REGION y los permisos "
            f"de lectura de secret-bundles."
        ) from error


def requerir_secreto(nombre: str, pista: str) -> str:
    """Como `obtener_secreto` pero falla con un mensaje accionable si falta."""
    valor = obtener_secreto(nombre)
    if not valor:
        raise SecretoNoDisponibleError(f"{nombre} no esta configurado. {pista}")
    return valor
