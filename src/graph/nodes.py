"""
Nodos del grafo LangGraph. IMPORTANTE: cada nodo devuelve SOLO las claves del
estado que modifica (dict parcial), nunca el 'state' completo. Esto evita
InvalidUpdateError cuando generar_caso_exito y generar_faq corren en paralelo
dentro del mismo superstep (ambos escribirian 'lote' sin cambios si se
devolviera el state entero). 'activos_generados' usa reducer operator.add
en state.py para concatenar las listas devueltas por ambos nodos.

Los activos se asignan como objetos Pydantic tipados (no dicts via model_dump)
para evitar PydanticSerializationUnexpectedValue al serializar el paquete final.
"""
import json
import time
from collections import Counter

from src.graph.state import CommunityLabState
from src.graph.llm_provider import get_llm
from src.ingestion.models import (
    AnalisisInteraccion, PuntuacionRelevancia, ResumenComunidad, ActivosDistribucion,
    PostLinkedIn, DestaqueNewsletter, SugerenciaFAQ, PaqueteDistribucion, MetadatosEjecucion,
    AlmacenamientoOCI,
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
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        for clave in ("texto", "resumen", "descripcion", "canal", "autor"):
            if clave in valor and isinstance(valor[clave], str):
                return valor[clave]
        return json.dumps(valor, ensure_ascii=False)
    return fallback or str(valor)


def nodo_analizar(state: CommunityLabState) -> dict:
    analisis_lista = []
    for interaccion in state["lote"].interacciones:
        resultado = _llm_json(PROMPT_ANALISIS, interaccion.texto)
        resultado["puntuacion_relevancia"] = PuntuacionRelevancia(**resultado["puntuacion_relevancia"])
        analisis_lista.append(AnalisisInteraccion(
            id=interaccion.id, autor=interaccion.autor, canal=interaccion.canal,
            tipo=interaccion.tipo, texto=interaccion.texto, **resultado,
        ))
    return {"analisis": analisis_lista}


def nodo_generar_caso_exito(state: CommunityLabState) -> dict:
    candidatos = [a for a in state["analisis"] if a.categoria_accion == "caso_exito"]
    if not candidatos:
        return {"activos_generados": []}
    mejor = max(candidatos, key=lambda a: a.score_relevancia)

    linkedin = _llm_json(PROMPT_LINKEDIN, f"Autor: {mejor.autor}\nTestimonio: {mejor.texto}")
    newsletter = _llm_json(PROMPT_NEWSLETTER, f"Autor: {mejor.autor}\nTestimonio: {mejor.texto}")

    linkedin["titulo"] = _forzar_string(linkedin.get("titulo"))
    linkedin["cuerpo"] = _forzar_string(linkedin.get("cuerpo"))
    linkedin["source_ids"] = [mejor.id]

    newsletter["titular"] = _forzar_string(newsletter.get("titular"))
    newsletter["resumen"] = _forzar_string(newsletter.get("resumen"))
    newsletter["source_ids"] = [mejor.id]

    return {"activos_generados": [
        {"post_linkedin": PostLinkedIn(**linkedin)},
        {"destaque_newsletter_semanal": DestaqueNewsletter(**newsletter)},
    ]}


def nodo_generar_faq(state: CommunityLabState) -> dict:
    candidatos = [a for a in state["analisis"] if a.categoria_accion == "faq_tip"]
    if not candidatos:
        return {"activos_generados": []}
    mejor = max(candidatos, key=lambda a: a.score_relevancia)

    faq = _llm_json(PROMPT_FAQ, f"Autor: {mejor.autor}\nCanal: {mejor.canal}\nPregunta: {mejor.texto}")
    faq["tema"] = _forzar_string(faq.get("tema"))
    faq["origen"] = _forzar_string(
        faq.get("origen"), fallback=f"Duda planteada por {mejor.autor} en el canal {mejor.canal}",
    )
    faq["status"] = _forzar_string(faq.get("status"), fallback="derivado_a_mentoria")
    faq["source_ids"] = [mejor.id]

    return {"activos_generados": [{"sugerencia_contenido_faq": SugerenciaFAQ(**faq)}]}


def enrutar_categorias(state: CommunityLabState) -> list[str]:
    categorias = {a.categoria_accion for a in state["analisis"]}
    destinos = []
    if "caso_exito" in categorias:
        destinos.append("generar_caso_exito")
    if "faq_tip" in categorias:
        destinos.append("generar_faq")
    return destinos or ["consolidar"]


def nodo_consolidar(state: CommunityLabState) -> dict:
    inicio = state.get("_inicio_ts", time.time())
    sentimientos = [a.sentimiento for a in state["analisis"]]
    predominante = Counter(sentimientos).most_common(1)[0][0] if sentimientos else "Neutral"
    temas = [t for a in state["analisis"] for t in a.temas]
    temas_top = [t for t, _ in Counter(temas).most_common(3)]
    alertas = [a.id for a in state["analisis"] if a.requiere_soporte]

    activos = ActivosDistribucion()
    for item in state.get("activos_generados", []):
        for k, v in item.items():
            setattr(activos, k, v)

    resumen = ResumenComunidad(
        total_interacciones_procesadas=len(state["lote"].interacciones) + len(state.get("rechazados", [])),
        registros_validos=len(state["analisis"]),
        registros_rechazados=len(state.get("rechazados", [])),
        sentimiento_predominante=predominante,
        temas_principales=temas_top,
        alertas_soporte=alertas,
    )

    paquete = PaqueteDistribucion(
        status="exito", resumen_comunidad=resumen, activos_distribucion_generados=activos,
        metadatos_ejecucion=MetadatosEjecucion(
            modelo="llm-configurado-via-env", latencia_ms=int((time.time() - inicio) * 1000),
        ),
    )
    return {"paquete_final": paquete}


def nodo_guardar_oci(state: CommunityLabState) -> dict:
    resultado = subir_paquete_a_oci(state["paquete_final"], periodo_referencia=state["lote"].periodo_referencia)
    paquete_actualizado = state["paquete_final"]
    if paquete_actualizado:
        paquete_actualizado.almacenamiento_oci = AlmacenamientoOCI(**resultado)
    return {"oci_resultado": resultado, "paquete_final": paquete_actualizado}
