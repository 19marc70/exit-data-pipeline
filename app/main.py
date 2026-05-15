from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .sources import build_exit_snapshot
from .engine import build_exit_engine

app = FastAPI(title="EXIT PLAN v10.1 Live Engine")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/market/exit-snapshot")
async def get_exit_snapshot():
    return await build_exit_snapshot()


@app.get("/market/exit-engine")
async def get_exit_engine():
    snapshot = await build_exit_snapshot()
    return build_exit_engine(snapshot)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>EXIT PLAN v10.1 Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0b1020;
            color: #e5e7eb;
            margin: 0;
            padding: 20px;
        }
        h1, h2 { color: #ffffff; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
        }
        .card {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
        }
        .good { color: #22c55e; }
        .warn { color: #facc15; }
        .bad { color: #ef4444; }
        .muted { color: #9ca3af; }
        pre {
            white-space: pre-wrap;
            background: #020617;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
        }
        button {
            background: #2563eb;
            color: white;
            border: none;
            padding: 10px 14px;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 16px;
        }
        button:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <h1>EXIT PLAN v10.1 Dashboard</h1>
    <button onclick="loadData()">Refresh</button>

    <div class="grid">
        <div class="card">
            <h2>Global Action</h2>
            <div id="global_action" class="warn">Loading...</div>
            <p class="muted">Exit Zone Score: <span id="exit_score">...</span></p>
        </div>

        <div class="card">
            <h2>Macro</h2>
            <p>Macro Score: <span id="macro_score">...</span></p>
            <p>Altseason Index: <span id="altseason">...</span></p>
            <p>Stablecoin Regime: <span id="stablecoin">...</span></p>
        </div>

        <div class="card">
            <h2>Guardrails</h2>
            <p>XRP sell allowed: <span class="bad">false</span></p>
            <p>Moonbags sell allowed: <span class="bad">false</span></p>
            <p>Single indicator exits: <span class="bad">false</span></p>
        </div>
    </div>

    <h2>Coin Signals</h2>
    <div id="coins" class="grid"></div>

    <h2>Allocation Plan</h2>
    <pre id="allocation"></pre>

    <h2>Re-entry Engine</h2>
    <pre id="reentry"></pre>

    <h2>Raw Engine Output</h2>
    <pre id="raw"></pre>

<script>
async function loadData() {
    const res = await fetch('/market/exit-engine');
    const data = await res.json();

    document.getElementById('global_action').innerText = data.global_action;
    document.getElementById('exit_score').innerText = data.exit_zone_score;

    const sc = data.score_components || {};
    document.getElementById('macro_score').innerText = sc.macro_score;
    document.getElementById('altseason').innerText = sc.altseason_index;
    document.getElementById('stablecoin').innerText = sc.stablecoin_regime;

    const coinsDiv = document.getElementById('coins');
    coinsDiv.innerHTML = '';

    for (const [symbol, coin] of Object.entries(data.signals || {})) {
        const card = document.createElement('div');
        card.className = 'card';

        card.innerHTML = `
            <h2>${symbol}</h2>
            <p><b>Signal:</b> ${coin.signal}</p>
            <p><b>Score:</b> ${coin.score}</p>
            <p><b>Sell %:</b> ${coin.sell_pct}</p>
            <p><b>Sell qty:</b> ${coin.sell_qty}</p>
            <p><b>Max daily qty:</b> ${coin.max_daily_qty}</p>
            <p><b>Liquidity:</b> ${coin.liquidity}</p>
            <p><b>Trend:</b> ${coin.trend}</p>
            <p><b>Volatility:</b> ${coin.volatility}</p>
            <p><b>RSI:</b> ${coin.rsi_14d}</p>
            <p><b>ATR:</b> ${coin.atr_14d}</p>
            <p><b>Confirmations:</b> ${(coin.confirmations || []).join(', ')}</p>
            <p><b>Blockers:</b> ${(coin.blockers || []).join(', ')}</p>
        `;

        coinsDiv.appendChild(card);
    }

    document.getElementById('allocation').innerText =
        JSON.stringify(data.allocation_plan || {}, null, 2);

    document.getElementById('reentry').innerText =
        JSON.stringify(data.reentry_engine || {}, null, 2);

    document.getElementById('raw').innerText =
        JSON.stringify(data, null, 2);
}

loadData();
</script>
</body>
</html>
"""
