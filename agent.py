import os
import random
import re
import subprocess
import socket
import threading
import traceback
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END

# Загрузка переменных окружения из .env файла
load_dotenv()

# 1. Описание функций в формате JSON Schema для function calling LLM
flight_functions = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Поиск доступных рейсов по маршруту и дате вылета",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Город вылета - IATA-код или название"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Город прилёта - IATA-код или название"
                    },
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Дата вылета в формате ГГГГ-ММ-ДД"
                    }
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
                    "flight_id": {
                        "type": "string",
                        "description": "Уникальный идентификатор рейса"
                    },
                    "seat_class": {
                        "type": "string",
                        "enum": ["economy", "business", "first"],
                        "description": "Класс обслуживания - эконом, бизнес или первый"
                    }
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
                    "flight_id": {
                        "type": "string",
                        "description": "Идентификатор рейса"
                    },
                    "passenger_name": {
                        "type": "string",
                        "description": "Полное имя пассажира"
                    },
                    "seat_class": {
                        "type": "string",
                        "enum": ["economy", "business", "first"],
                        "description": "Класс обслуживания"
                    }
                },
                "required": ["flight_id", "passenger_name", "seat_class"]
            }
        }
    }
]

# 2. Мок-данные (база рейсов) и функции-заглушки для имитации внешнего API
flights_db = {
    "FL123": {
        "origin": "Moscow",
        "destination": "Dubai",
        "date": "2026-08-10",
        "available": {"economy": 10, "business": 3, "first": 1}
    },
    "FL456": {
        "origin": "Dubai",
        "destination": "London",
        "date": "2026-08-12",
        "available": {"economy": 5, "business": 0, "first": 2}
    },
    "FL789": {
        "origin": "Moscow",
        "destination": "Paris",
        "date": "2026-08-15",
        "available": {"economy": 20, "business": 4, "first": 0}
    },
}

def search_flights(origin: str, destination: str, date: str) -> List[Dict]:
    """Поиск рейсов по городу вылета, городу прилёта и дате."""
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
    """Проверка наличия свободных мест на конкретном рейсе и классе."""
    if flight_id not in flights_db:
        return {"available": False, "error": "Рейс не найден"}
    seats = flights_db[flight_id]["available"].get(seat_class, 0)
    return {"available": seats > 0, "seats_left": seats}

def book_flight(flight_id: str, passenger_name: str, seat_class: str) -> Dict:
    """Бронирование билета с уменьшением количества свободных мест."""
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
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
}

# 3. Инициализация LLM через LM Studio (локальный сервер) с привязкой инструментов
# Для LM Studio ключ не требуется, но LangChain ожидает его наличие
os.environ.setdefault("OPENAI_API_KEY", "dummy")

llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",          # стандартный адрес LM Studio
    api_key="dummy",                              # можно любое значение
    model="Qwen2.5-7B-Instruct",                      # точное имя модели из LM Studio
    temperature=0,
)

# Привязываем инструменты (если модель поддерживает function calling)
llm_with_tools = llm.bind_tools(flight_functions)

# Системный промпт для агента
SYSTEM_PROMPT = """Ты — AI-агент для бронирования авиабилетов.
Ты должен использовать доступные инструменты (search_flights, check_availability, book_flight) для выполнения запросов пользователя.
После выполнения всех необходимых инструментов, предоставь итоговый ответ на русском языке.
Твой ответ должен быть понятным и включать детали бронирования."""


