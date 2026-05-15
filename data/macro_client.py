"""
Macro data client — DXY, S&P 500 (yfinance), M2 (FRED), Fear & Greed (Alternative.me).
"""

import logging
from typing import Optional

import requests

import config
from data.cache import cache

logger = logging.getLogger(__name__)


class MacroClient:

    def __init__(self):
        self.session = requests.Session()

    # ── DXY ───────────────────────────────────────────────────────────────

    def get_dxy(self) -> dict:
        cache_key = "dxy_data"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            import yfinance as yf
            ticker = yf.Ticker(config.YAHOO_DXY)
            hist = ticker.history(period="5d")
            if hist.empty:
                return {"direction": "flat", "change_pct": 0}
            closes = hist["Close"].tolist()
            if len(closes) >= 2:
                change = ((closes[-1] - closes[0]) / closes[0]) * 100
                direction = "rising" if change > 0.3 else "falling" if change < -0.3 else "flat"
            else:
                change, direction = 0, "flat"
            result = {"direction": direction, "change_pct": round(change, 2), "last": round(closes[-1], 2)}
            cache.set(cache_key, result, ttl=600)
            return result
        except Exception as e:
            logger.error(f"DXY error: {e}")
            return {"direction": "flat", "change_pct": 0}

    # ── S&P 500 ──────────────────────────────────────────────────────────

    def get_sp500(self) -> dict:
        cache_key = "sp500_data"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            import yfinance as yf
            ticker = yf.Ticker(config.YAHOO_SP500)
            hist = ticker.history(period="5d")
            if hist.empty:
                return {"direction": "flat", "change_pct": 0}
            closes = hist["Close"].tolist()
            if len(closes) >= 2:
                change = ((closes[-1] - closes[0]) / closes[0]) * 100
                direction = "rising" if change > 0.3 else "falling" if change < -0.3 else "flat"
            else:
                change, direction = 0, "flat"
            result = {"direction": direction, "change_pct": round(change, 2), "last": round(closes[-1], 2)}
            cache.set(cache_key, result, ttl=600)
            return result
        except Exception as e:
            logger.error(f"S&P 500 error: {e}")
            return {"direction": "flat", "change_pct": 0}

    # ── M2 Money Supply (FRED) ───────────────────────────────────────────

    def get_m2_supply(self) -> dict:
        cache_key = "m2_supply"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        if config.FRED_API_KEY == "YOUR_FRED_API_KEY":
            return {"available": False, "change_pct": 0}

        try:
            params = {
                "series_id": config.FRED_M2_SERIES,
                "api_key": config.FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 3,
            }
            resp = self.session.get(config.FRED_BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            observations = resp.json().get("observations", [])

            if len(observations) >= 2:
                current = float(observations[0]["value"])
                previous = float(observations[1]["value"])
                change_pct = ((current - previous) / previous) * 100
                result = {"available": True, "change_pct": round(change_pct, 2),
                          "current": current, "previous": previous}
            else:
                result = {"available": False, "change_pct": 0}

            cache.set(cache_key, result, ttl=3600)
            return result

        except Exception as e:
            logger.error(f"M2 supply error: {e}")
            return {"available": False, "change_pct": 0}

    # ── Fear & Greed Index ───────────────────────────────────────────────

    def get_fear_greed(self) -> Optional[int]:
        cache_key = "fear_greed"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            resp = self.session.get(config.FEAR_GREED_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            value = int(data["data"][0]["value"])
            cache.set(cache_key, value, ttl=600)
            return value
        except Exception as e:
            logger.error(f"Fear & Greed error: {e}")
            return None
