import uvicorn

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent


class BookingRequest(BaseModel):
    query: str


app = FastAPI(title="Flight Booking Agent API", version="1.0.0")


@app.post("/book", summary="Забронировать авиабилет через агента")
async def book_flight(request: BookingRequest):
    try:
        answer = run_agent(request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", summary="Проверка работоспособности")
async def health():
    return {"status": "ok"}


def run_server():
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)