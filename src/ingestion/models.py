"""
Modelos de datos (Pydantic) para CommunityLab.
Reflejan el esquema de entrada/salida definido en el brief del hackathon.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


TipoInteraccion = Literal["testimonio", "pregunta_tecnica", "feedback", "otro"]


class Interaccion(BaseModel):
    autor: str
    canal: str
    tipo: TipoInteraccion
    texto: str


class LoteInteracciones(BaseModel):
    origen_comunidad: str
    periodo_referencia: str
    interacciones: list[Interaccion]


class AnalisisInteraccion(BaseModel):
    """Resultado del analisis LLM para una interaccion individual."""
    autor: str
    canal: str
    tipo: TipoInteraccion
    texto: str
    sentimiento: Literal["Muy Positivo", "Positivo", "Neutral", "Negativo", "Muy Negativo"]
    temas: list[str] = Field(default_factory=list)
    score_relevancia: float = Field(ge=0.0, le=1.0)
    categoria_accion: Literal["caso_exito", "faq_tip", "alerta_soporte", "descartar"]


class ResumenComunidad(BaseModel):
    total_interacciones_procesadas: int
    sentimiento_predominante: str
    temas_principales: list[str]


class PostLinkedIn(BaseModel):
    titulo: str
    copy: str
    canal_recomendado: str = "LinkedIn Oficial"
    potencial_engagement: Literal["Alto", "Medio", "Bajo"]


class DestaqueNewsletter(BaseModel):
    seccion: str
    titular: str
    resumen: str


class SugerenciaFAQ(BaseModel):
    tema: str
    origen: str
    status: str = "derivado_a_mentoria"


class ActivosDistribucion(BaseModel):
    post_linkedin: Optional[PostLinkedIn] = None
    destaque_newsletter_semanal: Optional[DestaqueNewsletter] = None
    sugerencia_contenido_faq: Optional[SugerenciaFAQ] = None


class AlmacenamientoOCI(BaseModel):
    bucket: str
    ruta_objeto: str
    status: str


class PaqueteDistribucion(BaseModel):
    status: Literal["exito", "error"]
    resumen_comunidad: ResumenComunidad
    activos_distribucion_generados: ActivosDistribucion
    almacenamiento_oci: Optional[AlmacenamientoOCI] = None
