ENGINE_VERSION = "v10.1-macro-capped-coin-scoring-data-quality"

PORTFOLIO = {
    "XRP": {"qty": 11093.5, "sellable": 0.0, "moonbag": 11093.5, "avg_entry": 0.9699},
    "ONDO": {"qty": 22397.63463725, "sellable": 22397.63463725, "moonbag": 1925.0, "avg_entry": 0.5018},
    "AERO": {"qty": 10251.39604089, "sellable": 10251.39604089, "moonbag": 750.0, "avg_entry": 0.5379},
    "CFG": {"qty": 10667.05368724, "sellable": 10667.05368724, "moonbag": 744.0, "avg_entry": 0.2268},
}

GUARDRAILS = {
    "xrp_sell_allowed": False,
    "moonbags_sell_allowed": False,
    "single_indicator_exit_allowed": False,
    "full_exit_allowed_without_multi_category_confirmation": False,
    "slippage_above_5pct_allowed": False,
}

SELL_TARGETS = ["ONDO", "AERO", "CFG"]


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def text_contains(value, word):
    return word.lower() in str(value).lower()


def interpret_score(category, value):
    if value is None:
        return {
            "label": "⚪ unknown",
            "meaning": "geen data beschikbaar",
            "details": ["⚪ onvoldoende data"],
        }

    value = safe_float(value)

    rules = {
        "exit_zone": [
            (-999, 20, "🟢 Accumulatiezone", ["⚪ markt vroeg in cyclus", "⚪ geen agressieve verkoop nodig", "⚪ geen bevestigde distributiefase"]),
            (20, 40, "🟡 Vroege bullfase", ["⚪ opbouwfase", "⚪ nog geen sterke distributie", "⚪ monitoren"]),
            (40, 60, "🟠 Verhoogde distributiekans", ["⚪ voorzichtig worden", "⚪ gedeeltelijke winstneming mogelijk", "⚪ extra bevestiging nodig"]),
            (60, 80, "🔴 Exit-zone dichtbij", ["⚪ hogere kans op topvorming", "⚪ gedeeltelijke verkoop overwegen", "⚪ execution-limits respecteren"]),
            (80, 999, "🚨 Historische topzone", ["⚪ euforie", "⚪ grote distributierisico's", "⚪ alleen verkopen binnen liquidity guardrails"]),
        ],
        "cycle": [
            (-999, 0, "🟢 Accumulatie / onderwaardering", ["⚪ historisch goedkoop", "⚪ geen top-signalen"]),
            (0, 20, "🟡 Neutrale fase", ["⚪ zeer vroeg / neutraal", "⚪ geen top-signalen", "⚪ geen distributiefase"]),
            (20, 40, "🟡 Bullmarkt bouwt op", ["⚪ momentum neemt toe", "⚪ nog geen exit-zone"]),
            (40, 60, "🟠 Verhoogde distributiekans", ["⚪ markt wordt warmer", "⚪ voorzichtig worden"]),
            (60, 80, "🔴 Exit-zone", ["⚪ risico stijgt", "⚪ gedeeltelijke exits mogelijk"]),
            (80, 999, "🚨 Hoge euforie / top-risico", ["⚪ historisch oververhit", "⚪ top-risico hoog"]),
        ],
        "macro": [
            (-999, -20, "🟢 Macro positief", ["⚪ ondersteunende omgeving", "⚪ geen macro-exitdruk"]),
            (-20, 20, "🟡 Macro neutraal", ["⚪ geen duidelijke richting", "⚪ wachten op bevestiging"]),
            (20, 40, "🟠 Macro waarschuwing", ["⚪ macro-risico stijgt", "⚪ voorzichtig worden"]),
            (40, 60, "🔴 Hoog macro-risico", ["⚪ beschermingsmodus", "⚪ exits voorbereiden"]),
            (60, 999, "🚨 Extreem macro-risico", ["⚪ agressieve defensie", "⚪ multi-factor exit waarschijnlijk"]),
        ],
        "fear": [
            (0, 25, "🟢 Extreme Fear", ["⚪ historisch vaak accumulatie", "⚪ geen euforie"]),
            (25, 45, "🟡 Fear", ["⚪ voorzichtig sentiment", "⚪ geen top-euforie"]),
            (45, 55, "⚪ Neutral", ["⚪ geen duidelijke richting"]),
            (55, 75, "🟠 Greed", ["⚪ risico neemt toe", "⚪ monitoren"]),
            (75, 101, "🔴 Extreme Greed", ["⚪ euforie", "⚪ top-risico stijgt"]),
        ],
        "coin": [
            (-999, 0, "🟢 Accumulatie / laag risico", ["⚪ geen sell-druk vanuit score", "⚪ meestal HOLD"]),
            (0, 20, "🟡 Hold / normaal risico", ["⚪ normaal gedrag", "⚪ geen directe exit"]),
            (20, 40, "🟠 Voorzichtig", ["⚪ opletten", "⚪ extra bevestiging nodig"]),
            (40, 60, "🔴 Gedeeltelijke verkoopzone", ["⚪ distributie mogelijk", "⚪ alleen bij multi-factor bevestiging"]),
            (60, 999, "🚨 Sterke verkoopzone", ["⚪ hoog risico", "⚪ adaptive sell mogelijk"]),
        ],
        "portfolio_risk": [
            (0, 15, "🟢 Laag portfolio-risico", ["⚪ concentratie beperkt", "⚪ drawdown beheersbaar"]),
            (15, 30, "🟡 Medium portfolio-risico", ["⚪ concentratie of drawdown aanwezig", "⚪ extra voorzichtig met sizing"]),
            (30, 999, "🔴 Hoog portfolio-risico", ["⚪ concentratie/drawdown hoog", "⚪ portfolio modifier actief"]),
        ],
        "rsi": [
            (0, 30, "🟢 Oversold", ["⚪ mogelijk uitgeputte verkoopdruk", "⚪ geen automatische exit"]),
            (30, 70, "🟡 Normaal", ["⚪ geen extreme RSI", "⚪ neutraal"]),
            (70, 80, "🟠 Overbought", ["⚪ momentum heet", "⚪ monitoren"]),
            (80, 101, "🔴 Extreme overbought", ["⚪ euforie mogelijk", "⚪ exit-bevestiging zoeken"]),
        ],
    }

    for low, high, label, details in rules.get(category, []):
        if low <= value < high:
            return {"label": label, "meaning": label, "details": details}

    return {
        "label": "⚪ unknown",
        "meaning": "buiten bereik",
        "details": ["⚪ waarde buiten interpretatiebereik"],
    }


