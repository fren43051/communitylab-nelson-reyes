"""
Cliente OCI Object Storage (capa Always Free).
Sube el paquete de activos generado como JSON al bucket configurado.
"""
import os
import json
from datetime import date
from dotenv import load_dotenv

load_dotenv()


def subir_paquete_a_oci(paquete_final, periodo_referencia: str) -> dict:
    """
    Sube el paquete de distribucion a OCI Object Storage.
    Requiere ~/.oci/config configurado (OCI_CONFIG_FILE / OCI_CONFIG_PROFILE).
    """
    bucket_name = os.getenv("OCI_BUCKET_NAME", "communitylab-activos-marketing")
    namespace = os.getenv("OCI_NAMESPACE")
    ruta_objeto = f"activos/{date.today().isoformat()}-{periodo_referencia}/paquete-distribucion.json"

    try:
        import oci
        config = oci.config.from_file(
            file_location=os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")),
            profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
        )
        client = oci.object_storage.ObjectStorageClient(config)

        contenido = json.dumps(
            paquete_final.model_dump() if hasattr(paquete_final, "model_dump") else paquete_final,
            ensure_ascii=False, indent=2,
        )

        client.put_object(
            namespace_name=namespace,
            bucket_name=bucket_name,
            object_name=ruta_objeto,
            put_object_body=contenido.encode("utf-8"),
        )
        return {"bucket": bucket_name, "ruta_objeto": ruta_objeto, "status": "guardado_con_exito"}

    except Exception as e:
        return {"bucket": bucket_name, "ruta_objeto": ruta_objeto, "status": f"error: {e}"}
