import os
import random
import re
import socket
import subprocess
import threading
import json
import requests
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

# 1. Описание функций в JSON Schema (расширено)
flight_functions = [
    # ---- Авиабилеты ----
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Поиск доступных рейсов по маршруту и дате вылета",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Город вылета (IATA-код или название)"},
                    "destination": {"type": "string", "description": "Город прилёта (IATA-код или название)"},
                    "date": {"type": "string", "format": "date", "description": "Дата вылета в формате ГГГГ-ММ-ДД"}
                },
                "required": ["origin", "destination", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Проверка доступности мест на выбранный рейс",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_id": {"type": "string", "description": "Уникальный идентификатор рейса"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"], "description": "Класс обслуживания"}
                },
                "required": ["flight_id", "seat_class"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_flight",
            "description": "Бронирование билета на указанный рейс",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_id": {"type": "string", "description": "Идентификатор рейса"},
                    "passenger_name": {"type": "string", "description": "Полное имя пассажира"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"], "description": "Класс обслуживания"}
                },
                "required": ["flight_id", "passenger_name", "seat_class"]
            }
        }
    },
    # ---- Отправка сообщений ----
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Отправить сообщение получателю (email, Telegram, SMS – заглушка, настраивается)",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Имя или адрес получателя"},
                    "message": {"type": "string", "description": "Текст сообщения"},
                    "channel": {"type": "string", "enum": ["email", "telegram", "sms"], "description": "Канал доставки"}
                },
                "required": ["recipient", "message"]
            }
        }
    },
    # ---- Курс валют ----
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Получить текущий курс обмена между двумя валютами (если интернет недоступен, возвращает мок-данные)",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {"type": "string", "description": "Код базовой валюты (например, USD)"},
                    "to_currency": {"type": "string", "description": "Код целевой валюты (например, EUR)"}
                },
                "required": ["from_currency", "to_currency"]
            }
        }
    },
    # ---- Погода ----
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получить прогноз погоды для города (если интернет недоступен, возвращает мок-данные)",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Название города"},
                    "days": {"type": "integer", "description": "Количество дней прогноза (1-5)", "default": 1}
                },
                "required": ["city"]
            }
        }
    }
]

# 2. Мок-данные и функции-заглушки + реальный API с fallback
flights_db = {
    "FL123": {"origin": "Moscow", "destination": "Dubai", "date": "2026-08-10", "available": {"economy": 10, "business": 3, "first": 1}},
    "FL456": {"origin": "Dubai", "destination": "London", "date": "2026-08-12", "available": {"economy": 5, "business": 0, "first": 2}},
    "FL789": {"origin": "Moscow", "destination": "Paris", "date": "2026-08-15", "available": {"economy": 20, "business": 4, "first": 0}},
}

# --- Авиабилеты ---
def search_flights(origin: str, destination: str, date: str) -> List[Dict]:
    results = []
    for fid, info in flights_db.items():
        if (info["origin"].lower() == origin.lower() and
                info["destination"].lower() == destination.lower() and
                info["date"] == date):
            results.append({
                "flight_id": fid,
                "origin": info["origin"],
                "destination": info["destination"],
                "date": info["date"],
                "available_seats": info["available"]
            })
    return results

def check_availability(flight_id: str, seat_class: str) -> Dict:
    if flight_id not in flights_db:
        return {"available": False, "error": "Рейс не найден"}
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    return {"available": seats > 0, "seats_left": seats}

def book_flight(flight_id: str, passenger_name: str, seat_class: str) -> Dict:
    if flight_id not in flights_db:
        return {"success": False, "error": "Рейс не найден"}
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    if seats <= 0:
        return {"success": False, "error": f"Нет свободных мест класса {seat_class}"}
    flights_db[flight_id]["available"][seat_class] -= 1
    booking_id = f"BK-{random.randint(1000,9999)}"
    return {
        "success": True,
        "booking_id": booking_id,
        "flight_id": flight_id,
        "passenger": passenger_name,
        "class": seat_class,
        "message": f"Бронирование {booking_id} успешно создано!"
    }

# --- Отправка сообщений (заглушка) ---
def send_message(recipient: str, message: str, channel: str = "email") -> Dict:
    # В реальности здесь был бы вызов SMTP / Telegram API / SMS-шлюза
    print(f"\n📨 [ЗАГЛУШКА] Отправка {channel} сообщения для {recipient}: {message}\n")
    return {"success": True, "channel": channel, "recipient": recipient, "message": message}

