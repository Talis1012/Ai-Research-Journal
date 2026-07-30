import json
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from ai.base import AIProvider
from services.resource_limits import (
    concurrency_slot,
    consume_rate_limit,
    env_int,
)
from utils.prompts import GEMINI_SYSTEM_INSTRUCTION


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
        normalized_prompt = str(prompt or "")
        max_prompt_chars = env_int(
            "MAX_AI_PROMPT_CHARS",
            120_000,
            maximum=500_000,
        )

        if not normalized_prompt.strip():
            raise ValueError("The AI prompt cannot be empty.")

        if len(normalized_prompt) > max_prompt_chars:
            raise ValueError(
                "The selected context is too large for one AI request. "
                "Reduce the notes, sources, or manuscript sections and try again."
            )

        consume_rate_limit(
            "Gemini",
            per_user_hour=env_int("AI_REQUESTS_PER_USER_HOUR", 30, maximum=1000),
            per_user_day=env_int("AI_REQUESTS_PER_USER_DAY", 100, maximum=10000),
            global_per_minute=env_int(
                "AI_GLOBAL_REQUESTS_PER_MINUTE",
                60,
                maximum=5000,
            ),
            global_per_day=env_int(
                "AI_GLOBAL_REQUESTS_PER_DAY",
                1000,
                maximum=100000,
            ),
        )
        config_values = (
            config.model_dump(exclude_none=True)
            if config is not None
            else {}
        )
        config_values["system_instruction"] = GEMINI_SYSTEM_INSTRUCTION
        config_values.setdefault(
            "max_output_tokens",
            env_int("AI_MAX_OUTPUT_TOKENS", 4096, maximum=16384),
        )
        safe_config = types.GenerateContentConfig(**config_values)
        models = self._models_to_try()

        with concurrency_slot(
            "Gemini",
            global_limit=env_int(
                "AI_MAX_CONCURRENT_REQUESTS",
                8,
                maximum=100,
            ),
            lease_seconds=600,
        ):
            for index, model in enumerate(models):
                try:
                    return self.client.models.generate_content(
                        model=model,
                        contents=normalized_prompt,
                        config=safe_config,
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
        except json.JSONDecodeError as exc:
            raise ValueError("Gemini nu a returnat JSON valid.") from exc
