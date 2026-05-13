# Railway deploy checklist

## 1. GitHub
- Nieuwe repo maken: `exit-data-pipeline`
- Alle bestanden uploaden
- Committen naar main

## 2. Railway
- New Project
- Deploy from GitHub repo
- Selecteer `exit-data-pipeline`

## 3. Variables
Voeg toe:

```text
CACHE_TTL_SECONDS=300
COINGECKO_API_KEY=
COINGLASS_API_KEY=
```

CoinGlass API-key is nodig voor funding/OI.

## 4. Start command
Railway gebruikt de `Procfile`.

Controleer dat dit erin staat:

```text
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## 5. Test
Open:

```text
/health
```

Daarna:

```text
/market/exit-snapshot
```

## 6. GPT Action
- Open je GPT
- Configureren
- Handelingen
- Nieuwe handeling maken
- Authenticatie: Geen, tenzij je later API-auth toevoegt
- Plak `openapi_schema.json`
- Vervang `https://YOUR_RAILWAY_DOMAIN` door je Railway URL