def interpret_state(category, value):
    text = str(value)

    if category == "cycle_state":
        if "ACCUMULATION" in text:
            return {"label": "🟢 ACCUMULATION_SUPPORT", "meaning": "historisch goedkoop / ondersteunend", "details": ["⚪ geen topfase"]}
        if "NEUTRAL" in text:
            return {"label": "🟡 NEUTRAL_CYCLE", "meaning": "geen duidelijke richting", "details": ["⚪ geen top-signalen"]}
        if "LATE" in text or "DISTRIBUTION" in text:
            return {"label": "🟠 LATE_CYCLE", "meaning": "voorzichtig worden", "details": ["⚪ distributierisico stijgt"]}
        if "TOP" in text or "EXIT" in text or "EUPHORIA" in text:
            return {"label": "🔴 TOP / EXIT_ZONE", "meaning": "grote exitfase of euforie", "details": ["⚪ top-risico hoog"]}

    if category == "liquidity":
        if "strong" in text.lower():
            return {"label": "🟢 strong", "meaning": "goede uitvoerbaarheid", "details": ["⚪ lagere slippage"]}
        if "moderate" in text.lower():
            return {"label": "🟡 moderate", "meaning": "voorzichtig uitvoeren", "details": ["⚪ ladder execution"]}
        if "severe" in text.lower():
            return {"label": "🔴 severe", "meaning": "zeer slechte liquiditeit", "details": ["⚪ geen agressieve exits"]}

    if category == "volatility":
        if "low" in text.lower():
            return {"label": "🟢 low", "meaning": "rustige markt", "details": ["⚪ execution makkelijker"]}
        if "medium" in text.lower():
            return {"label": "🟡 medium", "meaning": "normale schommelingen", "details": ["⚪ standaard voorzichtigheid"]}
        if "elevated" in text.lower():
            return {"label": "🟠 elevated", "meaning": "verhoogde volatiliteit", "details": ["⚪ kleinere verkoopblokken"]}
        if "high" in text.lower():
            return {"label": "🔴 high", "meaning": "hoge volatiliteit", "details": ["⚪ execution risk hoog"]}

    return {"label": str(value), "meaning": "geen aanvullende interpretatie", "details": []}


def classify_liquidity(symbol, coin):
    volume = safe_float(coin.get("usd_24h_vol"))
    market_cap = safe_float(coin.get("usd_market_cap"))

    if volume <= 250000:
        return "🔴 severe"

    if volume <= 2500000:
        return "🟡 moderate"

    if market_cap > 0 and volume / market_cap < 0.01:
        return "🟡 moderate"

    return "🟢 strong"


def max_daily_pct_from_liquidity(liquidity):
    if text_contains(liquidity, "severe"):
        return 5
    if text_contains(liquidity, "moderate"):
        return 10
    return 15


def liquidity_multiplier(liquidity):
    if text_contains(liquidity, "severe"):
        return 0.0
    if text_contains(liquidity, "moderate"):
        return 0.55
    return 1.0


def volatility_multiplier(volatility):
    if text_contains(volatility, "high"):
        return 0.45
    if text_contains(volatility, "elevated"):
        return 0.65
    if text_contains(volatility, "medium"):
        return 0.85
    if text_contains(volatility, "low"):
        return 1.0
    return 0.75


