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
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
load_dotenv()
from rag.retriever import RAGRetriever
from rag.reranker import Reranker
from rag.generator import AnswerGenerator
from rag.judge import Judge
from config import config

# 1. Описание функций для бронирования (оставляем как есть)
flight_functions = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Поиск доступных рейсов по маршруту и дате вылета",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Город вылета - IATA-код или название"},
                    "destination": {"type": "string", "description": "Город прилёта - IATA-код или название"},
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
    }
]

# 2. Мок-данные и функции-заглушки
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

# 3. Инициализация LLM
os.environ.setdefault("OPENAI_API_KEY", config.llm_api_key)
llm = ChatOpenAI(
    base_url=config.llm_base_url,
    api_key=config.llm_api_key,
    model=config.llm_model,
    temperature=config.llm_temperature,
)
llm_with_tools = llm.bind_tools(flight_functions, tool_choice="auto")

# 4. Инициализация RAG-компонентов (если индекс существует)
retriever = None
reranker = None
generator = None
judge = None

if os.path.exists(config.index_path):
    retriever = RAGRetriever(config)
    retriever.load_index(config.index_path)
    reranker = Reranker(model_name=config.cross_encoder_model)
    generator = AnswerGenerator(llm)
    judge = Judge(llm)
else:
    print(f"Предупреждение: индекс не найден по пути {config.index_path}. RAG-функции будут недоступны.")

# 5. Подключение трейсинга Phoenix (оставляем)
def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def _start_phoenix_server():
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

