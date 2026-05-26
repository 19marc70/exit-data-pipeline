ENGINE_VERSION = "v10.1-corrected-rsi-atr-picycle"


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def rsi_state(rsi):
    if rsi is None:
        return "⚪ unavailable"
    if rsi < 30:
        return "🟢 oversold"
    if rsi < 55:
        return "🟢 neutral"
    if rsi < 70:
        return "🟡 elevated"
    if rsi < 80:
        return "🟠 overbought"
    return "🔴 extreme_overbought"


def coin_score_from_indicators(rsi, volatility):
    score = 0
    confirmations = []
    blockers = []

    if rsi is None:
        blockers.append("rsi_unavailable")
    elif rsi >= 80:
        score += 30
        confirmations.append("rsi_extreme_overbought")
    elif rsi >= 70:
        score += 20
        confirmations.append("rsi_overbought")
    elif rsi >= 60:
        score += 10
        confirmations.append("rsi_elevated")

    if "🔴" in volatility:
        score += 20
        confirmations.append("high_volatility")
    elif "🟡" in volatility:
        score += 10
        confirmations.append("medium_volatility")

    return score, confirmations, blockers


def signal_from_score(score):
    if score >= 70:
        return "SELL_REVIEW"
    if score >= 50:
        return "LIGHT_TRIM_WATCH"
    return "HOLD"


def sell_pct_from_score(score):
    if score >= 80:
        return 15
    if score >= 70:
        return 10
    if score >= 50:
        return 5
    return 0


