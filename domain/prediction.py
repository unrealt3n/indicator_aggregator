"""
Weighted scoring engine — converts raw indicator values into directional scores.
"""

from typing import List, Optional
from domain.models import IndicatorResult, PredictionResult, MACDResult, PivotLevels
import config


def score_higher_highs_lows(data: dict) -> IndicatorResult:
    p = data.get("pattern", "neutral")
    hh, hl = data.get("hh_count", 0), data.get("hl_count", 0)
    lh, ll = data.get("lh_count", 0), data.get("ll_count", 0)
    if p == "bullish":
        score = min(1.0, (hh + hl) / 8)
    elif p == "bearish":
        score = -min(1.0, (lh + ll) / 8)
    else:
        score = (hh + hl - lh - ll) / 10
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(1, "Higher Highs / Higher Lows", "price_structure", score,
                           round(score, 2), signal, f"HH:{hh} HL:{hl} LH:{lh} LL:{ll} — {p.title()}")


def score_price_vs_ma(data: dict, period: int, indicator_id: int) -> IndicatorResult:
    dist = data.get("distance_pct", 0)
    ma = data.get("ma")
    name = f"Price vs {period} MA"
    threshold = 2 if period == 50 else 5
    if dist > threshold:
        score = min(1.0, dist / (threshold * 3))
    elif dist < -threshold:
        score = max(-1.0, dist / (threshold * 3))
    else:
        score = dist / (threshold * 2)
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    label = f"{'Above' if dist > 0 else 'Below'} {period}MA by {abs(dist):.1f}%"
    return IndicatorResult(indicator_id, name, "price_structure", dist, round(score, 2),
                           signal, label, f"MA: {ma}")


def score_support_resistance(pivots: Optional[PivotLevels], price: float) -> IndicatorResult:
    if pivots is None:
        return IndicatorResult(4, "S&R Levels", "price_structure", None, 0, "neutral",
                               "Data unavailable", available=False)
    if price > pivots.r1:
        score = min(1.0, 0.5 + (price - pivots.r1) / (pivots.r2 - pivots.r1) * 0.5) if pivots.r2 != pivots.r1 else 0.7
    elif price < pivots.s1:
        score = max(-1.0, -0.5 - (pivots.s1 - price) / (pivots.s1 - pivots.s2) * 0.5) if pivots.s1 != pivots.s2 else -0.7
    else:
        mid_range = (pivots.r1 - pivots.s1)
        if mid_range > 0:
            score = ((price - pivots.pp) / mid_range) * 0.5
        else:
            score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    label = f"PP:{pivots.pp:,.0f} S1:{pivots.s1:,.0f} R1:{pivots.r1:,.0f}"
    return IndicatorResult(4, "S&R Levels", "price_structure", pivots.pp, round(score, 2), signal, label)


def score_session_range(data: dict, price: float) -> IndicatorResult:
    if not data.get("available"):
        return IndicatorResult(5, "Asia Session Range", "price_structure", None, 0, "neutral",
                               "Session data unavailable", available=False)
    h, l = data["high"], data["low"]
    if price > h:
        score = min(1.0, (price - h) / (h - l) * 0.5) if h != l else 0.5
    elif price < l:
        score = max(-1.0, -(l - price) / (h - l) * 0.5) if h != l else -0.5
    else:
        mid = (h + l) / 2
        score = ((price - mid) / (h - l)) * 0.3 if h != l else 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(5, "Asia Session Range", "price_structure", None, round(score, 2),
                           signal, f"Asia H:{h:,.0f} L:{l:,.0f}", f"Price: {price:,.0f}")


def score_cme_gap(data: dict) -> IndicatorResult:
    gap_pct = data.get("gap_pct", 0)
    filled = data.get("filled", True)
    direction = data.get("direction", "none")
    if direction == "none" or filled:
        score = 0
    elif direction == "up":
        score = -0.3  # Unfilled gap up tends to pull price down
    else:
        score = 0.3   # Unfilled gap down tends to pull price up
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    label = f"Gap: {gap_pct:+.2f}% {'(Filled)' if filled else '(Unfilled)'}" if direction != "none" else "No CME gap"
    return IndicatorResult(6, "CME Futures Gap", "price_structure", gap_pct, round(score, 2), signal, label)


