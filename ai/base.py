from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        pass

    @abstractmethod
    def generate_json(self, prompt: str) -> Any:
        pass