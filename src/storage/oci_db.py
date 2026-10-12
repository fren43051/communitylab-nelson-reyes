"""
Conector y operaciones de persistencia para Oracle Autonomous Database en OCI.

Todas las credenciales (DB_USER, DB_PASSWORD, DB_CONNECT_STRING) se leen
EXCLUSIVAMENTE desde OCI Vault a traves de `src.config.secrets.obtener_secreto`.
Utiliza `oracledb` en modo Thin (puro Python, sin necesidad de cliente Oracle binario
ni archivos de wallet en disco gracias a la conexion TLS nativa).
"""
import json
import logging
from typing import Any

import oracledb

from src.config.secrets import obtener_secreto, requerir_secreto

logger = logging.getLogger(__name__)


def obtener_conexion_db() -> oracledb.Connection:
    """
    Establece conexion con Oracle Autonomous Database utilizando las credenciales
    resueltas dinamicamente desde OCI Vault.
    """
    user = requerir_secreto("DB_USER", "Asegura communitylab-db-user en OCI Vault.")
    password = requerir_secreto("DB_PASSWORD", "Asegura communitylab-db-password en OCI Vault.")
    dsn = requerir_secreto("DB_CONNECT_STRING", "Asegura communitylab-db-connect-string en OCI Vault.")

    # Modo Thin de oracledb (sin drivers C locales, compatible con TLS)
    conexion = oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
    )
    return conexion


def inicializar_tablas() -> None:
    """
    Crea las tablas operativas en la base de datos si todavia no existen:
      - `communitylab_interacciones`: trazabilidad por registro individual
      - `communitylab_paquetes`: paquetes finales curados y estado de revision
    """
    ddl_interacciones = """
    CREATE TABLE communitylab_interacciones (
        id VARCHAR2(100) PRIMARY KEY,
        autor VARCHAR2(255),
        canal VARCHAR2(100),
        tipo VARCHAR2(100),
        texto CLOB,
        sentimiento VARCHAR2(50),
        puntuacion_relevancia NUMBER,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        datos_json CLOB
    )
    """

    ddl_paquetes = """
    CREATE TABLE communitylab_paquetes (
        id VARCHAR2(100) PRIMARY KEY,
        periodo_referencia VARCHAR2(50),
        origen_comunidad VARCHAR2(100),
        total_procesadas NUMBER,
        validas NUMBER,
        rechazadas NUMBER,
        sentimiento_predominante VARCHAR2(50),
        estado_revision VARCHAR2(50),
        revisor VARCHAR2(255),
        fecha_decision VARCHAR2(50),
        comentarios CLOB,
        paquete_json CLOB,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """

    with obtener_conexion_db() as conn:
        with conn.cursor() as cur:
            for tabla, ddl in [
                ("COMMUNITYLAB_INTERACCIONES", ddl_interacciones),
                ("COMMUNITYLAB_PAQUETES", ddl_paquetes),
            ]:
                cur.execute(
                    "SELECT COUNT(*) FROM user_tables WHERE table_name = :t",
                    {"t": tabla},
                )
                existe = cur.fetchone()[0] > 0
                if not existe:
                    cur.execute(ddl)
                    conn.commit()
                    logger.info(f"Tabla {tabla} creada exitosamente en OCI DB.")