# 6. Умная заглушка (оставляем для бронирования)
def fallback_stub(messages: List[Any]) -> AIMessage:
    """Генерирует ответ с вызовом инструментов на основе текста запроса в случае ошибки"""
    query_text = " ".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
    query_lower = query_text.lower()

    origin_match = re.search(r'из\s+(москв|питер|санкт|казань|екатеринбург|новосибирск)', query_lower)
    origin_map = {
        'москв': 'Москва', 'питер': 'Санкт-Петербург', 'санкт': 'Санкт-Петербург',
        'казань': 'Казань', 'екатеринбург': 'Екатеринбург', 'новосибирск': 'Новосибирск'
    }
    origin = origin_map.get(origin_match.group(1) if origin_match else '', 'Москва')

    dest_match = re.search(r'в\s+(дубай|лондон|париж|берлин|тамбов)', query_lower)
    dest_map = {
        'дубай': 'Дубай', 'лондон': 'Лондон', 'париж': 'Париж',
        'берлин': 'Берлин', 'тамбов': 'Тамбов'
    }
    destination = dest_map.get(dest_match.group(1) if dest_match else '', 'Дубай')

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

    pass_match = re.search(r'для\s+пассажира\s+([^.,]+?)[\.,]?\s*$', query_text)
    passenger = pass_match.group(1).strip() if pass_match else 'Иванов Иван Иванович'

    if 'бизнес' in query_lower:
        seat_class = 'business'
    elif 'первый' in query_lower or 'first' in query_lower:
        seat_class = 'first'
    else:
        seat_class = 'economy'

    has_tool_results = any(isinstance(m, ToolMessage) for m in messages)
    if has_tool_results:
        return AIMessage(
            content=(
                f"Билет успешно забронирован! Рейс {origin} → {destination} "
                f"на {extracted_date}, класс: {seat_class}. "
                f"Пассажир: {passenger}."
            )
        )
    if any(kw in query_lower for kw in ['забронир', 'купить', 'book', 'оформить']):
        return AIMessage(
            content="Сначала найду доступные рейсы...",
            tool_calls=[{
                "name": "search_flights",
                "args": {"origin": origin, "destination": destination, "date": extracted_date},
                "id": "stub_search_1",
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

# 7. LangGraph: состояние, узлы и граф
class AgentState(TypedDict):
    messages: List[Any]
    retrieved_docs: List[Document]
    reranked_docs: List[Document]
    final_answer: str

# Функция вызова LLM с обработкой ошибок (оставляем)
def _invoke_llm_with_retry(messages: List[Any], tools: bool = True) -> AIMessage:
    import httpx
    from openai import OpenAI as SyncOpenAI
    from langchain_core.messages import convert_to_openai_messages

    openai_messages = convert_to_openai_messages(messages)
    client = SyncOpenAI(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    openai_functions = flight_functions if tools else None
    try:
        if tools and openai_functions:
            response = client.chat.completions.create(
                model=config.llm_model,
                messages=openai_messages,
                tools=openai_functions,
                tool_choice="auto",
                temperature=config.llm_temperature,
            )
        else:
            response = client.chat.completions.create(
                model=config.llm_model,
                messages=openai_messages,
                temperature=config.llm_temperature,
            )
        choice = response.choices[0]
        ai_msg = AIMessage(
            content=choice.message.content or "",
            additional_kwargs={"function_call": choice.message.tool_calls},
        )
        if choice.message.tool_calls:
            ai_msg.tool_calls = [{
                "name": tc.function.name,
                "args": eval(tc.function.arguments) if tc.function.arguments else {},
                "id": tc.id,
                "type": "tool_call"
            } for tc in choice.message.tool_calls]
        return ai_msg
    except Exception as e:
        raise e

# Узлы для бронирования (старые)
def booking_agent_node(state: AgentState):
    messages = state["messages"]
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    if not has_system:
        messages = [SystemMessage(content="You are a helpful assistant that helps users book flights.")] + messages
    try:
        response = _invoke_llm_with_retry(messages, tools=True)
    except Exception:
        response = fallback_stub(messages)
    return {"messages": [response]}

def tools_node(state: AgentState):
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
            results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        else:
            results.append(ToolMessage(
                content=f"Ошибка: функция {func_name} не найдена",
                tool_call_id=tc["id"]
            ))
    return {"messages": results}

def should_continue_booking(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    else:
        return END

# Узлы для RAG
def rag_retrieve_node(state: AgentState):
    if retriever is None:
        return {"final_answer": "RAG не инициализирован. Проверьте наличие индекса."}
    query = state["messages"][-1].content
    docs = retriever.retrieve(query)
    state["retrieved_docs"] = docs
    return state

def rag_rerank_node(state: AgentState):
    if reranker is None:
        return state
    query = state["messages"][-1].content
    docs = reranker.rerank(query, state["retrieved_docs"], top_k=config.rerank_top_k)
    state["reranked_docs"] = docs
    return state

def rag_generate_node(state: AgentState):
    if generator is None:
        return {"final_answer": "Генератор не инициализирован."}
    query = state["messages"][-1].content
    answer = generator.generate(query, state["reranked_docs"])
    state["final_answer"] = answer
    state["messages"].append(AIMessage(content=answer))
    return state

# Определение типа запроса (бронирование или RAG)
def classify_query(state: AgentState) -> str:
    query = state["messages"][-1].content.lower()
    # Если есть ключевые слова бронирования – идём по старому пути
    booking_keywords = ['забронир', 'билет', 'рейс', 'вылет', 'прилёт', 'flight', 'book', 'search_flights']
    if any(kw in query for kw in booking_keywords):
        return "booking"
    else:
        return "rag"

# Создание графа с условным переходом
workflow = StateGraph(AgentState)

# Добавляем узлы бронирования
workflow.add_node("booking_agent", booking_agent_node)
workflow.add_node("tools", tools_node)

# Добавляем RAG-узлы
workflow.add_node("rag_retrieve", rag_retrieve_node)
workflow.add_node("rag_rerank", rag_rerank_node)
workflow.add_node("rag_generate", rag_generate_node)

# Начальная точка – классификация
workflow.set_entry_point("classify")
workflow.add_node("classify", lambda state: state)  # фиктивный узел, просто для перехода
workflow.add_conditional_edges("classify", classify_query, {
    "booking": "booking_agent",
    "rag": "rag_retrieve"
})

# Граф для бронирования
workflow.add_conditional_edges("booking_agent", should_continue_booking, {
    "tools": "tools",
    END: END
})
workflow.add_edge("tools", "booking_agent")

# Граф для RAG
workflow.add_edge("rag_retrieve", "rag_rerank")
workflow.add_edge("rag_rerank", "rag_generate")
workflow.add_edge("rag_generate", END)

# Компиляция
app = workflow.compile()
def run_agent(query: str) -> str:
    """Запуск агента с запросом и возврат финального ответа"""
    initial_messages = [HumanMessage(content=query)]
    final_state = app.invoke(
        {"messages": initial_messages, "retrieved_docs": [], "reranked_docs": [], "final_answer": ""},
        config={"recursion_limit": config.recursion_limit}
    )
    # Если это был RAG-запрос – ответ в final_answer
    if final_state.get("final_answer"):
        return final_state["final_answer"]
    # Иначе ищем последнее сообщение AIMessage без tool_calls (бронирование)
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content
    return "Не удалось получить ответ."
def run_interactive_agent():
    print("\n=== Гибридный агент (бронирование + RAG) ===")
    print("Введите запрос (или 'exit' для выхода):\n")
    while True:
        query = input("> ").strip()
        if not query or query.lower() in ('exit', 'quit', 'выйти'):
            print("До свидания!")
            break
        print("\nОтвет:", run_agent(query))
if __name__ == "__main__":
    if config.phoenix_enabled:
        init_phoenix()
    run_interactive_agent()