def atr_multiplier(price, atr):
    price = safe_float(price)
    atr = safe_float(atr)

    if price <= 0 or atr <= 0:
        return 0.75

    atr_pct = (atr / price) * 100

    if atr_pct >= 10:
        return 0.40
    if atr_pct >= 6:
        return 0.55
    if atr_pct >= 3:
        return 0.75
    if atr_pct >= 1:
        return 0.90
    return 1.0


def position_size_multiplier(symbol):
    sellable = safe_float(PORTFOLIO.get(symbol, {}).get("sellable"))

    if sellable <= 0:
        return 0.0
    if symbol == "CFG":
        return 0.50
    if sellable >= 20_000:
        return 0.85
    if sellable >= 10_000:
        return 0.90

    return 1.0


def estimate_slippage_risk(liquidity, volatility, sell_qty, max_daily_qty):
    if sell_qty <= 0:
        return "none"
    if text_contains(liquidity, "severe"):
        return "above_5pct_blocked"
    if max_daily_qty > 0 and sell_qty > max_daily_qty:
        return "above_daily_limit"
    if text_contains(volatility, "high"):
        return "elevated"
    if text_contains(volatility, "elevated") and text_contains(liquidity, "moderate"):
        return "elevated"

    return "controlled"


def score_market_structure(coin):
    score = 0
    reasons = []

    trend = coin.get("trend")
    volatility = coin.get("volatility")

    rsi_raw = coin.get("rsi_14d")
    rsi = None if rsi_raw is None else safe_float(rsi_raw)

    if text_contains(trend, "weakening"):
        score += 12
        reasons.append("trend_weakening")
    elif text_contains(trend, "strengthening"):
        score -= 8
        reasons.append("trend_strengthening")
    elif text_contains(trend, "sideways"):
        reasons.append("trend_sideways")

    # Volatility is primarily execution risk, not an automatic exit trigger.
    if text_contains(volatility, "high"):
        score += 6
        reasons.append("volatility_high_execution_risk")
    elif text_contains(volatility, "elevated"):
        score += 3
        reasons.append("volatility_elevated_execution_risk")
    elif text_contains(volatility, "low"):
        score -= 3
        reasons.append("volatility_low")

    if rsi is None:
        reasons.append("rsi_unavailable")
    elif rsi >= 80:
        score += 18
        reasons.append("rsi_extreme_overbought")
    elif rsi >= 70:
        score += 8
        reasons.append("rsi_overbought")
    elif rsi <= 30:
        score -= 8
        reasons.append("rsi_oversold")
    elif rsi <= 40:
        score -= 3
        reasons.append("rsi_weak")

    return score, reasons


def score_derivatives(coin):
    derivatives = coin.get("derivatives", {})
    state = derivatives.get("state", {})
    leverage_risk = state.get("leverage_risk")
    reasons = list(state.get("reasons", []))

    score = 0

    if text_contains(leverage_risk, "leverage_overheat"):
        score += 25
    elif text_contains(leverage_risk, "overheated"):
        score += 20
    elif text_contains(leverage_risk, "crowded"):
        score += 10
    elif text_contains(leverage_risk, "short_pressure"):
        score -= 8

    return score, reasons


def score_cycle_and_macro(snapshot):
    btc = snapshot.get("btc", {})
    cycle = btc.get("cycle_intelligence", {})
    macro = btc.get("macro_intelligence", {})
    cbbi = btc.get("cbbi", {})
    fear_greed = btc.get("fear_greed", {})
    btc_dominance = btc.get("dominance")

    raw_cycle_score = safe_float(cycle.get("cycle_score"))
    raw_macro_score = safe_float(macro.get("macro_score"))
    cbbi_value = cbbi.get("value")
    fg_value = fear_greed.get("value")

    risk_score = 0
    reasons = []

    if raw_cycle_score < 0:
        risk_score += abs(raw_cycle_score)
        reasons.append("cycle_risk_negative")
    elif raw_cycle_score > 0:
        risk_score -= min(raw_cycle_score, 20)
        reasons.append("cycle_support_positive")

    if raw_macro_score < 0:
        risk_score += abs(raw_macro_score)
        reasons.append("macro_risk_negative")
    elif raw_macro_score > 0:
        risk_score -= min(raw_macro_score, 20)
        reasons.append("macro_support_positive")

    if cbbi_value is not None:
        cbbi_value = safe_float(cbbi_value)

        if cbbi_value >= 85:
            risk_score += 35
            reasons.append("cbbi_top_zone")
        elif cbbi_value >= 75:
            risk_score += 20
            reasons.append("cbbi_late_cycle")
        elif cbbi_value <= 30:
            risk_score -= 10
            reasons.append("cbbi_accumulation_support")

    if fg_value is not None:
        fg_value = safe_float(fg_value)

        if fg_value >= 80:
            risk_score += 15
            reasons.append("fear_greed_extreme_greed")
        elif fg_value <= 25:
            risk_score -= 10
            reasons.append("fear_greed_fear_support")

    if btc_dominance is not None:
        btc_dominance = safe_float(btc_dominance)

        if btc_dominance >= 58:
            risk_score += 10
            reasons.append("btc_dominance_alt_headwind")
        elif btc_dominance <= 48:
            risk_score -= 5
            reasons.append("btc_dominance_alt_support")

    return risk_score, reasons


