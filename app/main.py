import os
import time
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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


class ChatRequest(BaseModel):
    question: str


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


def format_coin_answer(symbol, coin):
    adaptive = coin.get("adaptive_execution", {})
    portfolio = coin.get("portfolio_position", {})
    derivatives = coin.get("derivatives", {})
    der_state = derivatives.get("state", {})

    return f"""
🎯 {symbol}

Status:
{coin.get("signal")}

Score:
{coin.get("score")}

Verkoop:
{coin.get("sell_pct")}% / {coin.get("sell_qty")} vandaag

Trend:
{coin.get("trend")}

Volatiliteit:
{coin.get("volatility")}

RSI:
{coin.get("rsi_14d")}

ATR:
{coin.get("atr_14d")}

Liquidity:
{coin.get("liquidity")}

Funding/leverage:
{der_state.get("leverage_risk")}

Portfolio:
waarde ${portfolio.get("market_value")}
PnL {portfolio.get("pnl_pct")}%
allocatie {portfolio.get("allocation_pct")}%

Execution:
{coin.get("execution_type")}

Slippage:
{adaptive.get("slippage_risk")}

Confirmations:
{", ".join(coin.get("confirmations", [])) or "geen"}

Blockers:
{", ".join(coin.get("blockers", [])) or "geen"}
""".strip()


def build_today_answer(engine):
    sc = engine.get("score_components", {})
    portfolio = engine.get("portfolio_intelligence", {})
    risk = portfolio.get("portfolio_risk", {})

    return f"""
📡 BLOK 1 — SNEL BESLUIT

🚦 ACTIE:
{engine.get("global_action")}

🎯 REDEN:
Exit Zone Score = {engine.get("exit_zone_score")}.
Multi-category confirmed = {sc.get("multi_category_confirmed")}.
Er is dus geen volledige exit zolang meerdere categorieën niet samen bevestigen.

⏰ URGENTIE:
Laag tot middelmatig.

💧 EXECUTION:
Geen verkoop tenzij een coin specifiek een SELL-signaal krijgt.

📊 BLOK 2 — MARKT & SIGNALEN

Cycle score:
{sc.get("cycle_intelligence", {}).get("cycle_score")}

Cycle state:
{sc.get("cycle_intelligence", {}).get("cycle_state")}

Macro score:
{sc.get("macro_intelligence", {}).get("macro_score")}

Macro state:
{sc.get("macro_intelligence", {}).get("macro_state")}

Fear & Greed:
{sc.get("fear_greed", {}).get("value")} / {sc.get("fear_greed", {}).get("classification")}

BTC dominance:
{sc.get("btc_dominance")}

💰 BLOK 5 — PORTFOLIO

Totale waarde:
${portfolio.get("total_portfolio_value")}

Totale PnL:
${portfolio.get("total_unrealized_pnl")} / {portfolio.get("portfolio_pnl_pct")}%

Grootste positie:
{risk.get("largest_position")} ({risk.get("largest_position_pct")}%)

Portfolio risico:
{risk.get("state")}

🎯 BLOK 7 — CONCLUSIE

Het systeem staat momenteel niet in exit-modus.
Coin-specifieke verkoop blijft geblokkeerd zolang multi-factor bevestiging ontbreekt.
XRP blijft core-hold.
CFG blijft beperkt door liquiditeitsrisico.
""".strip()


def build_highest_risk_answer(engine):
    signals = engine.get("signals", {})

    ranked = sorted(
        signals.items(),
        key=lambda item: float(item[1].get("score", 0)),
        reverse=True
    )

    if not ranked:
        return "⚪ Geen coin-data beschikbaar."

    symbol, coin = ranked[0]

    return f"""
🎯 Hoogste actuele coin-risico

Coin:
{symbol}

Score:
{coin.get("score")}

Signaal:
{coin.get("signal")}

Redenen:
- Trend: {coin.get("trend")}
- Volatiliteit: {coin.get("volatility")}
- Liquidity: {coin.get("liquidity")}
- RSI: {coin.get("rsi_14d")}
- Blockers: {", ".join(coin.get("blockers", [])) or "geen"}

Verkoop:
{coin.get("sell_pct")}% / {coin.get("sell_qty")}

Conclusie:
{symbol} heeft nu de hoogste risicoscore, maar verkoop gebeurt alleen als adaptive execution en multi-factor confirmation dit toestaan.
""".strip()


