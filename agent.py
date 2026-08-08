import os
import random
import re
import socket
import subprocess
import threading
import requests
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
load_dotenv()

# 1. Описание функций в формате JSON Schema
# Эти описания передаются в LLM, чтобы она знала,
# какие функции можно вызывать и с какими параметрами.
# Список инструментов, доступных агенту.
# Каждый инструмент содержит имя, описание и схему параметров.
flight_functions = [
    # Инструмент: поиск авиарейсов
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

    # Инструмент: проверка наличия мест на рейсе
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

    # Инструмент: бронирование билета
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

    # Инструмент: отправка сообщения
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
                    "channel": {"type": "string", "enum": ["email", "telegram", "sms"], "description": "Канал"}
                },
                "required": ["recipient", "message"]
            }
        }
    },

    # Инструмент: получение курса валют
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

    # Инструмент: прогноз погоды
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

# 2. Реализация функций-инструментов
# Эти функции вызываются агентом при необходимости.
# База данных рейсов
flights_db = {
    "FL123": {"origin": "Moscow", "destination": "Dubai", "date": "2026-08-10", "available": {"economy": 10, "business": 3, "first": 1}},
    "FL456": {"origin": "Dubai", "destination": "London", "date": "2026-08-12", "available": {"economy": 5, "business": 0, "first": 2}},
    "FL789": {"origin": "Moscow", "destination": "Paris", "date": "2026-08-15", "available": {"economy": 20, "business": 4, "first": 0}},
}

def search_flights(origin: str, destination: str, date: str) -> List[Dict]:
    """Поиск рейсов по городу вылета, прилёта и дате."""
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
    """Проверка наличия мест на конкретном рейсе и классе."""
    if flight_id not in flights_db:
        return {"available": False, "error": "Рейс не найден"}
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    return {"available": seats > 0, "seats_left": seats}

def book_flight(flight_id: str, passenger_name: str, seat_class: str) -> Dict:
    """Бронирование билета с уменьшением количества мест."""
    if flight_id not in flights_db:
        return {"success": False, "error": "Рейс не найден"}
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
    """Отправка сообщения (заглушка, только вывод в консоль)."""
    print(f"\n📨 Отправка {channel} для {recipient}: {message}\n")
    return {"success": True, "channel": channel, "recipient": recipient, "message": message}

# Кэш для курсов валют
_exchange_cache = {}

def get_exchange_rate(from_currency: str, to_currency: str) -> Dict:
    """
    Получение курса валют.
    Сначала пытается запросить реальный API (exchangerate.host),
    при ошибке или отсутствии сети возвращает мок-данные.
    """
    from_cur = from_currency.upper()
    to_cur = to_currency.upper()
    cache_key = f"{from_cur}_{to_cur}"

    # Если курс уже есть в кэше, возвращаем его
    if cache_key in _exchange_cache:
        return _exchange_cache[cache_key]

    # Пытаемся получить реальный курс через бесплатное API
    try:
        url = f"https://api.exchangerate.host/convert?from={from_cur}&to={to_cur}"
        response = requests.get(url, timeout=3)  # короткий таймаут
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
        pass  # интернет недоступен или API не отвечает

    # Если не удалось, используем мок-курсы
    mock_rates = {
        "USD_EUR": 0.92, "EUR_USD": 1.09,
        "USD_RUB": 93.5, "RUB_USD": 0.0107,
        "EUR_RUB": 101.2, "RUB_EUR": 0.00988,
        "USD_GBP": 0.78, "GBP_USD": 1.28,
        "EUR_GBP": 0.85, "GBP_EUR": 1.18,
    }
    mock_key = f"{from_cur}_{to_cur}"
    rate = mock_rates.get(mock_key, 1.0)  # для неизвестной пары – 1.0
    result = {
        "from": from_cur,
        "to": to_cur,
        "rate": rate,
        "timestamp": "сегодня",
        "source": "мок (интернет недоступен)"
    }
    _exchange_cache[cache_key] = result
    return result

