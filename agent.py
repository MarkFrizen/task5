import os
import random
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END

# Загрузка переменных окружения из файла .env
load_dotenv()

# Описание функций в формате JSON Schema для передачи в LLM
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

# Мок-данные и функции-заглушки для имитации внешнего API
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

# Сопоставление имён функций с реальными функциями для вызова
available_functions = {
    "search_flights": search_flights,
    "check_availability": check_availability,
    "book_flight": book_flight,
}

# Инициализация LLM через локальный сервер LM Studio
os.environ.setdefault("OPENAI_API_KEY", "dummy")

llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",   # Адрес локального сервера LM Studio
    api_key="dummy",                       # Фиктивный ключ
    model="qwen/qwen3.5-9b",               # Имя модели, загруженной в LM Studio
    temperature=0,
)

# Привязываем инструменты к LLM для возможности вызова функций
llm_with_tools = llm.bind_tools(flight_functions)

# Подключение трейсинга Arize Phoenix
try:
    from phoenix.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor

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

# Построение графа LangGraph для агентского цикла
class AgentState(TypedDict):
    messages: List[Any]

def agent_node(state: AgentState):
    """Узел агента - вызывает LLM с текущими сообщениями."""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def tools_node(state: AgentState):
    """Узел выполнения инструментов - вызывает нужную функцию и возвращает результат."""
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
    """Условие перехода - если есть вызовы инструментов, идём в tools, иначе завершаем."""
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    else:
        return END

# Создание графа состояний
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END
})
workflow.add_edge("tools", "agent")   # После выполнения инструментов возвращаемся к агенту

# Компиляция графа в исполняемое приложение
app = workflow.compile()

# Главная функция запуска агента по текстовому запросу
def run_agent(query: str) -> str:
    """
    Запускает агента с пользовательским запросом и возвращает финальный ответ.
    """
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke({"messages": initial_messages})
    # Ищем последнее сообщение от агента без вызовов инструментов
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ от агента."

# Тестовый запуск при прямом выполнении файла
if __name__ == "__main__":
    test_query = (
        "Забронируй мне билет эконом-классом из Москвы в Дубай на 10 августа 2026 "
        "для пассажира Иванова Ивана Ивановича."
    )
    print("Запрос:", test_query)
    answer = run_agent(test_query)
    print("Ответ агента:", answer)