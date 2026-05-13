from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .sources import build_exit_snapshot, now_iso

app = FastAPI(
    title="Exit Data Pipeline",
    version="1.0.0",
    description="Live crypto data pipeline for EXIT PLAN v10.1 GPT Action."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "Exit Data Pipeline",
        "version": "1.0.0",
        "endpoints": ["/health", "/market/exit-snapshot"]
    }

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": now_iso()}

@app.get("/market/exit-snapshot")
async def market_exit_snapshot():
    return await build_exit_snapshot()