def score_rsi(rsi: Optional[float]) -> IndicatorResult:
    if rsi is None:
        return IndicatorResult(7, "RSI (14)", "momentum_volatility", None, 0, "neutral",
                               "Data unavailable", available=False)
    if 50 <= rsi <= 70:
        score = (rsi - 50) / 40
    elif rsi > 70:
        score = max(-1.0, -(rsi - 70) / 30)
    elif 30 <= rsi < 50:
        score = (rsi - 50) / 40
    else:
        score = max(-0.5, (rsi - 30) / 30)  # Oversold can mean bounce
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    zone = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Momentum" if rsi > 50 else "Weak"
    return IndicatorResult(7, "RSI (14)", "momentum_volatility", rsi, round(score, 2), signal, f"RSI: {rsi:.1f} — {zone}")


def score_macd(macd: Optional[MACDResult]) -> IndicatorResult:
    if macd is None:
        return IndicatorResult(8, "MACD", "momentum_volatility", None, 0, "neutral",
                               "Data unavailable", available=False)
    hist = macd.histogram
    if hist > 0:
        score = min(1.0, hist / max(abs(macd.macd_line), 1) * 2)
    else:
        score = max(-1.0, hist / max(abs(macd.macd_line), 1) * 2)
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(8, "MACD", "momentum_volatility", hist, round(score, 2), signal,
                           f"MACD:{macd.macd_line:.0f} Sig:{macd.signal_line:.0f} Hist:{hist:.0f}")


def score_volume_vs_avg(data: dict, last_candle_green: bool) -> IndicatorResult:
    ratio = data.get("ratio", 1.0)
    if ratio > 1.5 and last_candle_green:
        score = min(1.0, (ratio - 1) * 0.5)
    elif ratio > 1.5 and not last_candle_green:
        score = max(-1.0, -(ratio - 1) * 0.5)
    else:
        score = (ratio - 1) * 0.3 * (1 if last_candle_green else -1)
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(9, "Volume vs 20d Avg", "momentum_volatility", ratio, round(score, 2),
                           signal, f"Volume {ratio:.1f}x average")


def score_volume_up_down(data: dict) -> IndicatorResult:
    up_pct = data.get("up_pct", 50)
    if up_pct > 60:
        score = min(1.0, (up_pct - 50) / 30)
    elif up_pct < 40:
        score = max(-1.0, (up_pct - 50) / 30)
    else:
        score = (up_pct - 50) / 50
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(10, "Up/Down Volume", "momentum_volatility", up_pct, round(score, 2),
                           signal, f"Up Vol: {up_pct:.0f}% | Down: {data.get('down_pct', 50):.0f}%")


def score_atr(data: dict) -> IndicatorResult:
    atr_pct = data.get("atr_pct", 0)
    if atr_pct < 3:
        score = 0.3  # Low vol trending
    elif atr_pct > 5:
        score = -0.3  # High vol choppy
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    zone = "Low (Trending)" if atr_pct < 3 else "High (Volatile)" if atr_pct > 5 else "Normal"
    return IndicatorResult(11, "ATR % of Price", "momentum_volatility", atr_pct, round(score, 2),
                           signal, f"ATR: {data.get('atr', 0):,.0f} ({atr_pct:.2f}%) — {zone}")


def score_bollinger_width(data: dict) -> IndicatorResult:
    width = data.get("width", 0)
    if width < 4:
        score = 0.3  # Squeeze → breakout potential
    elif width > 12:
        score = -0.2  # Extreme expansion → reversal risk
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    zone = "Squeeze" if width < 4 else "Wide" if width > 12 else "Normal"
    return IndicatorResult(12, "Bollinger Band Width", "momentum_volatility", width, round(score, 2),
                           signal, f"BB Width: {width:.2f}% — {zone}")


def score_hv20(hv: Optional[float]) -> IndicatorResult:
    if hv is None:
        return IndicatorResult(13, "Historical Volatility", "momentum_volatility", None, 0, "neutral",
                               "Data unavailable", available=False)
    if hv < 40:
        score = 0.3
    elif hv > 80:
        score = -0.3
    else:
        score = 0
    zone = "Low (Calm)" if hv < 40 else "High (Volatile)" if hv > 80 else "Normal"
    return IndicatorResult(13, "Historical Volatility (HV20)", "momentum_volatility", hv, round(score, 2),
                           "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral",
                           f"HV20: {hv:.1f}% — {zone}")


def score_dxy(data: dict) -> IndicatorResult:
    direction = data.get("direction", "flat")
    change = data.get("change_pct", 0)
    if direction == "falling":
        score = min(1.0, abs(change) / 3)
    elif direction == "rising":
        score = -min(1.0, abs(change) / 3)
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(14, "DXY Direction", "macro_sentiment", change, round(score, 2),
                           signal, f"DXY {direction.title()} ({change:+.2f}%)")


