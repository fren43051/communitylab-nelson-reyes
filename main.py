"""
Script principal: ejecuta el pipeline completo de CommunityLab sobre un lote de interacciones.
Uso: python main.py
"""
from src.ingestion.loader import cargar_json
from src.graph.build_graph import construir_grafo


def main():
    lote = cargar_json("data/interacciones_ejemplo.json")
    grafo = construir_grafo()

    estado_inicial = {
        "lote": lote,
        "analisis": [],
        "activos_generados": [],
        "paquete_final": None,
        "oci_resultado": None,
    }

    resultado = grafo.invoke(estado_inicial)

    print("=== Resumen de la comunidad ===")
    print(resultado["paquete_final"].model_dump_json(indent=2))


if __name__ == "__main__":
    main()