def apply_macro_regime_cap(score, snapshot):
    btc = snapshot.get("btc", {})
    cycle = btc.get("cycle_intelligence", {}) or {}
    macro = btc.get("macro_intelligence", {}) or {}
    cbbi = btc.get("cbbi", {}) or {}
    fear_greed = btc.get("fear_greed", {}) or {}
    pi_cycle = btc.get("pi_cycle", {}) or {}

    cycle_state = str(cycle.get("cycle_state", ""))
    macro_state = str(macro.get("macro_state", ""))
    pi_state = str(pi_cycle.get("cycle_state", ""))

    cbbi_value = safe_float(cbbi.get("value"), None)
    fg_value = safe_float(fear_greed.get("value"), None)

    pi_top = bool(pi_cycle.get("top_risk")) or bool(pi_cycle.get("triggered"))

    if pi_top:
        return score

    early_or_neutral_cycle = (
        "NEUTRAL" in cycle_state
        or "ACCUMULATION" in cycle_state
        or "EARLY" in pi_state
    )

    no_euphoria = fg_value is None or fg_value < 75
    cbbi_not_hot = cbbi_value is None or cbbi_value < 75

    if fg_value is not None and fg_value <= 25:
        return min(score, 25)

    if early_or_neutral_cycle and no_euphoria and cbbi_not_hot:
        return min(score, 30)

    if "MACRO_NEUTRAL" in macro_state and cbbi_not_hot:
        return min(score, 35)

    return score


def build_data_quality(snapshot):
    missing = list(snapshot.get("missing_data", []))
    coins = snapshot.get("coins", {})
    btc = snapshot.get("btc", {})

    warnings = []

    for symbol, coin in coins.items():
        if coin.get("rsi_14d") is None:
            warnings.append(f"{symbol}_rsi_missing")

        if coin.get("atr_14d") is None:
            warnings.append(f"{symbol}_atr_missing")

        if coin.get("current_price") is None and coin.get("usd") is None:
            warnings.append(f"{symbol}_price_missing")

        derivatives = coin.get("derivatives", {}) or {}
        der_state = derivatives.get("state", {}) or {}

        if der_state.get("leverage_risk") in [None, "⚪ unknown"]:
            warnings.append(f"{symbol}_derivatives_unknown")

    if not btc.get("cbbi", {}).get("available"):
        warnings.append("cbbi_missing")

    if btc.get("fear_greed", {}).get("value") is None:
        warnings.append("fear_greed_missing")

    if btc.get("dominance") is None:
        warnings.append("btc_dominance_missing")

    pi_cycle = btc.get("pi_cycle", {})

    if not pi_cycle or pi_cycle.get("cycle_state") in [None, "⚪ unavailable"]:
        warnings.append("pi_cycle_missing_or_unavailable")

    all_warnings = missing + warnings

    unique_warnings = []
    for warning in all_warnings:
        if warning not in unique_warnings:
            unique_warnings.append(warning)

    if not unique_warnings:
        status = "✅ COMPLETE"
        label = "Alle belangrijke data beschikbaar"
    elif len(unique_warnings) <= 3:
        status = "⚠️ PARTIAL"
        label = "Enkele databronnen ontbreken"
    else:
        status = "❌ DEGRADED"
        label = "Meerdere belangrijke databronnen ontbreken"

    return {
        "status": status,
        "label": label,
        "warnings": unique_warnings,
        "warning_count": len(unique_warnings),
    }


