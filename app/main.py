from fastapi import FastAPI
from datetime import datetime, timezone

from .sources import build_exit_snapshot
from .engine import build_exit_engine

app = FastAPI()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/market/exit-snapshot")
async def get_exit_snapshot():
    snapshot = await build_exit_snapshot()
    return snapshot


@app.get("/market/exit-engine")
async def get_exit_engine():
    snapshot = await build_exit_snapshot()
    result = build_exit_engine(snapshot)
    return result