def get_weather(city: str, days: int = 1) -> Dict:
    """
    Прогноз погоды – всегда возвращает мок-данные.
    Легко заменить на реальный API (OpenWeatherMap и т.п.).
    """
    return {
        "city": city,
        "forecast": [
            {
                "day": f"День {i+1}",
                "temp": random.randint(10, 30),
                "condition": random.choice(["Солнечно", "Облачно", "Дождь", "Снег"])
            } for i in range(min(days, 5))  # максимум 5 дней
        ],
        "source": "мок (локальный прогноз)"
    }

# Словарь для вызова функций по имени (используется в узле tools_node)
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
    "send_message": send_message,
    "get_exchange_rate": get_exchange_rate,
    "get_weather": get_weather,
}

# 3. Настройка LLM
# Используем LangChain для единообразного вызова.
os.environ.setdefault("OPENAI_API_KEY", "dummy")  # для локального сервера ключ не нужен
llm = ChatOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),  # адрес локального сервера
    api_key="dummy",                                                # фиктивный ключ
    model=os.getenv("LLM_MODEL", "qwen/qwen3.5-9b"),               # модель, загруженная в LM Studio
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),        # температура генерации
)

# Привязываем описанные инструменты к LLM
llm_with_tools = llm.bind_tools(flight_functions, tool_choice="auto")