def build_portfolio_intelligence(snapshot):
    coins = snapshot.get("coins", {})
    positions = {}

    total_value = 0.0
    total_cost = 0.0
    total_unrealized_pnl = 0.0

    for symbol, config in PORTFOLIO.items():
        coin = coins.get(symbol, {})

        qty = safe_float(config.get("qty"))
        avg_entry = safe_float(config.get("avg_entry"))
        price = safe_float(coin.get("current_price") or coin.get("usd"))

        market_value = qty * price
        cost_basis = qty * avg_entry
        unrealized_pnl = market_value - cost_basis
        pnl_pct = (unrealized_pnl / cost_basis) * 100 if cost_basis > 0 else 0.0

        total_value += market_value
        total_cost += cost_basis
        total_unrealized_pnl += unrealized_pnl

        positions[symbol] = {
            "qty": round(qty, 8),
            "avg_entry": round(avg_entry, 6),
            "current_price": round(price, 6),
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "allocation_pct": 0.0,
            "risk_state": "unknown",
        }

    largest_position = None
    largest_position_pct = 0.0

    for symbol, position in positions.items():
        allocation_pct = (position["market_value"] / total_value) * 100 if total_value > 0 else 0.0

        risk_state = "normal"

        if allocation_pct >= 50:
            risk_state = "high_concentration"
        elif allocation_pct >= 35:
            risk_state = "medium_concentration"

        if position["pnl_pct"] <= -35:
            risk_state = "deep_drawdown"
        elif position["pnl_pct"] <= -25 and risk_state == "normal":
            risk_state = "drawdown_watch"

        position["allocation_pct"] = round(allocation_pct, 2)
        position["risk_state"] = risk_state

        if allocation_pct > largest_position_pct:
            largest_position_pct = allocation_pct
            largest_position = symbol

    portfolio_pnl_pct = (total_unrealized_pnl / total_cost) * 100 if total_cost > 0 else 0.0

    concentration_score = (
        25 if largest_position_pct >= 60
        else 15 if largest_position_pct >= 50
        else 8 if largest_position_pct >= 35
        else 0
    )

    drawdown_score = 0

    for position in positions.values():
        if position["pnl_pct"] <= -35:
            drawdown_score += 10
        elif position["pnl_pct"] <= -25:
            drawdown_score += 5

    portfolio_risk_score = concentration_score + drawdown_score

    portfolio_state = (
        "HIGH_RISK" if portfolio_risk_score >= 30
        else "MEDIUM_RISK" if portfolio_risk_score >= 15
        else "LOW_RISK"
    )

    return {
        "total_portfolio_value": round(total_value, 2),
        "total_cost_basis": round(total_cost, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "portfolio_pnl_pct": round(portfolio_pnl_pct, 2),
        "positions": positions,
        "portfolio_risk": {
            "portfolio_risk_score": portfolio_risk_score,
            "concentration_score": concentration_score,
            "drawdown_score": drawdown_score,
            "largest_position": largest_position,
            "largest_position_pct": round(largest_position_pct, 2),
            "state": portfolio_state,
        },
    }


def determine_global_action(exit_zone_score, multi_category_confirmed):
    if exit_zone_score >= 80 and multi_category_confirmed:
        return "HEAVY_DISTRIBUTION"
    if exit_zone_score >= 60 and multi_category_confirmed:
        return "PARTIAL_EXIT_ALLOWED"
    if exit_zone_score >= 40 and multi_category_confirmed:
        return "LIGHT_TRIM_ALLOWED"
    if exit_zone_score <= -20:
        return "ACCUMULATION_SUPPORT"

    return "NO_FULL_EXIT"


def base_sell_pct_from_exit_zone(exit_zone_score):
    if exit_zone_score >= 80:
        return 50
    if exit_zone_score >= 60:
        return 25
    if exit_zone_score >= 40:
        return 10

    return 0


def adaptive_sell_engine(symbol, coin, exit_zone_score, liquidity, blockers, confirmations):
    sellable = safe_float(PORTFOLIO.get(symbol, {}).get("sellable"))
    price = safe_float(coin.get("current_price") or coin.get("usd"))
    atr = safe_float(coin.get("atr_14d"))
    volatility = coin.get("volatility")

    base_sell_pct = base_sell_pct_from_exit_zone(exit_zone_score)

    multipliers = {
        "liquidity": liquidity_multiplier(liquidity),
        "volatility": volatility_multiplier(volatility),
        "atr": atr_multiplier(price, atr),
        "position_size": position_size_multiplier(symbol),
    }

    reasons = []

    if symbol not in SELL_TARGETS:
        return {
            "base_sell_pct": 0,
            "adaptive_sell_pct": 0,
            "target_total_qty": 0.0,
            "today_sell_qty": 0.0,
            "max_daily_qty": 0.0,
            "execution_days_estimate": 0,
            "slippage_risk": "blocked",
            "execution_style": "no_sell_target",
            "multipliers": multipliers,
            "reasons": ["not_sell_target"],
        }

    if "insufficient_multi_factor_confirmation" in blockers:
        reasons.append("blocked_insufficient_multi_factor_confirmation")
    if "execution_liquidity_severe" in blockers:
        reasons.append("blocked_execution_liquidity_severe")
    if "no_trade_if_expected_slippage_above_5pct" in blockers:
        reasons.append("blocked_expected_slippage_above_5pct")
    if len(confirmations) < 2:
        reasons.append("blocked_less_than_two_confirmations")

    if reasons:
        return {
            "base_sell_pct": base_sell_pct,
            "adaptive_sell_pct": 0,
            "target_total_qty": 0.0,
            "today_sell_qty": 0.0,
            "max_daily_qty": round(sellable * max_daily_pct_from_liquidity(liquidity) / 100, 6),
            "execution_days_estimate": 0,
            "slippage_risk": "blocked",
            "execution_style": "hold",
            "multipliers": multipliers,
            "reasons": reasons,
        }

    adjusted_pct = base_sell_pct

    for value in multipliers.values():
        adjusted_pct *= value

    if text_contains(liquidity, "moderate"):
        adjusted_pct = min(adjusted_pct, 10)

    if text_contains(liquidity, "severe"):
        adjusted_pct = 0

    adaptive_sell_pct = round(max(0, min(50, adjusted_pct)), 2)

    max_daily_pct = max_daily_pct_from_liquidity(liquidity)
    max_daily_qty = round(sellable * max_daily_pct / 100, 6)

    target_total_qty = round(sellable * adaptive_sell_pct / 100, 6)
    today_sell_qty = round(min(target_total_qty, max_daily_qty), 6)

    execution_days_estimate = 0

    if max_daily_qty > 0 and target_total_qty > 0:
        execution_days_estimate = int((target_total_qty + max_daily_qty - 0.000001) // max_daily_qty)

        if target_total_qty % max_daily_qty > 0:
            execution_days_estimate += 1

    slippage_risk = estimate_slippage_risk(liquidity, volatility, today_sell_qty, max_daily_qty)

    if slippage_risk in ["above_5pct_blocked", "above_daily_limit"]:
        today_sell_qty = 0.0
        adaptive_sell_pct = 0
        reasons.append(slippage_risk)

    execution_style = (
        "multi_day_ladder" if adaptive_sell_pct >= 25
        else "limit_ladder" if adaptive_sell_pct > 0
        else "hold"
    )

    return {
        "base_sell_pct": base_sell_pct,
        "adaptive_sell_pct": adaptive_sell_pct,
        "target_total_qty": target_total_qty,
        "today_sell_qty": today_sell_qty,
        "max_daily_qty": max_daily_qty,
        "execution_days_estimate": execution_days_estimate,
        "slippage_risk": slippage_risk,
        "execution_style": execution_style,
        "multipliers": multipliers,
        "reasons": reasons if reasons else ["adaptive_execution_ok"],
    }


def build_allocation_plan(global_action, exit_zone_score, portfolio_intelligence):
    portfolio_risk = portfolio_intelligence.get("portfolio_risk", {})
    largest_position = portfolio_risk.get("largest_position")
    largest_position_pct = safe_float(portfolio_risk.get("largest_position_pct"))

    if global_action in ["HEAVY_DISTRIBUTION", "PARTIAL_EXIT_ALLOWED"]:
        stablecoin_target_pct = min(70, max(25, int(exit_zone_score)))
        status = "RAISE_STABLECOINS"
    elif global_action == "LIGHT_TRIM_ALLOWED":
        stablecoin_target_pct = 15
        status = "LIGHT_STABLECOIN_BUILD"
    else:
        stablecoin_target_pct = 0
        status = "NO_NEW_STABLECOIN_ACTION"

    concentration_note = "none"

    if largest_position_pct >= 50:
        concentration_note = f"{largest_position}_concentration_above_50pct"

    return {
        "stablecoin_target_pct": stablecoin_target_pct,
        "target_pct_of_realized_sales": stablecoin_target_pct,
        "status": status,
        "rule": "only_from_confirmed_sell_signals",
        "portfolio_concentration_note": concentration_note,
        "xrp_allocation": {
            "action": "HOLD_10_YEAR_CORE",
            "sell_allowed": False,
        },
        "ondo_allocation": {
            "action": "MAINTAIN_CORE_RAW_POSITION",
        },
        "dca_out_ladder": [
            {"zone": "LIGHT_TRIM_ALLOWED", "sell_pct": 10},
            {"zone": "PARTIAL_EXIT_ALLOWED", "sell_pct": 25},
            {"zone": "HEAVY_DISTRIBUTION", "sell_pct": 50},
        ],
    }


def build_reentry_engine(snapshot, global_action):
    coins = snapshot.get("coins", {})
    result = {}

    for symbol, coin in coins.items():
        trend = coin.get("trend")
        volatility = coin.get("volatility")

        if global_action in ["HEAVY_DISTRIBUTION", "PARTIAL_EXIT_ALLOWED"]:
            status = "WAIT"
            deploy_pct = 0
            reason = "exit_mode_active"
        elif text_contains(trend, "strengthening") and text_contains(volatility, "low"):
            status = "WATCH"
            deploy_pct = 5
            reason = "trend_confirming_low_volatility"
        else:
            status = "WAIT"
            deploy_pct = 0
            reason = "conditions_not_met"

        result[symbol] = {
            "reentry_status": status,
            "deploy_pct": deploy_pct,
            "reason": reason,
            "trend": trend,
            "volatility": volatility,
        }

    return result


def build_score_interpretation(engine):
    sc = engine.get("score_components", {})
    cycle = sc.get("cycle_intelligence", {}) or {}
    macro = sc.get("macro_intelligence", {}) or {}
    fear = sc.get("fear_greed", {}) or {}
    portfolio_risk = engine.get("portfolio_intelligence", {}).get("portfolio_risk", {}) or {}

    return {
        "exit_zone": interpret_score("exit_zone", engine.get("exit_zone_score")),
        "cycle_score": interpret_score("cycle", cycle.get("cycle_score")),
        "cycle_state": interpret_state("cycle_state", cycle.get("cycle_state")),
        "macro_score": interpret_score("macro", macro.get("macro_score")),
        "fear_greed": interpret_score("fear", fear.get("value")),
        "portfolio_risk": interpret_score(
            "portfolio_risk",
            portfolio_risk.get("portfolio_risk_score"),
        ),
        "legend": {
            "exit_zone_score": [
                {"range": "<20", "meaning": "🟢 Accumulatiezone / geen agressieve verkoop"},
                {"range": "20–40", "meaning": "🟡 Vroege bullfase"},
                {"range": "40–60", "meaning": "🟠 Verhoogde distributiekans"},
                {"range": "60–80", "meaning": "🔴 Exit-zone dichtbij"},
                {"range": ">80", "meaning": "🚨 Historische topzone"},
            ],
            "cycle_score": [
                {"range": "<0", "meaning": "Accumulatie / onderwaardering"},
                {"range": "0–20", "meaning": "Neutrale fase"},
                {"range": "20–40", "meaning": "Bullmarkt bouwt op"},
                {"range": "40–60", "meaning": "Verhoogde distributiekans"},
                {"range": "60–80", "meaning": "Exit-zone nadert"},
                {"range": ">80", "meaning": "Hoge euforie / top-risico"},
            ],
            "coin_score": [
                {"range": "<0", "meaning": "Accumulatie / laag risico"},
                {"range": "0–20", "meaning": "Hold / normaal risico"},
                {"range": "20–40", "meaning": "Voorzichtig"},
                {"range": "40–60", "meaning": "Gedeeltelijke verkoopzone"},
                {"range": ">60", "meaning": "Sterke verkoopzone"},
            ],
            "rsi": [
                {"range": "<30", "meaning": "Oversold"},
                {"range": "30–70", "meaning": "Normaal"},
                {"range": "70–80", "meaning": "Overbought"},
                {"range": ">80", "meaning": "Extreme overbought"},
            ],
        },
    }


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})
    missing = list(snapshot.get("missing_data", []))

    data_quality = build_data_quality(snapshot)
    portfolio_intelligence = build_portfolio_intelligence(snapshot)
    macro_cycle_score, macro_cycle_reasons = score_cycle_and_macro(snapshot)

    portfolio_risk_score = safe_float(
        portfolio_intelligence.get("portfolio_risk", {}).get("portfolio_risk_score")
    )

    if portfolio_risk_score >= 30:
        macro_cycle_score += 10
        macro_cycle_reasons.append("portfolio_high_risk_modifier")
    elif portfolio_risk_score >= 15:
        macro_cycle_score += 5
        macro_cycle_reasons.append("portfolio_medium_risk_modifier")

    signals = {}
    coin_risk_scores = []

    for symbol, coin in coins.items():
        liquidity = classify_liquidity(symbol, coin)
        structure_score, structure_reasons = score_market_structure(coin)
        derivatives_score, derivatives_reasons = score_derivatives(coin)

        coin_risk = structure_score + derivatives_score
        coin_risk_scores.append(coin_risk)

        confirmations = []
        blockers = []

        if symbol == "XRP":
            confirmations.append("xrp_is_not_sell_target")
            blockers.append("xrp_sell_disabled")

        if text_contains(liquidity, "strong"):
            confirmations.append("execution_liquidity_strong")
        elif text_contains(liquidity, "severe"):
            blockers.append("execution_liquidity_severe")

        if structure_score >= 20:
            confirmations.append("market_structure_risk")
        if derivatives_score >= 10:
            confirmations.append("derivatives_risk")
        if macro_cycle_score >= 20:
            confirmations.append("macro_cycle_risk")

        position = portfolio_intelligence.get("positions", {}).get(symbol, {})
        allocation_pct = safe_float(position.get("allocation_pct"))
        pnl_pct = safe_float(position.get("pnl_pct"))

        if allocation_pct >= 35:
            confirmations.append("portfolio_concentration_risk")
        if pnl_pct >= 50:
            confirmations.append("portfolio_profit_available")
        if pnl_pct <= -30:
            blockers.append("avoid_forced_sell_deep_drawdown")

        if len(confirmations) < 2:
            blockers.append("insufficient_multi_factor_confirmation")

        if text_contains(liquidity, "severe"):
            blockers.append("no_trade_if_expected_slippage_above_5pct")

        raw_score = coin_risk + max(0, macro_cycle_score)
        raw_score = apply_macro_regime_cap(raw_score, snapshot)

        max_daily_pct = max_daily_pct_from_liquidity(liquidity)
        sellable = safe_float(PORTFOLIO.get(symbol, {}).get("sellable"))
        max_daily_qty = round(sellable * max_daily_pct / 100, 6)

        signals[symbol] = {
            "signal": "HOLD_NO_SELL_TARGET" if symbol == "XRP" else "HOLD",
            "score": round(raw_score, 2),
            "sell_pct": 0,
            "confirmations": confirmations,
            "blockers": blockers,
            "liquidity": liquidity,
            "price": coin.get("current_price") or coin.get("usd"),
            "change_24h": coin.get("usd_24h_change"),
            "volume_24h": coin.get("usd_24h_vol"),
            "rsi_14d": coin.get("rsi_14d"),
            "atr_14d": coin.get("atr_14d"),
            "atr_pct_14d": coin.get("atr_pct_14d"),
            "trend": coin.get("trend"),
            "volatility": coin.get("volatility"),
            "portfolio_position": position,
            "derivatives": coin.get("derivatives", {}),
            "sell_qty": 0.0,
            "max_daily_qty": 0.0 if symbol == "XRP" else max_daily_qty,
            "execution_type": "limit_or_ladder_only",
            "adaptive_execution": {},
            "score_breakdown": {
                "market_structure_score": structure_score,
                "market_structure_reasons": structure_reasons,
                "derivatives_score": derivatives_score,
                "derivatives_reasons": derivatives_reasons,
                "raw_coin_risk": coin_risk,
                "macro_cycle_score_applied": macro_cycle_score,
                "macro_regime_cap_applied": True,
            },
            "interpretations": {
                "coin_score": interpret_score("coin", round(raw_score, 2)),
                "rsi": interpret_score("rsi", coin.get("rsi_14d")),
                "liquidity": interpret_state("liquidity", liquidity),
                "volatility": interpret_state("volatility", coin.get("volatility")),
            },
        }

    avg_coin_risk = sum(coin_risk_scores) / len(coin_risk_scores) if coin_risk_scores else 0
    market_structure_score = max(0, avg_coin_risk)
    exit_zone_score = round(max(0, macro_cycle_score + market_structure_score), 2)

    category_confirmations = 0

    if macro_cycle_score >= 20:
        category_confirmations += 1
    if market_structure_score >= 20:
        category_confirmations += 1
    if any(score_derivatives(coin)[0] >= 10 for coin in coins.values()):
        category_confirmations += 1
    if portfolio_risk_score >= 15:
        category_confirmations += 1

    multi_category_confirmed = category_confirmations >= 2
    global_action = determine_global_action(exit_zone_score, multi_category_confirmed)

    for symbol, signal in signals.items():
        coin = coins.get(symbol, {})

        adaptive = adaptive_sell_engine(
            symbol=symbol,
            coin=coin,
            exit_zone_score=exit_zone_score,
            liquidity=signal["liquidity"],
            blockers=signal["blockers"],
            confirmations=signal["confirmations"],
        )

        sell_pct = adaptive["adaptive_sell_pct"]
        sell_qty = adaptive["today_sell_qty"]

        if sell_pct > 0:
            if sell_pct >= 25:
                signal_name = "SELL_ADAPTIVE_25"
            elif sell_pct >= 10:
                signal_name = "SELL_ADAPTIVE_10"
            else:
                signal_name = "SELL_ADAPTIVE_LIGHT"
        else:
            signal_name = "HOLD_NO_SELL_TARGET" if symbol == "XRP" else "HOLD"

        signal["signal"] = signal_name
        signal["sell_pct"] = sell_pct
        signal["sell_qty"] = sell_qty
        signal["target_total_sell_qty"] = adaptive["target_total_qty"]
        signal["max_daily_qty"] = adaptive["max_daily_qty"]
        signal["execution_type"] = adaptive["execution_style"]
        signal["adaptive_execution"] = adaptive

    allocation_plan = build_allocation_plan(
        global_action,
        exit_zone_score,
        portfolio_intelligence,
    )

    reentry_engine = build_reentry_engine(snapshot, global_action)
    btc = snapshot.get("btc", {})

    engine = {
        "engine_version": ENGINE_VERSION,
        "engine_status": "active",
        "data_quality": data_quality,
        "global_action": global_action,
        "exit_zone_score": exit_zone_score,
        "score_components": {
            "macro_cycle_risk_score": round(macro_cycle_score, 2),
            "market_structure_score": round(market_structure_score, 2),
            "portfolio_risk_score": portfolio_risk_score,
            "category_confirmations": category_confirmations,
            "multi_category_confirmed": multi_category_confirmed,
            "macro_cycle_reasons": macro_cycle_reasons,
            "cycle_intelligence": btc.get("cycle_intelligence"),
            "macro_intelligence": btc.get("macro_intelligence"),
            "cbbi": btc.get("cbbi"),
            "pi_cycle": btc.get("pi_cycle"),
            "fear_greed": btc.get("fear_greed"),
            "btc_dominance": btc.get("dominance"),
        },
        "portfolio_intelligence": portfolio_intelligence,
        "guardrails": GUARDRAILS,
        "execution_engine": {
            "execution_type": "adaptive_limit_ladder_only",
            "moonbags_protected": True,
            "liquidity_respect_required": True,
            "atr_adjusted_sizing": True,
            "volatility_adjusted_sizing": True,
            "position_size_adjusted_sizing": True,
            "portfolio_aware_sizing": True,
            "score_intelligence_enabled": True,
            "macro_regime_cap_enabled": True,
            "data_quality_monitoring_enabled": True,
            "no_trade_if_expected_slippage_above_5pct": True,
        },
        "allocation_plan": allocation_plan,
        "reentry_engine": reentry_engine,
        "signals": signals,
        "missing_engine_data": missing,
    }

    engine["score_interpretation"] = build_score_interpretation(engine)

    return engine
