from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        pass

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        pass

    @abstractmethod
    def generate_embedding(
        self,
        text: str,
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[float]:
        pass
