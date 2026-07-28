import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from ai.base import AIProvider


load_dotenv()

logger = logging.getLogger(__name__)

TRANSIENT_GEMINI_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GeminiProvider(AIProvider):
    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key or api_key == "pune_cheia_ta_aici":
            raise ValueError("Trebuie să setezi GEMINI_API_KEY în fișierul .env")

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.fallback_model = os.getenv(
            "GEMINI_FALLBACK_MODEL",
            "gemini-3.1-flash-lite",
        ).strip()

        try:
            retry_attempts = int(os.getenv("GEMINI_RETRY_ATTEMPTS", "2"))
        except ValueError:
            retry_attempts = 2

        retry_attempts = max(1, min(retry_attempts, 4))
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(
                    attempts=retry_attempts,
                    initial_delay=1,
                    max_delay=4,
                    exp_base=2,
                    jitter=1,
                    http_status_codes=sorted(TRANSIENT_GEMINI_STATUS_CODES),
                ),
            ),
        )

    def _models_to_try(self) -> list[str]:
        models = [self.model]

        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        return models

    def _generate_content(
        self,
        prompt: str,
        config: types.GenerateContentConfig | None = None,
    ):
        models = self._models_to_try()

        for index, model in enumerate(models):
            try:
                return self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
            except errors.APIError as exc:
                has_fallback = index < len(models) - 1
                is_transient = exc.code in TRANSIENT_GEMINI_STATUS_CODES

                if not (has_fallback and is_transient):
                    raise

                logger.warning(
                    "Gemini model %s returned transient status %s; retrying "
                    "with fallback model %s.",
                    model,
                    exc.code,
                    models[index + 1],
                )

    def generate_text(self, prompt: str) -> str:
        response = self._generate_content(prompt)

        if not response.text:
            raise ValueError("Gemini nu a returnat niciun text.")

        return response.text.strip()

    def generate_json(self, prompt: str) -> Any:
        response = self._generate_content(
            prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

        if not response.text:
            raise ValueError("Gemini nu a returnat niciun JSON.")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            raise ValueError(f"Gemini nu a returnat JSON valid: {response.text}")
