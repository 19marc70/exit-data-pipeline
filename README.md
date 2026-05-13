# EXIT PLAN v10.1 — Live Data Pipeline

FastAPI-backend voor je Custom GPT Action `/exit`.

## Wat dit doet

Endpoint:

```text
GET /market/exit-snapshot
```

Geeft live JSON terug voor:

- BTC dominance
- BTC Pi Cycle status
- CBBI
- Fear & Greed
- ATR(14)
- RSI(14)
- spot price
- 24h volume
- funding / open interest via CoinGlass, indien API-key aanwezig

## Belangrijk

Deze backend is een datapipeline, geen trading bot. De GPT gebruikt je knowledge files voor regels, thresholds en besluitvorming.

## Snel deployen op Railway

1. Maak een GitHub repo aan.
2. Upload alle bestanden uit deze map.
3. Ga naar Railway.
4. Klik `New Project` → `Deploy from GitHub repo`.
5. Kies je repo.
6. Voeg environment variables toe:

```text
COINGECKO_API_KEY=
COINGLASS_API_KEY=
CACHE_TTL_SECONDS=300
```

CoinGecko werkt ook zonder key, maar met lagere rate limits.
CoinGlass funding/OI werkt alleen met key.

7. Railway detecteert Python automatisch.
8. Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

9. Open na deploy:

```text
https://jouw-railway-url.up.railway.app/health
```

10. Test:

```text
https://jouw-railway-url.up.railway.app/market/exit-snapshot
```

## GPT Action

Gebruik `openapi_schema.json` en vervang:

```text
https://YOUR_RAILWAY_DOMAIN
```

door je Railway URL.

## Security

Zet API keys nooit in je GPT instructions. Alleen in Railway environment variables.
