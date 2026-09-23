"""
Punto de entrada de la API HTTP de CommunityLab.
Expone /health para chequeo general y monta el router de webhooks.
Ejecutar con: uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI

from api.webhooks import router as webhooks_router

app = FastAPI(
    title="CommunityLab API",
    version="1.0.0",
    description="API HTTP para recibir lotes de interacciones (n8n, LinkedIn simulado, etc.) y procesarlos con el pipeline de CommunityLab.",
)

app.include_router(webhooks_router)


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "communitylab-api",
    }
