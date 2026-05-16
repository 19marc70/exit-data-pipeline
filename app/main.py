import os
import time
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .sources import build_exit_snapshot
from .engine import build_exit_engine

app = FastAPI(title="EXIT PLAN v10.1 Live Engine")

ALERT_CACHE = {
    "last_alert_ts": 0,
    "last_message": None,
    "last_scan_ts": 0,
    "last_scan_result": None
}

ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "3600"))
AUTO_SCAN_ENABLED = os.getenv("AUTO_SCAN_ENABLED", "true").lower() == "true"
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "1800"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def alert_enabled():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def should_alert(engine):
    global_action = engine.get("global_action")
    signals = engine.get("signals", {})

    if global_action in [
        "RISK_OFF",
        "PARTIAL_EXIT_ALLOWED",
        "LIGHT_TRIM_ALLOWED",
        "HEAVY_DISTRIBUTION"
    ]:
        return True

    for coin in signals.values():
        signal = coin.get("signal", "")
        if signal.startswith("SELL"):
            return True

    return False


def build_alert_message(engine):
    lines = [
        "🚨 EXIT PLAN v10.1 ALERT",
        f"Time: {now_iso()}",
        f"Global action: {engine.get('global_action')}",
        f"Exit zone score: {engine.get('exit_zone_score')}",
        ""
    ]

    score_components = engine.get("score_components", {})
    lines.append(f"Macro/Cycle score: {score_components.get('macro_cycle_risk_score')}")
    lines.append(f"Market structure: {score_components.get('market_structure_score')}")
    lines.append("")

    for symbol, coin in engine.get("signals", {}).items():
        signal = coin.get("signal")
        if signal not in ["HOLD", "HOLD_NO_SELL_TARGET"]:
            lines.append(
                f"{symbol}: {signal} | sell {coin.get('sell_pct')}% | "
                f"qty {coin.get('sell_qty')} | liquidity {coin.get('liquidity')}"
            )

    if len(lines) <= 7:
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


async def run_scan():
    snapshot = await build_exit_snapshot()
    engine = build_exit_engine(snapshot)
    alert_result = await maybe_send_alert(engine)

    result = {
        "timestamp": now_iso(),
        "scan_status": "ok",
        "alert_result": alert_result,
        "engine": engine
    }

    ALERT_CACHE["last_scan_ts"] = time.time()
    ALERT_CACHE["last_scan_result"] = result

    return result


async def auto_scan_loop():
    await asyncio.sleep(10)

    while True:
        if AUTO_SCAN_ENABLED:
            try:
                await run_scan()
                print(f"AUTO SCAN OK: {now_iso()}")
            except Exception as e:
                print(f"AUTO SCAN ERROR: {e}")

        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    if AUTO_SCAN_ENABLED:
        asyncio.create_task(auto_scan_loop())


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
    return await run_scan()


@app.get("/automation/status")
async def automation_status():
    return {
        "auto_scan_enabled": AUTO_SCAN_ENABLED,
        "scan_interval_seconds": SCAN_INTERVAL_SECONDS,
        "last_scan_ts": ALERT_CACHE["last_scan_ts"],
        "last_scan_result": ALERT_CACHE["last_scan_result"]
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
            background: #070b18;
            color: #e5e7eb;
            margin: 0;
            padding: 20px;
        }

        h1, h2, h3 {
            color: #ffffff;
        }

        .topbar {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 10px;
            margin-bottom: 18px;
        }

        button {
            background: #2563eb;
            color: white;
            border: none;
            padding: 10px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }

        button:hover {
            background: #1d4ed8;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 22px;
        }

        .card {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 14px;
            padding: 18px;
            box-shadow: 0 10px 24px rgba(0,0,0,0.25);
        }

        .small {
            font-size: 13px;
            color: #9ca3af;
        }

        .muted {
            color: #9ca3af;
        }

        .good {
            color: #22c55e;
            font-weight: bold;
        }

        .warn {
            color: #facc15;
            font-weight: bold;
        }

        .bad {
            color: #ef4444;
            font-weight: bold;
        }

        .neutral {
            color: #93c5fd;
            font-weight: bold;
        }

        .metric {
            font-size: 28px;
            font-weight: bold;
            margin: 8px 0;
        }

        .pill {
            display: inline-block;
            padding: 4px 9px;
            border-radius: 999px;
            background: #020617;
            border: 1px solid #334155;
            font-size: 13px;
            margin: 2px;
        }

        .barwrap {
            width: 100%;
            background: #020617;
            border: 1px solid #334155;
            border-radius: 999px;
            height: 16px;
            overflow: hidden;
            margin-top: 8px;
        }

        .bar {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #22c55e, #facc15, #ef4444);
            transition: width 0.4s ease;
        }

        .coin-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        pre {
            white-space: pre-wrap;
            background: #020617;
            padding: 14px;
            border-radius: 10px;
            overflow-x: auto;
            border: 1px solid #1f2937;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        td, th {
            border-bottom: 1px solid #1f2937;
            padding: 8px;
            text-align: left;
        }

        .statusline {
            color: #9ca3af;
            font-size: 13px;
            margin-bottom: 14px;
        }
    </style>
