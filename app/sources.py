from datetime import datetime, timezone

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def build_exit_snapshot():
    return {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "btc": {
            "dominance": None,
            "cbbi": None,
            "pi_cycle": {
                "status": "unknown",
                "distance_pct": None
            }
        },
        "coins": {
            "XRP": {},
            "ONDO": {},
            "AERO": {},
            "CFG": {}
        },
        "missing_data": [
            "live_market_integrations_not_enabled_yet"
        ]
    }
