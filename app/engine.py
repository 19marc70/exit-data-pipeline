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


def score_coin(symbol, data):
    score = 0
    reasons = []

    change = data.get("usd_24h_change")
    volume = data.get("usd_24h_vol")
    rsi = data.get("rsi_14d")
    trend = data.get("trend")

    liquidity = classify_liquidity(volume)

    if change is not None:
        if change >= 15:
            score += 20
            reasons.append("strong_24h_expansion")
        elif change >= 8:
            score += 10
            reasons.append("moderate_24h_expansion")
        elif change <= -10:
            score -= 15
            reasons.append("weak_momentum")

    if rsi is not None:
        if rsi >= 80:
            score += 25
            reasons.append("rsi_extreme")
        elif rsi >= 70:
            score += 15
            reasons.append("rsi_overbought")
        elif rsi <= 35:
            score -= 10
            reasons.append("rsi_weak")

    if trend == "🟢 uptrend":
        score += 5
        reasons.append("uptrend")
    elif trend == "🔴 downtrend":
        score -= 10
        reasons.append("downtrend")

    if liquidity == "🟢 strong":
        score += 5
        reasons.append("strong_volume")
    elif liquidity == "🔴 severe":
        score -= 10
        reasons.append("low_liquidity")

    return score, reasons, liquidity


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})
    btc = snapshot.get("btc", {})

    btc_dominance = btc.get("dominance")
    fear_greed = btc.get("fear_greed", {})

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

    signals = {}
    coin_total = 0

    for symbol, data in coins.items():
        score, reasons, liquidity = score_coin(symbol, data)
        coin_total += score

        sellable = PORTFOLIO.get(symbol, {}).get("sellable", 0)

        if symbol == "XRP":
            signal = "HOLD_NO_SELL_TARGET"
            sell_pct = 0
            sell_qty = 0
            max_daily_qty = 0
            reasons = ["xrp_is_not_sell_target"]

        else:
            if score >= 45:
                signal = "SCALE_OUT_25"
                sell_pct = 25
            elif score >= 25:
                signal = "REDUCE_RISK_10"
                sell_pct = 10
            elif score <= -20:
                signal = "DEFENSIVE_HOLD"
                sell_pct = 0
            else:
                signal = "HOLD"
                sell_pct = 0

            raw_sell_qty = sellable * (sell_pct / 100)
            daily_limit = execution_limit(liquidity)
            max_daily_qty = sellable * daily_limit
            sell_qty = min(raw_sell_qty, max_daily_qty)

        signals[symbol] = {
            "signal": signal,
            "score": score,
            "sell_pct": sell_pct,
            "sell_qty": round(sell_qty, 4),
            "max_daily_qty": round(max_daily_qty, 4),
            "liquidity": liquidity,
            "price": data.get("usd"),
            "change_24h": data.get("usd_24h_change"),
            "volume_24h": data.get("usd_24h_vol"),
            "rsi_14d": data.get("rsi_14d"),
            "atr_14d": data.get("atr_14d"),
            "trend": data.get("trend"),
            "reasons": reasons
        }

    exit_zone_score = coin_total + macro_score

    if exit_zone_score >= 70:
        global_action = "RISK_OFF"
    elif exit_zone_score >= 40:
        global_action = "PARTIAL_EXIT_ALLOWED"
    else:
        global_action = "NO_FULL_EXIT"

    return {
        "engine_version": "0.5-phase-4",
        "engine_status": "active",
        "global_action": global_action,
        "exit_zone_score": exit_zone_score,
        "score_components": {
            "coin_score": coin_total,
            "macro_score": macro_score,
            "macro_reasons": macro_reasons
        },
        "guardrails": {
            "xrp_sell_allowed": False,
            "moonbags_sell_allowed": False,
            "full_exit_allowed_without_multi_category_confirmation": False
        },
        "execution_engine": {
            "slippage_guardrail": "no_trade_if_expected_slippage_above_5pct",
            "execution_type": "limit_or_ladder_only",
            "moonbags_protected": True
        },
        "signals": signals,
        "missing_engine_data": snapshot.get("missing_data", [])
    }
