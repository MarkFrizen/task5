import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent, init_phoenix
import os
app = FastAPI(
    title="Flight Booking Agent API",
    description="API для бронирования авиабилетов с помощью AI-агента",
    version="1.0.0"
)
class BookingRequest(BaseModel):
    query: str

@app.post("/book", summary="Забронировать авиабилет через агента")
async def book_flight(request: BookingRequest):
    try:
        # Запускаем синхронную функцию в отдельном потоке, чтобы не блокировать event loop
        answer = await asyncio.to_thread(run_agent, request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", summary="Проверка работоспособности сервиса")
async def health():
    return {"status": "ok", "model": os.getenv("LLM_MODEL", "qwen/qwen3.5-9b (локально через LM Studio)")}
if __name__ == "__main__":
    if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
        init_phoenix()
    import uvicorn
    uvicorn.run(app, host=os.getenv("API_HOST", "0.0.0.0"), port=int(os.getenv("API_PORT", "8000")))