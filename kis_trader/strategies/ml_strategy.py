import os
import joblib
import pandas as pd
import ta
from .base import BaseStrategy

MODEL_DIR = os.path.join(os.path.dirname(__file__), "../models")
os.makedirs(MODEL_DIR, exist_ok=True)


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("date")
    df["ma5"]  = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["rsi"]  = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    macd = ta.trend.MACD(df["close"])
    df["macd_diff"] = macd.macd_diff()
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    df["ret1"] = df["close"].pct_change(1)
    df["ret5"] = df["close"].pct_change(5)
    return df.dropna()

FEATURES = ["ma5", "ma20", "ma60", "rsi", "macd_diff", "vol_ratio", "ret1", "ret5"]


def train_model(stock_code: str, ohlcv: list) -> None:
    """RandomForest 모델 학습 및 저장 (joblib)"""
    from sklearn.ensemble import RandomForestClassifier
    df = pd.DataFrame(ohlcv)
    if len(df) < 70:
        return
    df = _build_features(df)
    df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)
    df = df.dropna()
    X = df[FEATURES].values
    y = df["target"].values
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)
    model_path = os.path.join(MODEL_DIR, f"{stock_code}.joblib")
    joblib.dump(clf, model_path)


class MLStrategy(BaseStrategy):
    """RandomForest 예측 기반 전략"""

    def _predict(self, ohlcv: list) -> float:
        model_path = os.path.join(MODEL_DIR, f"{self.stock_code}.joblib")
        if not os.path.exists(model_path):
            return 0.5
        clf = joblib.load(model_path)
        df = pd.DataFrame(ohlcv)
        df = _build_features(df)
        if df.empty:
            return 0.5
        X = df[FEATURES].values[-1:]
        prob = clf.predict_proba(X)[0][1]
        return float(prob)

    def should_buy(self, ohlcv: list, current: dict) -> bool:
        threshold = float(self.params.get("buy_threshold", 0.65))
        return self._predict(ohlcv) >= threshold

    def should_sell(self, ohlcv: list, current: dict) -> bool:
        threshold = float(self.params.get("sell_threshold", 0.35))
        return self._predict(ohlcv) <= threshold
