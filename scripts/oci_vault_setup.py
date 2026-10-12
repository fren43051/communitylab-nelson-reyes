"""
Aprovisiona OCI Vault para CommunityLab y migra los secretos del .env local.

Es idempotente: si el vault, la clave o los secretos ya existen, los reutiliza
(o rota su contenido) en lugar de duplicarlos. Verifica la lectura de cada
secreto ANTES de reescribir el .env, de modo que ninguna credencial se pierde
por el camino.

Nunca imprime valores de secretos: solo nombres, OCIDs y longitudes.

Uso:
    python scripts/oci_vault_setup.py --dry-run     # solo muestra que haria
    python scripts/oci_vault_setup.py               # crea/actualiza recursos en OCI
    python scripts/oci_vault_setup.py --keep-webhook-secret   # no rota WEBHOOK_SECRET

Tras ejecutarlo, el .env deja de contener secretos y apunta al vault.
"""
import argparse
import base64
import os
import secrets as pysecrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dotenv import dotenv_values, load_dotenv

load_dotenv()

import oci
from oci.key_management import KmsManagementClient, KmsVaultClient
from oci.key_management.models import CreateKeyDetails, CreateVaultDetails, KeyShape
from oci.vault import VaultsClient
from oci.vault.models import Base64SecretContentDetails, CreateSecretDetails, UpdateSecretDetails
from oci.secrets import SecretsClient
from oci.object_storage import ObjectStorageClient

from src.config.oci_auth import construir_cliente, obtener_config, obtener_region

NOMBRE_VAULT = "communitylab-secrets"
NOMBRE_CLAVE = "communitylab-master-key"
RUTA_ENV = RAIZ / ".env"
RUTA_ENTREGA_WEBHOOK = RAIZ / ".secrets" / "webhook-secret-n8n.txt"

# variable de entorno -> nombre del secreto en Vault (debe coincidir con src/config/secrets.py)
from src.config.secrets import SECRETS_EN_VAULT

VARIABLES_A_EVACUAR = [
    nombre for nombre in SECRETS_EN_VAULT
]


def log(mensaje: str) -> None:
    print(mensaje, flush=True)


def esperar(cliente, respuesta, atributo: str, valor: str, etiqueta: str, max_segundos: int = 600):
    """Bloquea hasta que el recurso alcance el estado deseado."""
    log(f"    esperando {etiqueta} -> {valor} ...")
    resultado = oci.wait_until(
        cliente,
        respuesta,
        atributo,
        valor,
        max_wait_seconds=max_segundos,
        wait_interval_seconds=5,
    )
    return resultado.data


def asegurar_vault(kms_vault: KmsVaultClient, compartment_id: str, dry_run: bool) -> tuple[str, str]:
    """Devuelve (vault_id, management_endpoint), creando el vault si hace falta."""
    existentes = oci.pagination.list_call_get_all_results(
        kms_vault.list_vaults, compartment_id
    ).data
    activos = [v for v in existentes if v.lifecycle_state == "ACTIVE" and v.display_name == NOMBRE_VAULT]

    if activos:
        vault_id = activos[0].id
        log(f"  [reutilizado] vault '{NOMBRE_VAULT}' ya existe y esta ACTIVE")
    else:
        if dry_run:
            log(f"  [dry-run] se crearia el vault '{NOMBRE_VAULT}' (type=DEFAULT)")
            return "<vault-ocid>", f"https://<vault>-management.kms.{obtener_region() or '<region>'}.oraclecloud.com"
        log(f"  [creando] vault '{NOMBRE_VAULT}' (type=DEFAULT) ...")
        creado = kms_vault.create_vault(
            CreateVaultDetails(
                compartment_id=compartment_id,
                display_name=NOMBRE_VAULT,
                vault_type="DEFAULT",
                freeform_tags={"proyecto": "communitylab", "gestionado_por": "scripts/oci_vault_setup.py"},
            )
        ).data
        vault_id = creado.id
        esperar(kms_vault, kms_vault.get_vault(vault_id), "lifecycle_state", "ACTIVE", "vault")

    detalle = kms_vault.get_vault(vault_id).data
    log(f"    vault_id           = {vault_id}")
    log(f"    management_endpoint= {detalle.management_endpoint}")
    return vault_id, detalle.management_endpoint


