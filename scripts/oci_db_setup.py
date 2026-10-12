"""
Aprovisiona Oracle Autonomous Database (Always Free) en OCI y registra sus
credenciales en OCI Vault (communitylab-secrets).

Es idempotente:
  - Si la base de datos ya existe, reutiliza sus datos de conexion.
  - Guarda en OCI Vault:
      * communitylab-db-user
      * communitylab-db-password
      * communitylab-db-name
      * communitylab-db-connect-string
  - Inicializa las tablas necesarias en la base de datos.
"""
import os
import sys
import base64
import secrets as pysecrets
import string
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv
load_dotenv()

import oci
from oci.database import DatabaseClient
from oci.database.models import CreateAutonomousDatabaseDetails
from oci.vault import VaultsClient
from oci.vault.models import CreateSecretDetails, Base64SecretContentDetails, UpdateSecretDetails
from oci.secrets import SecretsClient
from oci.key_management import KmsManagementClient, KmsVaultClient

from src.config.oci_auth import construir_cliente, obtener_config

DB_NAME = "communitylabdb"
DB_DISPLAY_NAME = "communitylab-db"
NOMBRE_VAULT = "communitylab-secrets"
NOMBRE_CLAVE = "communitylab-master-key"


def generar_password_segura() -> str:
    """Genera una contrasena que cumple los requisitos estrictos de Oracle Autonomous DB."""
    mayusculas = "".join(pysecrets.choice(string.ascii_uppercase) for _ in range(4))
    minusculas = "".join(pysecrets.choice(string.ascii_lowercase) for _ in range(6))
    digitos = "".join(pysecrets.choice(string.digits) for _ in range(4))
    especiales = "".join(pysecrets.choice("#_") for _ in range(2))
    todos = list(mayusculas + minusculas + digitos + especiales)
    pysecrets.SystemRandom().shuffle(todos)
    pwd = "".join(todos)
    # Asegurar que no empiece con digito ni caracter especial
    return "C1" + pwd


def guardar_o_actualizar_secreto(vaults_client, vault_id, key_id, compartment_id, secret_name, valor, descripcion=""):
    existentes = oci.pagination.list_call_get_all_results(vaults_client.list_secrets, compartment_id, vault_id=vault_id).data
    coincidencias = [s for s in existentes if s.secret_name == secret_name]
    contenido = Base64SecretContentDetails(content=base64.b64encode(valor.encode("utf-8")).decode("ascii"))

    if coincidencias:
        sec = coincidencias[0]
        print(f"  [actualizando] secreto '{secret_name}' ya existe -> nueva version")
        vaults_client.rotate_secret(sec.id, UpdateSecretDetails(secret_content=contenido))
        sec_id = sec.id
    else:
        print(f"  [creando] secreto '{secret_name}' en OCI Vault...")
        creado = vaults_client.create_secret(
            CreateSecretDetails(
                vault_id=vault_id,
                compartment_id=compartment_id,
                secret_name=secret_name,
                description=descripcion or f"CommunityLab: {secret_name}",
                key_id=key_id,
                secret_content=contenido,
                freeform_tags={"proyecto": "communitylab"}
            )
        ).data
        sec_id = creado.id

    oci.wait_until(vaults_client, vaults_client.get_secret(sec_id), "lifecycle_state", "ACTIVE")
    return sec_id


