import os
import random
import re
import socket
import subprocess
import threading
import requests
import json
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
try:
    load_dotenv()
except Exception:
    pass

# Описание инструментов в формате JSON Schema для передачи в LLM
flight_functions = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Поиск доступных рейсов по маршруту и дате",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Город вылета"},
                    "destination": {"type": "string", "description": "Город прилёта"},
                    "date": {"type": "string", "format": "date", "description": "Дата вылета"}
                },
                "required": ["origin", "destination", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Проверка свободных мест на рейсе",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_id": {"type": "string", "description": "Идентификатор рейса"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"], "description": "Класс"}
                },
                "required": ["flight_id", "seat_class"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_flight",
            "description": "Бронирование билета на рейс",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_id": {"type": "string", "description": "ID рейса"},
                    "passenger_name": {"type": "string", "description": "Имя пассажира"},
                    "seat_class": {"type": "string", "enum": ["economy", "business", "first"], "description": "Класс"}
                },
                "required": ["flight_id", "passenger_name", "seat_class"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Отправить сообщение получателю",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Имя или адрес получателя"},
                    "message": {"type": "string", "description": "Текст сообщения"},
                    "channel": {"type": "string", "enum": ["email", "telegram", "sms"], "description": "Канал", "default": "email"}
                },
                "required": ["recipient", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Получить курс обмена валют",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {"type": "string", "description": "Код базовой валюты"},
                    "to_currency": {"type": "string", "description": "Код целевой валюты"}
                },
                "required": ["from_currency", "to_currency"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Прогноз погоды для города",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Название города"},
                    "days": {"type": "integer", "description": "Количество дней прогноза", "default": 1}
                },
                "required": ["city"]
            }
        }
    }
]

# Генерация базы данных рейсов с фиктивными данными
def generate_flights_db():
    cities = [
        "Moscow", "Saint Petersburg", "Sochi", "Ekaterinburg", "Novosibirsk",
        "Vladivostok", "Kazan", "Krasnodar", "Rostov-on-Don", "Samara",
        "Minsk", "Kiev", "Astana", "Tashkent", "Baku",
        "London", "Paris", "Berlin", "Rome", "Madrid", "Barcelona",
        "Istanbul", "Dubai", "Abu Dhabi", "Doha", "Tehran",
        "Tokyo", "Beijing", "Shanghai", "Seoul", "Singapore",
        "New York", "Los Angeles", "Chicago", "Toronto", "Mexico City",
        "Sydney", "Melbourne", "Auckland", "Cape Town", "Nairobi"
    ]
    dates = ["2026-08-15", "2026-08-16", "2026-08-20", "2026-08-25", "2026-09-01", "2026-09-05"]
    db = {}
    flight_id_counter = 1000
    for city in cities:
        if city == "Moscow":
            continue
        for date in dates:
            fid = f"SU{flight_id_counter}"
            db[fid] = {
                "origin": "Moscow",
                "destination": city,
                "date": date,
                "available": {
                    "economy": random.randint(10, 30),
                    "business": random.randint(0, 8),
                    "first": random.randint(0, 3)
                }
            }
            flight_id_counter += 1
        for date in dates:
            fid = f"SU{flight_id_counter}"
            db[fid] = {
                "origin": city,
                "destination": "Moscow",
                "date": date,
                "available": {
                    "economy": random.randint(10, 30),
                    "business": random.randint(0, 8),
                    "first": random.randint(0, 3)
                }
            }
            flight_id_counter += 1
    extra_routes = [
        ("Saint Petersburg", "Helsinki"),
        ("Sochi", "Istanbul"),
        ("Ekaterinburg", "Dubai"),
        ("Novosibirsk", "Beijing"),
        ("Vladivostok", "Seoul"),
        ("Kiev", "Warsaw"),
        ("Minsk", "Vilnius"),
        ("Astana", "Dubai"),
        ("Tashkent", "Istanbul")
    ]
    for origin, dest in extra_routes:
        for date in dates:
            fid = f"SU{flight_id_counter}"
            db[fid] = {
                "origin": origin,
                "destination": dest,
                "date": date,
                "available": {
                    "economy": random.randint(8, 25),
                    "business": random.randint(0, 6),
                    "first": random.randint(0, 2)
                }
            }
            flight_id_counter += 1
            fid = f"SU{flight_id_counter}"
            db[fid] = {
                "origin": dest,
                "destination": origin,
                "date": date,
                "available": {
                    "economy": random.randint(8, 25),
                    "business": random.randint(0, 6),
                    "first": random.randint(0, 2)
                }
            }
            flight_id_counter += 1
    return db
flights_db = generate_flights_db()

# Реализация функций-инструментов
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
    if not results:
        new_id = f"SU{random.randint(2000, 9999)}"
        flights_db[new_id] = {
            "origin": origin,
            "destination": destination,
            "date": date,
            "available": {"economy": random.randint(5, 20), "business": random.randint(0, 5), "first": random.randint(0, 2)}
        }
        results.append({
            "flight_id": new_id,
            "origin": origin,
            "destination": destination,
            "date": date,
            "available_seats": flights_db[new_id]["available"]
        })
    return results

def check_availability(flight_id: str, seat_class: str) -> Dict:
    if flight_id not in flights_db:
        flights_db[flight_id] = {
            "origin": "Unknown",
            "destination": "Unknown",
            "date": "2026-01-01",
            "available": {"economy": 10, "business": 2, "first": 0}
        }
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    return {"available": seats > 0, "seats_left": seats}

