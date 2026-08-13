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

# описание инструментов для LLM в формате JSON Schema
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

# реализация функций инструментов
flights_db = {
    "FL123": {"origin": "Moscow", "destination": "Dubai", "date": "2026-08-10", "available": {"economy": 10, "business": 3, "first": 1}},
    "FL456": {"origin": "Dubai", "destination": "London", "date": "2026-08-12", "available": {"economy": 5, "business": 0, "first": 2}},
    "FL789": {"origin": "Moscow", "destination": "Paris", "date": "2026-08-15", "available": {"economy": 20, "business": 4, "first": 0}},
}

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
        "source": "мок (интернет недоступен)"
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
        "source": "мок (локальный прогноз)"
    }
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
    "send_message": send_message,
    "get_exchange_rate": get_exchange_rate,
    "get_weather": get_weather,
}

# настройка LLM (не используется, но оставлена для совместимости)
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

# функция для проверки занятости порта
def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# инициализация трейсинга Phoenix
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

# форматирование результата инструмента в читаемую строку
def format_tool_result(result):
    if isinstance(result, list):
        if not result:
            return "Рейсы не найдены."
        lines = ["Найденные рейсы:"]
        for r in result:
            seats = r.get('available_seats', {})
            seats_str = ", ".join(f"{cls}: {cnt}" for cls, cnt in seats.items())
            lines.append(f"  {r['flight_id']}: {r['origin']} -> {r['destination']}, {r['date']}, места: {seats_str}")
        return "\n".join(lines)
    if isinstance(result, dict):
        if "success" in result:
            if result["success"]:
                msg = result.get('message', 'Операция успешна')
                if 'booking_id' in result:
                    msg += f" (ID брони: {result['booking_id']})"
                return f"Успешно: {msg}"
            else:
                return f"Ошибка: {result.get('error', 'Неизвестная ошибка')}"

        if "rate" in result:
            return f"Курс {result['from']}/{result['to']}: {result['rate']} (источник: {result.get('source', 'неизвестно')})"

        if "forecast" in result:
            lines = [f"Прогноз для {result['city']}:"]
            for f in result['forecast']:
                lines.append(f"  {f['day']}: {f['temp']}°C, {f['condition']}")
            return "\n".join(lines)

        if "available" in result:
            if result["available"]:
                return f"Места есть (осталось {result.get('seats_left', '?')})"
            else:
                return "Мест нет"
        return str(result)
    return str(result)

