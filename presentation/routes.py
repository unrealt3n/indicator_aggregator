"""
Flask routes — REST API endpoints for the dashboard.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from data.binance_client import BinanceClient
from data.macro_client import MacroClient
from data.scraper_client import ScraperClient
from domain import indicators as ind
from domain import prediction as pred
from domain.models import DashboardData, SessionInfo, IndicatorResult
from presentation.serializers import serialize_dashboard

import config

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__)

# Data clients (singleton-ish for the blueprint)
binance = BinanceClient()
macro = MacroClient()
scraper = ScraperClient()


def _build_indicators_for_timeframe(tf: str, candles, hourly_candles,
                                     macro_data: dict, deriv_data: dict,
                                     session_name: str, session_weight: float,
                                     current_price: float):
    """Build all 25 indicator results for one timeframe."""
    closes = [c.close for c in candles]
    results = []

    # Group 1 — Price Structure
    results.append(pred.score_higher_highs_lows(ind.calc_higher_highs_lows(candles)))
    results.append(pred.score_price_vs_ma(ind.calc_price_vs_ma(closes, 50), 50, 2))
    results.append(pred.score_price_vs_ma(ind.calc_price_vs_ma(closes, 200), 200, 3))
    pivots = ind.calc_pivot_levels(candles)
    results.append(pred.score_support_resistance(pivots, current_price))
    asia = ind.calc_session_high_low(hourly_candles, 0, 8) if hourly_candles else {"available": False}
    results.append(pred.score_session_range(asia, current_price))
    results.append(pred.score_cme_gap(ind.calc_cme_gap(candles)))

    # Group 2 — Momentum & Volatility
    results.append(pred.score_rsi(ind.calc_rsi(closes)))
    results.append(pred.score_macd(ind.calc_macd(closes)))
    results.append(pred.score_volume_vs_avg(
        ind.calc_volume_vs_avg(candles),
        candles[-1].close >= candles[-1].open if candles else True))
    results.append(pred.score_volume_up_down(ind.calc_volume_up_down(candles)))
    atr_data = ind.calc_atr(candles)
    results.append(pred.score_atr(atr_data))
    results.append(pred.score_bollinger_width(ind.calc_bollinger_width(closes)))
    results.append(pred.score_hv20(ind.calc_historical_volatility(closes)))

    # Group 3 — Macro / Sentiment
    results.append(pred.score_dxy(macro_data.get("dxy", {})))
    results.append(pred.score_sp500(macro_data.get("sp500", {})))
    results.append(pred.score_m2(macro_data.get("m2", {})))
    results.append(pred.score_fear_greed(macro_data.get("fear_greed")))

    # Group 4 — Derivatives
    results.append(pred.score_funding_rate(deriv_data.get("funding_rate")))
    oi_data = deriv_data.get("oi", {})
    if oi_data.get("available"):
        oi_data["price_rising"] = candles[-1].close > candles[-2].close if len(candles) >= 2 else True
    results.append(pred.score_open_interest(oi_data))
    results.append(pred.score_cvd(ind.calc_cvd_approximation(candles)))
    results.append(pred.score_long_short_ratio(deriv_data.get("ls_ratio")))
    results.append(pred.score_etf_flows(deriv_data.get("etf_flows", {})))

    # Group 5 — Liquidation
    liq = deriv_data.get("liquidation", {})
    results.append(pred.score_liquidation_clusters(liq))
    results.append(pred.score_liquidation_asymmetry(liq))

    # Group 6 — Session
    results.append(pred.score_session_weight(session_name, session_weight))

    return results, atr_data.get("atr_pct", 2.0)


@api.route("/api/dashboard")
def dashboard():
    """Main endpoint — returns all data for all timeframes."""
    errors = []

    # Get current price
    ticker = binance.get_ticker()
    current_price = ticker["price"]

    # Session info
    now = datetime.now(timezone.utc)
    session_name, session_label, session_weight = ind.get_current_session(now.hour)
    session = SessionInfo(session_name, session_label, session_weight, True)

    # Fetch macro data (shared across timeframes)
    macro_data = {}
    try:
        macro_data["dxy"] = macro.get_dxy()
    except Exception as e:
        errors.append(f"DXY: {e}")
        macro_data["dxy"] = {"direction": "flat", "change_pct": 0}

    try:
        macro_data["sp500"] = macro.get_sp500()
    except Exception as e:
        errors.append(f"S&P500: {e}")
        macro_data["sp500"] = {"direction": "flat", "change_pct": 0}

    try:
        macro_data["m2"] = macro.get_m2_supply()
    except Exception as e:
        errors.append(f"M2: {e}")
        macro_data["m2"] = {"available": False}

    try:
        macro_data["fear_greed"] = macro.get_fear_greed()
    except Exception as e:
        errors.append(f"F&G: {e}")
        macro_data["fear_greed"] = None

    # Fetch derivatives data (shared across timeframes)
    deriv_data = {}
    try:
        deriv_data["funding_rate"] = binance.get_funding_rate()
    except Exception as e:
        errors.append(f"Funding: {e}")

    try:
        deriv_data["oi"] = binance.get_open_interest()
    except Exception as e:
        errors.append(f"OI: {e}")
        deriv_data["oi"] = {"available": False}

    try:
        deriv_data["ls_ratio"] = binance.get_long_short_ratio()
    except Exception as e:
        errors.append(f"L/S: {e}")

    try:
        deriv_data["etf_flows"] = scraper.get_etf_flows()
    except Exception as e:
        errors.append(f"ETF: {e}")
        deriv_data["etf_flows"] = {"available": False}

    try:
        deriv_data["liquidation"] = scraper.get_liquidation_data()
    except Exception as e:
        errors.append(f"Liq: {e}")
        deriv_data["liquidation"] = {"available": False}

    # Hourly candles for session analysis
    hourly_candles = binance.get_klines("1h", 48)

    # Build predictions for each timeframe
    predictions = []
    for tf_key, tf_config in config.TIMEFRAMES.items():
        try:
            candles = binance.get_klines(tf_config["kline_interval"], tf_config["kline_limit"])
            if not candles:
                continue

            indicator_results, atr_pct = _build_indicators_for_timeframe(
                tf_key, candles, hourly_candles, macro_data, deriv_data,
                session_name, session_weight, current_price
            )

            prediction = pred.compute_prediction(
                indicator_results, tf_key, tf_config["label"],
                current_price, atr_pct, session_weight
            )
            predictions.append(prediction)

        except Exception as e:
            logger.error(f"Timeframe {tf_key} error: {e}")
            errors.append(f"Timeframe {tf_key}: {e}")

    dashboard_data = DashboardData(
        current_price=current_price,
        price_change_24h=ticker["change"],
        price_change_pct_24h=ticker["change_pct"],
        predictions=predictions,
        session=session,
        last_updated=now.isoformat(),
        errors=errors,
    )

    return jsonify(serialize_dashboard(dashboard_data))
