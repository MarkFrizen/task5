# REST API для многофункционального агента на FastAPI
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent, init_phoenix
import os
app = FastAPI(
    title="Многофункциональный агент",
    description="API для бронирования авиабилетов, отправки сообщений, курса валют и погоды"
)
class Request(BaseModel):
    query: str
@app.post("/execute")
async def execute(request: Request):
    try:
        answer = await asyncio.to_thread(run_agent, request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/health")
async def health():
    return {"status": "ok", "model": os.getenv("LLM_MODEL", "локальная")}
if __name__ == "__main__":
    if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
        init_phoenix()
    import uvicorn
    uvicorn.run(app, host=os.getenv("API_HOST", "0.0.0.0"), port=int(os.getenv("API_PORT", "8000")))