</head>
<body>
    <h1>EXIT PLAN v10.1 Dashboard</h1>

    <div class="topbar">
        <button onclick="loadData()">Refresh</button>
        <button onclick="scanMarket()">Run Scan</button>
        <button onclick="testTelegram()">Telegram Test</button>
    </div>

    <div class="statusline">
        Laatste update: <span id="last_update">...</span>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Global Action</h2>
            <div id="global_action" class="metric warn">Loading...</div>
            <p>Exit Zone Score: <span id="exit_score" class="neutral">...</span></p>
            <div class="barwrap"><div id="exit_bar" class="bar"></div></div>
            <p class="small">Hoe hoger de score, hoe dichter bij distributie / exit-zone.</p>
        </div>

        <div class="card">
            <h2>Cycle Intelligence</h2>
            <p>Cycle Score: <span id="cycle_score">...</span></p>
            <p>Cycle State: <span id="cycle_state">...</span></p>
            <p>CBBI: <span id="cbbi_value">...</span></p>
            <p>Pi Cycle: <span id="pi_cycle">...</span></p>
        </div>

        <div class="card">
            <h2>Macro Intelligence</h2>
            <p>Macro Score: <span id="macro_score">...</span></p>
            <p>Macro State: <span id="macro_state">...</span></p>
            <p>Fear & Greed: <span id="fear_greed">...</span></p>
            <p>BTC Dominance: <span id="btc_dominance">...</span></p>
        </div>

        <div class="card">
            <h2>Execution Engine</h2>
            <p>Type: <span id="execution_type">...</span></p>
            <p>ATR sizing: <span id="atr_sizing">...</span></p>
            <p>Volatility sizing: <span id="vol_sizing">...</span></p>
            <p>Slippage guard: <span id="slippage_guard">...</span></p>
        </div>

        <div class="card">
            <h2>Automation</h2>
            <p>Auto scan: <span id="auto_scan">...</span></p>
            <p>Interval: <span id="scan_interval">...</span> sec</p>
            <p>Last scan: <span id="last_scan">...</span></p>
            <p id="scan_result" class="muted">No scan yet.</p>
        </div>

        <div class="card">
            <h2>Guardrails</h2>
            <p>XRP sell allowed: <span id="xrp_guard">...</span></p>
            <p>Moonbags sell allowed: <span id="moonbag_guard">...</span></p>
            <p>Single indicator exits: <span id="single_guard">...</span></p>
            <p>Full exit without confirmation: <span id="full_guard">...</span></p>
        </div>
    </div>

    <h2>Trigger Status</h2>
    <div class="card">
        <table>
            <tr>
                <th>Component</th>
                <th>Value</th>
                <th>Status</th>
            </tr>
            <tr>
                <td>Macro/Cycle Risk</td>
                <td id="trigger_macro_value">...</td>
                <td id="trigger_macro_status">...</td>
            </tr>
            <tr>
                <td>Market Structure</td>
                <td id="trigger_structure_value">...</td>
                <td id="trigger_structure_status">...</td>
            </tr>
            <tr>
                <td>Multi-category confirmation</td>
                <td id="trigger_multi_value">...</td>
                <td id="trigger_multi_status">...</td>
            </tr>
            <tr>
                <td>Missing Engine Data</td>
                <td id="missing_data">...</td>
                <td id="missing_status">...</td>
            </tr>
        </table>
    </div>

    <h2>Coin Signals</h2>
    <div id="coins" class="grid"></div>

    <h2>Macro Components</h2>
    <div id="macro_components" class="grid"></div>

    <h2>Allocation Plan</h2>
    <pre id="allocation"></pre>

    <h2>Re-entry Engine</h2>
    <pre id="reentry"></pre>

    <h2>Raw Engine Output</h2>
    <pre id="raw"></pre>

