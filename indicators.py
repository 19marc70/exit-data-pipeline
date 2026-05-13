from __future__ import annotations
import math
from typing import Any

def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period

def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def atr(ohlc: list[dict[str, float]], period: int = 14) -> float | None:
    if len(ohlc) < period + 1:
        return None
    true_ranges: list[float] = []
    rows = ohlc[-(period + 1):]
    for i in range(1, len(rows)):
        high = rows[i]["high"]
        low = rows[i]["low"]
        prev_close = rows[i - 1]["close"]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return round(sum(true_ranges) / period, 8)

def pi_cycle_status(btc_daily_closes: list[float]) -> dict[str, Any]:
    ma_111 = sma(btc_daily_closes, 111)
    ma_350 = sma(btc_daily_closes, 350)
    if ma_111 is None or ma_350 is None:
        return {
            "status": "insufficient_data",
            "ma_111": ma_111,
            "ma_350x2": None if ma_350 is None else round(ma_350 * 2, 2),
            "distance_pct": None
        }
    ma_350x2 = ma_350 * 2
    distance_pct = ((ma_350x2 - ma_111) / ma_350x2) * 100 if ma_350x2 else None
    if ma_111 >= ma_350x2:
        status = "crossed_top_signal"
    elif distance_pct is not None and distance_pct <= 5:
        status = "near_cross"
    else:
        status = "no_cross"
    return {
        "status": status,
        "ma_111": round(ma_111, 2),
        "ma_350x2": round(ma_350x2, 2),
        "distance_pct": None if distance_pct is None else round(distance_pct, 2)
    }
