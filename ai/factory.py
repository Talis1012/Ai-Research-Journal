import os
from dotenv import load_dotenv

from ai.gemini_provider import GeminiProvider
from ai.mock_provider import MockProvider

load_dotenv()

def get_ai_provider():
    provider = os.getenv("AI_PROVIDER", "mock").lower()

    if provider == "gemini":
        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        return GeminiProvider(model=model)

    if provider == "mock":
        return MockProvider()

    raise ValueError(f"Provider AI necunoscut: {provider}")