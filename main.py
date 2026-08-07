from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent, init_phoenix
from config import config
app = FastAPI(
    title="Flight Booking + RAG Agent API",
    description="API для бронирования авиабилетов и вопросов к RAG-агенту",
    version="1.0.0"
)
class QueryRequest(BaseModel):
    query: str
@app.post("/ask", summary="Задать вопрос агенту (бронирование или RAG)")
async def ask(request: QueryRequest):
    try:
        answer = run_agent(request.query)
        return {"response": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/health", summary="Проверка работоспособности")
async def health():
    return {
        "status": "ok",
        "model": config.llm_model,
        "rag_index_exists": bool(config.index_path and os.path.exists(config.index_path))
    }
if __name__ == "__main__":
    if config.phoenix_enabled:
        init_phoenix()
    import uvicorn
    uvicorn.run(app, host=config.api_host, port=config.api_port)