"""
Aislamiento de la suite de pruebas.

Estas asignaciones se ejecutan al importar el conftest, es decir ANTES de que
cualquier modulo del proyecto ejecute su `load_dotenv()`. Como python-dotenv no
sobreescribe variables ya presentes (override=False), un .env real del
desarrollador nunca filtra credenciales a las pruebas, y la suite tampoco
necesita red ni OCI Vault para pasar en un clon limpio.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

SECRETO_WEBHOOK_DE_PRUEBA = "secreto-de-prueba-no-usar-en-produccion"

os.environ["SECRETS_BACKEND"] = "env"
os.environ["SECRETS_CACHE_TTL"] = "0"
os.environ["WEBHOOK_SECRET"] = SECRETO_WEBHOOK_DE_PRUEBA
os.environ["WEBHOOK_MAX_ITEMS"] = "100"
os.environ["LLM_PROVIDER"] = "anthropic"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-falsa-solo-para-pruebas"
os.environ.pop("OCI_VAULT_ID", None)

import pytest

from src.config import secrets as gestor_secretos


@pytest.fixture(autouse=True)
def aislar_secretos(monkeypatch):
    """Fuerza el backend de entorno en cada prueba y vacia la cache de secretos."""
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    monkeypatch.setenv("SECRETS_CACHE_TTL", "0")
    monkeypatch.setenv("WEBHOOK_SECRET", SECRETO_WEBHOOK_DE_PRUEBA)
    monkeypatch.delenv("OCI_VAULT_ID", raising=False)
    gestor_secretos.limpiar_cache()
    yield
    gestor_secretos.limpiar_cache()
