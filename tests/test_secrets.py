"""
Pruebas del gestor de secretos (src/config/secrets.py) y de la autenticacion OCI
(src/config/oci_auth.py), mas la comprobacion de que los consumidores del
proyecto pasan efectivamente por ese punto unico.

Todas son offline: el cliente de Secrets se sustituye por un doble, de modo que
la suite no depende de OCI Vault ni de ninguna credencial real.
"""
import base64

import pytest
from fastapi import HTTPException

from src.config import secrets as gestor
from src.config.oci_auth import (
    AUTH_API_KEY,
    AUTH_INSTANCE_PRINCIPAL,
    AUTH_RESOURCE_PRINCIPAL,
    modo_autenticacion,
    obtener_config,
    obtener_region,
)
from src.config.secrets import (
    BACKEND_ENV,
    BACKEND_OCI_VAULT,
    SECRETS_EN_VAULT,
    SecretoNoDisponibleError,
    backend_activo,
    obtener_secreto,
    requerir_secreto,
    ttl_cache_segundos,
)

OCID_VAULT_FALSO = "ocid1.vault.oc1.phx.falso.solo-para-pruebas"


class _Contenido:
    def __init__(self, valor: str, content_type: str = "BASE64"):
        self.content = base64.b64encode(valor.encode("utf-8")).decode("ascii")
        self.content_type = content_type


class _Bundle:
    def __init__(self, valor: str, content_type: str = "BASE64"):
        self.secret_bundle_content = _Contenido(valor, content_type)


class _Respuesta:
    def __init__(self, valor: str, content_type: str = "BASE64"):
        self.data = _Bundle(valor, content_type)


class FakeSecretsClient:
    """Doble de SecretsClient que registra las llamadas para poder afirmar sobre la cache."""

    def __init__(self, valores: dict[str, str] | None = None, falla: Exception | None = None):
        self.valores = valores or {}
        self.falla = falla
        self.llamadas: list[tuple[str, str]] = []

    def get_secret_bundle_by_name(self, secret_name, vault_id, **kwargs):
        self.llamadas.append((secret_name, vault_id))
        if self.falla:
            raise self.falla
        if secret_name not in self.valores:
            raise LookupError(f"secreto inexistente: {secret_name}")
        return _Respuesta(self.valores[secret_name])


@pytest.fixture
def vault(monkeypatch):
    """Activa el backend de Vault con un cliente doble inyectado."""
    def activar(valores: dict[str, str] | None = None, falla: Exception | None = None, ttl: str = "300"):
        cliente = FakeSecretsClient(valores, falla)
        monkeypatch.setenv("SECRETS_BACKEND", BACKEND_OCI_VAULT)
        monkeypatch.setenv("OCI_VAULT_ID", OCID_VAULT_FALSO)
        monkeypatch.setenv("SECRETS_CACHE_TTL", ttl)
        monkeypatch.setattr(gestor, "construir_cliente", lambda clase, **kwargs: cliente)
        return cliente
    return activar


# =====================================================================
# 1. BACKENDS Y CONFIGURACION
# =====================================================================

def test_backend_por_defecto_es_entorno(monkeypatch):
    """Sin SECRETS_BACKEND declarado el proyecto lee del entorno (clon limpio, pruebas)."""
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    assert backend_activo() == BACKEND_ENV


def test_backend_invalido_falla_de_forma_explicita(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "hashicorp")
    with pytest.raises(ValueError, match="SECRETS_BACKEND no soportado"):
        backend_activo()


def test_ttl_por_defecto_y_personalizado(monkeypatch):
    monkeypatch.delenv("SECRETS_CACHE_TTL", raising=False)
    assert ttl_cache_segundos() == gestor.DEFAULT_CACHE_TTL_SEGUNDOS

    monkeypatch.setenv("SECRETS_CACHE_TTL", "45")
    assert ttl_cache_segundos() == 45.0

    monkeypatch.setenv("SECRETS_CACHE_TTL", "no-es-numero")
    assert ttl_cache_segundos() == gestor.DEFAULT_CACHE_TTL_SEGUNDOS


# =====================================================================
# 2. LECTURA DESDE OCI VAULT
# =====================================================================

def test_lectura_desde_vault_decodifica_base64(vault, monkeypatch):
    """El valor llega codificado en base64 y debe devolverse decodificado."""
    vault({"communitylab-webhook-secret": "valor-real-del-vault"})
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    assert obtener_secreto("WEBHOOK_SECRET") == "valor-real-del-vault"