# --- Курс валют с fallback на мок (работает без интернета) ---
_EXCHANGE_CACHE = {}  # простой кэш

def get_exchange_rate(from_currency: str, to_currency: str) -> Dict:
    from_cur = from_currency.upper()
    to_cur = to_currency.upper()
    cache_key = f"{from_cur}_{to_cur}"

    # Если есть в кэше, возвращаем
    if cache_key in _EXCHANGE_CACHE:
        return _EXCHANGE_CACHE[cache_key]

    # Пытаемся получить реальный курс
    try:
        url = f"https://api.exchangerate.host/convert?from={from_cur}&to={to_cur}"
        response = requests.get(url, timeout=3)  # короткий таймаут
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                result = {
                    "from": from_cur,
                    "to": to_cur,
                    "rate": data["result"],
                    "timestamp": data.get("date", "сегодня"),
                    "source": "API exchangerate.host"
                }
                _EXCHANGE_CACHE[cache_key] = result
                return result
    except Exception:
        pass  # интернет недоступен или API не отвечает

    # Если не удалось – генерируем мок-курс (реалистичный)
    mock_rates = {
        "USD_EUR": 0.92, "EUR_USD": 1.09,
        "USD_RUB": 93.5, "RUB_USD": 0.0107,
        "EUR_RUB": 101.2, "RUB_EUR": 0.00988,
        "USD_GBP": 0.78, "GBP_USD": 1.28,
        "EUR_GBP": 0.85, "GBP_EUR": 1.18,
    }
    mock_key = f"{from_cur}_{to_cur}"
    rate = mock_rates.get(mock_key, 1.0)  # если неизвестная пара, возвращаем 1.0

    result = {
        "from": from_cur,
        "to": to_cur,
        "rate": rate,
        "timestamp": "сегодня (мок-данные)",
        "source": "локальный мок (интернет недоступен)"
    }
    _EXCHANGE_CACHE[cache_key] = result
    return result

# --- Погода с fallback на мок (работает без интернета) ---
def get_weather(city: str, days: int = 1) -> Dict:
    # Пытаемся получить реальную погоду (заглушка – в реальности можно подключить OpenWeatherMap)
    # Пока просто возвращаем мок
    weather_data = {
        "city": city,
        "forecast": [
            {
                "day": f"День {i+1}",
                "temp": random.randint(10, 30),
                "condition": random.choice(["Солнечно", "Облачно", "Дождь", "Снег"]),
                "humidity": random.randint(40, 90)
            } for i in range(min(days, 5))
        ],
        "source": "локальный мок (без интернета)"
    }
    return weather_data

# Словарь доступных функций
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
    "send_message": send_message,
    "get_exchange_rate": get_exchange_rate,
    "get_weather": get_weather,
}

# 3. Инициализация LLM (локальный сервер)
os.environ.setdefault("OPENAI_API_KEY", "dummy")
llm = ChatOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
    api_key="dummy",
    model=os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
)
llm_with_tools = llm.bind_tools(flight_functions, tool_choice="auto")