# 4. Трейсинг Phoenix
# Используется для мониторинга и отладки работы агента.
def _is_port_in_use(port: int) -> bool:
    """Проверяет, занят ли порт (для запуска Phoenix)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def init_phoenix():
    """Запускает Phoenix сервер и подключает инструментарий LangChain."""
    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        # Если Phoenix не запущен – пытаемся запустить
        if not _is_port_in_use(6006):
            subprocess.Popen(["phoenix", "serve", "--port", "6006"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Ждём запуска
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
            print("✅ Трейсинг Phoenix подключён, доступен по адресу http://localhost:6006")
        else:
            print("⚠️ Phoenix не запустился, трейсинг отключён.")
    except (ImportError, Exception) as e:
        print(f"⚠️ Phoenix не доступен: {e}")

# 5. Заглушка для работы без LLM
# Если LLM недоступна, этот парсер анализирует запрос
# и вызывает подходящую функцию напрямую.
def fallback_stub(messages: List[Any]) -> AIMessage:
    """
    Генерирует ответ с вызовом инструментов на основе текста запроса,
    без обращения к LLM. Используется при ошибках или для тестирования.
    """
    query_text = " ".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
    query_lower = query_text.lower()

    # --- Обработка отправки сообщения ---
    if "отправ" in query_lower and ("сообщен" in query_lower or "письм" in query_lower):
        recipient_match = re.search(r'(?:для|получател[юе]?|кому)\s+([^.,]+?)(?:[,.]|$)', query_text)
        recipient = recipient_match.group(1).strip() if recipient_match else "Владимир"
        msg_match = re.search(r'["\'](.*?)["\']', query_text)
        if not msg_match:
            msg_match = re.search(r'сообщен(?:ие|ия?)\s+([^.,]+?)(?:[,.]|$)', query_text)
        message = msg_match.group(1).strip() if msg_match else "Привет!"
        return AIMessage(
            content="Отправляю сообщение...",
            tool_calls=[{
                "name": "send_message",
                "args": {"recipient": recipient, "message": message, "channel": "email"},
                "id": "stub_send_1",
                "type": "tool_call"
            }]
        )

    # --- Обработка курса валют ---
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

    # --- Обработка погоды ---
    if "погод" in query_lower or "weather" in query_lower:
        city_match = re.search(r'(?:в|для|город[е]?)\s+([А-Яа-яA-Za-z\-]+)', query_text)
        city = city_match.group(1) if city_match else "Москва"
        days_match = re.search(r'на\s+(\d+)\s+дн', query_lower)
        days = int(days_match.group(1)) if days_match else 1
        return AIMessage(
            content=f"Получаю погоду для {city} на {days} дн...",
            tool_calls=[{
                "name": "get_weather",
                "args": {"city": city, "days": days},
                "id": "stub_weather_1",
                "type": "tool_call"
            }]
        )

    # --- Обработка поиска рейсов ---
    if any(kw in query_lower for kw in ["рейс", "билет", "лететь", "вылет"]):
        origin_match = re.search(r'из\s+([А-Яа-я]+)', query_text)
        dest_match = re.search(r'в\s+([А-Яа-я]+)', query_text)
        origin = origin_match.group(1) if origin_match else "Москва"
        destination = dest_match.group(1) if dest_match else "Дубай"
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', query_text)
        date = date_match.group(0) if date_match else "2026-08-10"
        return AIMessage(
            content="Ищу рейсы...",
            tool_calls=[{
                "name": "search_flights",
                "args": {"origin": origin, "destination": destination, "date": date},
                "id": "stub_flight_1",
                "type": "tool_call"
            }]
        )

    # Если ничего не подошло – даём общий ответ
    return AIMessage(
        content="Я могу помочь с поиском и бронированием авиабилетов, отправкой сообщений, курсом валют и прогнозом погоды. Что вы хотите сделать?"
    )

# 6. LangGraph: определение состояния, узлов и графа
#    Здесь строится агентский цикл:
#    агент -> решение вызвать функцию -> выполнение -> возврат результата -> агент
class AgentState(TypedDict):
    """Состояние агента – просто список сообщений."""
    messages: List[Any]

def agent_node(state: AgentState):
    """
    Узел агента: вызывает LLM с текущим списком сообщений.
    Если LLM недоступна, использует fallback_stub.
    """
    messages = state["messages"]
    # Добавляем системный промпт, если его ещё нет
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_msg = SystemMessage(content=(
            "You are a helpful assistant with tools: search_flights, check_availability, book_flight, "
            "send_message, get_exchange_rate, get_weather. Always respond in Russian."
        ))
        messages = [system_msg] + messages
    try:
        response = llm_with_tools.invoke(messages)
    except Exception as e:
        print(f"⚠️ Ошибка LLM: {e}, используем fallback")
        response = fallback_stub(messages)
    return {"messages": [response]}

def tools_node(state: AgentState):
    """
    Узел выполнения инструментов: вызывает соответствующую функцию
    для каждого tool_call и возвращает результат в виде ToolMessage.
    """
    messages = state["messages"]
    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": []}
    results = []
    for tc in last_message.tool_calls:
        func_name = tc["name"]
        func_args = tc["args"]
        if func_name in available_functions:
            # Безопасно вызываем функцию с переданными аргументами
            result = available_functions[func_name](**func_args)
            results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        else:
            results.append(ToolMessage(content=f"Функция {func_name} не найдена", tool_call_id=tc["id"]))
    return {"messages": results}

def should_continue(state: AgentState):
    """
    Условный переход: если в последнем сообщении есть tool_calls,
    переходим в узел tools, иначе завершаем работу (END).
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# Строим граф
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)      # узел агента
workflow.add_node("tools", tools_node)      # узел инструментов
workflow.set_entry_point("agent")           # начинаем с агента
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
workflow.add_edge("tools", "agent")         # после инструментов возвращаемся к агенту

# Компилируем граф в исполняемое приложение
app = workflow.compile()

# 7. Основные функции для запуска агента
def run_agent(query: str) -> str:
    """
    Запускает агента с заданным запросом и возвращает финальный ответ.
    """
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages}, config={"recursion_limit": 10})
    # Ищем последнее AIMessage без tool_calls (это и есть ответ)
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ от агента."

def run_interactive_agent():
    """
    Интерактивный режим: пользователь вводит запросы в консоли.
    """
    print("\n=== Многофункциональный агент (работает без интернета) ===")
    print("Доступные действия: бронирование авиабилетов, отправка сообщений, курс валют, погода.")
    print("Введите запрос (или 'exit' для выхода):\n")
    while True:
        query = input("> ").strip()
        if not query or query.lower() in ('exit', 'quit', 'выйти'):
            print("До свидания!")
            break
        print("\nОтвет:", run_agent(query))

# Точка входа при запуске скрипта
if __name__ == "__main__":
    # Включаем Phoenix, если указано в .env
    if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
        init_phoenix()
    run_interactive_agent()