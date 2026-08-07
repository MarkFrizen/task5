"""Конфигурация приложения."""

import os
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class AppConfig:
    """Конфигурация приложения."""

    # LLM настройки (LM Studio)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    llm_model: str = os.getenv("LLM_MODEL", "qwen/qwen3.5-9b")
    llm_api_key: str = os.getenv("OPENAI_API_KEY", "dummy")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))

    # Режимы инструментов
    use_mock_flight: bool = os.getenv("USE_MOCK_FLIGHT", "true").lower() == "true"
    use_mock_currency: bool = os.getenv("USE_MOCK_CURRENCY", "true").lower() == "true"
    use_mock_weather: bool = os.getenv("USE_MOCK_WEATHER", "true").lower() == "true"

    # API ключи для реальных сервисов
    flight_api_key: str = os.getenv("FLIGHT_API_KEY", "")
    currency_api_key: str = os.getenv("CURRENCY_API_KEY", "")

    # FastAPI настройки
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # LangGraph настройки
    recursion_limit: int = int(os.getenv("RECURSION_LIMIT", "10"))

    # Phoenix трейсинг
    phoenix_enabled: bool = os.getenv("PHOENIX_ENABLED", "false").lower() == "true"
    phoenix_endpoint: str = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")

    def get_llm_config(self) -> Dict[str, Any]:
        return {
            "base_url": self.llm_base_url,
            "model": self.llm_model,
            "api_key": self.llm_api_key,
            "temperature": self.llm_temperature,
        }


# Глобальный экземпляр конфигурации
config = AppConfig()
