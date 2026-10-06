"""
Panel de curaduria CommunityLab (Streamlit).
Permite cargar un lote de interacciones, ver los registros aislados por validacion,
el analisis, los activos generados (con trazabilidad source_ids), y aplicar el
control de revision humana (aprobar/rechazar con comentarios) antes de publicar.
"""
import sys
from pathlib import Path

# Asegurar que la raiz del proyecto este en sys.path al ejecutar via streamlit run
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

import streamlit as st
import json

from src.ingestion.loader import cargar_json
from src.ingestion.models import LoteInteraccionesCrudo
from src.ingestion.validador import validar_lote_crudo
from src.graph.build_graph import construir_grafo
from src.storage.revision import aplicar_decision_revision, persistir_decision_en_oci

st.set_page_config(page_title="CommunityLab", page_icon="🚀", layout="wide")
st.title("🚀 CommunityLab — Motor Inteligente de Contenido")

st.sidebar.header("Cargar lote de interacciones")
archivo = st.sidebar.file_uploader("Archivo JSON", type=["json"])
DEMOS = {
    "Ejemplo completo": "interacciones_ejemplo.json",
    "01 — Contratación": "demo_01_contratacion.json",
    "02 — FAQ LangGraph": "demo_02_faq_langgraph.json",
    "03 — Mixto e inválido": "demo_03_mixto_invalido.json",
}
demo_seleccionado = st.sidebar.selectbox("Demo del jurado", list(DEMOS))
cargar_demo = st.sidebar.button("Cargar demo")

st.sidebar.divider()
st.sidebar.header("Identidad del curador")
nombre_revisor = st.sidebar.text_input("Tu nombre o alias", value="", placeholder="ej. nelson.reyes")

lote_validado = None
rechazados = []

if archivo is not None:
    data = json.load(archivo)
    crudo = LoteInteraccionesCrudo(**data)
    lote_validado, rechazados = validar_lote_crudo(crudo)
elif cargar_demo:
    ruta_demo = RAIZ_PROYECTO / "data" / DEMOS[demo_seleccionado]
    lote_validado, rechazados = cargar_json(str(ruta_demo))

if lote_validado:
    st.subheader(f"Comunidad: {lote_validado.origen_comunidad} — {lote_validado.periodo_referencia}")

    if rechazados:
        with st.expander(f"⚠️ {len(rechazados)} registro(s) aislado(s) por validacion", expanded=False):
            st.dataframe(rechazados, use_container_width=True)

    st.dataframe([i.model_dump() for i in lote_validado.interacciones], use_container_width=True)

    if st.button("Procesar y generar activos", type="primary"):
        with st.spinner("Analizando interacciones y generando activos..."):
            grafo = construir_grafo()
            estado_inicial = {
                "lote": lote_validado, "rechazados": rechazados, "analisis": [],
                "activos_generados": [], "paquete_final": None, "oci_resultado": None,
            }
            resultado = grafo.invoke(estado_inicial)
            st.session_state["resultado"] = resultado
            st.session_state.pop("decision_aplicada", None)
            for clave in ("titulo_li", "copy_li", "titular_nl", "resumen_nl", "tema_faq", "origen_faq"):
                st.session_state.pop(clave, None)