def book_flight(flight_id: str, passenger_name: str, seat_class: str) -> Dict:
    if flight_id not in flights_db:
        flights_db[flight_id] = {
            "origin": "Unknown",
            "destination": "Unknown",
            "date": "2026-01-01",
            "available": {"economy": 10, "business": 2, "first": 0}
        }
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    if seats <= 0:
        return {"success": False, "error": f"Нет мест класса {seat_class}"}
    flights_db[flight_id]["available"][seat_class] -= 1
    booking_id = f"BK-{random.randint(1000,9999)}"
    return {
        "success": True,
        "booking_id": booking_id,
        "flight_id": flight_id,
        "passenger": passenger_name,
        "class": seat_class,
        "message": f"Бронирование {booking_id} успешно"
    }

def send_message(recipient: str, message: str, channel: str = "email") -> Dict:
    print(f"\nОтправка {channel} для {recipient}: {message}\n")
    return {"success": True, "channel": channel, "recipient": recipient, "message": message}
_exchange_cache = {}

def get_exchange_rate(from_currency: str, to_currency: str) -> Dict:
    from_cur = from_currency.upper()
    to_cur = to_currency.upper()
    cache_key = f"{from_cur}_{to_cur}"
    if cache_key in _exchange_cache:
        return _exchange_cache[cache_key]
    try:
        url = f"https://api.exchangerate.host/convert?from={from_cur}&to={to_cur}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200 and "result" in response.json():
            data = response.json()
            result = {
                "from": from_cur,
                "to": to_cur,
                "rate": data["result"],
                "timestamp": data.get("date", ""),
                "source": "API exchangerate.host"
            }
            _exchange_cache[cache_key] = result
            return result
    except Exception:
        pass
    mock_rates = {
        "USD_EUR": 0.92, "EUR_USD": 1.09,
        "USD_RUB": 93.5, "RUB_USD": 0.0107,
        "EUR_RUB": 101.2, "RUB_EUR": 0.00988,
        "USD_GBP": 0.78, "GBP_USD": 1.28,
        "EUR_GBP": 0.85, "GBP_EUR": 1.18,
    }
    mock_key = f"{from_cur}_{to_cur}"
    rate = mock_rates.get(mock_key, 1.0)
    result = {
        "from": from_cur,
        "to": to_cur,
        "rate": rate,
        "timestamp": "сегодня",
        "source": "мок интернет недоступен"
    }
    _exchange_cache[cache_key] = result
    return result

def get_weather(city: str, days: int = 1) -> Dict:
    return {
        "city": city,
        "forecast": [
            {
                "day": f"День {i+1}",
                "temp": random.randint(10, 30),
                "condition": random.choice(["Солнечно", "Облачно", "Дождь", "Снег"])
            } for i in range(min(days, 5))
        ],
        "source": "мок локальный прогноз"
    }

# Словарь для вызова функций по имени
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
    "send_message": send_message,
    "get_exchange_rate": get_exchange_rate,
    "get_weather": get_weather,
}

# Настройка LLM с привязкой инструментов
os.environ.setdefault("OPENAI_API_KEY", "dummy")
llm = ChatOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
    api_key="dummy",
    model=os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
    timeout=60,
    max_retries=0,
)
llm_with_tools = llm.bind_tools(flight_functions, tool_choice="auto")

# Вспомогательные функции для работы с Phoenix трассировкой
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

# Определение состояния агента для LangGraph
class AgentState(TypedDict):
    messages: List[Any]

# Узел агента, вызывающий LLM с инструментами
def agent_node(state: AgentState):
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_msg = SystemMessage(content=(
            "You are a helpful assistant with tools: search_flights, check_availability, book_flight, "
            "send_message, get_exchange_rate, get_weather. Always respond in Russian."
        ))
        messages = [system_msg] + messages
    try:
        response = llm_with_tools.invoke(messages)
    except Exception as e:
        error_msg = f"Извините, произошла ошибка при обращении к модели: {e}"
        response = AIMessage(content=error_msg)
    return {"messages": [response]}

# Узел выполнения инструментов
def tools_node(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": []}
    results = []
    for tc in last_message.tool_calls:
        func_name = tc["name"]
        func_args = tc["args"]
        print(f"Вызов функции: {func_name} с аргументами {func_args}")
        if func_name in available_functions:
            try:
                result = available_functions[func_name](**func_args)
                if isinstance(result, (dict, list)):
                    content = json.dumps(result, ensure_ascii=False)
                else:
                    content = str(result)
            except Exception as e:
                content = json.dumps({"error": str(e)})
            results.append(ToolMessage(content=content, tool_call_id=tc["id"]))
        else:
            results.append(ToolMessage(content=f"Функция {func_name} не найдена", tool_call_id=tc["id"]))
    return {"messages": results}

# Условный переход: если есть вызовы функций, идём в узел tools, иначе завершаем
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# Построение графа LangGraph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
workflow.add_edge("tools", "agent")
app = workflow.compile()

# Функция запуска агента с одним запросом
def run_agent(query: str) -> str:
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages}, config={"recursion_limit": 10})
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return str(final_state["messages"][-1].content) if final_state["messages"] else "Нет ответа"

# Интерактивный режим общения
def run_interactive_agent():
    print("\nМногофункциональный агент база Аэрофлота")
    print("Доступные действия: поиск и бронирование авиабилетов, отправка сообщений, курс валют, погода.")
    print("Введите запрос или exit для выхода\n")
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