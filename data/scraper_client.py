"""
Web scraper client — ETF flows (Farside), Liquidation data.

ETF flows: Farside scraping with graceful degradation (often blocked on servers).
Liquidation proxy: Primary Binance futures, fallback to Bybit public API.
"""

import logging
import requests
from bs4 import BeautifulSoup

import config
from data.cache import cache

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# HTTP status codes indicating geo-block or IP ban
_BLOCK_CODES = {451, 403, 418}


def _is_blocked(e: Exception) -> bool:
    """Check if an exception indicates geo-blocking or access denial."""
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        return e.response.status_code in _BLOCK_CODES
    return any(str(code) in str(e) for code in _BLOCK_CODES)


class ScraperClient:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._binance_futures_blocked = False

    # ── ETF Flows (Farside Investors) ────────────────────────────────────

    def get_etf_flows(self) -> dict:
        cache_key = "etf_flows"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            resp = self.session.get(config.FARSIDE_URL, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Find the data table — Farside uses a simple HTML table
            tables = soup.find_all("table")
            if not tables:
                return {"available": False}

            # Look for the most recent row with data
            table = tables[0]
            rows = table.find_all("tr")

            net_flow = 0
            found = False
            for row in reversed(rows[1:]):  # Skip header, start from bottom
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # Try to find the "Total" or last numeric column
                    for cell in reversed(cells):
                        text = cell.get_text(strip=True).replace(",", "").replace("$", "")
                        text = text.replace("(", "-").replace(")", "")
                        try:
                            val = float(text)
                            net_flow = val
                            found = True
                            break
                        except (ValueError, TypeError):
                            continue
                    if found:
                        break

            result = {"available": found, "net_flow": net_flow}
            cache.set(cache_key, result, ttl=1800)  # 30 min cache
            return result

        except Exception as e:
            logger.error(f"ETF flows scraping error: {e}")
            return {"available": False}

    # ── Liquidation Data (Primary: Binance, Fallback: Bybit) ─────────────

    def get_liquidation_data(self) -> dict:
        """
        Approximates liquidation pressure using taker volume ratio and
        top trader positioning data.

        Primary: Binance public endpoints.
        Fallback: Bybit public endpoints (when Binance is geo-blocked).
        """
        cache_key = "liquidation_data"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # --- Primary: Binance ---
        if not self._binance_futures_blocked:
            try:
                result = self._binance_liquidation_data()
                if result.get("available"):
                    cache.set(cache_key, result, ttl=600)
                    return result
            except Exception as e:
                if _is_blocked(e):
                    logger.warning("Binance futures blocked (liquidation) — switching to Bybit")
                    self._binance_futures_blocked = True
                else:
                    logger.error(f"Liquidation data error: {e}")

        # --- Fallback: Bybit ---
        try:
            result = self._bybit_liquidation_data()
            if result.get("available"):
                cache.set(cache_key, result, ttl=600)
                return result
        except Exception as e:
            logger.error(f"Bybit liquidation fallback error: {e}")

        return {
            "available": False,
            "dominant_side": "balanced",
            "bias": "balanced",
        }

    def _binance_liquidation_data(self):
        base = "https://fapi.binance.com/futures/data"

        # 1. Taker buy/sell ratio (recent 4h of hourly data)
        taker_resp = self.session.get(
            f"{base}/takerlongshortRatio",
            params={"symbol": "BTCUSDT", "period": "1h", "limit": 4},
            timeout=10,
        )
        taker_resp.raise_for_status()
        taker_data = taker_resp.json()

        # 2. Top trader position ratio (recent 4h)
        pos_resp = self.session.get(
            f"{base}/topLongShortPositionRatio",
            params={"symbol": "BTCUSDT", "period": "1h", "limit": 4},
            timeout=10,
        )
        pos_resp.raise_for_status()
        pos_data = pos_resp.json()

        return self._analyze_liquidation(taker_data, pos_data)

    def _bybit_liquidation_data(self):
        bybit = config.BYBIT_BASE_URL

        # Bybit account ratio (similar to Binance top trader ratio)
        ratio_resp = self.session.get(
            f"{bybit}/v5/market/account-ratio",
            params={"category": "linear", "symbol": "BTCUSDT", "period": "1h", "limit": 4},
            timeout=10,
        )
        ratio_resp.raise_for_status()
        ratio_data = ratio_resp.json()

        if ratio_data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {ratio_data.get('retMsg')}")

        entries = ratio_data["result"]["list"]
        if not entries:
            return {"available": False, "dominant_side": "balanced", "bias": "balanced"}

        # Convert Bybit format to match the analysis function's expected input
        # Bybit: buyRatio/sellRatio → simulate taker data and position data
        taker_data = []
        pos_data = []
        for entry in entries:
            buy_r = float(entry["buyRatio"])
            sell_r = float(entry["sellRatio"])
            # Simulate Binance taker format
            taker_data.append({"buySellRatio": str(buy_r / sell_r if sell_r > 0 else 1.0)})
            # Simulate Binance position format
            pos_data.append({
                "longShortRatio": str(buy_r / sell_r if sell_r > 0 else 1.0),
                "longAccount": str(buy_r),
                "shortAccount": str(sell_r),
            })

        return self._analyze_liquidation(taker_data, pos_data)

    def _analyze_liquidation(self, taker_data, pos_data):
        """Shared analysis logic for both Binance and Bybit data."""
        # Analyze taker ratio: buySellRatio > 1 = more buys (bullish pressure)
        avg_taker = (
            sum(float(d["buySellRatio"]) for d in taker_data) / len(taker_data)
            if taker_data else 1.0
        )

        # Analyze top trader positioning: longShortRatio < 1 = more shorts
        avg_position = (
            sum(float(d["longShortRatio"]) for d in pos_data) / len(pos_data)
            if pos_data else 1.0
        )
        long_pct = float(pos_data[-1]["longAccount"]) * 100 if pos_data else 50
        short_pct = float(pos_data[-1]["shortAccount"]) * 100 if pos_data else 50

        # Determine liquidation bias:
        # If heavy longs → liquidation clusters below (support cushion = bullish)
        # If heavy shorts → liquidation clusters above (resistance magnet = bullish squeeze potential)
        if avg_position < 0.8:  # Short-heavy
            dominant = "shorts"
            bias = "below"      # Price may squeeze up to liquidate shorts above
        elif avg_position > 1.3:  # Long-heavy
            dominant = "longs"
            bias = "above"      # Clusters above means longs at risk
        else:
            dominant = "balanced"
            bias = "balanced"

        return {
            "available": True,
            "taker_ratio": round(avg_taker, 4),
            "position_ratio": round(avg_position, 4),
            "long_pct": round(long_pct, 1),
            "short_pct": round(short_pct, 1),
            "dominant_side": dominant,
            "bias": bias,
        }
