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


def calculate_exit_signal(symbol, coin_data):
    score = 0
    reasons = []

    change = coin_data.get("usd_24h_change")
    volume = coin_data.get("usd_24h_vol")
    price = coin_data.get("usd")
    rsi = coin_data.get("rsi_14d")
    atr = coin_data.get("atr_14d")

    liquidity = classify_liquidity(volume)

    if change is not None:
        if change > 15:
            score += 20
            reasons.append("strong_24h_expansion")
        elif change > 8:
            score += 10
            reasons.append("moderate_24h_expansion")
        elif change < -10:
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

    if volume is not None:
        if volume > 100_000_000:
            score += 5
            reasons.append("strong_volume")
        elif volume < 5_000_000:
            score -= 10
            reasons.append("low_liquidity")

    if symbol == "XRP":
        return {
            "signal": "HOLD_NO_SELL_TARGET",
            "score": 0,
            "sell_pct": 0,
            "liquidity": liquidity,
            "price": price,
            "change_24h": change,
            "volume_24h": volume,
            "rsi_14d": rsi,
            "atr_14d": atr,
            "reasons": ["xrp_is_not_sell_target"]
        }

    if score >= 45:
        signal = "PREPARE_PARTIAL_EXIT"
        sell_pct = 10
    elif score >= 25:
        signal = "WATCH_EXIT_ZONE"
        sell_pct = 0
    else:
        signal = "HOLD"
        sell_pct = 0

    return {
        "signal": signal,
        "score": score,
        "sell_pct": sell_pct,
        "liquidity": liquidity,
        "price": price,
        "change_24h": change,
        "volume_24h": volume,
        "rsi_14d": rsi,
        "atr_14d": atr,
        "reasons": reasons
    }


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})

    signals = {
        symbol: calculate_exit_signal(symbol, data)
        for symbol, data in coins.items()
    }

    exit_zone_score = sum(
        item["score"] for item in signals.values()
        if isinstance(item.get("score"), (int, float))
    )

    if exit_zone_score >= 90:
        global_action = "EXIT_ZONE_ACTIVE"
    elif exit_zone_score >= 50:
        global_action = "EXIT_ZONE_WATCH"
    else:
        global_action = "NO_FULL_EXIT"

    return {
        "engine_version": "0.3",
        "engine_status": "active",
        "global_action": global_action,
        "exit_zone_score": exit_zone_score,
        "guardrails": {
            "xrp_sell_allowed": False,
            "moonbags_sell_allowed": False,
            "full_exit_allowed_without_multi_category_confirmation": False
        },
        "signals": signals,
        "missing_engine_data": [
            "funding",
            "open_interest",
            "btc_dominance",
            "cbbi",
            "pi_cycle"
        ]
    }