if "resultado" in st.session_state:
    paquete = st.session_state["resultado"]["paquete_final"]
    st.success("Procesamiento completado")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Procesadas", paquete.resumen_comunidad.total_interacciones_procesadas)
    col2.metric("Validas", paquete.resumen_comunidad.registros_validos)
    col3.metric("Rechazadas", paquete.resumen_comunidad.registros_rechazados)
    col4.metric("Sentimiento predominante", paquete.resumen_comunidad.sentimiento_predominante)

    if paquete.resumen_comunidad.alertas_soporte:
        st.warning(f"Alertas de soporte: {', '.join(paquete.resumen_comunidad.alertas_soporte)}")

    st.divider()
    st.subheader("Activos generados")

    if paquete.activos_distribucion_generados.post_linkedin:
        with st.expander("📱 Post LinkedIn", expanded=True):
            post = paquete.activos_distribucion_generados.post_linkedin
            st.session_state.setdefault("titulo_li", post.titulo)
            st.session_state.setdefault("copy_li", post.cuerpo)
            st.text_input("Título", key="titulo_li")
            st.text_area("Copy", height=150, key="copy_li")
            post.titulo = st.session_state["titulo_li"]
            post.cuerpo = st.session_state["copy_li"]
            st.caption(f"Engagement potencial: {post.potencial_engagement} | Fuente: {post.source_ids}")

    if paquete.activos_distribucion_generados.destaque_newsletter_semanal:
        with st.expander("📰 Newsletter semanal"):
            nl = paquete.activos_distribucion_generados.destaque_newsletter_semanal
            st.session_state.setdefault("titular_nl", nl.titular)
            st.session_state.setdefault("resumen_nl", nl.resumen)
            st.text_input("Titular", key="titular_nl")
            st.text_area("Resumen", height=100, key="resumen_nl")
            nl.titular = st.session_state["titular_nl"]
            nl.resumen = st.session_state["resumen_nl"]
            st.caption(f"Fuente: {nl.source_ids}")

    if paquete.activos_distribucion_generados.sugerencia_contenido_faq:
        with st.expander("❓ Sugerencia FAQ"):
            faq = paquete.activos_distribucion_generados.sugerencia_contenido_faq
            st.session_state.setdefault("tema_faq", faq.tema)
            st.session_state.setdefault("origen_faq", faq.origen)
            st.text_input("Tema", key="tema_faq")
            st.text_area("Origen", key="origen_faq")
            faq.tema = st.session_state["tema_faq"]
            faq.origen = st.session_state["origen_faq"]
            st.caption(f"Fuente: {faq.source_ids}")

    st.divider()
    st.subheader("🧑‍⚖️ Control de revisión humana")

    rc = paquete.control_revision_humana
    estado_color = {"pendiente": "🟡", "aprobado": "🟢", "rechazado": "🔴"}.get(rc.estado_decision, "⚪")
    st.write(f"{estado_color} **Estado actual:** {rc.estado_decision} | **Revisión N°:** {rc.numero_revision}")
    if rc.revisor:
        st.caption(f"Última decisión por: {rc.revisor} — {rc.fecha_decision}")
    if rc.comentarios:
        st.caption(f"Comentarios previos: {rc.comentarios}")

    comentarios_revision = st.text_area(
        "Comentarios de revisión (motivo obligatorio al rechazar)",
        key="comentarios_revision",
        placeholder="Describe los cambios o el motivo de rechazo",
    )

    col_aprobar, col_rechazar = st.columns(2)

    with col_aprobar:
        if st.button("✅ Aprobar y guardar versión final", type="primary", use_container_width=True):
            if not nombre_revisor:
                st.error("Ingresa tu nombre o alias en la barra lateral antes de decidir.")
            else:
                paquete_actualizado = aplicar_decision_revision(
                    paquete, estado_decision="aprobado",
                    revisor=nombre_revisor, comentarios=comentarios_revision or None,
                )
                resultado_oci = persistir_decision_en_oci(
                    paquete_actualizado,
                    periodo_referencia=st.session_state["resultado"]["lote"].periodo_referencia,
                    sufijo="aprobado",
                )
                st.session_state["resultado"]["paquete_final"] = paquete_actualizado
                st.session_state["resultado"]["oci_resultado"] = resultado_oci
                st.session_state["decision_aplicada"] = ("aprobado", resultado_oci)
                st.rerun()

    with col_rechazar:
        if st.button("❌ Rechazar", use_container_width=True):
            if not nombre_revisor:
                st.error("Ingresa tu nombre o alias en la barra lateral antes de decidir.")
            elif not (comentarios_revision or "").strip():
                st.error("El rechazo requiere un motivo en los comentarios de revisión.")
            else:
                paquete_actualizado = aplicar_decision_revision(
                    paquete, estado_decision="rechazado",
                    revisor=nombre_revisor, comentarios=comentarios_revision or None,
                )
                resultado_oci = persistir_decision_en_oci(
                    paquete_actualizado,
                    periodo_referencia=st.session_state["resultado"]["lote"].periodo_referencia,
                    sufijo="rechazado",
                )
                st.session_state["resultado"]["paquete_final"] = paquete_actualizado
                st.session_state["resultado"]["oci_resultado"] = resultado_oci
                st.session_state["decision_aplicada"] = ("rechazado", resultado_oci)
                st.rerun()

    if "decision_aplicada" in st.session_state:
        decision, resultado_oci = st.session_state["decision_aplicada"]
        if decision == "aprobado":
            st.success(f"Paquete aprobado por {nombre_revisor} y republicado en OCI.")
        else:
            st.error(f"Paquete rechazado por {nombre_revisor}. Vuelve a generar los activos si es necesario.")
        st.json(resultado_oci)

    st.divider()
    st.subheader("Almacenamiento OCI (última persistencia)")
    st.json(st.session_state["resultado"]["oci_resultado"])