def asegurar_clave(
    kms_vault: KmsVaultClient,
    management_endpoint: str,
    compartment_id: str,
    dry_run: bool,
) -> str:
    """Devuelve el OCID de la clave maestra SOFTWARE, creandola si hace falta."""
    kms_mgmt = construir_cliente(KmsManagementClient, service_endpoint=management_endpoint)

    if not dry_run:
        existentes = oci.pagination.list_call_get_all_results(
            kms_mgmt.list_keys, compartment_id
        ).data
        candidatas = [k for k in existentes if k.display_name == NOMBRE_CLAVE]
        activas = [k for k in candidatas if k.lifecycle_state == "ENABLED"]
        if activas:
            log(f"  [reutilizada] clave '{NOMBRE_CLAVE}' ya existe y esta ENABLED")
            return activas[0].id
        recuperables = [k for k in candidatas if k.lifecycle_state == "PENDING_DELETION"]
        if recuperables:
            clave_id = recuperables[0].id
            log("  [recuperando] clave en PENDING_DELETION -> cancel_key_deletion")
            kms_mgmt.cancel_key_deletion(clave_id)
            esperar(kms_mgmt, kms_mgmt.get_key(clave_id), "lifecycle_state", "ENABLED", "clave")
            return clave_id
    else:
        log(f"  [dry-run] se crearia la clave '{NOMBRE_CLAVE}' (protection_mode=SOFTWARE, AES-256)")
        return "<key-ocid>"

    log(f"  [creando] clave '{NOMBRE_CLAVE}' (protection_mode=SOFTWARE, AES-256) ...")
    creada = kms_mgmt.create_key(
        CreateKeyDetails(
            compartment_id=compartment_id,
            display_name=NOMBRE_CLAVE,
            protection_mode="SOFTWARE",
            key_shape=KeyShape(algorithm="AES", length=32),
            freeform_tags={"proyecto": "communitylab"},
        )
    ).data
    esperar(kms_mgmt, kms_mgmt.get_key(creada.id), "lifecycle_state", "ENABLED", "clave")
    return creada.id


def asegurar_secreto(
    vaults_client: VaultsClient,
    secrets_client: SecretsClient,
    vault_id: str,
    key_id: str,
    compartment_id: str,
    variable: str,
    nombre_secreto: str,
    valor: str,
    dry_run: bool,
) -> str:
    """Crea o rota el secreto y verifica la lectura. Devuelve su OCID."""
    if dry_run:
        log(f"  [dry-run] secreto '{nombre_secreto}' <- {variable} (len={len(valor)})")
        return "<secret-ocid>"

    existentes = oci.pagination.list_call_get_all_results(
        vaults_client.list_secrets, compartment_id, vault_id=vault_id
    ).data
    coincidencias = [s for s in existentes if s.secret_name == nombre_secreto]
    contenido = Base64SecretContentDetails(content=base64.b64encode(valor.encode("utf-8")).decode("ascii"))

    if coincidencias:
        secreto = coincidencias[0]
        if secreto.lifecycle_state == "PENDING_DELETION":
            log(f"  [recuperando] secreto '{nombre_secreto}' en PENDING_DELETION -> cancel_secret_deletion")
            vaults_client.cancel_secret_deletion(secreto.id)
            esperar(vaults_client, vaults_client.get_secret(secreto.id), "lifecycle_state", "ACTIVE", "secreto")
        log(f"  [rotando] secreto '{nombre_secreto}' ya existe -> nueva version")
        vaults_client.rotate_secret(secreto.id, UpdateSecretDetails(secret_content=contenido))
        secreto_id = secreto.id
    else:
        log(f"  [creando] secreto '{nombre_secreto}' <- {variable} (len={len(valor)})")
        creado = vaults_client.create_secret(
            CreateSecretDetails(
                vault_id=vault_id,
                compartment_id=compartment_id,
                secret_name=nombre_secreto,
                description=f"CommunityLab: {variable}",
                key_id=key_id,
                secret_content=contenido,
                freeform_tags={"proyecto": "communitylab", "variable": variable},
            )
        ).data
        secreto_id = creado.id

    esperar(vaults_client, vaults_client.get_secret(secreto_id), "lifecycle_state", "ACTIVE", "secreto")

    leido = base64.b64decode(
        secrets_client.get_secret_bundle(secreto_id).data.secret_bundle_content.content
    ).decode("utf-8")
    if leido != valor:
        raise RuntimeError(f"La verificacion de lectura fallo para '{nombre_secreto}'; el .env NO sera modificado.")
    log(f"    verificado: lectura desde Vault coincide (len={len(leido)})")
    log(f"    secret_ocid = {secreto_id}")
    return secreto_id