def score_sp500(data: dict) -> IndicatorResult:
    direction = data.get("direction", "flat")
    change = data.get("change_pct", 0)
    if direction == "rising":
        score = min(1.0, abs(change) / 3)
    elif direction == "falling":
        score = -min(1.0, abs(change) / 3)
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(15, "S&P 500", "macro_sentiment", change, round(score, 2),
                           signal, f"S&P 500 {direction.title()} ({change:+.2f}%)")


def score_m2(data: dict) -> IndicatorResult:
    if not data.get("available", False):
        return IndicatorResult(16, "M2 Money Supply", "macro_sentiment", None, 0, "neutral",
                               "Data unavailable", available=False)
    change = data.get("change_pct", 0)
    if change > 0:
        score = min(0.5, change / 2)
    elif change < 0:
        score = max(-0.5, change / 2)
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(16, "M2 Money Supply", "macro_sentiment", change, round(score, 2),
                           signal, f"M2 MoM: {change:+.2f}%")


def score_fear_greed(value: Optional[int]) -> IndicatorResult:
    if value is None:
        return IndicatorResult(17, "Fear & Greed Index", "macro_sentiment", None, 0, "neutral",
                               "Data unavailable", available=False)
    if value > 75:
        score = -0.5  # Extreme greed → reversal risk
    elif value < 25:
        score = -0.3  # Extreme fear
    elif 25 <= value <= 50:
        score = (50 - value) / 50  # Recovery zone → bullish
    else:
        score = (value - 50) / 100
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    zone = "Extreme Greed" if value > 75 else "Greed" if value > 55 else "Neutral" if value > 45 else "Fear" if value > 25 else "Extreme Fear"
    return IndicatorResult(17, "Fear & Greed Index", "macro_sentiment", value, round(score, 2), signal,
                           f"F&G: {value} — {zone}")


def score_funding_rate(rate: Optional[float]) -> IndicatorResult:
    if rate is None:
        return IndicatorResult(18, "Funding Rate", "derivatives", None, 0, "neutral",
                               "Data unavailable", available=False)
    rate_pct = rate * 100
    if 0 < rate_pct <= 0.01:
        score = 0.3
    elif rate_pct > 0.05:
        score = -0.5  # Crowded longs
    elif rate_pct < -0.01:
        score = 0.5   # Shorts paying → bullish
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(18, "Funding Rate", "derivatives", rate_pct, round(score, 2),
                           signal, f"Funding: {rate_pct:.4f}%")


def score_open_interest(data: dict) -> IndicatorResult:
    if not data.get("available", False):
        return IndicatorResult(19, "Open Interest", "derivatives", None, 0, "neutral",
                               "Data unavailable", available=False)
    oi_change = data.get("change_pct", 0)
    price_rising = data.get("price_rising", True)
    if oi_change > 0 and price_rising:
        score = min(1.0, oi_change / 10)
    elif oi_change > 0 and not price_rising:
        score = max(-1.0, -oi_change / 10)
    elif oi_change < 0 and price_rising:
        score = 0.2  # Short squeeze
    else:
        score = max(-0.5, oi_change / 10)
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(19, "Open Interest", "derivatives", oi_change, round(score, 2),
                           signal, f"OI Change: {oi_change:+.2f}%")


def score_cvd(data: dict) -> IndicatorResult:
    trend = data.get("trend", "flat")
    if trend == "positive":
        score = 0.5
    elif trend == "negative":
        score = -0.5
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(20, "CVD (Approx.)", "derivatives", data.get("cvd", 0), round(score, 2),
                           signal, f"CVD Trend: {trend.title()}")


def score_long_short_ratio(ratio: Optional[float]) -> IndicatorResult:
    if ratio is None:
        return IndicatorResult(21, "Long/Short Ratio", "derivatives", None, 0, "neutral",
                               "Data unavailable", available=False)
    if ratio < 1.0:
        score = min(0.5, (1.0 - ratio) * 1.5)  # Shorts crowded → bullish
    elif ratio > 2.0:
        score = max(-0.5, -(ratio - 1.5))  # Longs crowded → bearish
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(21, "Long/Short Ratio", "derivatives", ratio, round(score, 2),
                           signal, f"L/S Ratio: {ratio:.2f}")


