"""Инструменты для бронирования авиабилетов с поддержкой real/mock API."""

import random
from typing import Any, Dict, List

from .base import BaseTool


class FlightBookingTool(BaseTool):
    """Инструмент для поиска, проверки и бронирования авиабилетов."""

    # Mock-база данных рейсов
    MOCK_FLIGHTS = {
        "FL123": {
            "flight_id": "FL123",
            "origin": "Moscow",
            "origin_ru": "Москва (SVO)",
            "destination": "Dubai",
            "destination_ru": "Дубай (DXB)",
            "date": "2026-08-10",
            "departure_time": "08:30",
            "arrival_time": "13:45",
            "duration": "4ч 15м",
            "price_economy": 45000,
            "price_business": 120000,
            "price_first": 250000,
            "available": {"economy": 10, "business": 3, "first": 1},
            "airline": "Emirates",
        },
        "FL456": {
            "flight_id": "FL456",
            "origin": "Dubai",
            "origin_ru": "Дубай (DXB)",
            "destination": "London",
            "destination_ru": "Лондон (LHR)",
            "date": "2026-08-12",
            "departure_time": "14:00",
            "arrival_time": "18:30",
            "duration": "6ч 30м",
            "price_economy": 55000,
            "price_business": 150000,
            "price_first": 320000,
            "available": {"economy": 5, "business": 0, "first": 2},
            "airline": "British Airways",
        },
        "FL789": {
            "flight_id": "FL789",
            "origin": "Moscow",
            "origin_ru": "Москва (SVO)",
            "destination": "Paris",
            "destination_ru": "Париж (CDG)",
            "date": "2026-08-15",
            "departure_time": "10:00",
            "arrival_time": "14:20",
            "duration": "4ч 20м",
            "price_economy": 42000,
            "price_business": 110000,
            "price_first": 230000,
            "available": {"economy": 20, "business": 4, "first": 0},
            "airline": "Air France",
        },
        "FL101": {
            "flight_id": "FL101",
            "origin": "Moscow",
            "origin_ru": "Москва (SVO)",
            "destination": "London",
            "destination_ru": "Лондон (LHR)",
            "date": "2026-08-10",
            "departure_time": "22:00",
            "arrival_time": "02:30",
            "duration": "4ч 30м",
            "price_economy": 48000,
            "price_business": 130000,
            "price_first": 280000,
            "available": {"economy": 8, "business": 2, "first": 0},
            "airline": "Aeroflot",
        },
        "FL202": {
            "flight_id": "FL202",
            "origin": "Moscow",
            "origin_ru": "Москва (SVO)",
            "destination": "Paris",
            "destination_ru": "Париж (CDG)",
            "date": "2026-08-12",
            "departure_time": "11:30",
            "arrival_time": "15:50",
            "duration": "4ч 20м",
            "price_economy": 44000,
            "price_business": 115000,
            "price_first": 240000,
            "available": {"economy": 15, "business": 5, "first": 1},
            "airline": "Aeroflot",
        },
    }

    def __init__(self, use_mock: bool = True, api_key: str = ""):
        super().__init__(use_mock=use_mock)
        self.api_key = api_key
        # Копия mock-данных для мутации (уменьшение мест при бронировании)
        self._flights_db = {fid: dict(flight) for fid, flight in self.MOCK_FLIGHTS.items()}

    @property
    def name(self) -> str:
        return "flight_booking"

    @property
    def description(self) -> str:
        return "Поиск, проверка доступности и бронирование авиабилетов. Поддерживает: search_flights, check_availability, book_flight."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_flights", "check_availability", "book_flight"],
                    "description": "Действие: search_flights (поиск), check_availability (проверка), book_flight (бронирование)",
                },
                "origin": {
                    "type": "string",
                    "description": "Город вылета (SVO, MOW)",
                },
                "destination": {
                    "type": "string",
                    "description": "Город назначения (DXB, LHR, CDG)",
                },
                "date": {
                    "type": "string",
                    "format": "date",
                    "description": "Дата вылета в формате YYYY-MM-DD",
                },
                "flight_id": {
                    "type": "string",
                    "description": "Идентификатор рейса (для check_availability и book_flight)",
                },
                "seat_class": {
                    "type": "string",
                    "enum": ["economy", "business", "first"],
                    "description": "Класс: economy (эконом), business (бизнес), first (первый)",
                },
                "passenger_name": {
                    "type": "string",
                    "description": "ФИО пассажира (для бронирования)",
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
        if action == "search_flights":
            return self._mock_search_flights(**kwargs)
        elif action == "check_availability":
            return self._mock_check_availability(**kwargs)
        elif action == "book_flight":
            return self._mock_book_flight(**kwargs)
        else:
            return {"error": f"Неизвестное действие: {action}"}

    def _mock_search_flights(
        self, origin: str, destination: str, date: str
    ) -> Dict[str, Any]:
        """Поиск рейсов (mock)."""
        results = []
        origin_lower = origin.lower()
        dest_lower = destination.lower()

        for fid, flight in self._flights_db.items():
            if (
                origin_lower in flight["origin"].lower()
                or origin_lower in flight["origin_ru"].lower()
                or origin_lower in flight["destination"].lower()
                or origin_lower in flight["destination_ru"].lower()
            ):
                if (
                    dest_lower in flight["destination"].lower()
                    or dest_lower in flight["destination_ru"].lower()
                    or dest_lower in flight["origin"].lower()
                    or dest_lower in flight["origin_ru"].lower()
                ):
                    if flight["date"] == date or date == "any":
                        results.append({
                            "flight_id": fid,
                            "origin": f"{flight['origin']} ({flight['origin_ru']})",
                            "destination": f"{flight['destination']} ({flight['destination_ru']})",
                            "date": flight["date"],
                            "departure_time": flight["departure_time"],
                            "arrival_time": flight["arrival_time"],
                            "duration": flight["duration"],
                            "airline": flight["airline"],
                            "price": {
                                "economy": flight["price_economy"],
                                "business": flight["price_business"],
                                "first": flight["price_first"],
                            },
                            "available_seats": flight["available"],
                        })

        if not results:
            # Возвращаем все рейсы на запрошенную дату для демонстрации
            for fid, flight in self._flights_db.items():
                if flight["date"] == date:
                    results.append({
                        "flight_id": fid,
                        "origin": f"{flight['origin']} ({flight['origin_ru']})",
                        "destination": f"{flight['destination']} ({flight['destination_ru']})",
                        "date": flight["date"],
                        "departure_time": flight["departure_time"],
                        "arrival_time": flight["arrival_time"],
                        "duration": flight["duration"],
                        "airline": flight["airline"],
                        "price": {
                            "economy": flight["price_economy"],
                            "business": flight["price_business"],
                            "first": flight["price_first"],
                        },
                        "available_seats": flight["available"],
                    })

        return {
            "success": True,
            "count": len(results),
            "flights": results,
        }

    def _mock_check_availability(
        self, flight_id: str, seat_class: str
    ) -> Dict[str, Any]:
        """Проверка доступности (mock)."""
        if flight_id not in self._flights_db:
            return {"success": False, "error": f"Рейс {flight_id} не найден"}

        flight = self._flights_db[flight_id]
        seats = flight["available"].get(seat_class, 0)

        return {
            "success": True,
            "flight_id": flight_id,
            "seat_class": seat_class,
            "seats_available": seats,
            "price": flight[f"price_{seat_class}"],
            "route": f"{flight['origin']} → {flight['destination']}",
        }

    def _mock_book_flight(
        self, flight_id: str, passenger_name: str, seat_class: str
    ) -> Dict[str, Any]:
        """Бронирование (mock)."""
        if flight_id not in self._flights_db:
            return {"success": False, "error": f"Рейс {flight_id} не найден"}

        flight = self._flights_db[flight_id]
        seats = flight["available"].get(seat_class, 0)

        if seats <= 0:
            return {
                "success": False,
                "error": f"Нет мест класса {seat_class} на рейсе {flight_id}",
            }

        # Уменьшаем количество мест
        flight["available"][seat_class] -= 1

        booking_id = f"BK-{random.randint(10000, 99999)}"

        return {
            "success": True,
            "booking_id": booking_id,
            "flight_id": flight_id,
            "passenger": passenger_name,
            "seat_class": seat_class,
            "price": flight[f"price_{seat_class}"],
            "route": f"{flight['origin']} → {flight['destination']}",
            "date": flight["date"],
            "departure_time": flight["departure_time"],
            "message": f"✅ Бронирование {booking_id} успешно создано!",
        }

    def _real_execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Реальная реализация (заглушка для подключения к API)."""
        return {
            "success": False,
            "error": "Real API not configured. Set FLIGHT_API_KEY in environment.",
            "hint": "For demo, use MOCK_FLIGHTS mode.",
        }
