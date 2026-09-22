"""
Panel de curaduria CommunityLab (Streamlit).
Permite cargar un lote de interacciones, ver el analisis y aprobar/editar los activos generados.
"""
import streamlit as st
import json

from src.ingestion.loader import cargar_json
from src.ingestion.models import LoteInteracciones
from src.graph.build_graph import construir_grafo

st.set_page_config(page_title="CommunityLab", page_icon="🚀", layout="wide")
st.title("🚀 CommunityLab — Motor Inteligente de Contenido")

st.sidebar.header("Cargar lote de interacciones")
archivo = st.sidebar.file_uploader("Archivo JSON", type=["json"])
usar_ejemplo = st.sidebar.button("Usar datos de ejemplo")

lote: LoteInteracciones | None = None

if archivo is not None:
    data = json.load(archivo)
    lote = LoteInteracciones(**data)
elif usar_ejemplo:
    lote = cargar_json("data/interacciones_ejemplo.json")

if lote:
    st.subheader(f"Comunidad: {lote.origen_comunidad} — {lote.periodo_referencia}")
    st.dataframe([i.model_dump() for i in lote.interacciones], use_container_width=True)

    if st.button("Procesar y generar activos", type="primary"):
        with st.spinner("Analizando interacciones y generando activos..."):
            grafo = construir_grafo()
            estado_inicial = {
                "lote": lote, "analisis": [], "activos_generados": [],
                "paquete_final": None, "oci_resultado": None,
            }
            resultado = grafo.invoke(estado_inicial)
            st.session_state["resultado"] = resultado

if "resultado" in st.session_state:
    paquete = st.session_state["resultado"]["paquete_final"]
    st.success("Procesamiento completado")

    col1, col2, col3 = st.columns(3)
    col1.metric("Interacciones procesadas", paquete.resumen_comunidad.total_interacciones_procesadas)
    col2.metric("Sentimiento predominante", paquete.resumen_comunidad.sentimiento_predominante)
    col3.metric("Temas principales", ", ".join(paquete.resumen_comunidad.temas_principales))

    st.divider()
    st.subheader("Activos generados")

    if paquete.activos_distribucion_generados.post_linkedin:
        with st.expander("📱 Post LinkedIn", expanded=True):
            post = paquete.activos_distribucion_generados.post_linkedin
            st.text_input("Titulo", value=post.titulo, key="titulo_li")
            st.text_area("Copy", value=post.copy, height=150, key="copy_li")
            st.caption(f"Engagement potencial: {post.potencial_engagement}")
            st.button("✅ Aprobar y publicar (simulado)", key="aprobar_li")

    if paquete.activos_distribucion_generados.destaque_newsletter_semanal:
        with st.expander("📰 Newsletter semanal"):
            nl = paquete.activos_distribucion_generados.destaque_newsletter_semanal
            st.write(f"**{nl.titular}**")
            st.write(nl.resumen)

    if paquete.activos_distribucion_generados.sugerencia_contenido_faq:
        with st.expander("❓ Sugerencia FAQ"):
            faq = paquete.activos_distribucion_generados.sugerencia_contenido_faq
            st.write(f"**Tema:** {faq.tema}")
            st.write(f"**Origen:** {faq.origen}")

    st.divider()
    st.subheader("Almacenamiento OCI")
    st.json(st.session_state["resultado"]["oci_resultado"])
