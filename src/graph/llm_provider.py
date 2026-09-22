"""
Selector de proveedor LLM. Permite cambiar entre Gemini, OpenAI y Claude
via variable de entorno LLM_PROVIDER, sin tocar el resto del codigo.
Valida que la API key este configurada y permite elegir el modelo exacto por env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def get_llm(temperature: float = 0.4):
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY no configurada. Configura tu API key en el archivo .env")
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=api_key,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada. Configura tu API key en el archivo .env")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada. Configura tu API key en el archivo .env")
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=api_key,
        )
    else:
        raise ValueError(f"Proveedor LLM no soportado: {provider}. Usa 'gemini', 'openai' o 'anthropic'.")
