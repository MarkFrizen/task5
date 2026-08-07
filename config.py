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

    # Режимы инструментов (бронирование)
    use_mock_flight: bool = os.getenv("USE_MOCK_FLIGHT", "true").lower() == "true"

    # API ключи для реальных сервисов (если нужны)
    flight_api_key: str = os.getenv("FLIGHT_API_KEY", "")
    currency_api_key: str = os.getenv("CURRENCY_API_KEY", "")

    # RAG настройки
    index_path: str = os.getenv("INDEX_PATH", "./faiss_index")
    use_hyde: bool = os.getenv("USE_HYDE", "true").lower() == "true"
    use_multi_query: bool = os.getenv("USE_MULTI_QUERY", "true").lower() == "true"
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "50"))
    rerank_top_k: int = int(os.getenv("RERANK_TOP_K", "5"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    cross_encoder_model: str = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # DSPy оптимизация
    use_dspy: bool = os.getenv("USE_DSPY", "false").lower() == "true"
    dspy_train_data_path: str = os.getenv("DSPY_TRAIN_DATA", "./train_data.json")

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