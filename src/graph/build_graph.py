"""Construccion del grafo LangGraph para CommunityLab."""
from langgraph.graph import StateGraph, START, END
from src.graph.state import CommunityLabState
from src.graph.nodes import (
    nodo_analizar, nodo_generar_caso_exito, nodo_generar_faq,
    nodo_consolidar, nodo_guardar_oci, enrutar_categorias,
)


def construir_grafo():
    grafo = StateGraph(CommunityLabState)
    grafo.add_node("analizar", nodo_analizar)
    grafo.add_node("generar_caso_exito", nodo_generar_caso_exito)
    grafo.add_node("generar_faq", nodo_generar_faq)
    grafo.add_node("consolidar", nodo_consolidar)
    grafo.add_node("guardar_oci", nodo_guardar_oci)

    grafo.add_edge(START, "analizar")
    grafo.add_conditional_edges("analizar", enrutar_categorias, {
        "generar_caso_exito": "generar_caso_exito",
        "generar_faq": "generar_faq",
        "consolidar": "consolidar",
    })
    grafo.add_edge("generar_caso_exito", "consolidar")
    grafo.add_edge("generar_faq", "consolidar")
    grafo.add_edge("consolidar", "guardar_oci")
    grafo.add_edge("guardar_oci", END)
    return grafo.compile()