<script>
function clsByRisk(value) {
    if (value >= 60) return "bad";
    if (value >= 30) return "warn";
    if (value <= -10) return "good";
    return "neutral";
}

function boolText(value) {
    return value ? "true" : "false";
}

function pctBar(value) {
    const v = Math.max(0, Math.min(100, Number(value || 0)));
    return v + "%";
}

function safe(obj, path, fallback = "...") {
    try {
        return path.split(".").reduce((a, b) => a[b], obj) ?? fallback;
    } catch {
        return fallback;
    }
}

async function loadData() {
    const res = await fetch('/market/exit-engine');
    const data = await res.json();

    document.getElementById('last_update').innerText = new Date().toLocaleString();

    const sc = data.score_components || {};
    const exec = data.execution_engine || {};
    const guards = data.guardrails || {};

    document.getElementById('global_action').innerText = data.global_action;
    document.getElementById('exit_score').innerText = data.exit_zone_score;
    document.getElementById('exit_bar').style.width = pctBar(data.exit_zone_score);

    document.getElementById('cycle_score').innerText = safe(sc, "cycle_intelligence.cycle_score");
    document.getElementById('cycle_state').innerText = safe(sc, "cycle_intelligence.cycle_state");
    document.getElementById('cbbi_value').innerText = safe(sc, "cbbi.value");
    document.getElementById('pi_cycle').innerText = safe(sc, "pi_cycle.cycle_state");

    document.getElementById('macro_score').innerText = safe(sc, "macro_intelligence.macro_score");
    document.getElementById('macro_state').innerText = safe(sc, "macro_intelligence.macro_state");
    document.getElementById('fear_greed').innerText = safe(sc, "fear_greed.value") + " / " + safe(sc, "fear_greed.classification");
    document.getElementById('btc_dominance').innerText = safe(sc, "btc_dominance");

    document.getElementById('execution_type').innerText = exec.execution_type;
    document.getElementById('atr_sizing').innerText = boolText(exec.atr_adjusted_sizing);
    document.getElementById('vol_sizing').innerText = boolText(exec.volatility_adjusted_sizing);
    document.getElementById('slippage_guard').innerText = boolText(exec.no_trade_if_expected_slippage_above_5pct);

    document.getElementById('xrp_guard').innerText = boolText(guards.xrp_sell_allowed);
    document.getElementById('moonbag_guard').innerText = boolText(guards.moonbags_sell_allowed);
    document.getElementById('single_guard').innerText = boolText(guards.single_indicator_exit_allowed);
    document.getElementById('full_guard').innerText = boolText(guards.full_exit_allowed_without_multi_category_confirmation);

    document.getElementById('trigger_macro_value').innerText = sc.macro_cycle_risk_score;
    document.getElementById('trigger_macro_status').innerText =
        sc.macro_cycle_risk_score >= 20 ? "risk active" : "no major risk";

    document.getElementById('trigger_structure_value').innerText = sc.market_structure_score;
    document.getElementById('trigger_structure_status').innerText =
        sc.market_structure_score >= 20 ? "structure risk" : "not confirmed";

    document.getElementById('trigger_multi_value').innerText = sc.multi_category_confirmed;
    document.getElementById('trigger_multi_status').innerText =
        sc.multi_category_confirmed ? "confirmed" : "not confirmed";

    const missing = data.missing_engine_data || [];
    document.getElementById('missing_data').innerText = missing.length ? missing.join(", ") : "none";
    document.getElementById('missing_status').innerText = missing.length ? "⚪ incomplete" : "✅ complete";

    const coinsDiv = document.getElementById('coins');
    coinsDiv.innerHTML = '';

    for (const [symbol, coin] of Object.entries(data.signals || {})) {
        const card = document.createElement('div');
        card.className = 'card';

        const adaptive = coin.adaptive_execution || {};
        const multipliers = adaptive.multipliers || {};

        card.innerHTML = `
            <div class="coin-title">
                <h2>${symbol}</h2>
                <span class="pill">${coin.signal}</span>
            </div>
            <p><b>Score:</b> ${coin.score}</p>
            <p><b>Sell %:</b> ${coin.sell_pct}</p>
            <p><b>Sell qty today:</b> ${coin.sell_qty}</p>
            <p><b>Target total sell qty:</b> ${coin.target_total_sell_qty || 0}</p>
            <p><b>Max daily qty:</b> ${coin.max_daily_qty}</p>
            <p><b>Execution:</b> ${coin.execution_type}</p>
            <p><b>Slippage risk:</b> ${adaptive.slippage_risk || "..."}</p>
            <hr>
            <p><b>Liquidity:</b> ${coin.liquidity}</p>
            <p><b>Trend:</b> ${coin.trend}</p>
            <p><b>Volatility:</b> ${coin.volatility}</p>
            <p><b>RSI:</b> ${coin.rsi_14d}</p>
            <p><b>ATR:</b> ${coin.atr_14d}</p>
            <hr>
            <p><b>Multipliers:</b></p>
            <p class="small">
                liquidity ${multipliers.liquidity ?? "..."} |
                volatility ${multipliers.volatility ?? "..."} |
                ATR ${multipliers.atr ?? "..."} |
                size ${multipliers.position_size ?? "..."}
            </p>
            <p><b>Confirmations:</b> ${(coin.confirmations || []).join(', ') || "none"}</p>
            <p><b>Blockers:</b> ${(coin.blockers || []).join(', ') || "none"}</p>
            <p><b>Adaptive reasons:</b> ${(adaptive.reasons || []).join(', ') || "none"}</p>
        `;

        coinsDiv.appendChild(card);
    }

    const macroDiv = document.getElementById('macro_components');
    macroDiv.innerHTML = '';

    const macroSignals = safe(sc, "macro_intelligence.signals", {});
    for (const [name, item] of Object.entries(macroSignals || {})) {
        const card = document.createElement('div');
        card.className = 'card';

        card.innerHTML = `
            <h3>${name}</h3>
            <p><b>Available:</b> ${item.available}</p>
            <p><b>Value:</b> ${item.value}</p>
            <p><b>State:</b> ${item.state}</p>
            <p><b>Score:</b> ${item.score}</p>
            <p><b>Reason:</b> ${item.reason}</p>
        `;

        macroDiv.appendChild(card);
    }

    document.getElementById('allocation').innerText =
        JSON.stringify(data.allocation_plan || {}, null, 2);

    document.getElementById('reentry').innerText =
        JSON.stringify(data.reentry_engine || {}, null, 2);

    document.getElementById('raw').innerText =
        JSON.stringify(data, null, 2);

    loadAutomation();
}

async function scanMarket() {
    const res = await fetch('/market/scan');
    const data = await res.json();

    document.getElementById('scan_result').innerText =
        JSON.stringify(data.alert_result, null, 2);

    loadData();
}

async function testTelegram() {
    const res = await fetch('/alerts/test');
    const data = await res.json();

    document.getElementById('scan_result').innerText =
        JSON.stringify(data, null, 2);
}

async function loadAutomation() {
    const res = await fetch('/automation/status');
    const data = await res.json();

    document.getElementById('auto_scan').innerText = data.auto_scan_enabled;
    document.getElementById('scan_interval').innerText = data.scan_interval_seconds;
    document.getElementById('last_scan').innerText = data.last_scan_ts;
}

loadData();
</script>
</body>
</html>
"""
