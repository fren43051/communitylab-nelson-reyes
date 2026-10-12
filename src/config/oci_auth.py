"""
Autenticacion OCI compartida por todo el proyecto.

Soporta tres modos para que el mismo codigo funcione sin cambios en el
portatil (API key + PEM) y en una Compute Instance (instance principal, sin
ninguna clave privada en disco):

    OCI_AUTH=auto                 -> api_key si existe el archivo de config, si no instance_principal
    OCI_AUTH=api_key              -> fuerza ~/.oci/config + PEM (desarrollo local)
    OCI_AUTH=instance_principal   -> fuerza el signer de Compute Instance (produccion)
    OCI_AUTH=resource_principal   -> fuerza el signer de recurso (Functions / OKE)

Con instance_principal y resource_principal no se lee ningun archivo de
credenciales: la identidad la aporta la propia plataforma de OCI y los permisos
se acotan con un dynamic group y una politica IAM.
"""
import os

from dotenv import load_dotenv

load_dotenv()

AUTH_API_KEY = "api_key"
AUTH_INSTANCE_PRINCIPAL = "instance_principal"
AUTH_RESOURCE_PRINCIPAL = "resource_principal"

_MODOS_VALIDOS = (AUTH_API_KEY, AUTH_INSTANCE_PRINCIPAL, AUTH_RESOURCE_PRINCIPAL)


def obtener_ruta_config() -> str:
    """Ruta expandida del archivo de config OCI declarado en el entorno."""
    return os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config"))


def obtener_region() -> str | None:
    """Region efectiva; None deja que el SDK la derive del archivo de config."""
    region = (os.getenv("OCI_REGION") or "").strip()
    return region or None


def modo_autenticacion() -> str:
    """Resuelve el modo de autenticacion efectivo (nunca devuelve 'auto')."""
    modo = (os.getenv("OCI_AUTH") or "auto").strip().lower()

    if modo == "auto":
        return AUTH_API_KEY if os.path.exists(obtener_ruta_config()) else AUTH_INSTANCE_PRINCIPAL

    if modo not in _MODOS_VALIDOS:
        raise ValueError(
            f"OCI_AUTH no soportado: {modo!r}. Usa 'auto', {_MODOS_VALIDOS[0]!r}, "
            f"{_MODOS_VALIDOS[1]!r} o {_MODOS_VALIDOS[2]!r}."
        )
    return modo


def obtener_config() -> dict:
    """
    Diccionario de configuracion para los clientes OCI.

    En modo api_key devuelve el perfil validado del archivo de config; en los
    modos de principal devuelve un diccionario vacio porque el signer ya porta
    la identidad y la region se fija con set_region().
    """
    if modo_autenticacion() != AUTH_API_KEY:
        return {}

    import oci.config

    config = oci.config.from_file(
        file_location=obtener_ruta_config(),
        profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
    )
    oci.config.validate_config(config)

    region = obtener_region()
    if region:
        config = {**config, "region": region}
    return config


def obtener_signer():
    """Signer de federacion para instance/resource principal; None en modo api_key."""
    modo = modo_autenticacion()

    if modo == AUTH_INSTANCE_PRINCIPAL:
        from oci.auth.signers import InstancePrincipalsSecurityTokenSigner

        return InstancePrincipalsSecurityTokenSigner.get_signer()

    if modo == AUTH_RESOURCE_PRINCIPAL:
        from oci.auth.signers import ResourcePrincipalsFederationSigner

        return ResourcePrincipalsFederationSigner.get_resource_principals_signer()

    return None


def construir_cliente(clase_cliente, **kwargs):
    """
    Instancia cualquier cliente del SDK OCI con el modo de autenticacion activo.

    Centralizar aqui la construccion evita que cada modulo decida como
    autenticarse, que es lo que permitiria que la migracion a Compute dejara
    algun cliente leyendo el PEM por accidente.
    """
    import oci.retry

    config = obtener_config()
    signer = obtener_signer()
    kwargs.setdefault("retry_strategy", oci.retry.DEFAULT_RETRY_STRATEGY)

    if signer is not None:
        cliente = clase_cliente(config, signer=signer, **kwargs)
    else:
        cliente = clase_cliente(config, **kwargs)

    # Los clientes no regionales (KMS) reciben su endpoint de forma explicita y
    # rechazan set_region, asi que solo se fija la region donde tiene sentido.
    region = obtener_region()
    if region and getattr(cliente.base_client, "regional_client", False):
        cliente.base_client.set_region(region)
    return cliente