# 4. Подключение трейсинга Phoenix (опционально)
def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def init_phoenix():
    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        if not _is_port_in_use(6006):
            subprocess.Popen(["phoenix", "serve", "--port", "6006"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(30):
                if _is_port_in_use(6006):
                    break
                threading.Event().wait(0.5)
        if _is_port_in_use(6006):
            tracer_provider = register(
                project_name="flight-booking-agent",
                endpoint="http://localhost:6006/v1/traces",
            )
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            print("Трейсинг Phoenix подключён, доступен по адресу http://localhost:6006")
        else:
            print("Phoenix не запустился, трейсинг отключён.")
    except (ImportError, Exception) as e:
        print(f"Phoenix не доступен: {e}")

# 5. Умная заглушка для тестирования без LLM (расширена)
def fallback_stub(messages: List[Any]) -> AIMessage:
    query_text = " ".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
    query_lower = query_text.lower()

    # Проверка на отправку сообщения
    if "отправ" in query_lower and ("сообщен" in query_lower or "письм" in query_lower or "смс" in query_lower):
        recipient_match = re.search(r'(?:для|получател[юе]?|кому)\s+([^.,]+?)(?:[,.]|$)', query_text)
        recipient = recipient_match.group(1).strip() if recipient_match else "Владимир"
        msg_match = re.search(r'["\'](.*?)["\']', query_text)
        if not msg_match:
            msg_match = re.search(r'сообщен(?:ие|ия?)\s+([^.,]+?)(?:[,.]|$)', query_text)
        message = msg_match.group(1).strip() if msg_match else "Привет!"
        return AIMessage(
            content=f"Отправляю сообщение...",
            tool_calls=[{
                "name": "send_message",
                "args": {"recipient": recipient, "message": message, "channel": "email"},
                "id": "stub_send_1",
                "type": "tool_call"
            }]
        )

    # Проверка на курс валют
    if "курс" in query_lower and ("валют" in query_lower or "доллар" in query_lower or "евро" in query_lower):
        currencies = re.findall(r'\b(USD|EUR|RUB|GBP|JPY|CNY)\b', query_text.upper())
        if len(currencies) >= 2:
            from_cur, to_cur = currencies[0], currencies[1]
        else:
            from_cur, to_cur = "USD", "EUR"
        return AIMessage(
            content=f"Запрашиваю курс {from_cur}/{to_cur}...",
            tool_calls=[{
                "name": "get_exchange_rate",
                "args": {"from_currency": from_cur, "to_currency": to_cur},
                "id": "stub_rate_1",
                "type": "tool_call"
            }]
        )

    # Проверка на погоду
    if "погод" in query_lower or "weather" in query_lower:
        city_match = re.search(r'(?:в|для|город[е]?)\s+([А-Яа-яA-Za-z\-]+)', query_text)
        city = city_match.group(1) if city_match else "Москва"
        days_match = re.search(r'на\s+(\d+)\s+дн', query_lower)
        days = int(days_match.group(1)) if days_match else 1
        return AIMessage(
            content=f"Получаю прогноз погоды для {city} на {days} дн...",
            tool_calls=[{
                "name": "get_weather",
                "args": {"city": city, "days": days},
                "id": "stub_weather_1",
                "type": "tool_call"
            }]
        )

    # Обработка авиабилетов (упрощённо)
    # ...
    # Если ни один паттерн не подошёл – даём общий ответ
    return AIMessage(
        content="Я могу помочь с поиском и бронированием авиабилетов, отправкой сообщений, получением курса валют и прогноза погоды. Что вы хотите сделать?"
    )

# 6. LangGraph: состояние, узлы и граф
class AgentState(TypedDict):
    messages: List[Any]

def agent_node(state: AgentState):
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_msg = SystemMessage(content=(
            "You are a helpful assistant with access to the following tools:\n"
            "- search_flights, check_availability, book_flight for flight booking\n"
            "- send_message for sending messages (email/telegram/sms)\n"
            "- get_exchange_rate for currency exchange rates (works offline with mock data)\n"
            "- get_weather for weather forecasts (works offline with mock data)\n"
            "Use these tools to fulfill user requests. Always respond in Russian."
        ))
        messages = [system_msg] + messages
    try:
        response = llm_with_tools.invoke(messages)
    except Exception as e:
        print(f"Ошибка LLM: {e}, используем fallback")
        response = fallback_stub(messages)
    return {"messages": [response]}

def tools_node(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": []}
    results = []
    for tc in last_message.tool_calls:
        func_name = tc["name"]
        func_args = tc["args"]
        if func_name in available_functions:
            func = available_functions[func_name]
            result = func(**func_args)
            results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        else:
            results.append(ToolMessage(content=f"Ошибка: функция {func_name} не найдена", tool_call_id=tc["id"]))
    return {"messages": results}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")
app = workflow.compile()

# 7. Функция запуска агента
def run_agent(query: str) -> str:
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages}, config={"recursion_limit": 10})
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ от агента."

def run_interactive_agent():
    print("\n=== Многофункциональный агент (работает без интернета) ===")
    print("Доступные действия: бронирование авиабилетов, отправка сообщений, курс валют, погода.")
    print("При отсутствии интернета используются локальные мок-данные.")
    print("Введите запрос (или 'exit' для выхода):\n")
    while True:
        query = input("> ").strip()
        if not query or query.lower() in ('exit', 'quit', 'выйти'):
            print("До свидания!")
            break
        print("\nОтвет:", run_agent(query))
if __name__ == "__main__":
    if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
        init_phoenix()
    run_interactive_agent()