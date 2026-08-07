from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent

# FastAPI-приложение с API для бронирования авиабилетов через AI-агента
app = FastAPI(
    title="Flight Booking Agent API",
    description="API для бронирования авиабилетов с помощью AI-агента",
    version="1.0.0"
)

# Модель запроса с текстом пользовательского запроса на естественном языке
class BookingRequest(BaseModel):
    query: str
@app.post("/book", summary="Забронировать авиабилет через агента")
async def book_flight(request: BookingRequest):
    try:
        answer = run_agent(request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/health", summary="Проверка работоспособности сервиса")
async def health():
    return {"status": "ok", "model": "qwen/qwen3.5-9b (локально через LM Studio)"}