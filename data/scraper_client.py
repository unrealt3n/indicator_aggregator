"""
Web scraper client — ETF flows (Farside), Liquidation data (CoinGlass).
These are fragile and degrade gracefully.
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


class ScraperClient:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

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

    # ── Liquidation Data (Binance Public Endpoints) ────────────────────────

    def get_liquidation_data(self) -> dict:
        """
        Approximates liquidation pressure using two Binance public endpoints:
        1. takerLongShortRatio — buy vs sell taker volume (aggressor side)
        2. topLongShortPositionRatio — top trader positioning skew

        These are reliable proxies for where liquidation clusters exist:
        - Heavy long positioning → liquidation clusters below price
        - Heavy short positioning → liquidation clusters above price
        """
        cache_key = "liquidation_data"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
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

            # Analyze taker ratio: buySellRatio > 1 = more buys (bullish pressure)
            avg_taker = sum(float(d["buySellRatio"]) for d in taker_data) / len(taker_data) if taker_data else 1.0

            # Analyze top trader positioning: longShortRatio < 1 = more shorts
            avg_position = sum(float(d["longShortRatio"]) for d in pos_data) / len(pos_data) if pos_data else 1.0
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

            result = {
                "available": True,
                "taker_ratio": round(avg_taker, 4),
                "position_ratio": round(avg_position, 4),
                "long_pct": round(long_pct, 1),
                "short_pct": round(short_pct, 1),
                "dominant_side": dominant,
                "bias": bias,
            }
            cache.set(cache_key, result, ttl=600)
            return result

        except Exception as e:
            logger.error(f"Liquidation data error: {e}")

        return {
            "available": False,
            "dominant_side": "balanced",
            "bias": "balanced",
        }