def build_portfolio_answer(engine):
    p = engine.get("portfolio_intelligence", {})
    risk = p.get("portfolio_risk", {})
    positions = p.get("positions", {})

    lines = [
        "💰 PORTFOLIO INTELLIGENCE",
        "",
        f"Totaalwaarde: ${p.get('total_portfolio_value')}",
        f"Cost basis: ${p.get('total_cost_basis')}",
        f"Ongerealiseerde PnL: ${p.get('total_unrealized_pnl')}",
        f"Portfolio PnL: {p.get('portfolio_pnl_pct')}%",
        "",
        f"Grootste positie: {risk.get('largest_position')} ({risk.get('largest_position_pct')}%)",
        f"Risico: {risk.get('state')}",
        ""
    ]

    for symbol, pos in positions.items():
        lines.append(
            f"{symbol}: waarde ${pos.get('market_value')} | "
            f"PnL {pos.get('pnl_pct')}% | allocatie {pos.get('allocation_pct')}% | "
            f"risico {pos.get('risk_state')}"
        )

    return "\n".join(lines)


def answer_question(question, engine):
    q = question.lower().strip()
    signals = engine.get("signals", {})

    if any(word in q for word in ["vandaag", "doen", "actie", "besluit", "moet ik"]):
        return build_today_answer(engine)

    if any(word in q for word in ["portfolio", "portefeuille", "pnl", "waarde", "allocatie"]):
        return build_portfolio_answer(engine)

    if any(word in q for word in ["hoogste risico", "meeste risico", "gevaarlijkste", "zwakste"]):
        return build_highest_risk_answer(engine)

    for symbol in ["XRP", "ONDO", "AERO", "CFG"]:
        if symbol.lower() in q:
            coin = signals.get(symbol)
            if not coin:
                return f"⚪ Geen data gevonden voor {symbol}."
            return format_coin_answer(symbol, coin)

    if any(word in q for word in ["waarom", "verkopen", "sell", "exit"]):
        return build_today_answer(engine)

    return build_today_answer(engine)


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


@app.get("/chat/status")
async def chat_status():
    return {
        "chat_layer": "active",
        "source": "/market/exit-engine",
        "mode": "rule_based_conversational_engine",
        "timestamp": now_iso()
    }