def score_etf_flows(data: dict) -> IndicatorResult:
    if not data.get("available", False):
        return IndicatorResult(22, "ETF Spot Flows", "derivatives", None, 0, "neutral",
                               "Data unavailable", available=False)
    flow = data.get("net_flow", 0)
    if flow > 100:
        score = min(1.0, flow / 500)
    elif flow < -100:
        score = max(-1.0, flow / 500)
    else:
        score = flow / 300
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(22, "ETF Spot Flows", "derivatives", flow, round(score, 2),
                           signal, f"Net Flow: ${flow:+,.0f}M")


def score_liquidation_clusters(data: dict) -> IndicatorResult:
    if not data.get("available", False):
        return IndicatorResult(23, "Liquidation Clusters", "liquidation", None, 0, "neutral",
                               "Data unavailable", available=False)
    bias = data.get("bias", "balanced")
    if bias == "below":
        score = 0.4
    elif bias == "above":
        score = -0.4
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(23, "Liquidation Clusters", "liquidation", None, round(score, 2),
                           signal, f"Major cluster: {bias}")


def score_liquidation_asymmetry(data: dict) -> IndicatorResult:
    if not data.get("available", False):
        return IndicatorResult(24, "Liquidation Asymmetry", "liquidation", None, 0, "neutral",
                               "Data unavailable", available=False)
    side = data.get("dominant_side", "balanced")
    if side == "shorts":
        score = 0.4
    elif side == "longs":
        score = -0.4
    else:
        score = 0
    signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return IndicatorResult(24, "Liquidation Asymmetry", "liquidation", None, round(score, 2),
                           signal, f"More {side} to liquidate")


def score_session_weight(session_name: str, weight: float) -> IndicatorResult:
    score = (weight - 1.0) * 0.5
    return IndicatorResult(25, "Session Weighting", "session", weight, round(score, 2),
                           "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral",
                           f"Session weight: {weight:.1f}x")


# =============================================================================
# COMPOSITE PREDICTION
# =============================================================================

def compute_prediction(indicators: List[IndicatorResult], timeframe: str,
                       timeframe_label: str, current_price: float,
                       atr_pct: float, session_weight: float) -> PredictionResult:
    """Compute final weighted prediction from all indicator scores."""
    group_scores = {}
    group_counts = {}

    for ind in indicators:
        g = ind.group
        if g not in group_scores:
            group_scores[g] = 0
            group_counts[g] = 0
        if ind.available:
            group_scores[g] += ind.score
            group_counts[g] += 1

    # Average score per group
    group_avgs = {}
    for g in group_scores:
        if group_counts[g] > 0:
            group_avgs[g] = group_scores[g] / group_counts[g]
        else:
            group_avgs[g] = 0

    # Apply weights
    weights = dict(config.GROUP_WEIGHTS)
    multipliers = config.TIMEFRAME_WEIGHT_MULTIPLIERS.get(timeframe, {})
    for g, mult in multipliers.items():
        if g in weights:
            weights[g] *= mult

    total_weight = sum(weights.get(g, 0) for g in group_avgs)
    if total_weight == 0:
        total_weight = 1

    composite = sum(group_avgs.get(g, 0) * weights.get(g, 0) for g in group_avgs) / total_weight

    # Direction
    if composite > 0.15:
        direction = "bullish"
    elif composite < -0.15:
        direction = "bearish"
    else:
        direction = "neutral"

    # Confidence: % of indicators agreeing
    available = [i for i in indicators if i.available]
    if available:
        agreeing = sum(1 for i in available if
                       (direction == "bullish" and i.score > 0) or
                       (direction == "bearish" and i.score < 0) or
                       (direction == "neutral" and abs(i.score) < 0.15))
        confidence = (agreeing / len(available)) * 100
    else:
        confidence = 0

    # Estimated move %
    move_pct = abs(composite) * max(atr_pct, 1.0) * session_weight
    range_low = current_price * (1 - move_pct / 100)
    range_high = current_price * (1 + move_pct / 100)

    return PredictionResult(
        timeframe=timeframe,
        timeframe_label=timeframe_label,
        composite_score=round(composite, 3),
        direction=direction,
        confidence=round(confidence, 1),
        estimated_move_pct=round(move_pct, 2),
        estimated_range_low=round(range_low, 2),
        estimated_range_high=round(range_high, 2),
        current_price=current_price,
        indicators=indicators,
        groups={g: round(v, 3) for g, v in group_avgs.items()},
    )
