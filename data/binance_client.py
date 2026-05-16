"""
Binance API client with automatic Bybit fallback.

Primary: Binance (best data, but geo-blocked in some regions).
Fallback: Bybit public API (works globally, same data structure).

The client auto-detects geo-blocks (HTTP 451/403/418) and switches
to Bybit for subsequent requests without retrying Binance each time.
"""

import logging
import requests
from typing import List, Optional

import config
from domain.models import Candle
from data.cache import cache

logger = logging.getLogger(__name__)

# HTTP status codes indicating geo-block or IP ban
_BLOCK_CODES = {451, 403, 418}


def _is_blocked(e: Exception) -> bool:
    """Check if an exception indicates geo-blocking or access denial."""
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        return e.response.status_code in _BLOCK_CODES
    return any(str(code) in str(e) for code in _BLOCK_CODES)


# Bybit interval mapping from Binance notation
_BYBIT_INTERVALS = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W", "1M": "M",
}


class BinanceClient:

    def __init__(self):
        self.base = config.BINANCE_BASE_URL
        self.futures = config.BINANCE_FUTURES_URL
        self.bybit = config.BYBIT_BASE_URL
        self.symbol = config.SYMBOL
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        # Sticky flags — once blocked, skip Binance for the rest of
        # the process lifetime (resets on redeploy / restart).
        self._spot_blocked = False
        self._futures_blocked = False

    # ════════════════════════════════════════════════════════════════════
    # Klines
    # ════════════════════════════════════════════════════════════════════

    def get_klines(self, interval: str = "1d", limit: int = 250) -> List[Candle]:
        cache_key = f"klines_{self.symbol}_{interval}_{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._spot_blocked:
            try:
                result = self._binance_klines(interval, limit)
                if result:
                    cache.set(cache_key, result)
                    return result
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance spot blocked (klines) — switching to Bybit")
                    self._spot_blocked = True
                else:
                    logger.error(f"Binance klines error ({interval}): {e}")

        # --- Fallback: Bybit ---
        try:
            result = self._bybit_klines(interval, limit)
            if result:
                cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Bybit klines fallback error ({interval}): {e}")

        return []

    def _binance_klines(self, interval, limit):
        url = f"{self.base}/api/v3/klines"
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [
            Candle(
                timestamp=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                taker_buy_volume=float(k[9]),
            )
            for k in data
        ]

    def _bybit_klines(self, interval, limit):
        bybit_interval = _BYBIT_INTERVALS.get(interval, interval)
        url = f"{self.bybit}/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": self.symbol,
            "interval": bybit_interval,
            "limit": min(limit, 1000),
        }
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")

        klines = data["result"]["list"]
        klines.reverse()  # Bybit returns newest-first; we need chronological

        return [
            Candle(
                timestamp=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                # Bybit doesn't provide taker-buy volume separately;
                # estimate as 50% of total volume (neutral assumption).
                taker_buy_volume=float(k[5]) * 0.5,
            )
            for k in klines
        ]

    # ════════════════════════════════════════════════════════════════════
    # Funding Rate
    # ════════════════════════════════════════════════════════════════════

    def get_funding_rate(self) -> Optional[float]:
        cache_key = "funding_rate"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._futures_blocked:
            try:
                rate = self._binance_funding_rate()
                if rate is not None:
                    cache.set(cache_key, rate)
                    return rate
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance futures blocked (funding) — switching to Bybit")
                    self._futures_blocked = True
                else:
                    logger.error(f"Funding rate error: {e}")

        # --- Fallback: Bybit ---
        try:
            rate = self._bybit_funding_rate()
            if rate is not None:
                cache.set(cache_key, rate)
                return rate
        except Exception as e:
            logger.error(f"Bybit funding rate fallback error: {e}")

        return None

    def _binance_funding_rate(self):
        url = f"{self.futures}/fapi/v1/fundingRate"
        params = {"symbol": self.symbol, "limit": 1}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[-1]["fundingRate"])
        return None

    def _bybit_funding_rate(self):
        url = f"{self.bybit}/v5/market/tickers"
        params = {"category": "linear", "symbol": self.symbol}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")
        tickers = data["result"]["list"]
        if tickers:
            rate_str = tickers[0].get("fundingRate", "0")
            return float(rate_str)
        return None

    # ════════════════════════════════════════════════════════════════════
    # Open Interest
    # ════════════════════════════════════════════════════════════════════

    def get_open_interest(self) -> dict:
        cache_key = "open_interest"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._futures_blocked:
            try:
                result = self._binance_open_interest()
                if result.get("available"):
                    cache.set(cache_key, result)
                    return result
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance futures blocked (OI) — switching to Bybit")
                    self._futures_blocked = True
                else:
                    logger.error(f"Open interest error: {e}")

        # --- Fallback: Bybit ---
        try:
            result = self._bybit_open_interest()
            if result.get("available"):
                cache.set(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Bybit OI fallback error: {e}")

        return {"available": False}

    def _binance_open_interest(self):
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

        return {
            "current": current_oi,
            "change_pct": round(change_pct, 2),
            "available": True,
        }

    def _bybit_open_interest(self):
        url = f"{self.bybit}/v5/market/open-interest"
        params = {
            "category": "linear",
            "symbol": self.symbol,
            "intervalTime": "1h",
            "limit": 25,
        }
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")

        entries = data["result"]["list"]
        if not entries:
            return {"available": False}

        # Bybit returns newest-first
        current_oi = float(entries[0]["openInterest"])
        if len(entries) >= 2:
            old_oi = float(entries[-1]["openInterest"])
            change_pct = ((current_oi - old_oi) / old_oi) * 100 if old_oi else 0
        else:
            change_pct = 0

        return {
            "current": current_oi,
            "change_pct": round(change_pct, 2),
            "available": True,
        }

    # ════════════════════════════════════════════════════════════════════
    # Long/Short Ratio
    # ════════════════════════════════════════════════════════════════════

    def get_long_short_ratio(self) -> Optional[float]:
        cache_key = "ls_ratio"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._futures_blocked:
            try:
                ratio = self._binance_long_short_ratio()
                if ratio is not None:
                    cache.set(cache_key, ratio)
                    return ratio
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance futures blocked (L/S) — switching to Bybit")
                    self._futures_blocked = True
                else:
                    logger.error(f"Long/short ratio error: {e}")

        # --- Fallback: Bybit ---
        try:
            ratio = self._bybit_long_short_ratio()
            if ratio is not None:
                cache.set(cache_key, ratio)
                return ratio
        except Exception as e:
            logger.error(f"Bybit L/S ratio fallback error: {e}")

        return None

    def _binance_long_short_ratio(self):
        url = f"{self.futures}/futures/data/globalLongShortAccountRatio"
        params = {"symbol": self.symbol, "period": "1h", "limit": 1}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[-1]["longShortRatio"])
        return None

    def _bybit_long_short_ratio(self):
        url = f"{self.bybit}/v5/market/account-ratio"
        params = {"category": "linear", "symbol": self.symbol, "period": "1h", "limit": 1}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")

        entries = data["result"]["list"]
        if entries:
            buy_ratio = float(entries[0]["buyRatio"])
            sell_ratio = float(entries[0]["sellRatio"])
            # Convert to longShortRatio format (same as Binance)
            return round(buy_ratio / sell_ratio, 4) if sell_ratio > 0 else 1.0
        return None

    # ════════════════════════════════════════════════════════════════════
    # Current Price (Ticker)
    # ════════════════════════════════════════════════════════════════════

    def get_ticker(self) -> dict:
        cache_key = "ticker_24h"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._spot_blocked:
            try:
                result = self._binance_ticker()
                if result["price"] > 0:
                    cache.set(cache_key, result, ttl=60)
                    return result
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance spot blocked (ticker) — switching to Bybit")
                    self._spot_blocked = True
                else:
                    logger.error(f"Ticker error: {e}")

        # --- Fallback: Bybit ---
        try:
            result = self._bybit_ticker()
            if result["price"] > 0:
                cache.set(cache_key, result, ttl=60)
                return result
        except Exception as e:
            logger.error(f"Bybit ticker fallback error: {e}")

        # --- Last resort: CoinGecko ---
        try:
            result = self._coingecko_ticker()
            if result["price"] > 0:
                cache.set(cache_key, result, ttl=60)
                return result
        except Exception as e:
            logger.error(f"CoinGecko ticker fallback error: {e}")

        return {"price": 0, "change": 0, "change_pct": 0}

    def _binance_ticker(self):
        url = f"{self.base}/api/v3/ticker/24hr"
        params = {"symbol": self.symbol}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "price": float(data["lastPrice"]),
            "change": float(data["priceChange"]),
            "change_pct": float(data["priceChangePercent"]),
        }

    def _bybit_ticker(self):
        url = f"{self.bybit}/v5/market/tickers"
        params = {"category": "spot", "symbol": self.symbol}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")

        tickers = data["result"]["list"]
        if tickers:
            t = tickers[0]
            price = float(t["lastPrice"])
            prev_price = float(t["prevPrice24h"]) if t.get("prevPrice24h") else price
            change = price - prev_price
            change_pct = float(t.get("price24hPcnt", 0)) * 100  # Bybit returns decimal
            return {
                "price": price,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
        raise RuntimeError("No ticker data from Bybit")

    def _coingecko_ticker(self):
        url = f"{config.COINGECKO_BASE_URL}/simple/price"
        params = {
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("bitcoin", {})
        price = data.get("usd", 0)
        change_pct = data.get("usd_24h_change", 0)
        change = price * (change_pct / 100) if price else 0
        return {
            "price": price,
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
        }