def reescribir_env(valores_nuevos: dict[str, str], variables_a_eliminar: list[str]) -> None:
    """Actualiza el .env preservando comentarios y orden: quita secretos y fija config."""
    lineas = RUTA_ENV.read_text(encoding="utf-8").splitlines() if RUTA_ENV.exists() else []
    salida: list[str] = []
    vistos: set[str] = set()

    for linea in lineas:
        clave = None
        texto = linea.strip()
        if texto and not texto.startswith("#") and "=" in texto:
            clave = texto.split("=", 1)[0].replace("export ", "").strip()

        if clave in variables_a_eliminar:
            vistos.add(clave)
            continue
        if clave in valores_nuevos:
            salida.append(f"{clave}={valores_nuevos[clave]}")
            vistos.add(clave)
            continue
        salida.append(linea)

    pendientes = {k: v for k, v in valores_nuevos.items() if k not in vistos}
    if pendientes:
        if salida and salida[-1].strip():
            salida.append("")
        salida.append("# --- Gestion de secretos con OCI Vault (generado por scripts/oci_vault_setup.py) ---")
        for clave, valor in pendientes.items():
            salida.append(f"{clave}={valor}")

    RUTA_ENV.write_text("\n".join(salida) + "\n", encoding="utf-8")


def reconciliar_region() -> None:
    """
    Fija OCI_REGION con la region real del perfil OCI antes de aprovisionar.

    OCI_REGION es opcional y puede estar desactualizado en el .env; como Vault y
    KMS son servicios regionales, crear los recursos en la region equivocada los
    dejaria inutilizables. La fuente de verdad aqui es el archivo de config, que
    es lo que hoy autentica correctamente contra el tenancy.
    """
    import oci.config

    from src.config.oci_auth import obtener_ruta_config

    config_archivo = oci.config.from_file(
        file_location=obtener_ruta_config(),
        profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
    )
    region_archivo = (config_archivo.get("region") or "").strip()
    region_env = (os.getenv("OCI_REGION") or "").strip()

    if not region_archivo:
        return
    if region_env and region_env != region_archivo:
        log(f"  !! OCI_REGION del entorno ({region_env}) difiere del perfil OCI ({region_archivo})")
        log(f"     se aprovisionara en {region_archivo} y el .env quedara corregido")
    os.environ["OCI_REGION"] = region_archivo


