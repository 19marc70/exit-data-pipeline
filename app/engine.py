def classify_liquidity(volume):
    if volume is None: return "⚪ unknown"
    if volume < 5_000_000: return "🔴 severe"
    if volume < 25_000_000: return "🟠 thin"
    if volume < 100_000_000: return "🟡 moderate"
    return "🟢 strong"

def score_indicators(data):
    score, reasons = 0, []
    rsi = data.get("rsi_14d")
    atr = data.get("atr_14d")
    trend = data.get("trend")

    if rsi is not None:
        if rsi >= 80:
            score += 25; reasons.append("rsi_extreme")
        elif rsi >= 70:
            score += 15; reasons.append("rsi_overbought")
        elif rsi <= 35:
            score -= 10; reasons.append("rsi_weak")

    if trend == "🟢 uptrend":
        score += 5; reasons.append("uptrend")
    elif trend == "🔴 downtrend":
        score -= 10; reasons.append("downtrend")

    if atr is not None:
        if atr > 0:
            reasons.append("atr_available")

    return score, reasons

def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})
    signals = {}
    total_score = 0

    for symbol, data in coins.items():
        score, reasons = score_indicators(data)

        change = data.get("usd_24h_change")
        volume = data.get("usd_24h_vol")
        liquidity = classify_liquidity(volume)

        if change is not None:
            if change > 15:
                score += 20; reasons.append("strong_24h_expansion")
            elif change < -10:
                score -= 15; reasons.append("weak_momentum")

        if volume is not None:
            if volume > 100_000_000:
                score += 5; reasons.append("strong_volume")
            elif volume < 5_000_000:
                score -= 10; reasons.append("low_liquidity")

        if symbol == "XRP":
            signal, sell_pct, score = "HOLD_NO_SELL_TARGET", 0, 0
            reasons = ["xrp_is_not_sell_target"]
        elif score >= 45:
            signal, sell_pct = "WATCH_EXIT_ZONE", 0
        elif score >= 25:
            signal, sell_pct = "REDUCE_RISK", 10
        else:
            signal, sell_pct = "HOLD", 0

        total_score += score

        signals[symbol] = {
            "signal": signal,
            "score": score,
            "sell_pct": sell_pct,
            "liquidity": liquidity,
            "price": data.get("usd"),
            "change_24h": change,
            "volume_24h": volume,
            "rsi_14d": data.get("rsi_14d"),
            "atr_14d": data.get("atr_14d"),
            "trend": data.get("trend"),
            "reasons": reasons
        }

    return {
        "engine_version": "0.4-phase-3b",
        "engine_status": "active",
        "global_action": "NO_FULL_EXIT" if total_score < 50 else "EXIT_ZONE_WATCH",
        "exit_zone_score": total_score,
        "signals": signals,
        "guardrails": {
            "xrp_sell_allowed": False,
            "moonbags_sell_allowed": False,
            "full_exit_allowed_without_multi_category_confirmation": False
        },
        "missing_engine_data": snapshot.get("missing_data", [])
    }
