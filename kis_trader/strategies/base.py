from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, stock_code: str, params: dict):
        self.stock_code = stock_code
        self.params = params

    @abstractmethod
    def should_buy(self, ohlcv: list, current: dict) -> bool:
        pass

    @abstractmethod
    def should_sell(self, ohlcv: list, current: dict) -> bool:
        pass

    def get_quantity(self) -> int:
        return int(self.params.get("buy_qty", 1))

    def check_stop_loss(self, avg_price: float, current_price: float) -> bool:
        stop_pct = float(self.params.get("stop_loss_pct", -5.0))
        if avg_price <= 0:
            return False
        change = (current_price - avg_price) / avg_price * 100
        return change <= stop_pct

    def check_take_profit(self, avg_price: float, current_price: float) -> bool:
        tp_pct = float(self.params.get("take_profit_pct", 10.0))
        if avg_price <= 0:
            return False
        change = (current_price - avg_price) / avg_price * 100
        return change >= tp_pct