# fallback-обработчик запросов без использования LLM
def fallback_stub(messages: List[Any]) -> AIMessage:
    user_query = ""
    tool_results = []
    for m in messages:
        if isinstance(m, HumanMessage):
            user_query += m.content + " "
        elif isinstance(m, ToolMessage):
            tool_results.append(m.content)
    user_query = user_query.strip()

    # если есть результаты инструментов, формируем финальный ответ
    if tool_results:
        formatted_parts = []
        for tr in tool_results:
            try:
                data = json.loads(tr)
                formatted_parts.append(format_tool_result(data))
            except (json.JSONDecodeError, TypeError):
                formatted_parts.append(str(tr))
        return AIMessage(content="\n".join(formatted_parts))

    query_lower = user_query.lower()

    # распознавание отправки сообщения
    if any(kw in query_lower for kw in ("отправ", "письм", "сообщен", "напиши")):
        recipient_match = re.search(r'(?:для|получател[юе]?|кому|адресат[у]?)\s+([А-Яа-яA-Za-z\-]+)', user_query)
        if not recipient_match:
            recipient_match = re.search(r'(?:сообщен[ие]|письм[оа])\s+([А-Яа-яA-Za-z\-]+)', user_query)
        if recipient_match:
            recipient = recipient_match.group(1).strip()
        else:
            recipient = "Владимир"
        msg_match = re.search(r'["\'](.*?)["\']', user_query)
        if not msg_match:
            msg_match = re.search(r'(?:сообщен(?:ие|ия?)|текст)\s+([^.,]+?)(?:[,.]|$)', user_query)
        message = msg_match.group(1).strip() if msg_match else "Привет!"
        channel = "email"
        if "телеграм" in query_lower or "telegram" in query_lower:
            channel = "telegram"
        elif "смс" in query_lower or "sms" in query_lower:
            channel = "sms"
        return AIMessage(
            content="Отправляю сообщение...",
            tool_calls=[{
                "name": "send_message",
                "args": {"recipient": recipient, "message": message, "channel": channel},
                "id": "stub_send_1",
                "type": "tool_call"
            }]
        )

    # распознавание курса валют
    if any(kw in query_lower for kw in ("курс", "валют", "доллар", "евро", "рубл", "фунт", "йен", "юань")):
        currency_map = {"доллар": "USD", "евро": "EUR", "рубль": "RUB", "фунт": "GBP",
                        "йена": "JPY", "юань": "CNY", "долларов": "USD"}
        found = re.findall(r'\b(USD|EUR|RUB|GBP|JPY|CNY|доллар|евро|рубль|фунт|йена|юань|долларов)\b', user_query, re.IGNORECASE)
        codes = []
        for f in found:
            f_upper = f.upper()
            if f_upper in currency_map:
                codes.append(currency_map[f_upper])
            elif f_upper in ["USD","EUR","RUB","GBP","JPY","CNY"]:
                codes.append(f_upper)
        if len(codes) >= 2:
            from_cur, to_cur = codes[0], codes[1]
        else:
            if "доллар" in query_lower or "USD" in query_lower:
                from_cur, to_cur = "USD", "EUR"
            elif "евро" in query_lower or "EUR" in query_lower:
                from_cur, to_cur = "EUR", "USD"
            else:
                from_cur, to_cur = "USD", "RUB"
        return AIMessage(
            content=f"Запрашиваю курс {from_cur}/{to_cur}...",
            tool_calls=[{
                "name": "get_exchange_rate",
                "args": {"from_currency": from_cur, "to_currency": to_cur},
                "id": "stub_rate_1",
                "type": "tool_call"
            }]
        )

    # распознавание погоды
    if any(kw in query_lower for kw in ("погод", "weather", "температур")):
        city_match = re.search(r'(?:в|для|город[е]?)\s+([А-Яа-яA-Za-z\-]+)', user_query)
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

    # распознавание поиска рейсов
    if any(kw in query_lower for kw in ("рейс", "билет", "лететь", "вылет", "прилет")):
        origin_match = re.search(r'из\s+([А-Яа-я]+)', user_query)
        dest_match = re.search(r'в\s+([А-Яа-я]+)', user_query)
        origin = origin_match.group(1) if origin_match else "Москва"
        destination = dest_match.group(1) if dest_match else "Дубай"
        date_match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', user_query)
        if date_match:
            date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        else:
            date = "2026-08-10"
        return AIMessage(
            content="Ищу рейсы...",
            tool_calls=[{
                "name": "search_flights",
                "args": {"origin": origin, "destination": destination, "date": date},
                "id": "stub_flight_1",
                "type": "tool_call"
            }]
        )

    # общий ответ, если намерение не распознано
    return AIMessage(
        content="Я могу помочь с поиском и бронированием авиабилетов, отправкой сообщений, курсом валют и прогнозом погоды. Что вы хотите сделать?"
    )

# определение состояния агента
class AgentState(TypedDict):
    messages: List[Any]

# узел агента – теперь всегда используем fallback, чтобы избежать ошибок
def agent_node(state: AgentState):
    messages = state["messages"]
    # добавляем системный промпт, если его нет (для совместимости)
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_msg = SystemMessage(content=(
            "You are a helpful assistant with tools: search_flights, check_availability, book_flight, "
            "send_message, get_exchange_rate, get_weather. Always respond in Russian."
        ))
        messages = [system_msg] + messages
    # используем только fallback, LLM не вызываем
    response = fallback_stub(messages)
    return {"messages": [response]}

# узел выполнения инструментов
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

# условие перехода между узлами
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# построение графа на LangGraph
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

# функция запуска агента с одним запросом
def run_agent(query: str) -> str:
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages}, config={"recursion_limit": 10})
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ от агента."

# интерактивный режим
def run_interactive_agent():
    print("\n=== Многофункциональный агент ===")
    print("Доступные действия: бронирование авиабилетов, отправка сообщений, курс валют, погода.")
    print("Введите запрос или exit для выхода\n")
    while True:
        query = input("> ").strip()
        if not query or query.lower() in ('exit', 'quit', 'выйти'):
            print("До свидания!")
            break
        print("\nОтвет:", run_agent(query))

# точка входа
if __name__ == "__main__":
    if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
        init_phoenix()
    run_interactive_agent()