@app.post("/chat/ask")
async def chat_ask(req: ChatRequest):
    snapshot = await build_exit_snapshot()
    engine = build_exit_engine(snapshot)

    answer = answer_question(req.question, engine)

    return {
        "question": req.question,
        "answer": answer,
        "engine_version": engine.get("engine_version"),
        "global_action": engine.get("global_action"),
        "exit_zone_score": engine.get("exit_zone_score"),
        "timestamp": now_iso()
    }


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>EXIT PLAN v10.1 Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #070b18;
            color: #e5e7eb;
            margin: 0;
            padding: 20px;
        }

        h1 {
            color: #ffffff;
        }

        .box {
            max-width: 900px;
            margin: auto;
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 14px;
            padding: 18px;
        }

        textarea {
            width: 100%;
            height: 90px;
            background: #020617;
            color: #e5e7eb;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 12px;
            font-size: 16px;
            box-sizing: border-box;
        }

        button {
            margin-top: 10px;
            background: #2563eb;
            color: white;
            border: none;
            padding: 11px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }

        button:hover {
            background: #1d4ed8;
        }

        pre {
            white-space: pre-wrap;
            background: #020617;
            border: 1px solid #1f2937;
            border-radius: 10px;
            padding: 14px;
            margin-top: 16px;
            font-size: 15px;
            line-height: 1.45;
        }

        .examples {
            color: #9ca3af;
            font-size: 14px;
            margin-bottom: 12px;
        }

        .pill {
            display: inline-block;
            background: #020617;
            border: 1px solid #334155;
            border-radius: 999px;
            padding: 5px 9px;
            margin: 3px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="box">
        <h1>EXIT PLAN v10.1 Chat</h1>

        <div class="examples">
            Klik een voorbeeld of stel zelf een vraag:
            <br>
            <span class="pill" onclick="setQ('Wat moet ik vandaag doen?')">Wat moet ik vandaag doen?</span>
            <span class="pill" onclick="setQ('Hoe staat ONDO ervoor?')">Hoe staat ONDO ervoor?</span>
            <span class="pill" onclick="setQ('Welke coin heeft het hoogste risico?')">Hoogste risico?</span>
            <span class="pill" onclick="setQ('Hoe staat mijn portfolio ervoor?')">Portfolio</span>
            <span class="pill" onclick="setQ('Waarom verkoopt het systeem niet?')">Waarom geen verkoop?</span>
        </div>

        <textarea id="question">Wat moet ik vandaag doen?</textarea>
        <br>
        <button onclick="ask()">Vraag aan EXIT PLAN</button>

        <pre id="answer">Antwoord verschijnt hier...</pre>
    </div>

<script>
function setQ(text) {
    document.getElementById("question").value = text;
}

async function ask() {
    const question = document.getElementById("question").value;
    document.getElementById("answer").innerText = "Engine wordt geraadpleegd...";

    const res = await fetch("/chat/ask", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question})
    });

    const data = await res.json();

    document.getElementById("answer").innerText =
        data.answer +
        "\\n\\n---\\n" +
        "Engine: " + data.engine_version + "\\n" +
        "Global action: " + data.global_action + "\\n" +
        "Exit zone score: " + data.exit_zone_score + "\\n" +
        "Timestamp: " + data.timestamp;
}
</script>
</body>
</html>
"""


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

        h1, h2, h3 { color: #ffffff; }

        .topbar {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 10px;
            margin-bottom: 18px;
        }

        button, a.button {
            background: #2563eb;
            color: white;
            border: none;
            padding: 10px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            text-decoration: none;
            display: inline-block;
        }

        button:hover, a.button:hover { background: #1d4ed8; }

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

        .small { font-size: 13px; color: #9ca3af; }
        .muted { color: #9ca3af; }
        .metric { font-size: 28px; font-weight: bold; margin: 8px 0; }
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
        <a class="button" href="/chat">Open Chat</a>
    </div>

    <div class="statusline">
        Laatste update: <span id="last_update">...</span>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Global Action</h2>
            <div id="global_action" class="metric">Loading...</div>
            <p>Exit Zone Score: <span id="exit_score">...</span></p>
            <div class="barwrap"><div id="exit_bar" class="bar"></div></div>
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
            <h2>Portfolio</h2>
            <p>Total value: <span id="portfolio_value">...</span></p>
            <p>Total PnL: <span id="portfolio_pnl">...</span></p>
            <p>Risk: <span id="portfolio_risk">...</span></p>
            <p>Largest: <span id="largest_position">...</span></p>
        </div>
    </div>

    <h2>Coin Signals</h2>
    <div id="coins" class="grid"></div>

    <h2>Raw Engine Output</h2>
    <pre id="raw"></pre>

<script>
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
    const portfolio = data.portfolio_intelligence || {};
    const risk = portfolio.portfolio_risk || {};

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

    document.getElementById('portfolio_value').innerText = "$" + portfolio.total_portfolio_value;
    document.getElementById('portfolio_pnl').innerText = "$" + portfolio.total_unrealized_pnl + " / " + portfolio.portfolio_pnl_pct + "%";
    document.getElementById('portfolio_risk').innerText = risk.state;
    document.getElementById('largest_position').innerText = risk.largest_position + " / " + risk.largest_position_pct + "%";

    const coinsDiv = document.getElementById('coins');
    coinsDiv.innerHTML = '';

    for (const [symbol, coin] of Object.entries(data.signals || {})) {
        const card = document.createElement('div');
        card.className = 'card';

        const adaptive = coin.adaptive_execution || {};
        const portfolioPos = coin.portfolio_position || {};

        card.innerHTML = `
            <div class="coin-title">
                <h2>${symbol}</h2>
                <span class="pill">${coin.signal}</span>
            </div>
            <p><b>Score:</b> ${coin.score}</p>
            <p><b>Sell %:</b> ${coin.sell_pct}</p>
            <p><b>Sell qty today:</b> ${coin.sell_qty}</p>
            <p><b>Execution:</b> ${coin.execution_type}</p>
            <p><b>Slippage risk:</b> ${adaptive.slippage_risk || "..."}</p>
            <hr>
            <p><b>Portfolio value:</b> $${portfolioPos.market_value}</p>
            <p><b>PnL:</b> ${portfolioPos.pnl_pct}%</p>
            <p><b>Allocation:</b> ${portfolioPos.allocation_pct}%</p>
            <hr>
            <p><b>Liquidity:</b> ${coin.liquidity}</p>
            <p><b>Trend:</b> ${coin.trend}</p>
            <p><b>Volatility:</b> ${coin.volatility}</p>
            <p><b>RSI:</b> ${coin.rsi_14d}</p>
            <p><b>ATR:</b> ${coin.atr_14d}</p>
            <p><b>Confirmations:</b> ${(coin.confirmations || []).join(', ') || "none"}</p>
            <p><b>Blockers:</b> ${(coin.blockers || []).join(', ') || "none"}</p>
        `;

        coinsDiv.appendChild(card);
    }

    document.getElementById('raw').innerText =
        JSON.stringify(data, null, 2);
}

async function scanMarket() {
    const res = await fetch('/market/scan');
    const data = await res.json();
    alert(JSON.stringify(data.alert_result, null, 2));
    loadData();
}

async function testTelegram() {
    const res = await fetch('/alerts/test');
    const data = await res.json();
    alert(JSON.stringify(data, null, 2));
}

loadData();
</script>
</body>
</html>
"""