def guardar_interacciones(interacciones: list) -> int:
    """Inserta o actualiza un lote de interacciones en la base de datos OCI."""
    if not interacciones:
        return 0

    sql = """
    MERGE INTO communitylab_interacciones t
    USING (SELECT :id AS id FROM dual) s
    ON (t.id = s.id)
    WHEN MATCHED THEN
        UPDATE SET autor = :autor, canal = :canal, tipo = :tipo,
                   texto = :texto, sentimiento = :sentimiento,
                   puntuacion_relevancia = :relevancia, datos_json = :datos_json
    WHEN NOT MATCHED THEN
        INSERT (id, autor, canal, tipo, texto, sentimiento, puntuacion_relevancia, datos_json)
        VALUES (:id, :autor, :canal, :tipo, :texto, :sentimiento, :relevancia, :datos_json)
    """

    filas = []
    for item in interacciones:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        filas.append({
            "id": str(data.get("id")),
            "autor": str(data.get("autor") or ""),
            "canal": str(data.get("canal") or ""),
            "tipo": str(data.get("tipo") or ""),
            "texto": str(data.get("texto") or ""),
            "sentimiento": str(data.get("sentimiento") or ""),
            "relevancia": float(data.get("puntuacion_relevancia") or 0.0),
            "datos_json": json.dumps(data, ensure_ascii=False),
        })

    with obtener_conexion_db() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, filas)
            conn.commit()
            return len(filas)


def guardar_paquete_distribucion(paquete, periodo_referencia: str) -> dict[str, Any]:
    """Guarda un paquete generado y su estado de revision en Oracle Autonomous DB."""
    data = paquete.model_dump() if hasattr(paquete, "model_dump") else paquete
    resumen = data.get("resumen_comunidad", {})
    control = data.get("control_revision_humana", {})

    id_paquete = f"{periodo_referencia}-{control.get('numero_revision', 1)}"

    sql = """
    MERGE INTO communitylab_paquetes t
    USING (SELECT :id AS id FROM dual) s
    ON (t.id = s.id)
    WHEN MATCHED THEN
        UPDATE SET estado_revision = :estado_revision, revisor = :revisor,
                   fecha_decision = :fecha_decision, comentarios = :comentarios,
                   paquete_json = :paquete_json
    WHEN NOT MATCHED THEN
        INSERT (id, periodo_referencia, origen_comunidad, total_procesadas,
                validas, rechazadas, sentimiento_predominante, estado_revision,
                revisor, fecha_decision, comentarios, paquete_json)
        VALUES (:id, :periodo, :origen, :total, :validas, :rechazadas,
                :sentimiento, :estado_revision, :revisor, :fecha_decision,
                :comentarios, :paquete_json)
    """

    params = {
        "id": id_paquete,
        "periodo": periodo_referencia,
        "origen": resumen.get("origen_comunidad", "comunidad"),
        "total": int(resumen.get("total_interacciones_procesadas", 0)),
        "validas": int(resumen.get("registros_validos", 0)),
        "rechazadas": int(resumen.get("registros_rechazados", 0)),
        "sentimiento": str(resumen.get("sentimiento_predominante", "neutral")),
        "estado_revision": str(control.get("estado_decision", "pendiente")),
        "revisor": str(control.get("revisor") or ""),
        "fecha_decision": str(control.get("fecha_decision") or ""),
        "comentarios": str(control.get("comentarios") or ""),
        "paquete_json": json.dumps(data, ensure_ascii=False, indent=2),
    }

    with obtener_conexion_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()

    return {
        "status": "guardado_en_db",
        "id_paquete": id_paquete,
        "base_de_datos": "Oracle Autonomous DB (Always Free)",
    }


def consultar_estadisticas_db() -> dict[str, Any]:
    """Consulta resumen de registros persistidos en la base de datos."""
    with obtener_conexion_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM communitylab_interacciones")
            total_interacciones = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM communitylab_paquetes")
            total_paquetes = cur.fetchone()[0]

            cur.execute("""
                SELECT id, periodo_referencia, estado_revision, revisor, fecha_registro
                FROM communitylab_paquetes
                ORDER BY fecha_registro DESC
                FETCH FIRST 5 ROWS ONLY
            """)
            filas_paquetes = [
                {
                    "id": row[0],
                    "periodo": row[1],
                    "estado": row[2],
                    "revisor": row[3],
                    "fecha": str(row[4]),
                }
                for row in cur.fetchall()
            ]

    return {
        "total_interacciones_guardadas": total_interacciones,
        "total_paquetes_guardados": total_paquetes,
        "ultimos_paquetes": filas_paquetes,
    }