def main() -> int:
    parser = argparse.ArgumentParser(description="Aprovisiona OCI Vault y migra los secretos de CommunityLab.")
    parser.add_argument("--dry-run", action="store_true", help="No crea nada en OCI ni modifica el .env")
    parser.add_argument(
        "--keep-webhook-secret",
        action="store_true",
        help="Migra WEBHOOK_SECRET tal cual en vez de rotarlo por uno nuevo",
    )
    parser.add_argument(
        "--set-secret",
        metavar="VARIABLE",
        help="Pide un valor nuevo por terminal sin eco y lo crea/rota en Vault, sin tocar el .env",
    )
    args = parser.parse_args()

    reconciliar_region()

    config = obtener_config()
    if not config:
        log("ERROR: este script necesita autenticacion con API key (OCI_AUTH=api_key).")
        log("       Ejecutalo desde el entorno donde existe ~/.oci/config.")
        return 2

    region = config.get("region") or obtener_region()
    compartment_id = config["tenancy"]

    log("=== Configuracion detectada ===")
    log(f"  region      : {region}")
    log(f"  compartment : {compartment_id} (raiz del tenancy)")
    log(f"  auth        : api_key (archivo de config local)")

    valores_env = dotenv_values(RUTA_ENV)
    secretos_a_crear: dict[str, str] = {}
    solo_un_secreto = bool(args.set_secret)

    if solo_un_secreto:
        import getpass

        variable = args.set_secret.strip().upper()
        if variable not in SECRETS_EN_VAULT:
            log(f"ERROR: {variable!r} no esta gestionada por Vault.")
            log(f"       Variables disponibles: {', '.join(sorted(SECRETS_EN_VAULT))}")
            return 2

        log("")
        log(f"=== Rotacion interactiva de {variable} ===")
        log("  El valor se pide sin eco: no quedara en el historial del shell ni en logs.")
        valor = getpass.getpass(f"  Valor nuevo para {variable}: ")
        if not valor.strip():
            log("ERROR: valor vacio; no se modifico nada.")
            return 2
        if getpass.getpass("  Repite el valor para confirmar: ") != valor:
            log("ERROR: los valores no coinciden; no se modifico nada.")
            return 2
        secretos_a_crear[variable] = valor
    else:
        namespace_real = construir_cliente(ObjectStorageClient).get_namespace().data
        log(f"  namespace API: {namespace_real}")
        if valores_env.get("OCI_NAMESPACE") and valores_env["OCI_NAMESPACE"] != namespace_real:
            log(f"  !! OCI_NAMESPACE del .env ({valores_env['OCI_NAMESPACE']}) no coincide con el real; se corregira")

        for variable in VARIABLES_A_EVACUAR:
            if variable == "WEBHOOK_SECRET":
                if args.keep_webhook_secret and valores_env.get("WEBHOOK_SECRET"):
                    secretos_a_crear[variable] = valores_env["WEBHOOK_SECRET"]
                    log(f"  {variable}: se migrara tal cual (--keep-webhook-secret)")
                else:
                    secretos_a_crear[variable] = pysecrets.token_urlsafe(48)
                    log(f"  {variable}: se generara uno NUEVO de {len(secretos_a_crear[variable])} chars (rotacion)")
                continue

            actual = valores_env.get(variable)
            if actual:
                secretos_a_crear[variable] = actual
                log(f"  {variable}: presente en .env (len={len(actual)}); se migrara tal cual")
            else:
                log(f"  {variable}: ausente en .env; se omite")

        if "ANTHROPIC_API_KEY" not in secretos_a_crear and valores_env.get("LLM_PROVIDER") == "anthropic":
            log("ERROR: LLM_PROVIDER=anthropic pero no hay ANTHROPIC_API_KEY en el .env.")
            return 2

    log("")
    log("=== Vault y clave maestra ===")
    kms_vault = construir_cliente(KmsVaultClient)
    vault_id, management_endpoint = asegurar_vault(kms_vault, compartment_id, args.dry_run)
    key_id = asegurar_clave(kms_vault, management_endpoint, compartment_id, args.dry_run)

    log("")
    log("=== Secretos ===")
    vaults_client = construir_cliente(VaultsClient)
    secrets_client = construir_cliente(SecretsClient)
    for variable, valor in secretos_a_crear.items():
        asegurar_secreto(
            vaults_client=vaults_client,
            secrets_client=secrets_client,
            vault_id=vault_id,
            key_id=key_id,
            compartment_id=compartment_id,
            variable=variable,
            nombre_secreto=SECRETS_EN_VAULT[variable],
            valor=valor,
            dry_run=args.dry_run,
        )

    if args.dry_run:
        log("")
        if solo_un_secreto:
            log(f"[dry-run] No se modifico nada. Se rotaria en Vault: {', '.join(secretos_a_crear)}")
        else:
            log("[dry-run] No se modifico nada. Cambios que se aplicarian al .env:")
            log(f"  - se eliminarian: {', '.join(secretos_a_crear)}")
            log(f"  - SECRETS_BACKEND=oci-vault")
            log(f"  - OCI_VAULT_ID={vault_id}")
            log(f"  - OCI_NAMESPACE={namespace_real}")
            log(f"  - OCI_REGION={region}")
        return 0

    if solo_un_secreto:
        log("")
        log("=== Rotacion completada ===")
        log(f"  {', '.join(secretos_a_crear)} actualizado en Vault. El .env no se modifico.")
        log("  Si el proceso de la API o de Streamlit esta corriendo, reinicialo para que")
        log("  expire la cache en memoria (SECRETS_CACHE_TTL, 300s por defecto).")
        log("")
        log("Comprueba con:  python scripts/oci_vault_check.py")
        return 0

    log("")
    log("=== Actualizando .env ===")
    reescribir_env(
        valores_nuevos={
            "SECRETS_BACKEND": "oci-vault",
            "OCI_VAULT_ID": vault_id,
            "OCI_NAMESPACE": namespace_real,
            "OCI_REGION": region,
        },
        variables_a_eliminar=list(secretos_a_crear),
    )
    log(f"  .env actualizado: sin secretos, backend=oci-vault")

    if "WEBHOOK_SECRET" in secretos_a_crear and not args.keep_webhook_secret:
        RUTA_ENTREGA_WEBHOOK.parent.mkdir(parents=True, exist_ok=True)
        RUTA_ENTREGA_WEBHOOK.write_text(secretos_a_crear["WEBHOOK_SECRET"], encoding="utf-8")
        try:
            os.chmod(RUTA_ENTREGA_WEBHOOK, 0o600)
        except OSError:
            pass
        log(f"  WEBHOOK_SECRET rotado -> copialo al header X-Webhook-Secret de n8n desde:")
        log(f"    {RUTA_ENTREGA_WEBHOOK}")
        log(f"  (archivo ignorado por git; BORRALO cuando n8n este actualizado)")

    log("")
    log("Listo. Comprueba con:  python scripts/oci_vault_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
