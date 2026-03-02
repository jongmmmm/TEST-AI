import pandas as pd
from .base import BaseStrategy

class MAStrategy(BaseStrategy):
    """이동평균선 골든크로스/데드크로스 전략"""

    def _calc_ma(self, ohlcv: list) -> pd.DataFrame:
        df = pd.DataFrame(ohlcv)
        if df.empty:
            return df
        df = df.sort_values("date")
        short = int(self.params.get("short_period", 5))
        long_ = int(self.params.get("long_period", 20))
        df["ma_short"] = df["close"].rolling(short).mean()
        df["ma_long"] = df["close"].rolling(long_).mean()
        return df

    def should_buy(self, ohlcv: list, current: dict) -> bool:
        df = self._calc_ma(ohlcv)
        if len(df) < 2:
            return False
        prev, last = df.iloc[-2], df.iloc[-1]
        return (prev["ma_short"] <= prev["ma_long"] and
                last["ma_short"] > last["ma_long"])

    def should_sell(self, ohlcv: list, current: dict) -> bool:
        df = self._calc_ma(ohlcv)
        if len(df) < 2:
            return False
        prev, last = df.iloc[-2], df.iloc[-1]
        return (prev["ma_short"] >= prev["ma_long"] and
                last["ma_short"] < last["ma_long"])
