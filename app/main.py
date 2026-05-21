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
    if engine.get("global_action") in [
        "PARTIAL_EXIT_ALLOWED",
        "LIGHT_TRIM_ALLOWED",
        "HEAVY_DISTRIBUTION"
    ]:
        return True

    for coin in engine.get("signals", {}).values():
        if str(coin.get("signal", "")).startswith("SELL"):
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

    for symbol, coin in engine.get("signals", {}).items():
        if str(coin.get("signal", "")).startswith("SELL"):
            lines.append(
                f"{symbol}: {coin.get('signal')} | "
                f"sell {coin.get('sell_pct')}% | "
                f"qty {coin.get('sell_qty')} | "
                f"liquidity {coin.get('liquidity')}"
            )

    if len(lines) <= 5:
        lines.append("No active sell trigger. Monitoring only.")

    return "\n".join(lines)


async def send_telegram(message):
    if not alert_enabled():
        return {"sent": False, "reason": "telegram_not_configured"}

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )

    return {
        "sent": response.status_code == 200,
        "status_code": response.status_code,
        "response": response.text
    }


async def maybe_send_alert(engine):
    if not should_alert(engine):
        return {"alert": False, "reason": "no_trigger"}

    now = time.time()

    if now - ALERT_CACHE["last_alert_ts"] < ALERT_COOLDOWN_SECONDS:
        return {"alert": False, "reason": "cooldown_active"}

    message = build_alert_message(engine)
    result = await send_telegram(message)

    ALERT_CACHE["last_alert_ts"] = now
    ALERT_CACHE["last_message"] = message

    return {"alert": True, "telegram": result, "message": message}


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

Target total sell qty:
{coin.get("target_total_sell_qty")}

Max daily qty:
{coin.get("max_daily_qty")}

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
Geen volledige exit zolang meerdere categorieën niet samen bevestigen.

⏰ URGENTIE:
Laag tot middelmatig.

💧 EXECUTION:
Alleen verkopen wanneer een coin specifiek een SELL-signaal krijgt.

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

