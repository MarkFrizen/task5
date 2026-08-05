from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent
class BookingRequest(BaseModel):
    query: str
app = FastAPI(title="Flight Booking Agent API", version="1.0.0")
# Схема запроса и маршрут бронирования
@app.post("/book", summary="Забронировать авиабилет через агента")
async def book_flight(request: BookingRequest):
    try:
        answer = run_agent(request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Маршрут проверки здоровья API
@app.get("/health", summary="Проверка работоспособности")
async def health():
    return {"status": "ok"}