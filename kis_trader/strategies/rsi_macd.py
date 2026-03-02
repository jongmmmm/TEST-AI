import pandas as pd
import ta
from .base import BaseStrategy

class RsiMacdStrategy(BaseStrategy):
    """RSI 과매도/과매수 + MACD 시그널 전략"""

    def _calc(self, ohlcv: list) -> pd.DataFrame:
        df = pd.DataFrame(ohlcv).sort_values("date")
        if len(df) < 30:
            return df
        rsi_p = int(self.params.get("rsi_period", 14))
        macd_f = int(self.params.get("macd_fast", 12))
        macd_s = int(self.params.get("macd_slow", 26))
        macd_sig = int(self.params.get("macd_signal", 9))
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], rsi_p).rsi()
        macd = ta.trend.MACD(df["close"], macd_f, macd_s, macd_sig)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        return df

    def should_buy(self, ohlcv: list, current: dict) -> bool:
        df = self._calc(ohlcv)
        if len(df) < 2 or "rsi" not in df.columns:
            return False
        last = df.iloc[-1]
        oversold = float(self.params.get("rsi_oversold", 30))
        return (last["rsi"] < oversold and last["macd"] > last["macd_signal"])

    def should_sell(self, ohlcv: list, current: dict) -> bool:
        df = self._calc(ohlcv)
        if len(df) < 2 or "rsi" not in df.columns:
            return False
        last = df.iloc[-1]
        overbought = float(self.params.get("rsi_overbought", 70))
        return (last["rsi"] > overbought and last["macd"] < last["macd_signal"])