def build_portfolio(snapshot):
    holdings = snapshot.get("holdings", {})
    avg_entry = snapshot.get("avg_entry", {})
    indicators = snapshot.get("coin_indicators", {})

    positions = {}
    total_value = 0
    total_cost = 0

    for symbol, qty in holdings.items():
        price = safe_float(indicators.get(symbol, {}).get("current_price"))
        entry = safe_float(avg_entry.get(symbol))
        qty = safe_float(qty)

        market_value = qty * price
        cost_basis = qty * entry
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0

        total_value += market_value
        total_cost += cost_basis

        positions[symbol] = {
            "qty": round(qty, 8),
            "current_price": round(price, 6),
            "avg_entry": round(entry, 6),
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "unrealized_pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        }

    for symbol, pos in positions.items():
        allocation = (pos["market_value"] / total_value * 100) if total_value else 0
        pos["allocation_pct"] = round(allocation, 2)

        if allocation > 45:
            pos["risk_state"] = "🔴 concentrated"
        elif allocation > 30:
            pos["risk_state"] = "🟡 elevated"
        else:
            pos["risk_state"] = "🟢 normal"

    largest_symbol = None
    largest_pct = 0

    for symbol, pos in positions.items():
        if pos["allocation_pct"] > largest_pct:
            largest_symbol = symbol
            largest_pct = pos["allocation_pct"]

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    if largest_pct > 45:
        state = "🔴 concentration_risk"
    elif largest_pct > 30:
        state = "🟡 moderate_concentration"
    else:
        state = "🟢 balanced"

    return {
        "total_portfolio_value": round(total_value, 2),
        "total_cost_basis": round(total_cost, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
        "portfolio_pnl_pct": round(total_pnl_pct, 2),
        "portfolio_risk": {
            "largest_position": largest_symbol,
            "largest_position_pct": round(largest_pct, 2),
            "state": state,
        },
        "positions": positions,
    }


def build_signal(symbol, snapshot, portfolio):
    indicators = snapshot.get("coin_indicators", {}).get(symbol, {})
    position = portfolio.get("positions", {}).get(symbol, {})

    rsi = indicators.get("rsi_14d")
    atr = indicators.get("atr_14d")
    atr_pct = indicators.get("atr_pct_14d")
    volatility = indicators.get("volatility", "⚪ unavailable")

    score, confirmations, blockers = coin_score_from_indicators(rsi, volatility)

    if symbol == "XRP":
        blockers.append("xrp_core_hold")
        sell_pct = 0
        signal = "CORE_HOLD"
    else:
        sell_pct = sell_pct_from_score(score)
        signal = signal_from_score(score)

    qty = safe_float(position.get("qty"))
    sell_qty = qty * sell_pct / 100
    max_daily_qty = qty * 0.15

    if sell_qty > max_daily_qty:
        sell_qty = max_daily_qty
        confirmations.append("daily_sell_cap_applied")

    return {
        "signal": signal,
        "score": round(score, 2),
        "sell_pct": sell_pct,
        "sell_qty": round(sell_qty, 6),
        "target_total_sell_qty": round(qty * sell_pct / 100, 6),
        "max_daily_qty": round(max_daily_qty, 6),
        "trend": "⚪ not_calculated",
        "volatility": volatility,
        "rsi_14d": rsi,
        "atr_14d": atr,
        "atr_pct_14d": atr_pct,
        "liquidity": "⚪ not_calculated",
        "execution_type": "hold" if sell_pct == 0 else "manual_review",
        "confirmations": confirmations,
        "blockers": blockers,
        "portfolio_position": position,
        "adaptive_execution": {
            "slippage_risk": "manual_check_required",
            "reasons": ["liquidity_not_connected"],
        },
        "derivatives": {
            "state": {
                "leverage_risk": "⚪ not_connected",
            }
        },
        "interpretations": {
            "coin_score": {
                "label": signal,
                "meaning": "Gebaseerd op gecorrigeerde daily RSI en ATR.",
                "details": confirmations or ["geen directe risicosignalen"],
            },
            "rsi": {
                "label": rsi_state(rsi),
                "meaning": "RSI wordt berekend op daily candles met voldoende historie.",
                "details": [f"RSI: {rsi}"],
            },
            "volatility": {
                "label": volatility,
                "meaning": "Gebaseerd op ATR% van de huidige prijs.",
                "details": [f"ATR: {atr}", f"ATR%: {atr_pct}"],
            },
            "liquidity": {
                "label": "⚪ not_connected",
                "meaning": "Liquidity is nog niet gekoppeld aan live volume.",
                "details": [],
            },
        },
    }


def build_score_interpretation():
    return {
        "exit_zone": {
            "label": "🟢 No exit zone",
            "meaning": "Geen brede exit zolang meerdere categorieën niet bevestigen.",
            "details": ["RSI/ATR zijn nu gecorrigeerd op daily candles."],
        },
        "cycle_score": {
            "label": "🟡 Neutral",
            "meaning": "Cycle-score gebruikt Pi Cycle als waarschuwing, niet als los verkoopsignaal.",
            "details": [],
        },
        "cycle_state": {
            "label": "Pi Cycle monitored",
            "meaning": "Pi Cycle wordt berekend op BTC 111DMA versus 2x 350DMA.",
            "details": [],
        },
        "macro_score": {
            "label": "⚪ Not connected",
            "meaning": "Macro-data is in deze versie niet live gekoppeld.",
            "details": [],
        },
        "fear_greed": {
            "label": "⚪ Not connected",
            "meaning": "Fear & Greed is niet live gekoppeld in deze module.",
            "details": [],
        },
        "portfolio_risk": {
            "label": "Portfolio concentration check",
            "meaning": "Risico wordt bepaald door grootste positie en allocatie.",
            "details": [],
        },
        "legend": {
            "exit_zone_score": [
                {"range": "0-30", "meaning": "Geen exit-zone"},
                {"range": "30-60", "meaning": "Waakzaam"},
                {"range": "60-80", "meaning": "Exit-review"},
                {"range": "80-100", "meaning": "Distributie-risico"},
            ],
            "cycle_score": [
                {"range": "0-20", "meaning": "Geen top-signalen"},
                {"range": "20-50", "meaning": "Neutraal"},
                {"range": "50-80", "meaning": "Cycle warning"},
                {"range": "80-100", "meaning": "Cycle top risk"},
            ],
            "coin_score": [
                {"range": "0-49", "meaning": "Hold"},
                {"range": "50-69", "meaning": "Trim watch"},
                {"range": "70+", "meaning": "Sell review"},
            ],
            "rsi": [
                {"range": "<30", "meaning": "Oversold"},
                {"range": "30-55", "meaning": "Neutraal"},
                {"range": "55-70", "meaning": "Verhoogd"},
                {"range": "70-80", "meaning": "Overbought"},
                {"range": ">80", "meaning": "Extreme overbought"},
            ],
        },
    }


def build_exit_engine(snapshot):
    portfolio = build_portfolio(snapshot)

    signals = {}
    for symbol in ["XRP", "ONDO", "AERO", "CFG"]:
        signals[symbol] = build_signal(symbol, snapshot, portfolio)

    pi_cycle = snapshot.get("pi_cycle", {})
    pi_triggered = pi_cycle.get("triggered", False)

    cycle_score = 40 if pi_triggered else 5

    coin_risk_score = max([safe_float(c.get("score")) for c in signals.values()] or [0])
    portfolio_risk_score = 15 if portfolio["portfolio_risk"]["largest_position_pct"] > 45 else 5

    exit_zone_score = min(100, cycle_score + coin_risk_score + portfolio_risk_score)

    if exit_zone_score >= 80:
        global_action = "HEAVY_DISTRIBUTION"
    elif exit_zone_score >= 60:
        global_action = "PARTIAL_EXIT_ALLOWED"
    elif exit_zone_score >= 40:
        global_action = "LIGHT_TRIM_ALLOWED"
    else:
        global_action = "NO_FULL_EXIT"

    return {
        "engine_version": ENGINE_VERSION,
        "timestamp": snapshot.get("timestamp"),
        "global_action": global_action,
        "exit_zone_score": round(exit_zone_score, 2),
        "signals": signals,
        "portfolio_intelligence": portfolio,
        "missing_engine_data": snapshot.get("missing_data", []),
        "score_components": {
            "cycle_intelligence": {
                "cycle_score": cycle_score,
                "cycle_state": pi_cycle.get("cycle_state"),
            },
            "macro_intelligence": {
                "macro_score": 0,
                "macro_state": "⚪ not_connected",
            },
            "fear_greed": {
                "value": None,
                "classification": "not_connected",
            },
            "btc_dominance": None,
            "cbbi": {
                "value": None,
            },
            "pi_cycle": pi_cycle,
            "macro_cycle_risk_score": cycle_score,
            "market_structure_score": coin_risk_score,
            "portfolio_risk_score": portfolio_risk_score,
            "multi_category_confirmed": exit_zone_score >= 60,
        },
        "score_interpretation": build_score_interpretation(),
    }
