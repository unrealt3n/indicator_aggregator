"""
Binance API client — handles all crypto data: klines, funding, OI, L/S ratio.
All endpoints are public and require no authentication.
"""

import logging
import requests
from typing import List, Optional

import config
from domain.models import Candle
from data.cache import cache

logger = logging.getLogger(__name__)


class BinanceClient:

    def __init__(self):
        self.base = config.BINANCE_BASE_URL
        self.futures = config.BINANCE_FUTURES_URL
        self.symbol = config.SYMBOL
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # ── Klines ────────────────────────────────────────────────────────────

    def get_klines(self, interval: str = "1d", limit: int = 250) -> List[Candle]:
        cache_key = f"klines_{self.symbol}_{interval}_{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base}/api/v3/klines"
            params = {"symbol": self.symbol, "interval": interval, "limit": limit}
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            candles = []
            for k in data:
                candles.append(Candle(
                    timestamp=int(k[0]),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                    taker_buy_volume=float(k[9]),
                ))
            cache.set(cache_key, candles)
            return candles

        except Exception as e:
            logger.error(f"Binance klines error ({interval}): {e}")
            return []

    # ── Funding Rate ─────────────────────────────────────────────────────

    def get_funding_rate(self) -> Optional[float]:
        cache_key = "funding_rate"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.futures}/fapi/v1/fundingRate"
            params = {"symbol": self.symbol, "limit": 1}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data:
                rate = float(data[-1]["fundingRate"])
                cache.set(cache_key, rate)
                return rate
        except Exception as e:
            logger.error(f"Funding rate error: {e}")
        return None

    # ── Open Interest ────────────────────────────────────────────────────

    def get_open_interest(self) -> dict:
        cache_key = "open_interest"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # Current OI
            url = f"{self.futures}/fapi/v1/openInterest"
            params = {"symbol": self.symbol}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            current_oi = float(resp.json()["openInterest"])

            # Historical OI (last 2 data points for comparison)
            hist_url = f"{self.futures}/futures/data/openInterestHist"
            hist_params = {"symbol": self.symbol, "period": "1h", "limit": 25}
            hist_resp = self.session.get(hist_url, params=hist_params, timeout=10)
            hist_resp.raise_for_status()
            hist_data = hist_resp.json()

            if len(hist_data) >= 2:
                old_oi = float(hist_data[0]["sumOpenInterest"])
                change_pct = ((current_oi - old_oi) / old_oi) * 100 if old_oi else 0
            else:
                change_pct = 0

            result = {
                "current": current_oi,
                "change_pct": round(change_pct, 2),
                "available": True,
            }
            cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Open interest error: {e}")
            return {"available": False}

    # ── Long/Short Ratio ─────────────────────────────────────────────────

    def get_long_short_ratio(self) -> Optional[float]:
        cache_key = "ls_ratio"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.futures}/futures/data/globalLongShortAccountRatio"
            params = {"symbol": self.symbol, "period": "1h", "limit": 1}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data:
                ratio = float(data[-1]["longShortRatio"])
                cache.set(cache_key, ratio)
                return ratio
        except Exception as e:
            logger.error(f"Long/short ratio error: {e}")
        return None

    # ── Current Price (quick) ────────────────────────────────────────────

    def get_ticker(self) -> dict:
        cache_key = "ticker_24h"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base}/api/v3/ticker/24hr"
            params = {"symbol": self.symbol}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            result = {
                "price": float(data["lastPrice"]),
                "change": float(data["priceChange"]),
                "change_pct": float(data["priceChangePercent"]),
            }
            cache.set(cache_key, result, ttl=60)
            return result
        except Exception as e:
            logger.error(f"Ticker error: {e}")
            return {"price": 0, "change": 0, "change_pct": 0}
