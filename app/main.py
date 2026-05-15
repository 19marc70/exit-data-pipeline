import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .sources import build_exit_snapshot
from .engine import build_exit_engine

app = FastAPI(title="EXIT PLAN v10.1 Live Engine")

ALERT_CACHE = {
    "last_alert_ts": 0,
    "last_message": None
}

ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "3600"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def alert_enabled():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def should_alert(engine):
    global_action = engine.get("global_action")
    signals = engine.get("signals", {})

    if global_action in ["RISK_OFF", "PARTIAL_EXIT_ALLOWED"]:
        return True

    for coin in signals.values():
        if coin.get("signal") in ["SELL_10", "SELL_25", "SELL_50"]:
            return True

    return False


def build_alert_message(engine):
    lines = []

    lines.append("🚨 EXIT PLAN v10.1 ALERT")
    lines.append(f"Time: {now_iso()}")
    lines.append(f"Global action: {engine.get('global_action')}")
    lines.append(f"Exit zone score: {engine.get('exit_zone_score')}")
    lines.append("")

    for symbol, coin in engine.get("signals", {}).items():
        signal = coin.get("signal")
        sell_pct = coin.get("sell_pct")
        liquidity = coin.get("liquidity")
        score = coin.get("score")

        if signal not in ["HOLD", "HOLD_NO_SELL_TARGET"]:
            lines.append(
                f"{symbol}: {signal} | sell {sell_pct}% | score {score} | liquidity {liquidity}"
            )

    if len(lines) <= 5:
        lines.append("No active sell trigger. Monitoring only.")

    return "\n".join(lines)


async def send_telegram(message):
    if not alert_enabled():
        return {
            "sent": False,
            "reason": "telegram_not_configured"
        }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            }
        )

    return {
        "sent": response.status_code == 200,
        "status_code": response.status_code,
        "response": response.text
    }


async def maybe_send_alert(engine):
    if not should_alert(engine):
        return {
            "alert": False,
            "reason": "no_trigger"
        }

    now = time.time()

    if now - ALERT_CACHE["last_alert_ts"] < ALERT_COOLDOWN_SECONDS:
        return {
            "alert": False,
            "reason": "cooldown_active"
        }

    message = build_alert_message(engine)
    result = await send_telegram(message)

    ALERT_CACHE["last_alert_ts"] = now
    ALERT_CACHE["last_message"] = message

    return {
        "alert": True,
        "telegram": result,
        "message": message
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": now_iso()
    }


@app.get("/market/exit-snapshot")
async def get_exit_snapshot():
    return await build_exit_snapshot()


@app.get("/market/exit-engine")
async def get_exit_engine():
    snapshot = await build_exit_snapshot()
    return build_exit_engine(snapshot)


@app.get("/market/scan")
async def scan_market():
    snapshot = await build_exit_snapshot()
    engine = build_exit_engine(snapshot)
    alert_result = await maybe_send_alert(engine)

    return {
        "timestamp": now_iso(),
        "scan_status": "ok",
        "alert_result": alert_result,
        "engine": engine
    }


@app.get("/alerts/status")
async def alerts_status():
    return {
        "telegram_enabled": alert_enabled(),
        "alert_cooldown_seconds": ALERT_COOLDOWN_SECONDS,
        "last_alert_ts": ALERT_CACHE["last_alert_ts"],
        "last_message": ALERT_CACHE["last_message"]
    }


@app.get("/alerts/test")
async def alerts_test():
    message = f"✅ EXIT PLAN v10.1 test alert\nTime: {now_iso()}"
    result = await send_telegram(message)

    return {
        "test": "telegram",
        "result": result
    }


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
            margin-right: 8px;
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <h1>EXIT PLAN v10.1 Dashboard</h1>

    <button onclick="loadData()">Refresh</button>
    <button onclick="scanMarket()">Run Scan</button>

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
            <h2>Automation</h2>
            <p>Scan endpoint: <code>/market/scan</code></p>
            <p>Alert status: <code>/alerts/status</code></p>
            <p>Telegram test: <code>/alerts/test</code></p>
            <p id="scan_result" class="muted">No scan yet.</p>
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

async function scanMarket() {
    const res = await fetch('/market/scan');
    const data = await res.json();
    document.getElementById('scan_result').innerText =
        JSON.stringify(data.alert_result, null, 2);
    loadData();
}

loadData();
</script>
</body>
</html>
"""
