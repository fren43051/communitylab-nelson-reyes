"""
Benchmark y verificacion de rendimiento de lectura de OCI Vault en CommunityLab.
Evalua la latencia inicial de red OCI, la aceleracion por cache en memoria,
la instanciacion del proveedor LLM y el rendimiento del endpoint de webhooks.
"""
import time
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi.testclient import TestClient

from src.config.secrets import (
    SECRETS_EN_VAULT,
    backend_activo,
    limpiar_cache,
    obtener_secreto,
    ttl_cache_segundos,
)
from src.graph.llm_provider import get_llm
from api.main import app


def medir_latencias_secretos():
    print("=" * 60)
    print("1. MEDICI\u00d3N DE LATENCIA DE LECTURA DIRECTA DESDE OCI VAULT")
    print("=" * 60)
    print(f"Backend activo : {backend_activo()}")
    print(f"TTL de cach\u00e9   : {ttl_cache_segundos():.0f} segundos\n")

    limpiar_cache()

    # Lectura inicial de red (Cache Fr\u00eda)
    print("--- [Cache Fr\u00eda: Petici\u00f3n HTTPS directa a Oracle Cloud KMS] ---")
    tiempos_red = {}
    for var in ["ANTHROPIC_API_KEY", "WEBHOOK_SECRET", "OCI_CONFIG", "OCI_PRIVATE_KEY", "DB_CONNECT_STRING", "DB_PASSWORD"]:
        t0 = time.perf_counter()
        valor = obtener_secreto(var)
        dt = (time.perf_counter() - t0) * 1000
        tiempos_red[var] = dt
        longitud = len(valor) if valor else 0
        print(f"  {var:22} -> {dt:7.2f} ms  (longitud: {longitud:4} chars)")

    # Lecturas consecutivas (Cache Caliente en memoria)
    print("\n--- [Cache Caliente: Acceso en memoria ultrarr\u00e1pido] ---")
    iteraciones = 10000
    for var in ["ANTHROPIC_API_KEY", "WEBHOOK_SECRET"]:
        t0 = time.perf_counter()
        for _ in range(iteraciones):
            _ = obtener_secreto(var)
        dt_total = (time.perf_counter() - t0) * 1000
        dt_promedio = dt_total / iteraciones
        speedup = tiempos_red[var] / dt_promedio if dt_promedio > 0 else 0
        print(
            f"  {var:22} -> {dt_promedio * 1000:7.2f} \u00b5s ({dt_promedio:.4f} ms) por lectura "
            f"| {speedup:,.0f}x m\u00e1s r\u00e1pido"
        )


def probar_consumidor_llm():
    print("\n" + "=" * 60)
    print("2. CONSUMIDOR: INSTANCIACI\u00d3N DEL PROVEEDOR LLM (get_llm)")
    print("=" * 60)
    t0 = time.perf_counter()
    llm = get_llm()
    dt = (time.perf_counter() - t0) * 1000
    print(f"  Clase del LLM instanciado : {llm.__class__.__name__}")
    print(f"  Modelo configurado        : {getattr(llm, 'model_name', getattr(llm, 'model', 'N/A'))}")
    print(f"  Tiempo de resoluci\u00f3n     : {dt:.3f} ms")


def probar_consumidor_webhook():
    print("\n" + "=" * 60)
    print("3. CONSUMIDOR: VALIDACI\u00d3N DE SEGURIDAD EN API FASTAPI (WEBHOOK)")
    print("=" * 60)
    cliente = TestClient(app)
    secreto_real = obtener_secreto("WEBHOOK_SECRET")

    # Prueba funcional
    resp = cliente.post(
        "/api/webhooks/linkedin",
        json={"schema_version": "1.0.0", "origen_comunidad": "linkedin", "periodo_referencia": "2026-10-12", "interacciones": []},
        headers={"X-Webhook-Secret": secreto_real},
    )
    print(f"  Autenticaci\u00f3n webhook con clave de Vault: HTTP {resp.status_code} (esperado 422 sin lote)")

    # Benchmark de 100 peticiones
    n_peticiones = 100
    t0 = time.perf_counter()
    for _ in range(n_peticiones):
        cliente.post(
            "/api/webhooks/linkedin",
            json={"schema_version": "1.0.0", "origen_comunidad": "linkedin", "periodo_referencia": "2026-10-12", "interacciones": []},
            headers={"X-Webhook-Secret": secreto_real},
        )
    dt_total = time.perf_counter() - t0
    latencia_media = (dt_total / n_peticiones) * 1000
    rps = n_peticiones / dt_total
    print(f"  Latencia media por petici\u00f3n con Vault : {latencia_media:.2f} ms")
    print(f"  Rendimiento sostenido                 : {rps:.1f} req/seg")


def probar_consumidor_database():
    print("\n" + "=" * 60)
    print("4. CONSUMIDOR: CONEXI\u00d3N A ORACLE AUTONOMOUS DB CON VAULT")
    print("=" * 60)
    from src.storage.oci_db import obtener_conexion_db, consultar_estadisticas_db

    t0 = time.perf_counter()
    with obtener_conexion_db() as conn:
        t_conn = (time.perf_counter() - t0) * 1000
        print(f"  Tiempo de conexi\u00f3n a DB con Vault : {t_conn:.2f} ms")
        print(f"  Versi\u00f3n de Oracle DB              : {conn.version}")

    t0 = time.perf_counter()
    stats = consultar_estadisticas_db()
    t_query = (time.perf_counter() - t0) * 1000
    print(f"  Tiempo de consulta de m\u00e9tricas     : {t_query:.2f} ms")
    print(f"  Registros encontrados             : {stats['total_interacciones_guardadas']} interacciones")


def main():
    medir_latencias_secretos()
    probar_consumidor_llm()
    probar_consumidor_webhook()
    probar_consumidor_database()
    print("\n" + "=" * 60)
    print("RESULTADO: Verificaci\u00f3n y benchmark completados con \u00e9xito.")
    print("=" * 60)


if __name__ == "__main__":
    main()

