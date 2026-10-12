"""
Cliente OCI Object Storage (capa Always Free).
Sube el paquete de activos generado como JSON al bucket configurado y VERIFICA
la lectura del objeto tras subirlo (comprobacion_lectura), en lugar de confiar
unicamente en la respuesta de put_object.
La autenticacion se delega en src.config.oci_auth, de modo que en local usa el
perfil de ~/.oci/config y en una Compute Instance usa instance principal.
"""
import os
import json
from datetime import date
from dotenv import load_dotenv

from src.config.oci_auth import construir_cliente

load_dotenv()


def subir_paquete_a_oci(paquete_final, periodo_referencia: str, sufijo: str = "borrador") -> dict:
    """
    Sube el paquete de distribucion a OCI Object Storage y relee el objeto para confirmar
    que la escritura persistio correctamente (comprobacion_lectura=True solo si tuvo exito).
    En local requiere ~/.oci/config (OCI_CONFIG_FILE / OCI_CONFIG_PROFILE); en OCI usa
    el signer del recurso y no necesita ninguna clave privada en disco.
    """
    bucket_name = os.getenv("OCI_BUCKET_NAME", "communitylab-activos-marketing")
    namespace = os.getenv("OCI_NAMESPACE")
    sufijo_limpio = "".join(c for c in sufijo if c.isalnum() or c in "-_") or "borrador"
    ruta_objeto = (
        f"activos/{date.today().isoformat()}-{periodo_referencia}/"
        f"paquete-distribucion-{sufijo_limpio}.json"
    )

    try:
        import oci

        client = None
        try:
            from src.config.oci_auth import construir_cliente

            client = construir_cliente(oci.object_storage.ObjectStorageClient)
        except Exception:
            pass

        if client is None:
            config = oci.config.from_file(
                file_location=os.path.expanduser(os.getenv("OCI_CONFIG_FILE", "~/.oci/config")),
                profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
            )
            client = oci.object_storage.ObjectStorageClient(config)

        contenido_dict = paquete_final.model_dump(mode="json") if hasattr(paquete_final, "model_dump") else paquete_final
        contenido = json.dumps(contenido_dict, ensure_ascii=False, indent=2)

        client.put_object(
            namespace_name=namespace,
            bucket_name=bucket_name,
            object_name=ruta_objeto,
            put_object_body=contenido.encode("utf-8"),
        )

        comprobacion_lectura = False
        detalle_error = None
        try:
            respuesta_lectura = client.get_object(
                namespace_name=namespace,
                bucket_name=bucket_name,
                object_name=ruta_objeto,
            )
            leido = respuesta_lectura.data.content.decode("utf-8")
            comprobacion_lectura = json.loads(leido) == contenido_dict
        except Exception as error_lectura:
            comprobacion_lectura = False
            detalle_error = str(error_lectura)

        return {
            "bucket": bucket_name,
            "ruta_objeto": ruta_objeto,
            "status": "guardado_con_exito" if comprobacion_lectura else "guardado_error",
            "comprobacion_lectura": comprobacion_lectura,
            "detalle_error": detalle_error,
        }

    except Exception as e:
        return {
            "bucket": bucket_name,
            "ruta_objeto": ruta_objeto,
            "status": "guardado_error",
            "comprobacion_lectura": False,
            "detalle_error": str(e),
        }
