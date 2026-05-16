ENGINE_VERSION = "1.9-phase-19-exit-zone-intelligence-v2"

PORTFOLIO = {
    "XRP": {"sellable": 0.0, "moonbag": 11093.0},
    "ONDO": {"sellable": 21369.0243205, "moonbag": 1925.0},
    "AERO": {"sellable": 10000.553, "moonbag": 750.0},
    "CFG": {"sellable": 10383.736, "moonbag": 744.0},
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


def classify_liquidity(symbol, coin):
    volume = safe_float(coin.get("usd_24h_vol"))
    market_cap = safe_float(coin.get("usd_market_cap"))

    if symbol == "CFG":
        return "🔴 severe"

    if volume <= 500_000:
        return "🔴 severe"

    if volume <= 5_000_000:
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


def score_market_structure(coin):
    score = 0
    reasons = []

    trend = coin.get("trend")
    volatility = coin.get("volatility")
    rsi = safe_float(coin.get("rsi_14d"))

    if text_contains(trend, "weakening"):
        score += 12
        reasons.append("trend_weakening")
    elif text_contains(trend, "strengthening"):
        score -= 8
        reasons.append("trend_strengthening")
    elif text_contains(trend, "sideways"):
        score += 0
        reasons.append("trend_sideways")

    if text_contains(volatility, "high"):
        score += 15
        reasons.append("volatility_high")
    elif text_contains(volatility, "elevated"):
        score += 8
        reasons.append("volatility_elevated")
    elif text_contains(volatility, "low"):
        score -= 5
        reasons.append("volatility_low")

    if rsi >= 78:
        score += 18
        reasons.append("rsi_overheated")
    elif rsi >= 68:
        score += 8
        reasons.append("rsi_elevated")
    elif rsi <= 30:
        score -= 10
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
    elif text_contains(leverage_risk, "neutral"):
        score += 0

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


def determine_sell_pct(exit_zone_score, symbol, liquidity, blockers, confirmations):
    if symbol not in SELL_TARGETS:
        return 0

    if "insufficient_multi_factor_confirmation" in blockers:
        return 0

    if "execution_liquidity_severe" in blockers:
        return 0

    if len(confirmations) < 2:
        return 0

    if exit_zone_score >= 80:
        base = 50
    elif exit_zone_score >= 60:
        base = 25
    elif exit_zone_score >= 40:
        base = 10
    else:
        base = 0

    if text_contains(liquidity, "moderate"):
        base = min(base, 10)

    if text_contains(liquidity, "severe"):
        base = 0

    return base


def build_allocation_plan(global_action, exit_zone_score):
    if global_action in ["HEAVY_DISTRIBUTION", "PARTIAL_EXIT_ALLOWED"]:
        stablecoin_target_pct = min(70, max(25, int(exit_zone_score)))
        status = "RAISE_STABLECOINS"
    elif global_action == "LIGHT_TRIM_ALLOWED":
        stablecoin_target_pct = 15
        status = "LIGHT_STABLECOIN_BUILD"
    elif global_action == "ACCUMULATION_SUPPORT":
        stablecoin_target_pct = 0
        status = "NO_NEW_STABLECOIN_ACTION"
    else:
        stablecoin_target_pct = 0
        status = "NO_NEW_STABLECOIN_ACTION"

    return {
        "stablecoin_target_pct": stablecoin_target_pct,
        "target_pct_of_realized_sales": stablecoin_target_pct,
        "status": status,
        "rule": "only_from_confirmed_sell_signals",
        "xrp_allocation": {
            "action": "HOLD_10_YEAR_CORE",
            "sell_allowed": False
        },
        "ondo_allocation": {
            "action": "MAINTAIN_CORE_RAW_POSITION"
        },
        "dca_out_ladder": [
            {"zone": "LIGHT_TRIM_ALLOWED", "sell_pct": 10},
            {"zone": "PARTIAL_EXIT_ALLOWED", "sell_pct": 25},
            {"zone": "HEAVY_DISTRIBUTION", "sell_pct": 50}
        ]
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
            "volatility": volatility
        }

    return result


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})
    missing = list(snapshot.get("missing_data", []))

    macro_cycle_score, macro_cycle_reasons = score_cycle_and_macro(snapshot)

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

        if len(confirmations) < 2:
            blockers.append("insufficient_multi_factor_confirmation")

        if text_contains(liquidity, "severe"):
            blockers.append("no_trade_if_expected_slippage_above_5pct")

        raw_score = coin_risk - macro_cycle_score

        max_daily_pct = max_daily_pct_from_liquidity(liquidity)
        sellable = PORTFOLIO.get(symbol, {}).get("sellable", 0.0)
        max_daily_qty = round(sellable * max_daily_pct / 100, 6)

        signals[symbol] = {
            "signal": "HOLD_NO_SELL_TARGET" if symbol == "XRP" else "HOLD",
            "score": round(raw_score, 2),
            "sell_pct": 0,
            "confirmations": confirmations,
            "blockers": blockers,
            "liquidity": liquidity,
            "price": coin.get("usd"),
            "change_24h": coin.get("usd_24h_change"),
            "volume_24h": coin.get("usd_24h_vol"),
            "rsi_14d": coin.get("rsi_14d"),
            "atr_14d": coin.get("atr_14d"),
            "trend": coin.get("trend"),
            "volatility": coin.get("volatility"),
            "derivatives": coin.get("derivatives", {}),
            "sell_qty": 0.0,
            "max_daily_qty": 0.0 if symbol == "XRP" else max_daily_qty,
            "execution_type": "limit_or_ladder_only"
        }

    avg_coin_risk = sum(coin_risk_scores) / len(coin_risk_scores) if coin_risk_scores else 0

    market_structure_score = max(0, avg_coin_risk)
    exit_zone_score = round(max(0, macro_cycle_score + market_structure_score), 2)

    category_confirmations = 0
    if macro_cycle_score >= 20:
        category_confirmations += 1
    if market_structure_score >= 20:
        category_confirmations += 1
    if any(
        score_derivatives(coin)[0] >= 10
        for coin in coins.values()
    ):
        category_confirmations += 1

    multi_category_confirmed = category_confirmations >= 2

    global_action = determine_global_action(exit_zone_score, multi_category_confirmed)

    for symbol, signal in signals.items():
        sell_pct = determine_sell_pct(
            exit_zone_score,
            symbol,
            signal["liquidity"],
            signal["blockers"],
            signal["confirmations"]
        )

        sellable = PORTFOLIO.get(symbol, {}).get("sellable", 0.0)
        sell_qty = round(sellable * sell_pct / 100, 6)

        if sell_pct > 0:
            if sell_pct >= 50:
                signal_name = "SELL_50"
            elif sell_pct >= 25:
                signal_name = "SELL_25"
            else:
                signal_name = "SELL_10"
        else:
            signal_name = "HOLD_NO_SELL_TARGET" if symbol == "XRP" else "HOLD"

        signal["signal"] = signal_name
        signal["sell_pct"] = sell_pct
        signal["sell_qty"] = sell_qty

    allocation_plan = build_allocation_plan(global_action, exit_zone_score)
    reentry_engine = build_reentry_engine(snapshot, global_action)

    btc = snapshot.get("btc", {})

    return {
        "engine_version": ENGINE_VERSION,
        "engine_status": "active",
        "global_action": global_action,
        "exit_zone_score": exit_zone_score,
        "score_components": {
            "macro_cycle_risk_score": round(macro_cycle_score, 2),
            "market_structure_score": round(market_structure_score, 2),
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
        "guardrails": GUARDRAILS,
        "execution_engine": {
            "execution_type": "limit_or_ladder_only",
            "moonbags_protected": True,
            "liquidity_respect_required": True,
            "no_trade_if_expected_slippage_above_5pct": True
        },
        "allocation_plan": allocation_plan,
        "reentry_engine": reentry_engine,
        "signals": signals,
        "missing_engine_data": missing
    }
