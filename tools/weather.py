"""Инструмент погоды с поддержкой реального API Open-Meteo."""

import requests
from typing import Any, Dict

from .base import BaseTool


# Координаты городов
CITY_COORDS = {
    "Moscow": {"lat": 55.7558, "lon": 37.6173, "name": "Москва"},
    "Dubai": {"lat": 25.2048, "lon": 55.2708, "name": "Дубай"},
    "London": {"lat": 51.5074, "lon": -0.1278, "name": "Лондон"},
    "Paris": {"lat": 48.8566, "lon": 2.3522, "name": "Париж"},
    "Berlin": {"lat": 52.5200, "lon": 13.4050, "name": "Берлин"},
}

MOCK_WEATHER = {
    "Moscow": {"temp": 22, "condition": "Ясно", "humidity": 45, "wind": 5},
    "Dubai": {"temp": 42, "condition": "Жарко и солнечно", "humidity": 30, "wind": 8},
    "London": {"temp": 18, "condition": "Облачно", "humidity": 70, "wind": 12},
    "Paris": {"temp": 24, "condition": "Тёплая погода", "humidity": 55, "wind": 6},
    "Berlin": {"temp": 20, "condition": "Переменная облачность", "humidity": 60, "wind": 10},
}


class WeatherTool(BaseTool):
    """Инструмент для получения погоды в городе."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Получение текущей погоды в городе: температура, влажность, ветер, описание условий."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Город: Moscow, Dubai, London, Paris, Berlin",
                },
            },
            "required": ["city"],
        }

    def execute(self, city: str) -> Dict[str, Any]:
        """Получение погоды."""
        if self.use_mock:
            return self._mock_weather(city)
        else:
            return self._real_weather(city)

    def _mock_weather(self, city: str) -> Dict[str, Any]:
        """Mock-реализация."""
        city_lower = city.lower()
        # Поиск города
        city_key = None
        for key in CITY_COORDS:
            if city_lower in key.lower() or city_lower in CITY_COORDS[key]["name"].lower():
                city_key = key
                break

        if not city_key:
            return {
                "success": False,
                "error": f"Город {city} не найден. Доступные: {', '.join(CITY_COORDS.keys())}",
            }

        weather = MOCK_WEATHER.get(city_key, MOCK_WEATHER["Moscow"])

        return {
            "success": True,
            "city": f"{city_key} ({CITY_COORDS[city_key]['name']})",
            "temperature": f"{weather['temp']}°C",
            "condition": weather["condition"],
            "humidity": f"{weather['humidity']}%",
            "wind": f"{weather['wind']} км/ч",
            "description": f"В {CITY_COORDS[city_key]['name']} сейчас {weather['condition'].lower()}, {weather['temp']}°C",
        }

    def _real_weather(self, city: str) -> Dict[str, Any]:
        """Реальная реализация через Open-Meteo API."""
        city_lower = city.lower()
        city_key = None
        for key in CITY_COORDS:
            if city_lower in key.lower() or city_lower in CITY_COORDS[key]["name"].lower():
                city_key = key
                break

        if not city_key:
            return {
                "success": False,
                "error": f"Город {city} не найден.",
            }

        coords = CITY_COORDS[city_key]
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": coords["lat"],
                "longitude": coords["lon"],
                "current": "temperature_2m,relative_humidity_2m,weather_state,wind_speed_10m",
                "timezone": "auto",
            }
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]

            return {
                "success": True,
                "city": f"{city_key} ({coords['name']})",
                "temperature": f"{current['temperature_2m']}°C",
                "condition": f"Код {current['weather_state']}",
                "humidity": f"{current['relative_humidity_2m']}%",
                "wind": f"{current['wind_speed_10m']} км/ч",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка получения данных: {str(e)}",
            }