Het systeem staat momenteel niet automatisch in exit-modus.
Coin-specifieke verkoop blijft geblokkeerd zolang multi-factor bevestiging ontbreekt.
XRP blijft core-hold.
CFG blijft beperkt door liquiditeitsrisico.
""".strip()


def build_highest_risk_answer(engine):
    ranked = sorted(
        engine.get("signals", {}).items(),
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

    if any(word in q for word in ["portfolio", "portefeuille", "pnl", "waarde", "allocatie"]):
        return build_portfolio_answer(engine)

    if any(word in q for word in ["hoogste risico", "meeste risico", "gevaarlijkste", "zwakste"]):
        return build_highest_risk_answer(engine)

    for symbol in ["XRP", "ONDO", "AERO", "CFG"]:
        if symbol.lower() in q:
            coin = engine.get("signals", {}).get(symbol)
            if not coin:
                return f"⚪ Geen data gevonden voor {symbol}."
            return format_coin_answer(symbol, coin)

    return build_today_answer(engine)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": now_iso()}


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
    return {"test": "telegram", "result": result}


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
        body { font-family: Arial, sans-serif; background:#070b18; color:#e5e7eb; margin:0; padding:20px; }
        .box { max-width:900px; margin:auto; background:#111827; border:1px solid #1f2937; border-radius:14px; padding:18px; }
        textarea { width:100%; height:90px; background:#020617; color:#e5e7eb; border:1px solid #334155; border-radius:10px; padding:12px; font-size:16px; box-sizing:border-box; }
        button, a { margin-top:10px; background:#2563eb; color:white; border:none; padding:11px 16px; border-radius:8px; cursor:pointer; font-weight:bold; text-decoration:none; display:inline-block; }
        pre { white-space:pre-wrap; background:#020617; border:1px solid #1f2937; border-radius:10px; padding:14px; margin-top:16px; font-size:15px; line-height:1.45; }
        .pill { display:inline-block; background:#020617; border:1px solid #334155; border-radius:999px; padding:5px 9px; margin:3px; cursor:pointer; }
    </style>
</head>
<body>
    <div class="box">
        <h1>EXIT PLAN v10.1 Chat</h1>
        <a href="/">Terug naar dashboard</a>
        <br><br>

        <span class="pill" onclick="setQ('Wat moet ik vandaag doen?')">Wat moet ik vandaag doen?</span>
        <span class="pill" onclick="setQ('Hoe staat ONDO ervoor?')">ONDO</span>
        <span class="pill" onclick="setQ('Hoe staat AERO ervoor?')">AERO</span>
        <span class="pill" onclick="setQ('Welke coin heeft het hoogste risico?')">Hoogste risico</span>
        <span class="pill" onclick="setQ('Hoe staat mijn portfolio ervoor?')">Portfolio</span>

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
        body { font-family: Arial, sans-serif; background:#070b18; color:#e5e7eb; margin:0; padding:20px; }
        h1,h2,h3 { color:#fff; }
        .topbar { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:18px; }
        button,a.button { background:#2563eb; color:white; border:none; padding:10px 14px; border-radius:8px; cursor:pointer; font-weight:bold; text-decoration:none; display:inline-block; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; margin-bottom:22px; }
        .card { background:#111827; border:1px solid #1f2937; border-radius:14px; padding:18px; box-shadow:0 10px 24px rgba(0,0,0,.25); }
        .metric { font-size:28px; font-weight:bold; margin:8px 0; }
        .pill { display:inline-block; padding:4px 9px; border-radius:999px; background:#020617; border:1px solid #334155; font-size:13px; }
        .barwrap { width:100%; background:#020617; border:1px solid #334155; border-radius:999px; height:16px; overflow:hidden; margin-top:8px; }
        .bar { height:100%; width:0%; background:linear-gradient(90deg,#22c55e,#facc15,#ef4444); }
        .coin-title { display:flex; justify-content:space-between; align-items:center; }
        pre { white-space:pre-wrap; background:#020617; padding:14px; border-radius:10px; overflow-x:auto; border:1px solid #1f2937; }
        .statusline { color:#9ca3af; font-size:13px; margin-bottom:14px; }
        table { width:100%; border-collapse:collapse; }
        td,th { border-bottom:1px solid #1f2937; padding:8px; text-align:left; }
        .explain { background:#020617; border:1px solid #334155; border-radius:10px; padding:10px; margin-top:10px; color:#cbd5e1; font-size:14px; }
        .explain-title { font-weight:bold; color:#ffffff; margin-bottom:5px; }
        .detail { display:block; margin:2px 0; color:#cbd5e1; }
        .legend { margin-top:10px; font-size:13px; color:#cbd5e1; }
        .legend-row { display:flex; justify-content:space-between; border-bottom:1px solid #1f2937; padding:4px 0; gap:12px; }
        .legend-row span:first-child { color:#93c5fd; min-width:70px; }
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

    <div class="statusline">Laatste update: <span id="last_update">...</span></div>

    <div class="grid">
        <div class="card">
            <h2>Global Action</h2>
            <div id="global_action" class="metric">Loading...</div>
            <p>Exit Zone Score: <span id="exit_score">...</span></p>
            <div class="barwrap"><div id="exit_bar" class="bar"></div></div>
            <div id="exit_zone_explain" class="explain"></div>
        </div>

        <div class="card">
            <h2>Cycle Intelligence</h2>
            <p>Cycle Score: <span id="cycle_score">...</span></p>
            <p>Cycle State: <span id="cycle_state">...</span></p>
            <p>CBBI: <span id="cbbi_value">...</span></p>
            <p>Pi Cycle: <span id="pi_cycle">...</span></p>
            <div id="cycle_explain" class="explain"></div>
        </div>

        <div class="card">
            <h2>Macro Intelligence</h2>
            <p>Macro Score: <span id="macro_score">...</span></p>
            <p>Macro State: <span id="macro_state">...</span></p>
            <p>Fear & Greed: <span id="fear_greed">...</span></p>
            <p>BTC Dominance: <span id="btc_dominance">...</span></p>
            <div id="macro_explain" class="explain"></div>
            <div id="fear_explain" class="explain"></div>
        </div>

        <div class="card">
            <h2>Portfolio</h2>
            <p>Total value: <span id="portfolio_value">...</span></p>
            <p>Total PnL: <span id="portfolio_pnl">...</span></p>
            <p>Risk: <span id="portfolio_risk">...</span></p>
            <p>Largest: <span id="largest_position">...</span></p>
            <div id="portfolio_explain" class="explain"></div>
        </div>
    </div>

    <h2>Score Legenda</h2>
    <div id="score_legend" class="grid"></div>

    <h2>Trigger Status</h2>
    <div class="card">
        <table>
            <tr><th>Component</th><th>Waarde</th><th>Status</th></tr>
            <tr><td>Macro/Cycle Risk</td><td id="trigger_macro_value">...</td><td id="trigger_macro_status">...</td></tr>
            <tr><td>Market Structure</td><td id="trigger_structure_value">...</td><td id="trigger_structure_status">...</td></tr>
            <tr><td>Portfolio Risk</td><td id="trigger_portfolio_value">...</td><td id="trigger_portfolio_status">...</td></tr>
            <tr><td>Multi-category</td><td id="trigger_multi_value">...</td><td id="trigger_multi_status">...</td></tr>
            <tr><td>Missing Data</td><td id="missing_data">...</td><td id="missing_status">...</td></tr>
        </table>
    </div>

    <h2>Coin Signals</h2>
    <div id="coins" class="grid"></div>

    <!-- Raw engine output verborgen -->
<div id="raw" style="display:none;"></div>

<script>
function pctBar(value) {
    const v = Math.max(0, Math.min(100, Number(value || 0)));
    return v + "%";
}

function safe(obj, path, fallback = "...") {
    try {
        const value = path.split(".").reduce((a,b) => a && a[b], obj);
        return value === undefined || value === null ? fallback : value;
    } catch {
        return fallback;
    }
}

function explainHtml(title, item) {
    if (!item) return "";
    const details = item.details || [];
    return `
        <div class="explain-title">${title}: ${item.label || "..."}</div>
        <div>${item.meaning || ""}</div>
        ${details.map(d => `<span class="detail">${d}</span>`).join("")}
    `;
}

function legendHtml(title, rows) {
    if (!rows || !rows.length) return "";
    return `
        <div class="card">
            <h3>${title}</h3>
            <div class="legend">
                ${rows.map(r => `
                    <div class="legend-row">
                        <span>${r.range}</span>
                        <span>${r.meaning}</span>
                    </div>
                `).join("")}
            </div>
        </div>
    `;
}

async function loadData() {
    const res = await fetch('/market/exit-engine');
    const data = await res.json();

    document.getElementById('last_update').innerText = new Date().toLocaleString();

    const sc = data.score_components || {};
    const portfolio = data.portfolio_intelligence || {};
    const risk = portfolio.portfolio_risk || {};
    const interp = data.score_interpretation || {};
    const legend = interp.legend || {};

    document.getElementById('global_action').innerText = data.global_action || "...";
    document.getElementById('exit_score').innerText = data.exit_zone_score ?? "...";
    document.getElementById('exit_bar').style.width = pctBar(data.exit_zone_score);

    document.getElementById('cycle_score').innerText = safe(sc, "cycle_intelligence.cycle_score");
    document.getElementById('cycle_state').innerText = safe(sc, "cycle_intelligence.cycle_state");
    document.getElementById('cbbi_value').innerText = safe(sc, "cbbi.value");
    document.getElementById('pi_cycle').innerText = safe(sc, "pi_cycle.cycle_state");

    document.getElementById('macro_score').innerText = safe(sc, "macro_intelligence.macro_score");
    document.getElementById('macro_state').innerText = safe(sc, "macro_intelligence.macro_state");
    document.getElementById('fear_greed').innerText = safe(sc, "fear_greed.value") + " / " + safe(sc, "fear_greed.classification");
    document.getElementById('btc_dominance').innerText = safe(sc, "btc_dominance");

    document.getElementById('portfolio_value').innerText = "$" + (portfolio.total_portfolio_value ?? "...");
    document.getElementById('portfolio_pnl').innerText = "$" + (portfolio.total_unrealized_pnl ?? "...") + " / " + (portfolio.portfolio_pnl_pct ?? "...") + "%";
    document.getElementById('portfolio_risk').innerText = risk.state ?? "...";
    document.getElementById('largest_position').innerText = (risk.largest_position ?? "...") + " / " + (risk.largest_position_pct ?? "...") + "%";

    document.getElementById('exit_zone_explain').innerHTML = explainHtml("Betekenis Exit Zone", interp.exit_zone);
    document.getElementById('cycle_explain').innerHTML =
        explainHtml("Betekenis Cycle Score", interp.cycle_score) +
        "<hr>" +
        explainHtml("Betekenis Cycle State", interp.cycle_state);

    document.getElementById('macro_explain').innerHTML = explainHtml("Betekenis Macro Score", interp.macro_score);
    document.getElementById('fear_explain').innerHTML = explainHtml("Betekenis Fear & Greed", interp.fear_greed);
    document.getElementById('portfolio_explain').innerHTML = explainHtml("Betekenis Portfolio Risk", interp.portfolio_risk);

    document.getElementById('score_legend').innerHTML =
        legendHtml("Exit Zone Score", legend.exit_zone_score) +
        legendHtml("Cycle Score", legend.cycle_score) +
        legendHtml("Coin Score", legend.coin_score) +
        legendHtml("RSI", legend.rsi);

    document.getElementById('trigger_macro_value').innerText = sc.macro_cycle_risk_score ?? "...";
    document.getElementById('trigger_macro_status').innerText = (sc.macro_cycle_risk_score || 0) >= 20 ? "risk active" : "geen groot risico";

    document.getElementById('trigger_structure_value').innerText = sc.market_structure_score ?? "...";
    document.getElementById('trigger_structure_status').innerText = (sc.market_structure_score || 0) >= 20 ? "bevestigd" : "niet bevestigd";

    document.getElementById('trigger_portfolio_value').innerText = sc.portfolio_risk_score ?? "...";
    document.getElementById('trigger_portfolio_status').innerText = (sc.portfolio_risk_score || 0) >= 15 ? "portfolio modifier actief" : "laag";

    document.getElementById('trigger_multi_value').innerText = sc.multi_category_confirmed ?? "...";
    document.getElementById('trigger_multi_status').innerText = sc.multi_category_confirmed ? "bevestigd" : "niet bevestigd";

    const missing = data.missing_engine_data || [];
    document.getElementById('missing_data').innerText = missing.length ? missing.join(", ") : "geen";
    document.getElementById('missing_status').innerText = missing.length ? "⚪ incomplete" : "✅ compleet";

    const coinsDiv = document.getElementById('coins');
    coinsDiv.innerHTML = '';

    for (const [symbol, coin] of Object.entries(data.signals || {})) {
        const card = document.createElement('div');
        card.className = 'card';

        const adaptive = coin.adaptive_execution || {};
        const p = coin.portfolio_position || {};
        const ci = coin.interpretations || {};

        card.innerHTML = `
            <div class="coin-title">
                <h2>${symbol}</h2>
                <span class="pill">${coin.signal}</span>
            </div>

            <p><b>Score:</b> ${coin.score}</p>
            <div class="explain">${explainHtml("Betekenis Coin Score", ci.coin_score)}</div>

            <p><b>Verkooppercentage:</b> ${coin.sell_pct}</p>
            <p><b>Verkoophoeveelheid vandaag:</b> ${coin.sell_qty}</p>
            <p><b>Doelhoeveelheid verkoop:</b> ${coin.target_total_sell_qty || 0}</p>
            <p><b>Max dagelijkse hoeveelheid:</b> ${coin.max_daily_qty}</p>
            <p><b>Uitvoering:</b> ${coin.execution_type}</p>
            <p><b>Slippage risico:</b> ${adaptive.slippage_risk || "..."}</p>

            <hr>

            <p><b>Portfolio waarde:</b> $${p.market_value ?? "..."}</p>

<p><b>Holdings:</b> ${p.qty ?? "..."} ${symbol}</p>

<p><b>Gemiddelde aankoopprijs:</b> $${p.avg_entry ?? "..."}</p>

<p><b>Huidige prijs:</b> $${p.current_price ?? "..."}</p>

<p><b>Cost basis:</b> $${p.cost_basis ?? "..."}</p>

<p><b>PnL:</b> ${p.pnl_pct ?? "..."}%</p>

<p><b>Allocatie:</b> ${p.allocation_pct ?? "..."}%</p>

<p><b>Risk state:</b> ${p.risk_state ?? "..."}</p>
            <hr>

            <p><b>Liquidity:</b> ${coin.liquidity}</p>
            <div class="explain">${explainHtml("Betekenis Liquidity", ci.liquidity)}</div>

            <p><b>Trend:</b> ${coin.trend}</p>

            <p><b>Volatility:</b> ${coin.volatility}</p>
            <div class="explain">${explainHtml("Betekenis Volatility", ci.volatility)}</div>

            <p><b>RSI:</b> ${coin.rsi_14d}</p>
            <div class="explain">${explainHtml("Betekenis RSI", ci.rsi)}</div>

            <p><b>ATR:</b> ${coin.atr_14d}</p>

            <hr>

            <p><b>Confirmations:</b> ${(coin.confirmations || []).join(', ') || "none"}</p>
            <p><b>Blockers:</b> ${(coin.blockers || []).join(', ') || "none"}</p>
            <p><b>Adaptive reasons:</b> ${(adaptive.reasons || []).join(', ') || "none"}</p>
        `;

        coinsDiv.appendChild(card);
    }

    // Raw output verborgen
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
