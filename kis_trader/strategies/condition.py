from .base import BaseStrategy

OPERATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}

class ConditionStrategy(BaseStrategy):
    """
    사용자 조건식 전략
    params.conditions 예시:
      [{"indicator": "change_rate", "operator": ">", "value": 3.0}]
    params.action: "buy" | "sell" | "both"
    """

    def _evaluate(self, conditions: list, current: dict) -> bool:
        for cond in conditions:
            ind = cond.get("indicator", "")
            op = cond.get("operator", ">")
            val = float(cond.get("value", 0))
            actual = float(current.get(ind, 0))
            fn = OPERATORS.get(op)
            if fn is None or not fn(actual, val):
                return False
        return True

    def should_buy(self, ohlcv: list, current: dict) -> bool:
        action = self.params.get("action", "buy")
        if action not in ("buy", "both"):
            return False
        return self._evaluate(self.params.get("conditions", []), current)

    def should_sell(self, ohlcv: list, current: dict) -> bool:
        action = self.params.get("action", "sell")
        if action not in ("sell", "both"):
            return False
        return self._evaluate(self.params.get("conditions", []), current)
