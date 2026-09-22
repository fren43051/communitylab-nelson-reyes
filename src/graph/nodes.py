"""
Nodos del grafo LangGraph:
1. nodo_analizar: sentimiento, temas, rubrica de relevancia y categoria por interaccion (LLM)
2. enrutar_categorias: edge condicional
3. nodo_generar_caso_exito: genera post LinkedIn + newsletter, con source_ids trazables
4. nodo_generar_faq: genera sugerencia de FAQ/tip, con source_ids trazables
5. nodo_consolidar: arma el paquete final de distribucion (incluye rechazados y alertas)
6. nodo_guardar_oci: persiste el paquete en OCI Object Storage y verifica lectura
"""
import json
import time
from collections import Counter

from src.graph.state import CommunityLabState
from src.graph.llm_provider import get_llm
from src.ingestion.models import (
    AnalisisInteraccion, PuntuacionRelevancia, ResumenComunidad, ActivosDistribucion,
    PostLinkedIn, DestaqueNewsletter, SugerenciaFAQ, PaqueteDistribucion, MetadatosEjecucion,
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
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    return json.loads(texto)


def _forzar_string(valor, fallback: str = "") -> str:
    """
    Normaliza un valor devuelto por el LLM a string plano.
    Si el LLM devuelve un dict/objeto en un campo que deberia ser texto,
    se extrae el contenido textual mas relevante en lugar de fallar la validacion.
    """
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        for clave_preferida in ("texto", "resumen", "descripcion", "canal", "autor"):
            if clave_preferida in valor and isinstance(valor[clave_preferida], str):
                return valor[clave_preferida]
        return json.dumps(valor, ensure_ascii=False)
    return fallback or str(valor)


def nodo_analizar(state: CommunityLabState) -> CommunityLabState:
    analisis_lista = []
    for interaccion in state["lote"].interacciones:
        resultado = _llm_json(PROMPT_ANALISIS, interaccion.texto)
        resultado["puntuacion_relevancia"] = PuntuacionRelevancia(**resultado["puntuacion_relevancia"])
        analisis_lista.append(AnalisisInteraccion(
            id=interaccion.id,
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

    linkedin["titulo"] = _forzar_string(linkedin.get("titulo"))
    linkedin["cuerpo"] = _forzar_string(linkedin.get("cuerpo"))
    linkedin["source_ids"] = [mejor.id]

    newsletter["titular"] = _forzar_string(newsletter.get("titular"))
    newsletter["resumen"] = _forzar_string(newsletter.get("resumen"))
    newsletter["source_ids"] = [mejor.id]

    state["activos_generados"].append({"post_linkedin": PostLinkedIn(**linkedin).model_dump()})
    state["activos_generados"].append({"destaque_newsletter_semanal": DestaqueNewsletter(**newsletter).model_dump()})
    return state


def nodo_generar_faq(state: CommunityLabState) -> CommunityLabState:
    candidatos = [a for a in state["analisis"] if a.categoria_accion == "faq_tip"]
    if not candidatos:
        return state
    mejor = max(candidatos, key=lambda a: a.score_relevancia)

    faq = _llm_json(PROMPT_FAQ, f"Autor: {mejor.autor}\nCanal: {mejor.canal}\nPregunta: {mejor.texto}")

    faq["tema"] = _forzar_string(faq.get("tema"))
    faq["origen"] = _forzar_string(
        faq.get("origen"),
        fallback=f"Duda planteada por {mejor.autor} en el canal {mejor.canal}",
    )
    faq["status"] = _forzar_string(faq.get("status"), fallback="derivado_a_mentoria")
    faq["source_ids"] = [mejor.id]

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
    inicio = state.get("_inicio_ts", time.time())
    sentimientos = [a.sentimiento for a in state["analisis"]]
    predominante = Counter(sentimientos).most_common(1)[0][0] if sentimientos else "Neutral"
    temas = [t for a in state["analisis"] for t in a.temas]
    temas_top = [t for t, _ in Counter(temas).most_common(3)]
    alertas = [a.id for a in state["analisis"] if a.requiere_soporte]

    activos = ActivosDistribucion()
    for item in state["activos_generados"]:
        for k, v in item.items():
            setattr(activos, k, v if isinstance(v, dict) else v)

    resumen = ResumenComunidad(
        total_interacciones_procesadas=len(state["lote"].interacciones) + len(state.get("rechazados", [])),
        registros_validos=len(state["analisis"]),
        registros_rechazados=len(state.get("rechazados", [])),
        sentimiento_predominante=predominante,
        temas_principales=temas_top,
        alertas_soporte=alertas,
    )

    paquete = PaqueteDistribucion(
        status="exito",
        resumen_comunidad=resumen,
        activos_distribucion_generados=activos,
        metadatos_ejecucion=MetadatosEjecucion(
            modelo="llm-configurado-via-env",
            latencia_ms=int((time.time() - inicio) * 1000),
        ),
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
