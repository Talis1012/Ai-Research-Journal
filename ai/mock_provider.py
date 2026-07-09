from typing import Any

from ai.base import AIProvider


class MockProvider(AIProvider):
    def generate_text(self, prompt: str) -> str:
        return """
Acesta este un rezumat de test.

Experimentul conține observații importante, iar cercetătorul a notat rezultate care pot fi analizate ulterior.
"""

    def generate_json(self, prompt: str) -> Any:
        return {
            "ideas": [
                {
                    "title": "Idee de test",
                    "description": "Aceasta este o idee principală generată pentru testare.",
                    "evidence": "Bazată pe notițele de test.",
                    "importance": "medium"
                }
            ]
        }