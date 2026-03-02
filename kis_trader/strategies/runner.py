"""전략 실행기: DB 전략 조회 → 지표 계산 → 주문 실행"""
import logging
from datetime import datetime
from db import db
from models import Strategy, Order
from kis_api import get_current_price, get_daily_ohlcv, get_balance, place_order
from .ma_strategy import MAStrategy
from .rsi_macd import RsiMacdStrategy
from .condition import ConditionStrategy
from .ml_strategy import MLStrategy

logger = logging.getLogger(__name__)

STRATEGY_MAP = {
    "ma":        MAStrategy,
    "rsi_macd":  RsiMacdStrategy,
    "condition": ConditionStrategy,
    "ml":        MLStrategy,
}


def is_market_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 900 <= t <= 1530


def is_auction_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (800 <= t < 900) or (1520 <= t <= 1530)


def run_strategies(app):
    with app.app_context():
        if not is_market_hours() or is_auction_time():
            return
        strategies = Strategy.query.filter_by(is_active=True).all()
        balance_cache = {}
        for strat in strategies:
            try:
                _execute_strategy(strat, balance_cache)
            except Exception as e:
                logger.error(f"Strategy {strat.id} error: {e}")


def _execute_strategy(strat: Strategy, balance_cache: dict):
    cls = STRATEGY_MAP.get(strat.strategy_type)
    if cls is None:
        return

    engine = cls(strat.stock_code, strat.params or {})
    ohlcv = get_daily_ohlcv(strat.stock_code, strat.mode, count=100)
    current = get_current_price(strat.stock_code, strat.mode)
    price = current["price"]

    cache_key = strat.mode
    if cache_key not in balance_cache:
        balance_cache[cache_key] = {r["stock_code"]: r for r in get_balance(strat.mode)}
    holding = balance_cache[cache_key].get(strat.stock_code)

    if holding:
        avg_p = holding["avg_price"]
        if engine.check_stop_loss(avg_p, price) or engine.check_take_profit(avg_p, price):
            _place_and_record(strat, "sell", price, holding["quantity"])
            return

    if holding and engine.should_sell(ohlcv, current):
        _place_and_record(strat, "sell", price, holding["quantity"])
        return

    if not holding and engine.should_buy(ohlcv, current):
        _place_and_record(strat, "buy", price, engine.get_quantity())


def _place_and_record(strat: Strategy, order_type: str, price: float, qty: int):
    result = place_order(strat.stock_code, order_type, int(price), qty, strat.mode)
    order = Order(
        strategy_id=strat.id,
        stock_code=strat.stock_code,
        order_type=order_type,
        price=price,
        quantity=qty,
        status="submitted" if result["success"] else "pending",
        trigger="auto",
        mode=strat.mode,
        kis_order_no=result.get("order_no", ""),
    )
    db.session.add(order)
    db.session.commit()
