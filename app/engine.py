from datetime import datetime, timezone

def calculate_exit_signal(coin_data):
    score = 0

    change = coin_data.get("usd_24h_change", 0)

    if change > 15:
        score += 2
    elif change > 8:
        score += 1

    if change < -10:
        score -= 1

    if score >= 2:
        action = "PARTIAL_EXIT"
    elif score == 1:
        action = "REDUCE_RISK"
    else:
        action = "HOLD"

    return {
        "signal": action,
        "score": score,
        "change_24h": change
    }


def build_exit_engine(snapshot):
    coins = snapshot.get("coins", {})

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine_status": "active",
        "signals": {}
    }

    for symbol, data in coins.items():
        result["signals"][symbol] = calculate_exit_signal(data)

    return result