def test_cache_evita_llamadas_repetidas_al_vault(vault, monkeypatch):
    """get_llm() corre por cada nodo del grafo: sin cache seria una peticion a Vault por nodo."""
    cliente = vault({"communitylab-anthropic-api-key": "sk-ant-falsa"}, ttl="300")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert obtener_secreto("ANTHROPIC_API_KEY") == "sk-ant-falsa"
    assert obtener_secreto("ANTHROPIC_API_KEY") == "sk-ant-falsa"
    assert len(cliente.llamadas) == 1
    assert cliente.llamadas[0] == ("communitylab-anthropic-api-key", OCID_VAULT_FALSO)


def test_ttl_cero_desactiva_la_cache(vault, monkeypatch):
    cliente = vault({"communitylab-anthropic-api-key": "sk-ant-falsa"}, ttl="0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    obtener_secreto("ANTHROPIC_API_KEY")
    obtener_secreto("ANTHROPIC_API_KEY")
    assert len(cliente.llamadas) == 2


def test_limpiar_cache_fuerza_nueva_lectura(vault, monkeypatch):
    """Al rotar un secreto en Vault, limpiar_cache() debe hacer visible el valor nuevo."""
    cliente = vault({"communitylab-webhook-secret": "version-1"}, ttl="300")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    assert obtener_secreto("WEBHOOK_SECRET") == "version-1"
    cliente.valores["communitylab-webhook-secret"] = "version-2"
    assert obtener_secreto("WEBHOOK_SECRET") == "version-1"

    gestor.limpiar_cache()
    assert obtener_secreto("WEBHOOK_SECRET") == "version-2"


def test_falta_vault_id_da_error_accionable(vault):
    """OCI_VAULT_ID es obligatorio en modo Vault; el error debe decir como arreglarlo."""
    import os

    vault({"communitylab-webhook-secret": "irrelevante"})
    os.environ.pop("OCI_VAULT_ID", None)

    with pytest.raises(SecretoNoDisponibleError, match="OCI_VAULT_ID"):
        obtener_secreto("WEBHOOK_SECRET")


def test_fallo_de_vault_no_degrada_a_texto_plano(vault, monkeypatch):
    """
    Propiedad de seguridad clave: si Vault falla, el resolver NO debe devolver en
    silencio un valor en claro del entorno. Debe fallar de forma ruidosa.
    """
    vault(falla=RuntimeError("sin ruta a Vault"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "valor-en-claro-que-no-debe-usarse")

    with pytest.raises(SecretoNoDisponibleError, match="No se pudo leer"):
        obtener_secreto("ANTHROPIC_API_KEY")


def test_secreto_inexistente_en_vault_no_reintenta_en_entorno(vault, monkeypatch):
    vault({})
    monkeypatch.setenv("WEBHOOK_SECRET", "valor-en-claro-que-no-debe-usarse")

    with pytest.raises(SecretoNoDisponibleError):
        obtener_secreto("WEBHOOK_SECRET")


def test_secreto_no_aprovisionado_devuelve_none(vault, monkeypatch):
    """
    Un proveedor LLM que no se usa no existe en Vault (404). Debe devolverse None
    para que get_llm() lance su ValueError habitual en lugar de romper el arranque.
    """
    class Error404(Exception):
        status = 404

    vault(falla=Error404("NotAuthorizedOrNotFound"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert obtener_secreto("OPENAI_API_KEY") is None


def test_contenido_no_base64_se_rechaza(vault, monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", BACKEND_OCI_VAULT)
    monkeypatch.setenv("OCI_VAULT_ID", OCID_VAULT_FALSO)
    monkeypatch.setattr(
        gestor,
        "construir_cliente",
        lambda clase, **kwargs: type("C", (), {
            "get_secret_bundle_by_name": lambda self, nombre, vault_id, **kw: type(
                "R", (), {"data": type("D", (), {"secret_bundle_content": _Contenido("x", "SMELL")})()}
            )
        })(),
    )

    with pytest.raises(SecretoNoDisponibleError, match="BASE64"):
        obtener_secreto("WEBHOOK_SECRET")


def test_variable_no_gestionada_por_vault_se_lee_del_entorno(vault, monkeypatch):
    """La configuracion (modelos, bucket, limites) no es secreto y no viaja por Vault."""
    cliente = vault({})
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    assert obtener_secreto("LLM_PROVIDER") == "anthropic"
    assert cliente.llamadas == []


# =====================================================================
# 3. requerir_secreto
# =====================================================================

def test_requerir_secreto_devuelve_valor(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "valor-presente")
    assert requerir_secreto("WEBHOOK_SECRET", "Definela en Vault.") == "valor-presente"


def test_requerir_secreto_incluye_la_pista(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SecretoNoDisponibleError, match="Cargala en OCI Vault"):
        requerir_secreto("ANTHROPIC_API_KEY", "Cargala en OCI Vault con scripts/oci_vault_setup.py")


# =====================================================================
# 4. AUTENTICACION OCI (local vs Compute Instance)
# =====================================================================

def test_modo_auto_elige_api_key_cuando_existe_config(monkeypatch, tmp_path):
    archivo = tmp_path / "config"
    archivo.write_text("[DEFAULT]\nregion=us-phoenix-1\n", encoding="utf-8")
    monkeypatch.setenv("OCI_CONFIG_FILE", str(archivo))
    monkeypatch.delenv("OCI_AUTH", raising=False)

    assert modo_autenticacion() == AUTH_API_KEY


def test_modo_auto_elige_instance_principal_sin_config(monkeypatch, tmp_path):
    """Es el camino que se activara solo al mudar el proyecto a la Compute Instance."""
    monkeypatch.setenv("OCI_CONFIG_FILE", str(tmp_path / "no-existe"))
    monkeypatch.delenv("OCI_AUTH", raising=False)

    assert modo_autenticacion() == AUTH_INSTANCE_PRINCIPAL


@pytest.mark.parametrize(
    "declarado,esperado",
    [
        ("api_key", AUTH_API_KEY),
        ("instance_principal", AUTH_INSTANCE_PRINCIPAL),
        ("resource_principal", AUTH_RESOURCE_PRINCIPAL),
        ("INSTANCE_PRINCIPAL", AUTH_INSTANCE_PRINCIPAL),
    ],
)
def test_modo_explicito(monkeypatch, declarado, esperado):
    monkeypatch.setenv("OCI_AUTH", declarado)
    assert modo_autenticacion() == esperado


def test_modo_invalido_falla(monkeypatch):
    monkeypatch.setenv("OCI_AUTH", "magia")
    with pytest.raises(ValueError, match="OCI_AUTH no soportado"):
        modo_autenticacion()


def test_instance_principal_no_lee_ningun_archivo(monkeypatch):
    """Con instance principal la config queda vacia: no hay PEM ni perfil en disco."""
    monkeypatch.setenv("OCI_AUTH", "instance_principal")
    assert obtener_config() == {}


def test_region_se_toma_del_entorno(monkeypatch):
    monkeypatch.setenv("OCI_REGION", "us-phoenix-1")
    assert obtener_region() == "us-phoenix-1"

    monkeypatch.setenv("OCI_REGION", "   ")
    assert obtener_region() is None


# =====================================================================
# 5. LOS CONSUMIDORES PASAN POR EL RESOLVER
# =====================================================================

def test_webhook_autoriza_con_el_secreto_del_resolver(monkeypatch):
    """El endpoint no lee os.getenv directamente: usa obtener_secreto."""
    import api.webhooks as webhooks

    monkeypatch.setattr(webhooks, "obtener_secreto", lambda nombre: "valor-del-vault")

    webhooks.validar_secreto_webhook("valor-del-vault")

    with pytest.raises(HTTPException) as error:
        webhooks.validar_secreto_webhook("valor-equivocado")
    assert error.value.status_code == 401


def test_webhook_sin_secreto_configurado_falla(monkeypatch):
    import api.webhooks as webhooks

    monkeypatch.setattr(webhooks, "obtener_secreto", lambda nombre: None)

    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET no esta configurado"):
        webhooks.validar_secreto_webhook("cualquier-cosa")


def test_llm_provider_exige_la_clave_resuelta(monkeypatch):
    """Si el resolver no devuelve clave, get_llm falla antes de instanciar el proveedor."""
    from src.graph import llm_provider

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_provider, "obtener_secreto", lambda nombre: None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY no configurada"):
        llm_provider.get_llm()


def test_llm_provider_usa_la_clave_del_resolver(monkeypatch):
    from src.graph import llm_provider

    capturadas = {}

    class ChatAnthropicFalso:
        def __init__(self, **kwargs):
            capturadas.update(kwargs)

    import sys
    import types

    modulo = types.ModuleType("langchain_anthropic")
    modulo.ChatAnthropic = ChatAnthropicFalso
    monkeypatch.setitem(sys.modules, "langchain_anthropic", modulo)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(llm_provider, "obtener_secreto", lambda nombre: "clave-desde-vault")

    llm_provider.get_llm()

    assert capturadas["api_key"] == "clave-desde-vault"


def test_todas_las_api_keys_de_proveedor_estan_mapeadas():
    """Si se agrega un proveedor LLM, su clave debe quedar bajo gestion de Vault."""
    assert {"GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "WEBHOOK_SECRET"} <= set(SECRETS_EN_VAULT)
    assert all(nombre.startswith("communitylab-") for nombre in SECRETS_EN_VAULT.values())
