"""
Verificacion de punta a punta de la resolucion de secretos y del acceso a OCI.

No imprime ningun valor: solo nombres, longitudes y estados. Sirve tanto en
local (api_key) como en la Compute Instance (instance_principal).

Uso:
    python scripts/oci_vault_check.py
    python scripts/oci_vault_check.py --storage   # ademas comprueba Object Storage
"""
import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv

load_dotenv()

from src.config.oci_auth import construir_cliente, modo_autenticacion, obtener_region
from src.config.secrets import SECRETS_EN_VAULT, backend_activo, obtener_secreto, ttl_cache_segundos

log = print


def comprobar_secretos() -> int:
    fallos = 0

    log("=== Backend de secretos ===")
    log(f"  SECRETS_BACKEND : {backend_activo()}")
    log(f"  OCI_AUTH        : {modo_autenticacion()}")
    log(f"  OCI_REGION      : {obtener_region() or '<derivada del archivo de config>'}")
    log(f"  OCI_VAULT_ID    : {os.getenv('OCI_VAULT_ID', '<no definido>')}")
    log(f"  TTL cache       : {ttl_cache_segundos():.0f}s")
    log("")
    log("=== Resolucion de secretos ===")

    for variable, nombre_secreto in SECRETS_EN_VAULT.items():
        try:
            valor = obtener_secreto(variable)
        except Exception as error:
            log(f"  [FALLO] {variable:20} {type(error).__name__}: {error}")
            fallos += 1
            continue

        if valor:
            log(f"  [ OK  ] {variable:20} len={len(valor):3}  vault={nombre_secreto}")
        else:
            log(f"  [vacio] {variable:20} no definido (proveedor no en uso)")
    return fallos


def comprobar_storage() -> int:
    from oci.object_storage import ObjectStorageClient

    log("")
    log("=== Object Storage ===")
    namespace = os.getenv("OCI_NAMESPACE")
    bucket = os.getenv("OCI_BUCKET_NAME", "communitylab-activos-marketing")
    try:
        cliente = construir_cliente(ObjectStorageClient)
        ns_api = cliente.get_namespace().data
        log(f"  namespace segun API : {ns_api}")
        log(f"  OCI_NAMESPACE (.env): {namespace or '<no definido>'}")
        if namespace and namespace != ns_api:
            log("  [AVISO] OCI_NAMESPACE no coincide con el namespace real del tenancy")
        respuesta = cliente.head_bucket(namespace_name=ns_api, bucket_name=bucket)
        log(f"  [ OK  ] head_bucket '{bucket}' -> HTTP {respuesta.status}")
        return 0
    except Exception as error:
        log(f"  [FALLO] {type(error).__name__}: {getattr(error, 'message', error)}")
        return 1


def comprobar_database() -> int:
    log("")
    log("=== Oracle Autonomous Database ===")
    try:
        from src.storage.oci_db import obtener_conexion_db, consultar_estadisticas_db

        with obtener_conexion_db() as conn:
            log(f"  [ OK  ] Conexion establecida con Oracle Autonomous DB")
            log(f"         Version: {conn.version}")
        stats = consultar_estadisticas_db()
        log(f"  [ OK  ] Tablas accesibles: {stats['total_interacciones_guardadas']} interacciones, {stats['total_paquetes_guardados']} paquetes")
        return 0
    except Exception as error:
        log(f"  [FALLO] Error conectando a DB: {type(error).__name__}: {error}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Comprueba la lectura de secretos desde OCI Vault.")
    parser.add_argument("--storage", action="store_true", help="Comprueba tambien el acceso a Object Storage")
    parser.add_argument("--db", action="store_true", help="Comprueba tambien la conexion a Oracle Autonomous DB")
    args = parser.parse_args()

    fallos = comprobar_secretos()
    if args.storage:
        fallos += comprobar_storage()
    if args.db:
        fallos += comprobar_database()

    print("")
    print("Resultado:", "TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

