import json
import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from ai.base import AIProvider


load_dotenv()


class GeminiProvider(AIProvider):
    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key or api_key == "pune_cheia_ta_aici":
            raise ValueError("Trebuie să setezi GEMINI_API_KEY în fișierul .env")

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.client = genai.Client(api_key=api_key)

    def generate_text(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        if not response.text:
            return ""

        return response.text.strip()

    def generate_json(self, prompt: str) -> Any:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        if not response.text:
            raise ValueError("Gemini nu a returnat niciun JSON.")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            raise ValueError(f"Gemini nu a returnat JSON valid: {response.text}")