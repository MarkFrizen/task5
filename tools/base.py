"""Базовый класс для всех инструментов агента."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseTool(ABC):
    """Базовый класс для инструментов с поддержкой real/mock режимов."""

    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя инструмента для LLM."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Описание инструмента для LLM."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema параметров инструмента."""
        ...

    @property
    def tool_spec(self) -> Dict[str, Any]:
        """Полная спецификация инструмента для OpenAI API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Выполнить инструмент с реальными или mock данными."""
        ...

    def __repr__(self) -> str:
        mode = "real" if not self.use_mock else "mock"
        return f"<{self.__class__.__name__} (mode={mode}, name={self.name})>"
