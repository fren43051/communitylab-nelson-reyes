"""
Nodos del grafo LangGraph:
1. nodo_analizar: sentimiento, temas, score y categoria por interaccion (LLM)
2. enrutar_categorias: edge condicional
3. nodo_generar_caso_exito: genera post LinkedIn + newsletter
4. nodo_generar_faq: genera sugerencia de FAQ/tip
5. nodo_consolidar: arma el paquete final de distribucion
6. nodo_guardar_oci: persiste el paquete en OCI Object Storage
"""
import json
from collections import Counter

from src.graph.state import CommunityLabState
from src.graph.llm_provider import get_llm
from src.ingestion.models import (
    AnalisisInteraccion, ResumenComunidad, ActivosDistribucion,
    PostLinkedIn, DestaqueNewsletter, SugerenciaFAQ, PaqueteDistribucion,
)
from src.prompts.canal_prompts import (
    PROMPT_ANALISIS, PROMPT_LINKEDIN, PROMPT_NEWSLETTER, PROMPT_FAQ,
)
from src.storage.oci_client import subir_paquete_a_oci


def _llm_json(prompt_sistema: str, contenido_usuario: str) -> dict:
    llm = get_llm()
    respuesta = llm.invoke([
        {"role": "system", "content": prompt_sistema},
        {"role": "user", "content": contenido_usuario},
    ])
    texto = respuesta.content.strip()
    if texto.startswith("```"):
        texto = texto.strip("`").replace("json\n", "", 1)
    return json.loads(texto)


def nodo_analizar(state: CommunityLabState) -> CommunityLabState:
    analisis_lista = []
    for interaccion in state["lote"].interacciones:
        resultado = _llm_json(PROMPT_ANALISIS, interaccion.texto)
        analisis_lista.append(AnalisisInteraccion(
            autor=interaccion.autor,
            canal=interaccion.canal,
            tipo=interaccion.tipo,
            texto=interaccion.texto,
            **resultado,
        ))
    state["analisis"] = analisis_lista
    return state


def nodo_generar_caso_exito(state: CommunityLabState) -> CommunityLabState:
    candidatos = [a for a in state["analisis"] if a.categoria_accion == "caso_exito"]
    if not candidatos:
        return state
    mejor = max(candidatos, key=lambda a: a.score_relevancia)

    linkedin = _llm_json(PROMPT_LINKEDIN, f"Autor: {mejor.autor}\nTestimonio: {mejor.texto}")
    newsletter = _llm_json(PROMPT_NEWSLETTER, f"Autor: {mejor.autor}\nTestimonio: {mejor.texto}")

    state["activos_generados"].append({"post_linkedin": PostLinkedIn(**linkedin).model_dump()})
    state["activos_generados"].append({"destaque_newsletter_semanal": DestaqueNewsletter(**newsletter).model_dump()})
    return state


def nodo_generar_faq(state: CommunityLabState) -> CommunityLabState:
    candidatos = [a for a in state["analisis"] if a.categoria_accion == "faq_tip"]
    if not candidatos:
        return state
    mejor = max(candidatos, key=lambda a: a.score_relevancia)

    faq = _llm_json(PROMPT_FAQ, f"Autor: {mejor.autor}\nCanal: {mejor.canal}\nPregunta: {mejor.texto}")
    state["activos_generados"].append({"sugerencia_contenido_faq": SugerenciaFAQ(**faq).model_dump()})
    return state


def enrutar_categorias(state: CommunityLabState) -> list[str]:
    categorias = {a.categoria_accion for a in state["analisis"]}
    destinos = []
    if "caso_exito" in categorias:
        destinos.append("generar_caso_exito")
    if "faq_tip" in categorias:
        destinos.append("generar_faq")
    return destinos or ["consolidar"]


def nodo_consolidar(state: CommunityLabState) -> CommunityLabState:
    sentimientos = [a.sentimiento for a in state["analisis"]]
    predominante = Counter(sentimientos).most_common(1)[0][0] if sentimientos else "Neutral"
    temas = [t for a in state["analisis"] for t in a.temas]
    temas_top = [t for t, _ in Counter(temas).most_common(3)]

    activos = ActivosDistribucion()
    for item in state["activos_generados"]:
        for k, v in item.items():
            setattr(activos, k, v if isinstance(v, dict) else v)

    paquete = PaqueteDistribucion(
        status="exito",
        resumen_comunidad=ResumenComunidad(
            total_interacciones_procesadas=len(state["analisis"]),
            sentimiento_predominante=predominante,
            temas_principales=temas_top,
        ),
        activos_distribucion_generados=activos,
    )
    state["paquete_final"] = paquete
    return state


def nodo_guardar_oci(state: CommunityLabState) -> CommunityLabState:
    resultado = subir_paquete_a_oci(
        state["paquete_final"],
        periodo_referencia=state["lote"].periodo_referencia,
    )
    state["oci_resultado"] = resultado
    if state["paquete_final"]:
        state["paquete_final"].almacenamiento_oci = resultado
    return state
