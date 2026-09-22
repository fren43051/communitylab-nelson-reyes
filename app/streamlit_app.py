"""
Panel de curaduria CommunityLab (Streamlit).
Permite cargar un lote de interacciones, ver los registros aislados por validacion,
el analisis y los activos generados (con trazabilidad source_ids) antes de aprobar.
"""
import streamlit as st
import json

from src.ingestion.loader import cargar_json
from src.ingestion.models import LoteInteraccionesCrudo
from src.ingestion.validador import validar_lote_crudo
from src.graph.build_graph import construir_grafo

st.set_page_config(page_title="CommunityLab", page_icon="🚀", layout="wide")
st.title("🚀 CommunityLab — Motor Inteligente de Contenido")

st.sidebar.header("Cargar lote de interacciones")
archivo = st.sidebar.file_uploader("Archivo JSON", type=["json"])
usar_ejemplo = st.sidebar.button("Usar datos de ejemplo")

lote_validado = None
rechazados = []

if archivo is not None:
    data = json.load(archivo)
    crudo = LoteInteraccionesCrudo(**data)
    lote_validado, rechazados = validar_lote_crudo(crudo)
elif usar_ejemplo:
    lote_validado, rechazados = cargar_json("data/interacciones_ejemplo.json")

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
            st.text_input("Titulo", value=post.titulo, key="titulo_li")
            st.text_area("Copy", value=post.cuerpo, height=150, key="copy_li")
            st.caption(f"Engagement potencial: {post.potencial_engagement} | Fuente: {post.source_ids}")
            st.button("✅ Aprobar y publicar (simulado)", key="aprobar_li")

    if paquete.activos_distribucion_generados.destaque_newsletter_semanal:
        with st.expander("📰 Newsletter semanal"):
            nl = paquete.activos_distribucion_generados.destaque_newsletter_semanal
            st.write(f"**{nl.titular}**")
            st.write(nl.resumen)
            st.caption(f"Fuente: {nl.source_ids}")

    if paquete.activos_distribucion_generados.sugerencia_contenido_faq:
        with st.expander("❓ Sugerencia FAQ"):
            faq = paquete.activos_distribucion_generados.sugerencia_contenido_faq
            st.write(f"**Tema:** {faq.tema}")
            st.write(f"**Origen:** {faq.origen}")
            st.caption(f"Fuente: {faq.source_ids}")

    st.divider()
    st.subheader("Almacenamiento OCI")
    st.json(st.session_state["resultado"]["oci_resultado"])
