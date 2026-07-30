import os
from dotenv import load_dotenv

load_dotenv()


def get_ai_provider():
    provider = os.getenv("AI_PROVIDER", "mock").lower()

    if provider == "gemini":
        # google-genai has a comparatively expensive import. Load it only when
        # an AI action actually needs the Gemini provider.
        from ai.gemini_provider import GeminiProvider

        model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        return GeminiProvider(model=model)

    if provider == "mock":
        from ai.mock_provider import MockProvider

        return MockProvider()

    raise ValueError(f"Provider AI necunoscut: {provider}")
