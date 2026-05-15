"""
Serializers — convert domain models to JSON-safe dicts for API responses.
"""

from dataclasses import asdict
from domain.models import DashboardData, PredictionResult, IndicatorResult, SessionInfo


def serialize_indicator(ind: IndicatorResult) -> dict:
    return {
        "id": ind.id,
        "name": ind.name,
        "group": ind.group,
        "value": ind.value,
        "score": ind.score,
        "signal": ind.signal,
        "label": ind.label,
        "detail": ind.detail,
        "available": ind.available,
    }


def serialize_prediction(pred: PredictionResult) -> dict:
    return {
        "timeframe": pred.timeframe,
        "timeframe_label": pred.timeframe_label,
        "composite_score": pred.composite_score,
        "direction": pred.direction,
        "confidence": pred.confidence,
        "estimated_move_pct": pred.estimated_move_pct,
        "estimated_range_low": pred.estimated_range_low,
        "estimated_range_high": pred.estimated_range_high,
        "current_price": pred.current_price,
        "indicators": [serialize_indicator(i) for i in pred.indicators],
        "groups": pred.groups,
    }


def serialize_session(session: SessionInfo) -> dict:
    if session is None:
        return None
    return {
        "name": session.name,
        "label": session.label,
        "weight": session.weight,
        "is_active": session.is_active,
    }


def serialize_dashboard(data: DashboardData) -> dict:
    return {
        "current_price": data.current_price,
        "price_change_24h": data.price_change_24h,
        "price_change_pct_24h": data.price_change_pct_24h,
        "predictions": [serialize_prediction(p) for p in data.predictions],
        "session": serialize_session(data.session),
        "last_updated": data.last_updated,
        "errors": data.errors,
    }