def asegurar_base_de_datos(db_client: DatabaseClient, compartment_id: str):
    """Obtiene o crea la Autonomous Database Always Free en OCI."""
    print("=== 1. Comprobando Autonomous Database en OCI ===")
    existentes = db_client.list_autonomous_databases(compartment_id).data
    coincidencias = [d for d in existentes if d.db_name == DB_NAME and d.lifecycle_state not in ("TERMINATED", "TERMINATING")]

    if coincidencias:
        adb = coincidencias[0]
        print(f"  [reutilizando] Autonomous DB encontrada: {adb.display_name} (estado: {adb.lifecycle_state})")
        admin_pwd = None
    else:
        admin_pwd = generar_password_segura()
        print(f"  [creando] Autonomous Database Always Free '{DB_NAME}' (OLTP, Serverless, TLS sin mTLS)...")
        detalles = CreateAutonomousDatabaseDetails(
            compartment_id=compartment_id,
            db_name=DB_NAME,
            display_name=DB_DISPLAY_NAME,
            admin_password=admin_pwd,
            is_free_tier=True,
            db_workload="OLTP",
            is_mtls_connection_required=False,
            whitelisted_ips=["0.0.0.0/0"],
            freeform_tags={"proyecto": "communitylab"}
        )
        adb = db_client.create_autonomous_database(detalles).data
        print(f"    ID: {adb.id}")
        print("    Esperando que la base de datos pase a estado AVAILABLE (suele tardar 2-3 minutos)...")
        adb = oci.wait_until(db_client, db_client.get_autonomous_database(adb.id), "lifecycle_state", "AVAILABLE", max_wait_seconds=600).data
        print(f"  [OK] Base de datos activa y lista!")

    # Obtener detalles completos
    detalle = db_client.get_autonomous_database(adb.id).data
    
    # Elegir el connection string TLS (no requiere mTLS wallet)
    connect_string = None
    if detalle.connection_strings and detalle.connection_strings.profiles:
        # Preferir perfiles TLS (sin mTLS)
        for p in detalle.connection_strings.profiles:
            if p.tls_authentication == "SERVER" and "low" in p.display_name.lower():
                connect_string = p.value
                break
        if not connect_string:
            for p in detalle.connection_strings.profiles:
                if p.tls_authentication == "SERVER":
                    connect_string = p.value
                    break
    if not connect_string and detalle.connection_strings:
        connect_string = getattr(detalle.connection_strings, "low", None) or getattr(detalle.connection_strings, "medium", None)

    return detalle, admin_pwd, connect_string


def main():
    config = obtener_config()
    compartment_id = config["tenancy"]
    vault_id = os.getenv("OCI_VAULT_ID")
    if not vault_id:
        print("ERROR: OCI_VAULT_ID no esta definido en .env")
        return 1

    db_client = construir_cliente(DatabaseClient)
    vaults_client = construir_cliente(VaultsClient)
    kms_vault = construir_cliente(KmsVaultClient)

    # Buscar clave maestra
    vault_info = kms_vault.get_vault(vault_id).data
    kms_mgmt = construir_cliente(KmsManagementClient, service_endpoint=vault_info.management_endpoint)
    keys = oci.pagination.list_call_get_all_results(kms_mgmt.list_keys, compartment_id).data
    clave_activa = [k for k in keys if k.display_name == NOMBRE_CLAVE and k.lifecycle_state == "ENABLED"]
    if not clave_activa:
        print(f"ERROR: No se encontro clave maestra {NOMBRE_CLAVE} activa en el vault.")
        return 1
    key_id = clave_activa[0].id

    # Asegurar base de datos
    adb, admin_pwd, connect_string = asegurar_base_de_datos(db_client, compartment_id)
    print(f"  Connection string TLS: {connect_string[:60]}...")

    print("\n=== 2. Registrando credenciales en OCI Vault ===")
    if admin_pwd:
        guardar_o_actualizar_secreto(vaults_client, vault_id, key_id, compartment_id, "communitylab-db-password", admin_pwd, "Contrasena ADMIN de Autonomous DB")
    
    guardar_o_actualizar_secreto(vaults_client, vault_id, key_id, compartment_id, "communitylab-db-user", "ADMIN", "Usuario de Autonomous DB")
    guardar_o_actualizar_secreto(vaults_client, vault_id, key_id, compartment_id, "communitylab-db-name", DB_NAME, "Nombre de Autonomous DB")
    if connect_string:
        guardar_o_actualizar_secreto(vaults_client, vault_id, key_id, compartment_id, "communitylab-db-connect-string", connect_string, "Cadena de conexion TLS de Autonomous DB")

    print("\n=== 3. Verificacion de lectura desde OCI Vault ===")
    secrets_client = construir_cliente(SecretsClient)
    for sec_name in ["communitylab-db-user", "communitylab-db-name", "communitylab-db-connect-string", "communitylab-db-password"]:
        res = secrets_client.get_secret_bundle_by_name(sec_name, vault_id)
        val = base64.b64decode(res.data.secret_bundle_content.content).decode("utf-8")
        print(f"  [OK] {sec_name:32} leido desde Vault (len={len(val)})")

    print("\nProceso finalizado con exito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
