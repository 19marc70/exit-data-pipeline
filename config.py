import os
from pydantic import BaseModel

class Settings(BaseModel):
    coingecko_api_key: str | None = os.getenv("COINGECKO_API_KEY") or None
    coinglass_api_key: str | None = os.getenv("COINGLASS_API_KEY") or None
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))

settings = Settings()
