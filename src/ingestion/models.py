"""
Modelos de datos (Pydantic) para CommunityLab.
Incorpora validacion en dos capas (admision permisiva + validacion estricta),
trazabilidad de activos generados (source_ids) y verificacion de persistencia en OCI,
siguiendo el patron adoptado del Grupo 34 (esquemas.py / validador.py).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


TipoInteraccion = Literal["testimonio", "pregunta_tecnica", "feedback", "otro", "sin_clasificar"]


def default_fecha_generacion() -> datetime:
    return datetime.now(timezone.utc)


# =====================================================================
# CAPA 1: INGESTA - ADMISION PERMISIVA
# =====================================================================

class MetadataOrigen(BaseModel):
    plataforma: str = Field(default="desconocida", description="Discord, Slack, GitHub, Form, etc.")
    identificador_original: Optional[str] = Field(default=None, description="ID nativo en la plataforma de origen")
    fecha: Optional[str] = Field(default=None, description="Timestamp ISO-8601 del mensaje original")


class InteraccionCruda(BaseModel):
    """Esquema permisivo a nivel de registro: admite lotes crudos sin bloquear la ingestion completa."""
    id: str
    autor: str = Field(default="Anonimo")
    canal: str
    tipo: TipoInteraccion = Field(default="sin_clasificar")
    texto: Optional[str] = Field(default="")
    metadata_origen: MetadataOrigen = Field(default_factory=MetadataOrigen)


class LoteInteraccionesCrudo(BaseModel):
    """Contrato del sobre de entrada tal como llega (JSON/CSV/Webhook), sin garantias de calidad."""
    schema_version: str = Field(default="1.0.0")
    origen_comunidad: str
    periodo_referencia: str
    interacciones: list[InteraccionCruda] = Field(..., min_length=1)


# =====================================================================
# CAPA 2: VALIDACION ESTRICTA (aplicada registro por registro)
# =====================================================================

class Interaccion(BaseModel):
    """Modelo estricto exigido antes de enviar un registro al grafo de analisis."""
    id: str
    autor: str
    canal: str
    tipo: TipoInteraccion
    texto: str = Field(..., min_length=1)
    metadata_origen: MetadataOrigen = Field(default_factory=MetadataOrigen)

    @field_validator("texto")
    @classmethod
    def validar_texto_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El texto de la interaccion no puede estar vacio ni contener solo espacios")
        return v.strip()


class LoteInteracciones(BaseModel):
    origen_comunidad: str
    periodo_referencia: str
    interacciones: list[Interaccion]


# =====================================================================
# ANALISIS COGNITIVO
# =====================================================================

class PuntuacionRelevancia(BaseModel):
    """Rubrica explicable de 3 criterios en lugar de un score arbitrario del LLM."""
    evidencia_explicita: int = Field(..., ge=0, le=2, description="Datos/hechos verificables (0-2)")
    utilidad_comunitaria: int = Field(..., ge=0, le=2, description="Valor formativo/tecnico/motivacional (0-2)")
    claridad_contexto: int = Field(..., ge=0, le=2, description="Claridad tematica y contexto (0-2)")
    total: int = Field(..., ge=0, le=6)


class AnalisisInteraccion(BaseModel):
    """Resultado del analisis LLM para una interaccion individual."""
    id: str
    autor: str
    canal: str
    tipo: TipoInteraccion
    texto: str
    sentimiento: Literal["Muy Positivo", "Positivo", "Neutral", "Negativo", "Muy Negativo"]
    temas: list[str] = Field(default_factory=list)
    puntuacion_relevancia: PuntuacionRelevancia
    motivo_seleccion: str = Field(..., min_length=10, description="Justificacion objetiva de la puntuacion")
    categoria_accion: Literal["caso_exito", "faq_tip", "alerta_soporte", "descartar"]
    requiere_soporte: bool = Field(default=False)

    @property
    def score_relevancia(self) -> float:
        return round(self.puntuacion_relevancia.total / 6.0, 3)


class ResumenComunidad(BaseModel):
    total_interacciones_procesadas: int
    registros_validos: int
    registros_rechazados: int = Field(default=0, ge=0)
    sentimiento_predominante: str
    temas_principales: list[str]
    alertas_soporte: list[str] = Field(default_factory=list)


# =====================================================================
# ACTIVOS DE DISTRIBUCION - con trazabilidad (source_ids)
# =====================================================================

class PostLinkedIn(BaseModel):
    titulo: str = Field(..., min_length=5)
    cuerpo: str = Field(..., min_length=20)
    canal_recomendado: str = "LinkedIn Oficial"
    potencial_engagement: Literal["Alto", "Medio", "Bajo"]
    source_ids: list[str] = Field(..., min_length=1, description="IDs de mensajes que respaldan el post")


class DestaqueNewsletter(BaseModel):
    seccion: str
    titular: str = Field(..., min_length=5)
    resumen: str = Field(..., min_length=20)
    source_ids: list[str] = Field(..., min_length=1, description="IDs de mensajes que respaldan la sintesis")


class SugerenciaFAQ(BaseModel):
    tema: str
    origen: str
    status: str = "derivado_a_mentoria"
    source_ids: list[str] = Field(..., min_length=1, description="IDs de mensajes que originaron la duda")


class ActivosDistribucion(BaseModel):
    post_linkedin: Optional[PostLinkedIn] = None
    destaque_newsletter_semanal: Optional[DestaqueNewsletter] = None
    sugerencia_contenido_faq: Optional[SugerenciaFAQ] = None


# =====================================================================
# PERSISTENCIA OCI - con verificacion de lectura
# =====================================================================

class AlmacenamientoOCI(BaseModel):
    bucket: str = Field(default="communitylab-activos-marketing")
    ruta_objeto: str = Field(..., description="Ruta inmutable: activos/{periodo}/{run_id}/paquete.json")
    status: Literal["guardado_con_exito", "guardado_error", "no_iniciado"] = "no_iniciado"
    comprobacion_lectura: bool = Field(
        default=False,
        description="True solo si la aplicacion releyo y verifico el objeto en OCI tras subirlo",
    )


class MetadatosEjecucion(BaseModel):
    modelo: str = Field(..., description="Identificador exacto del LLM usado")
    latencia_ms: int = Field(default=0, ge=0)


class PaqueteDistribucion(BaseModel):
    schema_version: str = Field(default="1.1.0")
    status: Literal["exito", "error"]
    fecha_generacion: datetime = Field(default_factory=default_fecha_generacion)
    resumen_comunidad: ResumenComunidad
    activos_distribucion_generados: ActivosDistribucion
    almacenamiento_oci: Optional[AlmacenamientoOCI] = None
    metadatos_ejecucion: Optional[MetadatosEjecucion] = None
