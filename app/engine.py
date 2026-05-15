PORTFOLIO = {
    "ONDO": {"sellable": 19139, "moonbag": 1925},
    "AERO": {"sellable": 9250, "moonbag": 750},
    "CFG": {"sellable": 9639, "moonbag": 744},
    "XRP": {"sellable": 0, "moonbag": 11093}
}


def classify_liquidity(volume):
    if volume is None:
        return "⚪ unknown"
    if volume < 5_000_000:
        return "🔴 severe"
    if volume < 25_000_000:
        return "🟠 thin"
    if volume < 100_000_000:
        return "🟡 moderate"
    return "🟢 strong"


def execution_limit(liquidity):
    if liquidity == "🔴 severe":
        return 0.05
    if liquidity == "🟠 thin":
        return 0.07
    if liquidity == "🟡 moderate":
        return 0.10
    if liquidity == "🟢 strong":
        return 0.15
    return 0.03


def trigger_matrix(symbol, data, macro_score):
    confirmations = []
    blockers = []
    score = 0

    change = data.get("usd_24h_change")
    volume = data.get("usd_24h_vol")
    rsi = data.get("rsi_14d")
    trend = data.get("trend")
    volatility = data.get("volatility")
    liquidity = classify_liquidity(volume)

    if symbol == "XRP":
        return {
            "signal": "HOLD_NO_SELL_TARGET",
            "score": 0,
            "sell_pct": 0,
            "confirmations": ["xrp_is_not_sell_target"],
            "blockers": ["xrp_sell_disabled"],
            "liquidity": liquidity
        }

    if change is not None:
        if change >= 15:
            score += 20
            confirmations.append("momentum_expansion")
        elif change >= 8:
            score += 10
            confirmations.append("positive_momentum")
        elif change <= -10:
            score -= 15
            blockers.append("weak_momentum")

    if rsi is not None:
        if rsi >= 80:
            score += 25
            confirmations.append("rsi_extreme")
        elif rsi >= 70:
            score += 15
            confirmations.append("rsi_overbought")
        elif rsi <= 35:
            score -= 10
            blockers.append("rsi_weak")
    else:
        blockers.append("rsi_missing")

    if trend in ["🟢 strong_uptrend", "🟢 uptrend", "🟢 strengthening"]:
        score += 10
        confirmations.append("trend_positive")
    elif trend in ["🟠 weakening", "🔴 breakdown", "🔴 downtrend"]:
        score -= 10
        blockers.append("trend_weakening")

    if volatility in ["🔴 high", "🔴 high_volatility", "🟠 elevated", "🟠 elevated_volatility"]:
        score += 5
        confirmations.append("volatility_expansion")
    elif volatility is None or "unavailable" in str(volatility):
        blockers.append("volatility_missing")

    if liquidity == "🟢 strong":
        score += 5
        confirmations.append("execution_liquidity_strong")
    elif liquidity == "🔴 severe":
        score -= 15
        blockers.append("execution_liquidity_severe")
    elif liquidity == "🟠 thin":
        score -= 5
        blockers.append("execution_liquidity_thin")

    score += macro_score

    if len(confirmations) < 2:
        signal = "HOLD"
        sell_pct = 0
        blockers.append("insufficient_multi_factor_confirmation")
    elif score >= 60:
        signal = "SELL_50"
        sell_pct = 50
    elif score >= 40:
        signal = "SELL_25"
        sell_pct = 25
    elif score >= 25:
        signal = "SELL_10"
        sell_pct = 10
    elif score <= -25:
        signal = "DEFENSIVE_HOLD"
        sell_pct = 0
    else:
        signal = "HOLD"
        sell_pct = 0

    return {
        "signal": signal,
        "score": score,
        "sell_pct": sell_pct,
        "confirmations": confirmations,
        "blockers": blockers,
        "liquidity": liquidity
    }


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})
    btc = snapshot.get("btc", {})

    btc_dominance = btc.get("dominance")
    fear_greed = btc.get("fear_greed", {})
    altseason_index = btc.get("altseason_index")
    stablecoin_regime = btc.get("stablecoin_regime")

    macro_score = 0
    macro_reasons = []

    if btc_dominance is not None:
        if btc_dominance >= 58:
            macro_score -= 10
            macro_reasons.append("btc_dominance_alt_headwind")
        elif btc_dominance <= 52:
            macro_score += 10
            macro_reasons.append("btc_dominance_alt_supportive")

    fg_value = fear_greed.get("value") if isinstance(fear_greed, dict) else None

    if fg_value is not None:
        if fg_value >= 80:
            macro_score += 15
            macro_reasons.append("extreme_greed")
        elif fg_value <= 25:
            macro_score -= 10
            macro_reasons.append("fear_no_euphoria")

    if altseason_index is not None:
        if altseason_index >= 45:
            macro_score += 10
            macro_reasons.append("altseason_supportive")
        elif altseason_index <= 38:
            macro_score -= 10
            macro_reasons.append("btc_dominance_heavy")

    if stablecoin_regime == "🔴 euphoric_risk":
        macro_score += 10
        macro_reasons.append("euphoria_expansion")
    elif stablecoin_regime == "🟢 defensive_rotation":
        macro_score -= 10
        macro_reasons.append("defensive_stablecoin_rotation")

    signals = {}
    total_score = macro_score

    for symbol, data in coins.items():
        trigger = trigger_matrix(symbol, data, macro_score)
        sellable = PORTFOLIO.get(symbol, {}).get("sellable", 0)

        liquidity = trigger["liquidity"]
        daily_limit = execution_limit(liquidity)

        raw_sell_qty = sellable * (trigger["sell_pct"] / 100)
        max_daily_qty = sellable * daily_limit
        sell_qty = min(raw_sell_qty, max_daily_qty)

        if symbol == "XRP":
            sell_qty = 0
            max_daily_qty = 0

        total_score += trigger["score"]

        signals[symbol] = {
            **trigger,
            "price": data.get("usd"),
            "change_24h": data.get("usd_24h_change"),
            "volume_24h": data.get("usd_24h_vol"),
            "rsi_14d": data.get("rsi_14d"),
            "atr_14d": data.get("atr_14d"),
            "trend": data.get("trend"),
            "volatility": data.get("volatility"),
            "sell_qty": round(sell_qty, 4),
            "max_daily_qty": round(max_daily_qty, 4),
            "execution_type": "limit_or_ladder_only"
        }

    if total_score >= 90:
        global_action = "RISK_OFF"
    elif total_score >= 50:
        global_action = "PARTIAL_EXIT_ALLOWED"
    else:
        global_action = "NO_FULL_EXIT"

    return {
        "engine_version": "1.0-phase-10-compatible",
        "engine_status": "active",
        "global_action": global_action,
        "exit_zone_score": total_score,
        "score_components": {
            "macro_score": macro_score,
            "macro_reasons": macro_reasons,
            "altseason_index": altseason_index,
            "stablecoin_regime": stablecoin_regime
        },
        "guardrails": {
            "xrp_sell_allowed": False,
            "moonbags_sell_allowed": False,
            "single_indicator_exit_allowed": False,
            "full_exit_allowed_without_multi_category_confirmation": False,
            "slippage_above_5pct_allowed": False
        },
        "execution_engine": {
            "execution_type": "limit_or_ladder_only",
            "moonbags_protected": True,
            "liquidity_respect_required": True
        },
        "signals": signals,
        "missing_engine_data": snapshot.get("missing_data", [])
    }
