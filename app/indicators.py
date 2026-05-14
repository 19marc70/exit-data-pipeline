def calculate_rsi(closes, period=14):
    if not closes or len(closes) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_atr_proxy(closes, period=14):
    if not closes or len(closes) <= period:
        return None

    ranges = []

    for i in range(1, len(closes)):
        ranges.append(abs(closes[i] - closes[i - 1]))

    return round(sum(ranges[-period:]) / period, 6)


def classify_trend(closes):
    if not closes or len(closes) < 20:
        return "⚪ unknown"

    last = closes[-1]
    ma7 = sum(closes[-7:]) / 7
    ma20 = sum(closes[-20:]) / 20

    if last > ma7 > ma20:
        return "🟢 uptrend"
    if last < ma7 < ma20:
        return "🔴 downtrend"
    return "🟡 mixed"