# 4. Подключение трейсинга Arize Phoenix для мониторинга вызовов (опционально)
def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def _start_phoenix_server():
    """Запускает сервер Phoenix, если он ещё не работает."""
    phoenix_bin = None
    candidate = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'phoenix')
    if os.path.isfile(candidate):
        phoenix_bin = candidate
    if phoenix_bin is None:
        import sys
        phoenix_bin = os.path.join(os.path.dirname(sys.executable), 'phoenix')
    if not os.path.isfile(phoenix_bin):
        phoenix_bin = 'phoenix'
    subprocess.Popen(
        [phoenix_bin, 'serve', '--port', '6006'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if _is_port_in_use(6006):
            break
        threading.Event().wait(0.5)

def init_phoenix():
    """Инициализирует Phoenix: запускает серве�� (если нужно) и подключает трейсинг.
    Вызывается из main.py перед запуском приложения."""
    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor

        if not _is_port_in_use(6006):
            _start_phoenix_server()

        tracer_provider = register(
            project_name="flight-booking-agent",
            endpoint="http://localhost:6006/v1/traces",
        )
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        print("Трейсинг Phoenix подключён, доступен по адресу http://localhost:6006")
    except ImportError:
        print("Phoenix не установлен, трейсинг отключён.")
    except Exception as e:
        print(f"Ошибка подключения Phoenix: {e}")
        traceback.print_exc()

# 5. Умная заглушка для тестирования без подключённого LLM (парсинг запроса regex и эмуляция вызовов инструментов)
def fallback_stub(messages: List[Any]) -> AIMessage:
    """Генерирует ответ с вызовом инструментов на основе текста запроса (запасной вариант)."""
    query_text = " ".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
    query_lower = query_text.lower()

    # Извлечение города вылета
    origin_match = re.search(r'из\s+(москв|питер|санкт|казань|екатеринбург|новосибирск)', query_lower)
    origin_map = {
        'москв': 'Москва',
        'питер': 'Санкт-Петербург',
        'санкт': 'Санкт-Петербург',
        'казань': 'Казань',
        'екатеринбург': 'Екатеринбург',
        'новосибирск': 'Новосибирск'
    }
    origin = origin_map.get(origin_match.group(1) if origin_match else '', 'Москва')

    # Извлечение города прилёта
    dest_match = re.search(r'в\s+(дубай|лондон|париж|берлин|тамбов)', query_lower)
    dest_map = {
        'дубай': 'Дубай',
        'лондон': 'Лондон',
        'париж': 'Париж',
        'берлин': 'Берлин',
        'тамбов': 'Тамбов'
    }
    destination = dest_map.get(dest_match.group(1) if dest_match else '', 'Дубай')

    # Извлечение даты
    date_match = re.search(r'(\d{1,2})\s+(январ|феврал|мар|апрел|май|июн|июл|август|сентябр|октябр|ноябр|декабр)\s+(\d{4})', query_text)
    if date_match:
        day = date_match.group(1).zfill(2)
        month_str = date_match.group(2)
        year = date_match.group(3)
        month_map = {
            'январ': '01', 'феврал': '02', 'мар': '03', 'апрел': '04',
            'май': '05', 'июн': '06', 'июл': '07', 'август': '08',
            'сентябр': '09', 'октябр': '10', 'ноябр': '11', 'декабр': '12'
        }
        month = month_map.get(month_str, '08')
        extracted_date = f"{year}-{month}-{day}"
    else:
        extracted_date = "2026-08-10"

    # Извлечение имени пассажира
    pass_match = re.search(r'для\s+пассажира\s+([^.,]+?)[\.,]?\s*$', query_text)
    passenger = pass_match.group(1).strip() if pass_match else 'Иванов Иван Иванович'

    # Определение класса
    if 'бизнес' in query_lower:
        seat_class = 'business'
    elif 'первый' in query_lower or 'first' in query_lower:
        seat_class = 'first'
    else:
        seat_class = 'economy'

    # Логика: если запрос на бронирование, имитируем цепочку вызовов
    if any(kw in query_lower for kw in ['забронир', 'купить', 'book', 'оформить']):
        # Проверяем, был ли уже выполнен поиск
        has_search = any('search_flights' in str(m) for m in messages if hasattr(m, 'content'))
        if not has_search:
            return AIMessage(
                content="Сначала найду доступные рейсы...",
                tool_calls=[{
                    "name": "search_flights",
                    "args": {"origin": origin, "destination": destination, "date": extracted_date},
                    "id": "stub_search_1",
                    "type": "tool_call"
                }]
            )
        else:
            return AIMessage(
                content="Проверяю доступность мест...",
                tool_calls=[{
                    "name": "check_availability",
                    "args": {"flight_id": "FL123", "seat_class": seat_class},
                    "id": "stub_check_1",
                    "type": "tool_call"
                }]
            )
    elif any(kw in query_lower for kw in ['найди', 'search', 'поиск', 'найти']):
        return AIMessage(
            content="Ищу доступные рейсы...",
            tool_calls=[{
                "name": "search_flights",
                "args": {"origin": origin, "destination": destination, "date": extracted_date},
                "id": "stub_search_1",
                "type": "tool_call"
            }]
        )
    elif any(kw in query_lower for kw in ['доступн', 'check', 'провер']):
        return AIMessage(
            content="Проверяю доступность...",
            tool_calls=[{
                "name": "check_availability",
                "args": {"flight_id": "FL123", "seat_class": seat_class},
                "id": "stub_check_1",
                "type": "tool_call"
            }]
        )
    else:
        return AIMessage(
            content="Я могу помочь с бронированием авиабилетов. Например: "
                    '"Забронируй билет из Москвы в Дубай на 10 августа"'
        )

# 6. LangGraph: определение состояния агента, узлов (agent, tools) и направленного графа обработки запроса
class AgentState(TypedDict):
    messages: List[Any]

def agent_node(state: AgentState):
    """Узел агента - вызов LLM с текущими сообщениями."""
    messages = state["messages"]
    # Добавляем системный промпт, если его ещё нет
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    try:
        response = llm_with_tools.invoke(messages)
    except Exception as e:
        print(f"Ошибка вызова LLM с инструментами: {e}")
        try:
            # Пробуем без инструментов
            response = llm.invoke(messages)
        except Exception as e2:
            print(f"Ошибка Fallback LLM: {e2}")
            print("Использование умной заглушки для тестирования...")
            response = fallback_stub(messages)
    return {"messages": [response]}

def tools_node(state: AgentState):
    """Узел выполнения инструментов - вызов функций и возврат результатов."""
    messages = state["messages"]
    last_message = messages[-1]
    tool_calls = last_message.tool_calls
    results = []
    for tc in tool_calls:
        func_name = tc["name"]
        func_args = tc["args"]
        if func_name in available_functions:
            func = available_functions[func_name]
            result = func(**func_args)
            results.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )
        else:
            results.append(
                ToolMessage(
                    content=f"Ошибка: функция {func_name} не найдена",
                    tool_call_id=tc["id"]
                )
            )
    return {"messages": results}

def should_continue(state: AgentState):
    """Условие перехода - в tools при наличии tool_calls, иначе END."""
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    else:
        return END

# Создание графа
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
workflow.add_edge("tools", "agent")   # После выполнения инструментов возвращаемся к агенту

app = workflow.compile()

# 7. Функция запуска агента с запросом и тестовый запуск
def run_agent(query: str) -> str:
    """Запуск агента с запросом и возврат финального ответа."""
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages})
    # Ищем последнее сообщение от агента без вызовов инструментов
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ от агента."

def run_test_agent():
    """Запуск тестового запроса."""
    test_query = (
        "Забронируй мне билет эконом-классом из Москвы в Дубай на 10 августа 2026 "
        "для пассажира Иванова Ивана Ивановича."
    )
    print("Запрос:", test_query)
    answer = run_agent(test_query)
    print("Ответ агента:", answer)

if __name__ == "__main__":
    init_phoenix()
    run_test_agent()
