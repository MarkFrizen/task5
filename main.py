import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent
# Модель запроса для бронирования
class BookingRequest(BaseModel): query: str

# Создание приложения FastAPI
app = FastAPI(title="Flight Booking Agent API", version="1.0.0")
# Маршрут бронирования через агента
@app.post("/book", summary="Забронировать авиабилет через агента")
async def book_flight(request: BookingRequest):
    try:
        answer = run_agent(request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Маршрут проверки состояния API
@app.get("/health", summary="Проверка работоспособности")
async def health():
    return {"status": "ok"}
def run_server():
    """ Запуск сервера на порту 8000 """
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)