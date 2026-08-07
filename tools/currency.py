"""Инструменты для конвертации валют с поддержкой real/mock API."""

from typing import Any, Dict

import requests

from .base import BaseTool


class CurrencyTool(BaseTool):
    """Инструмент для получения курсов валют и конвертации."""

    MOCK_RATES = {
        "RUB_USD": {"rate": 92.50, "from": "RUB", "to": "USD", "inverse_rate": 0.0108},
        "RUB_EUR": {"rate": 100.20, "from": "RUB", "to": "EUR", "inverse_rate": 0.00998},
        "RUB_AED": {"rate": 25.15, "from": "RUB", "to": "AED", "inverse_rate": 0.0398},
        "USD_RUB": {"rate": 0.0108, "from": "USD", "to": "RUB", "inverse_rate": 92.50},
        "EUR_RUB": {"rate": 0.00998, "from": "EUR", "to": "RUB", "inverse_rate": 100.20},
        "AED_RUB": {"rate": 0.0398, "from": "AED", "to": "RUB", "inverse_rate": 25.15},
        "USD_EUR": {"rate": 0.92, "from": "USD", "to": "EUR", "inverse_rate": 1.087},
        "EUR_USD": {"rate": 1.087, "from": "EUR", "to": "USD", "inverse_rate": 0.92},
    }

    def __init__(self, use_mock: bool = True, api_key: str = ""):
        super().__init__(use_mock=use_mock)
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "currency"

    @property
    def description(self) -> str:
        return "Получение курсов валют и конвертация между валютами (RUB, USD, EUR, AED)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_rate", "convert"],
                    "description": "get_rate (курс валюты), convert (конвертация суммы)",
                },
                "from_currency": {
                    "type": "string",
                    "enum": ["RUB", "USD", "EUR", "AED"],
                    "description": "Исходная валюта",
                },
                "to_currency": {
                    "type": "string",
                    "enum": ["RUB", "USD", "EUR", "AED"],
                    "description": "Целевая валюта",
                },
                "amount": {
                    "type": "number",
                    "description": "Сумма для конвертации (для action=convert)",
                },
            },
            "required": ["action"],
        }

    def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Выполнение действия."""
        if self.use_mock:
            return self._mock_execute(action, **kwargs)
        else:
            return self._real_execute(action, **kwargs)

    def _mock_execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Mock-реализация."""
        if action == "get_rate":
            return self._mock_get_rate(**kwargs)
        elif action == "convert":
            return self._mock_convert(**kwargs)
        else:
            return {"error": f"Неизвестное действие: {action}"}

    def _mock_get_rate(self, from_currency: str, to_currency: str) -> Dict[str, Any]:
        """Получение курса валют (mock)."""
        rate_key = f"{from_currency}_{to_currency}"
        if rate_key not in self.MOCK_RATES:
            # Пробуем инвертированный курс
            inverse_key = f"{to_currency}_{from_currency}"
            if inverse_key in self.MOCK_RATES:
                rate_data = self.MOCK_RATES[inverse_key]
                return {
                    "success": True,
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate": rate_data["inverse_rate"],
                    "note": f"1 {from_currency} = {rate_data['inverse_rate']:.4f} {to_currency}",
                }
            return {
                "success": False,
                "error": f"Курс {from_currency} → {to_currency} недоступен",
            }

        rate_data = self.MOCK_RATES[rate_key]
        return {
            "success": True,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": rate_data["rate"],
            "note": f"1 {from_currency} = {rate_data['rate']:.2f} {to_currency}",
        }

    def _mock_convert(self, from_currency: str, to_currency: str, amount: float) -> Dict[str, Any]:
        """Конвертация суммы (mock)."""
        rate_data = self._mock_get_rate(from_currency, to_currency)
        if not rate_data.get("success"):
            return rate_data

        rate = rate_data["rate"]
        converted = amount * rate

        return {
            "success": True,
            "from_amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": rate,
            "to_amount": converted,
            "formatted": f"{amount:,.2f} {from_currency} = {converted:,.2f} {to_currency}",
        }

    def _real_execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Реальная реализация через API."""
        if not self.api_key:
            return {
                "success": False,
                "error": "API key not configured",
                "hint": "Set CURRENCY_API_KEY in environment.",
            }
        try:
            if action == "get_rate":
                from_curr = kwargs.get("from_currency", "USD")
                to_curr = kwargs.get("to_currency", "RUB")
                url = f"https://open.er-api.com/v6/latest/{from_curr}"
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                rate = data["rates"].get(to_curr)
                if rate is None:
                    return {"success": False, "error": f"Currency {to_curr} not found"}
                return {
                    "success": True,
                    "from_currency": from_curr,
                    "to_currency": to_curr,
                    "rate": rate,
                    "source": "real_api",
                }
            elif action == "convert":
                from_curr = kwargs.get("from_currency", "USD")
                to_curr = kwargs.get("to_currency", "RUB")
                amount = kwargs.get("amount", 1)
                url = f"https://open.er-api.com/v6/latest/{from_curr}"
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                rate = data["rates"].get(to_curr)
                if rate is None:
                    return {"success": False, "error": f"Currency {to_curr} not found"}
                return {
                    "success": True,
                    "from_amount": amount,
                    "from_currency": from_curr,
                    "to_currency": to_curr,
                    "rate": rate,
                    "to_amount": amount * rate,
                    "source": "real_api",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
