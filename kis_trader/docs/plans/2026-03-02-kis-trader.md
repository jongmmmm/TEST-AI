# KIS 자동매매 시스템 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 한국투자증권 Open API를 사용한 Flask 기반 자동매매 웹 시스템 — 모의/실전 전환, 4가지 전략(MA/EMA, RSI/MACD, 조건식, ML), 동시호가 웹 UI 팝업 수동 승인 지원.

**Architecture:** Flask + APScheduler 단일 프로세스. APScheduler가 1분마다 전략을 실행하고 동시호가 시간에 SSE(Server-Sent Events)로 웹 클라이언트에 팝업을 전송. SQLite로 전략/주문/알림을 저장.

**Tech Stack:** Flask, APScheduler, SQLAlchemy (SQLite), requests, pandas, ta (기술지표), scikit-learn + joblib, Fernet (암호화)

---

## 사전 지식

### 한국투자증권 API 구조
- **인증:** `POST /oauth2/tokenP` → `access_token` (24시간 유효)
- **모의 서버:** `https://openapivts.koreainvestment.com:29443`
- **실전 서버:** `https://openapi.koreainvestment.com:9443`
- **TR ID:** 모의는 앞에 `V`, 실전은 `T` (예: `VTTC0802U` vs `TTTC0802U`)
- **헤더:** `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype: P`

### 동시호가 시간
- **시가 동시호가:** 08:00~09:00 (09:00 일괄 체결)
- **종가 동시호가:** 15:20~15:30 (15:30 일괄 체결)

---

## Task 1: 프로젝트 초기화 및 의존성 설치

**Files:**
- Create: `requirements.txt`
- Create: `run.py`
- Create: `config.py`
- Create: `.env.example`

**Step 1: requirements.txt 작성**

```
flask==3.1.0
flask-sqlalchemy==3.1.1
apscheduler==3.10.4
requests==2.32.3
pandas==2.2.3
ta==0.11.0
scikit-learn==1.6.1
joblib==1.4.2
cryptography==44.0.2
python-dotenv==1.0.1
```

**Step 2: 의존성 설치**

```bash
cd /home/yms/kis_trader
pip install -r requirements.txt
```

Expected: 설치 완료, 오류 없음

**Step 3: config.py 작성**

```python
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "kis-trader-secret-change-me")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'kis_trader.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # KIS API
    KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
    KIS_ACCOUNT_SUFFIX = os.getenv("KIS_ACCOUNT_SUFFIX", "01")

    # URL
    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    REAL_BASE_URL  = "https://openapi.koreainvestment.com:9443"

    # 스케줄러
    STRATEGY_INTERVAL_SECONDS = 60
    AUCTION_CHECK_INTERVAL_SECONDS = 30
```

**Step 4: run.py 작성**

```python
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000, debug=False)
```

**Step 5: .env.example 작성**

```
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678
KIS_ACCOUNT_SUFFIX=01
SECRET_KEY=change-this-secret
```

**Step 6: Commit**

```bash
cd /home/yms/kis_trader
git add requirements.txt run.py config.py .env.example
git commit -m "feat: project init - config and requirements"
```

---

## Task 2: DB 모델 정의

**Files:**
- Create: `db.py`
- Create: `models.py`

**Step 1: db.py 작성**

```python
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

**Step 2: models.py 작성**

```python
from datetime import datetime
from db import db

class Strategy(db.Model):
    __tablename__ = "strategies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    stock_code = db.Column(db.String(10), nullable=False)
    stock_name = db.Column(db.String(50), default="")
    strategy_type = db.Column(db.String(20), nullable=False)  # ma|rsi_macd|condition|ml
    params = db.Column(db.JSON, default={})
    is_active = db.Column(db.Boolean, default=True)
    mode = db.Column(db.String(10), default="paper")  # paper|real
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey("strategies.id"), nullable=True)
    stock_code = db.Column(db.String(10), nullable=False)
    order_type = db.Column(db.String(4), nullable=False)   # buy|sell
    price = db.Column(db.Float, default=0)
    quantity = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="pending")   # pending|submitted|filled|cancelled
    trigger = db.Column(db.String(20), default="auto")     # auto|auction_manual
    mode = db.Column(db.String(10), default="paper")
    kis_order_no = db.Column(db.String(50), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuctionAlert(db.Model):
    __tablename__ = "auction_alerts"
    id = db.Column(db.Integer, primary_key=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey("strategies.id"), nullable=True)
    stock_code = db.Column(db.String(10), nullable=False)
    stock_name = db.Column(db.String(50), default="")
    suggested_action = db.Column(db.String(4))   # buy|sell
    suggested_price = db.Column(db.Float, default=0)
    suggested_qty = db.Column(db.Integer, default=0)
    user_decision = db.Column(db.String(4), nullable=True)  # buy|sell|pass|None
    decided_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PortfolioSnapshot(db.Model):
    __tablename__ = "portfolio_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(10))
    stock_code = db.Column(db.String(10))
    quantity = db.Column(db.Integer, default=0)
    avg_price = db.Column(db.Float, default=0)
    current_price = db.Column(db.Float, default=0)
    snapped_at = db.Column(db.DateTime, default=datetime.utcnow)

class KisToken(db.Model):
    """KIS 액세스 토큰 캐시"""
    __tablename__ = "kis_tokens"
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(10), unique=True)  # paper|real
    access_token = db.Column(db.Text, default="")
    expires_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Step 3: Commit**

```bash
git add db.py models.py
git commit -m "feat: add SQLAlchemy models (Strategy, Order, AuctionAlert, KisToken)"
```

---

## Task 3: KIS API 래퍼

**Files:**
- Create: `kis_api.py`

**Step 1: kis_api.py 작성**

```python
"""
한국투자증권 Open API 래퍼
- 토큰 자동 갱신 (DB 캐시)
- 모의/실전 URL 자동 전환
- 현재가, 일봉, 주문(매수/매도), 잔고 조회
"""
import requests
from datetime import datetime, timedelta
from flask import current_app
from db import db
from models import KisToken


def _base_url(mode: str) -> str:
    cfg = current_app.config
    return cfg["PAPER_BASE_URL"] if mode == "paper" else cfg["REAL_BASE_URL"]


def get_token(mode: str) -> str:
    """액세스 토큰 반환 (캐시 유효하면 재사용)"""
    cfg = current_app.config
    token_row = KisToken.query.filter_by(mode=mode).first()
    now = datetime.utcnow()

    if token_row and token_row.expires_at and token_row.expires_at > now + timedelta(minutes=5):
        return token_row.access_token

    url = f"{_base_url(mode)}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": cfg["KIS_APP_KEY"],
        "appsecret": cfg["KIS_APP_SECRET"],
    }
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    new_token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))

    if not token_row:
        token_row = KisToken(mode=mode)
        db.session.add(token_row)
    token_row.access_token = new_token
    token_row.expires_at = now + timedelta(seconds=expires_in)
    token_row.updated_at = now
    db.session.commit()
    return new_token


def _headers(mode: str, tr_id: str) -> dict:
    cfg = current_app.config
    return {
        "authorization": f"Bearer {get_token(mode)}",
        "appkey": cfg["KIS_APP_KEY"],
        "appsecret": cfg["KIS_APP_SECRET"],
        "tr_id": tr_id,
        "custtype": "P",
        "Content-Type": "application/json; charset=utf-8",
    }


def get_current_price(stock_code: str, mode: str = "paper") -> dict:
    """현재가 조회 → {"price": 70000, "change_rate": 1.23, "volume": ...}"""
    url = f"{_base_url(mode)}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
    }
    resp = requests.get(url, headers=_headers(mode, "FHKST01010100"), params=params, timeout=10)
    resp.raise_for_status()
    output = resp.json().get("output", {})
    return {
        "price": int(output.get("stck_prpr", 0)),
        "change_rate": float(output.get("prdy_ctrt", 0)),
        "volume": int(output.get("acml_vol", 0)),
        "high": int(output.get("stck_hgpr", 0)),
        "low": int(output.get("stck_lwpr", 0)),
    }


def get_daily_ohlcv(stock_code: str, mode: str = "paper", count: int = 100) -> list:
    """일봉 데이터 조회"""
    from datetime import date
    url = f"{_base_url(mode)}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    today = date.today().strftime("%Y%m%d")
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": "19000101",
        "FID_INPUT_DATE_2": today,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    resp = requests.get(url, headers=_headers(mode, "FHKST03010100"), params=params, timeout=15)
    resp.raise_for_status()
    output2 = resp.json().get("output2", [])
    result = []
    for row in output2[:count]:
        result.append({
            "date": row.get("stck_bsop_date", ""),
            "open": int(row.get("stck_oprc", 0)),
            "high": int(row.get("stck_hgpr", 0)),
            "low": int(row.get("stck_lwpr", 0)),
            "close": int(row.get("stck_clpr", 0)),
            "volume": int(row.get("acml_vol", 0)),
        })
    return result


def place_order(stock_code: str, order_type: str, price: int,
                quantity: int, mode: str = "paper") -> dict:
    """주문 실행 → {"order_no": "...", "success": True}"""
    cfg = current_app.config
    if order_type == "buy":
        tr_id = "VTTC0802U" if mode == "paper" else "TTTC0802U"
    else:
        tr_id = "VTTC0801U" if mode == "paper" else "TTTC0801U"

    url = f"{_base_url(mode)}/uapi/domestic-stock/v1/trading/order-cash"
    body = {
        "CANO": cfg["KIS_ACCOUNT_NO"],
        "ACNT_PRDT_CD": cfg["KIS_ACCOUNT_SUFFIX"],
        "PDNO": stock_code,
        "ORD_DVSN": "00" if price > 0 else "01",
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
    }
    resp = requests.post(url, headers=_headers(mode, tr_id), json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    output = data.get("output", {})
    return {
        "success": data.get("rt_cd") == "0",
        "order_no": output.get("ODNO", ""),
        "message": data.get("msg1", ""),
    }


def get_balance(mode: str = "paper") -> list:
    """잔고 조회"""
    cfg = current_app.config
    tr_id = "VTTC8434R" if mode == "paper" else "TTTC8434R"
    url = f"{_base_url(mode)}/uapi/domestic-stock/v1/trading/inquire-balance"
    params = {
        "CANO": cfg["KIS_ACCOUNT_NO"],
        "ACNT_PRDT_CD": cfg["KIS_ACCOUNT_SUFFIX"],
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "N",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    resp = requests.get(url, headers=_headers(mode, tr_id), params=params, timeout=10)
    resp.raise_for_status()
    output1 = resp.json().get("output1", [])
    result = []
    for row in output1:
        qty = int(row.get("hldg_qty", 0))
        if qty > 0:
            result.append({
                "stock_code": row.get("pdno", ""),
                "stock_name": row.get("prdt_name", ""),
                "quantity": qty,
                "avg_price": float(row.get("pchs_avg_pric", 0)),
                "current_price": int(row.get("prpr", 0)),
                "eval_profit_loss": float(row.get("evlu_pfls_amt", 0)),
                "profit_loss_rate": float(row.get("evlu_pfls_rt", 0)),
            })
    return result
```

**Step 2: Commit**

```bash
git add kis_api.py
git commit -m "feat: add KIS API wrapper (token, price, ohlcv, order, balance)"
```

---

## Task 4: 전략 엔진

**Files:**
- Create: `strategies/__init__.py`
- Create: `strategies/base.py`
- Create: `strategies/ma_strategy.py`
- Create: `strategies/rsi_macd.py`
- Create: `strategies/condition.py`
- Create: `strategies/ml_strategy.py`
- Create: `strategies/runner.py`

**Step 1: strategies/base.py 작성**

```python
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
```

**Step 2: strategies/ma_strategy.py 작성**

```python
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
```

**Step 3: strategies/rsi_macd.py 작성**

```python
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
```

**Step 4: strategies/condition.py 작성**

```python
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
```

**Step 5: strategies/ml_strategy.py 작성**
(joblib 사용 — scikit-learn 표준 직렬화 방식)

```python
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
```

**Step 6: strategies/runner.py 작성**

```python
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
        if not is_market_hours() and not is_auction_time():
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
```

**Step 7: strategies/__init__.py 작성**

```python
from .runner import run_strategies, is_auction_time, is_market_hours
from .ml_strategy import train_model
```

**Step 8: Commit**

```bash
git add strategies/
git commit -m "feat: add strategy engine (MA, RSI/MACD, Condition, ML+joblib) + runner"
```

---

## Task 5: APScheduler 설정

**Files:**
- Create: `scheduler.py`

**Step 1: scheduler.py 작성**

```python
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
_scheduler = None


def check_auction_and_alert(app):
    from strategies import is_auction_time
    from datetime import datetime
    from db import db
    from models import Strategy, AuctionAlert
    from kis_api import get_current_price
    from routers.auction import broadcast_auction

    with app.app_context():
        if not is_auction_time():
            return
        now = datetime.now()
        expires = now.replace(hour=9, minute=0, second=0) if now.hour < 9 else \
                  now.replace(hour=15, minute=30, second=0)

        for strat in Strategy.query.filter_by(is_active=True).all():
            existing = AuctionAlert.query.filter_by(
                stock_code=strat.stock_code, user_decision=None
            ).filter(AuctionAlert.expires_at >= now).first()
            if existing:
                continue
            try:
                current = get_current_price(strat.stock_code, strat.mode)
                action = "buy" if current["change_rate"] >= 0 else "sell"
                qty = int((strat.params or {}).get("buy_qty", 1))
                alert = AuctionAlert(
                    strategy_id=strat.id,
                    stock_code=strat.stock_code,
                    stock_name=strat.stock_name,
                    suggested_action=action,
                    suggested_price=current["price"],
                    suggested_qty=qty,
                    expires_at=expires,
                )
                db.session.add(alert)
                db.session.commit()
                broadcast_auction(alert.id)
            except Exception as e:
                logger.error(f"Auction alert error {strat.stock_code}: {e}")


def expire_undecided_alerts(app):
    from datetime import datetime
    from db import db
    from models import AuctionAlert
    with app.app_context():
        now = datetime.utcnow()
        alerts = AuctionAlert.query.filter_by(user_decision=None).filter(
            AuctionAlert.expires_at < now
        ).all()
        for alert in alerts:
            alert.user_decision = "pass"
            alert.decided_at = now
        db.session.commit()


def retrain_ml_models(app):
    from db import db
    from models import Strategy
    from kis_api import get_daily_ohlcv
    from strategies import train_model
    with app.app_context():
        for strat in Strategy.query.filter_by(strategy_type="ml", is_active=True).all():
            try:
                ohlcv = get_daily_ohlcv(strat.stock_code, strat.mode, count=120)
                train_model(strat.stock_code, ohlcv)
                logger.info(f"ML retrained: {strat.stock_code}")
            except Exception as e:
                logger.error(f"ML retrain error {strat.stock_code}: {e}")


def init_scheduler(app):
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    cfg = app.config

    from strategies import run_strategies
    _scheduler.add_job(
        lambda: run_strategies(app),
        IntervalTrigger(seconds=int(cfg.get("STRATEGY_INTERVAL_SECONDS", 60))),
        id="run_strategies", replace_existing=True,
    )
    _scheduler.add_job(
        lambda: check_auction_and_alert(app),
        IntervalTrigger(seconds=int(cfg.get("AUCTION_CHECK_INTERVAL_SECONDS", 30))),
        id="auction_check", replace_existing=True,
    )
    _scheduler.add_job(
        lambda: expire_undecided_alerts(app),
        IntervalTrigger(seconds=60),
        id="expire_alerts", replace_existing=True,
    )
    _scheduler.add_job(
        lambda: retrain_ml_models(app),
        CronTrigger(hour=3, minute=0),
        id="ml_retrain", replace_existing=True,
    )
    _scheduler.start()
    return _scheduler
```

**Step 2: Commit**

```bash
git add scheduler.py
git commit -m "feat: add APScheduler (strategy runner, auction alert, ML retrain)"
```

---

## Task 6: Flask 앱 팩토리 + 라우터

**Files:**
- Create: `app.py`
- Create: `routers/__init__.py`
- Create: `routers/dashboard.py`
- Create: `routers/strategies.py`
- Create: `routers/orders.py`
- Create: `routers/auction.py`
- Create: `routers/settings.py`

**Step 1: routers/auction.py 작성 (SSE + 수동 승인)**

```python
import json
import queue
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, stream_with_context
from db import db
from models import AuctionAlert, Order

bp = Blueprint("auction", __name__, url_prefix="/api/auction")

_sse_clients: list = []
_lock = threading.Lock()


def broadcast_auction(alert_id: int):
    alert = AuctionAlert.query.get(alert_id)
    if not alert:
        return
    msg = json.dumps({
        "id": alert.id,
        "stock_code": alert.stock_code,
        "stock_name": alert.stock_name,
        "suggested_action": alert.suggested_action,
        "suggested_price": alert.suggested_price,
        "suggested_qty": alert.suggested_qty,
        "expires_at": alert.expires_at.isoformat(),
    })
    with _lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


@bp.route("/stream")
def stream():
    q = queue.Queue(maxsize=20)
    with _lock:
        _sse_clients.append(q)

    def generate():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            with _lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/pending")
def pending():
    now = datetime.utcnow()
    alerts = AuctionAlert.query.filter_by(user_decision=None).filter(
        AuctionAlert.expires_at >= now
    ).order_by(AuctionAlert.created_at.desc()).all()
    return jsonify([{
        "id": a.id, "stock_code": a.stock_code, "stock_name": a.stock_name,
        "suggested_action": a.suggested_action, "suggested_price": a.suggested_price,
        "suggested_qty": a.suggested_qty, "expires_at": a.expires_at.isoformat(),
    } for a in alerts])


@bp.route("/decide/<int:alert_id>", methods=["POST"])
def decide(alert_id: int):
    data = request.get_json()
    decision = data.get("decision")
    if decision not in ("buy", "sell", "pass"):
        return jsonify({"error": "decision must be buy/sell/pass"}), 400

    alert = AuctionAlert.query.get_or_404(alert_id)
    if alert.user_decision is not None:
        return jsonify({"error": "already decided"}), 400

    alert.user_decision = decision
    alert.decided_at = datetime.utcnow()
    db.session.commit()

    if decision in ("buy", "sell"):
        from kis_api import place_order
        from models import Strategy
        strat = Strategy.query.get(alert.strategy_id)
        mode = strat.mode if strat else "paper"
        result = place_order(alert.stock_code, decision,
                             int(alert.suggested_price), alert.suggested_qty, mode)
        order = Order(
            strategy_id=alert.strategy_id,
            stock_code=alert.stock_code,
            order_type=decision,
            price=alert.suggested_price,
            quantity=alert.suggested_qty,
            status="submitted" if result["success"] else "pending",
            trigger="auction_manual",
            mode=mode,
            kis_order_no=result.get("order_no", ""),
        )
        db.session.add(order)
        db.session.commit()

    return jsonify({"message": f"{decision} 처리 완료"})
```

**Step 2: routers/dashboard.py 작성**

```python
from flask import Blueprint, render_template, jsonify, current_app
from kis_api import get_balance

bp = Blueprint("dashboard", __name__)

@bp.route("/")
def index():
    return render_template("dashboard.html")

@bp.route("/api/balance")
def balance():
    mode = current_app.config.get("CURRENT_MODE", "paper")
    try:
        data = get_balance(mode)
    except Exception:
        data = []
    return jsonify({"balance": data, "mode": mode})
```

**Step 3: routers/strategies.py 작성**

```python
from flask import Blueprint, render_template, request, jsonify
from db import db
from models import Strategy

bp = Blueprint("strategies", __name__, url_prefix="/strategies")

@bp.route("/")
def index():
    return render_template("strategies.html")

@bp.route("/api/strategies")
def list_strategies():
    items = Strategy.query.order_by(Strategy.created_at.desc()).all()
    return jsonify([{
        "id": s.id, "name": s.name, "stock_code": s.stock_code,
        "stock_name": s.stock_name, "strategy_type": s.strategy_type,
        "params": s.params, "is_active": s.is_active, "mode": s.mode,
    } for s in items])

@bp.route("/api/strategies", methods=["POST"])
def create_strategy():
    d = request.get_json()
    s = Strategy(
        name=d["name"], stock_code=d["stock_code"],
        stock_name=d.get("stock_name", ""),
        strategy_type=d["strategy_type"],
        params=d.get("params", {}),
        is_active=d.get("is_active", True),
        mode=d.get("mode", "paper"),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify({"id": s.id, "message": "전략 등록 완료"})

@bp.route("/api/strategies/<int:sid>", methods=["PUT"])
def update_strategy(sid):
    s = Strategy.query.get_or_404(sid)
    d = request.get_json()
    for field in ("name", "stock_code", "stock_name", "strategy_type", "params", "is_active", "mode"):
        if field in d:
            setattr(s, field, d[field])
    db.session.commit()
    return jsonify({"message": "업데이트 완료"})

@bp.route("/api/strategies/<int:sid>", methods=["DELETE"])
def delete_strategy(sid):
    s = Strategy.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    return jsonify({"message": "삭제 완료"})

@bp.route("/api/strategies/<int:sid>/toggle", methods=["POST"])
def toggle_strategy(sid):
    s = Strategy.query.get_or_404(sid)
    s.is_active = not s.is_active
    db.session.commit()
    return jsonify({"is_active": s.is_active})
```

**Step 4: routers/orders.py 작성**

```python
from flask import Blueprint, render_template, jsonify, request
from models import Order

bp = Blueprint("orders", __name__, url_prefix="/orders")

@bp.route("/")
def index():
    return render_template("orders.html")

@bp.route("/api/orders")
def list_orders():
    mode = request.args.get("mode", "")
    trigger = request.args.get("trigger", "")
    q = Order.query
    if mode:
        q = q.filter_by(mode=mode)
    if trigger:
        q = q.filter_by(trigger=trigger)
    orders = q.order_by(Order.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": o.id, "stock_code": o.stock_code,
        "order_type": o.order_type, "price": o.price,
        "quantity": o.quantity, "status": o.status,
        "trigger": o.trigger, "mode": o.mode,
        "kis_order_no": o.kis_order_no,
        "created_at": o.created_at.isoformat(),
    } for o in orders])
```

**Step 5: routers/settings.py 작성**

```python
from flask import Blueprint, render_template, request, jsonify, current_app

bp = Blueprint("settings", __name__, url_prefix="/settings")

@bp.route("/")
def index():
    return render_template("settings.html")

@bp.route("/api/settings/mode", methods=["POST"])
def set_mode():
    d = request.get_json()
    mode = d.get("mode")
    if mode not in ("paper", "real"):
        return jsonify({"error": "mode must be paper or real"}), 400
    current_app.config["CURRENT_MODE"] = mode
    return jsonify({"message": f"{mode} 모드로 전환됨", "mode": mode})

@bp.route("/api/settings/mode", methods=["GET"])
def get_mode():
    mode = current_app.config.get("CURRENT_MODE", "paper")
    return jsonify({"mode": mode})

@bp.route("/api/settings/token-refresh", methods=["POST"])
def refresh_token():
    from models import KisToken
    from db import db
    KisToken.query.delete()
    db.session.commit()
    return jsonify({"message": "토큰 캐시 삭제 완료 — 다음 요청 시 자동 갱신"})
```

**Step 6: routers/__init__.py 작성**

```python
from .dashboard import bp as dashboard_bp
from .strategies import bp as strategies_bp
from .orders import bp as orders_bp
from .auction import bp as auction_bp
from .settings import bp as settings_bp
```

**Step 7: app.py 작성**

```python
from flask import Flask
from config import Config
from db import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["CURRENT_MODE"] = "paper"

    db.init_app(app)
    with app.app_context():
        db.create_all()

    from routers import dashboard_bp, strategies_bp, orders_bp, auction_bp, settings_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(auction_bp)
    app.register_blueprint(settings_bp)

    from scheduler import init_scheduler
    init_scheduler(app)

    return app
```

**Step 8: Commit**

```bash
git add app.py routers/
git commit -m "feat: Flask app factory + routers (dashboard, strategies, orders, auction SSE, settings)"
```

---

## Task 7: HTML 템플릿

**Files:**
- Create: `templates/base.html`
- Create: `templates/dashboard.html`
- Create: `templates/strategies.html`
- Create: `templates/orders.html`
- Create: `templates/settings.html`
- Create: `static/js/auction.js`

**Step 1: static/js/auction.js 작성 (SSE + 팝업 처리)**

```javascript
let _currentAlertId = null;

const evtSource = new EventSource("/api/auction/stream");
evtSource.onmessage = function(e) {
  showAuctionPopup(JSON.parse(e.data));
};

function showAuctionPopup(data) {
  _currentAlertId = data.id;
  document.getElementById("au-name").textContent = data.stock_name || "-";
  document.getElementById("au-code").textContent = data.stock_code;
  const actionEl = document.getElementById("au-action");
  actionEl.textContent = data.suggested_action === "buy" ? "매수 추천" : "매도 추천";
  actionEl.className = "badge " + (data.suggested_action === "buy" ? "bg-primary" : "bg-danger");
  document.getElementById("au-price").textContent = Number(data.suggested_price).toLocaleString();
  document.getElementById("au-qty").textContent = data.suggested_qty;
  document.getElementById("au-expires").textContent = data.expires_at.replace("T", " ").slice(0, 19);
  document.getElementById("auction-overlay").classList.add("show");
}

function auctionDecide(decision) {
  if (!_currentAlertId) return;
  fetch("/api/auction/decide/" + _currentAlertId, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  })
    .then(r => r.json())
    .then(d => {
      document.getElementById("auction-overlay").classList.remove("show");
      _currentAlertId = null;
      if (d.message) alert(d.message);
    })
    .catch(() => alert("처리 실패"));
}

// 페이지 로드 시 미결 알림 확인
fetch("/api/auction/pending")
  .then(r => r.json())
  .then(list => { if (list.length > 0) showAuctionPopup(list[0]); });
```

**Step 2: templates/base.html 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}KIS 자동매매{% endblock %}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    body { background: #f4f6f9; }
    .navbar-brand { color: #fff !important; font-weight: bold; }
    .navbar { background: #1a1a2e !important; }
    .sidebar { min-height: calc(100vh - 52px); background: #16213e; padding-top: 16px; width: 200px; flex-shrink: 0; }
    .sidebar a { color: #ccc; display: block; padding: 10px 20px; text-decoration: none; border-radius: 6px; margin: 2px 8px; }
    .sidebar a:hover, .sidebar a.active { background: #6c63ff; color: #fff; }
    .mode-badge { font-size: .75rem; padding: 3px 8px; border-radius: 10px; }
    .mode-paper { background: #fff3cd; color: #856404; }
    .mode-real  { background: #f8d7da; color: #721c24; }
    #auction-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.65); z-index: 9999; align-items: center; justify-content: center; }
    #auction-overlay.show { display: flex; }
    .auction-card { background: #fff; border-radius: 14px; padding: 32px; min-width: 360px; box-shadow: 0 8px 40px rgba(0,0,0,.35); }
  </style>
</head>
<body>
<nav class="navbar px-3 py-2 d-flex justify-content-between">
  <span class="navbar-brand">KIS 자동매매</span>
  <span id="mode-badge" class="mode-badge mode-paper">모의투자</span>
</nav>
<div class="d-flex">
  <nav class="sidebar">
    <a href="/" class="{% if request.path == '/' %}active{% endif %}">
      <i class="fa-solid fa-chart-line me-2"></i>대시보드
    </a>
    <a href="/strategies/" class="{% if '/strategies' in request.path %}active{% endif %}">
      <i class="fa-solid fa-robot me-2"></i>전략 관리
    </a>
    <a href="/orders/" class="{% if '/orders' in request.path %}active{% endif %}">
      <i class="fa-solid fa-list me-2"></i>주문 내역
    </a>
    <a href="/settings/" class="{% if '/settings' in request.path %}active{% endif %}">
      <i class="fa-solid fa-gear me-2"></i>설정
    </a>
  </nav>
  <main class="flex-grow-1 p-4">{% block content %}{% endblock %}</main>
</div>

<!-- 동시호가 팝업 -->
<div id="auction-overlay">
  <div class="auction-card">
    <h5 class="fw-bold mb-3"><i class="fa-solid fa-bell text-warning me-2"></i>동시호가 알림</h5>
    <p class="mb-1"><strong>종목:</strong> <span id="au-name"></span> (<span id="au-code"></span>)</p>
    <p class="mb-1"><strong>추천:</strong> <span id="au-action" class="badge"></span></p>
    <p class="mb-1"><strong>가격:</strong> <span id="au-price"></span>원</p>
    <p class="mb-3"><strong>수량:</strong> <span id="au-qty"></span>주</p>
    <p class="text-muted small mb-3">만료: <span id="au-expires"></span></p>
    <div class="d-flex gap-2">
      <button class="btn btn-danger flex-fill" onclick="auctionDecide('sell')">매도</button>
      <button class="btn btn-primary flex-fill" onclick="auctionDecide('buy')">매수</button>
      <button class="btn btn-secondary flex-fill" onclick="auctionDecide('pass')">패스</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="/static/js/auction.js"></script>
<script>
  fetch("/api/settings/mode").then(r => r.json()).then(d => {
    const b = document.getElementById("mode-badge");
    if (d.mode === "real") { b.textContent = "실전투자"; b.className = "mode-badge mode-real"; }
    else { b.textContent = "모의투자"; b.className = "mode-badge mode-paper"; }
  });
</script>
{% block scripts %}{% endblock %}
</body>
</html>
```

**Step 3: templates/dashboard.html 작성**

```html
{% extends "base.html" %}
{% block title %}대시보드 — KIS 자동매매{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="fw-bold mb-0">대시보드</h4>
  <button class="btn btn-sm btn-outline-secondary" onclick="loadBalance()">
    <i class="fa-solid fa-rotate-right"></i> 새로고침
  </button>
</div>
<div class="row g-3 mb-4">
  <div class="col-md-4">
    <div class="card shadow-sm">
      <div class="card-body">
        <div class="text-muted small">보유 종목 수</div>
        <div id="stat-count" class="fs-3 fw-bold">-</div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card shadow-sm">
      <div class="card-body">
        <div class="text-muted small">총 평가손익</div>
        <div id="stat-pnl" class="fs-3 fw-bold">-</div>
      </div>
    </div>
  </div>
  <div class="col-md-4">
    <div class="card shadow-sm">
      <div class="card-body">
        <div class="text-muted small">투자 모드</div>
        <div id="stat-mode" class="fs-3 fw-bold">-</div>
      </div>
    </div>
  </div>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-bold">보유 종목</div>
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light">
        <tr><th>종목코드</th><th>종목명</th><th>수량</th><th>평균단가</th><th>현재가</th><th>평가손익</th><th>수익률</th></tr>
      </thead>
      <tbody id="balance-body">
        <tr><td colspan="7" class="text-center text-muted py-4">로딩 중...</td></tr>
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script>
function loadBalance() {
  fetch("/api/balance").then(r => r.json()).then(d => {
    document.getElementById("stat-mode").textContent = d.mode === "real" ? "실전" : "모의";
    const tbody = document.getElementById("balance-body");
    tbody.textContent = "";
    if (!d.balance || !d.balance.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7; td.className = "text-center text-muted py-4";
      td.textContent = "보유 종목 없음";
      tr.appendChild(td); tbody.appendChild(tr);
      document.getElementById("stat-count").textContent = "0종목";
      document.getElementById("stat-pnl").textContent = "0원";
      return;
    }
    let totalPnl = 0;
    d.balance.forEach(row => {
      const pnl = row.eval_profit_loss || 0;
      totalPnl += pnl;
      const pnlClass = pnl >= 0 ? "text-danger" : "text-primary";
      const tr = document.createElement("tr");
      [
        [row.stock_code, ""],
        [row.stock_name, ""],
        [row.quantity + "주", ""],
        [row.avg_price.toLocaleString() + "원", ""],
        [row.current_price.toLocaleString() + "원", ""],
        [pnl.toLocaleString() + "원", pnlClass],
        [(row.profit_loss_rate || 0).toFixed(2) + "%", pnlClass],
      ].forEach(([text, cls]) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (cls) td.className = cls;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    document.getElementById("stat-count").textContent = d.balance.length + "종목";
    const pnlEl = document.getElementById("stat-pnl");
    pnlEl.textContent = totalPnl.toLocaleString() + "원";
    pnlEl.className = "fs-3 fw-bold " + (totalPnl >= 0 ? "text-danger" : "text-primary");
  });
}
loadBalance();
setInterval(loadBalance, 30000);
</script>
{% endblock %}
```

**Step 4: templates/strategies.html 작성**

```html
{% extends "base.html" %}
{% block title %}전략 관리 — KIS 자동매매{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="fw-bold mb-0">전략 관리</h4>
  <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addModal">
    <i class="fa-solid fa-plus me-1"></i>전략 추가
  </button>
</div>
<div class="card shadow-sm">
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light">
        <tr><th>이름</th><th>종목</th><th>전략유형</th><th>모드</th><th>상태</th><th>관리</th></tr>
      </thead>
      <tbody id="strategy-body">
        <tr><td colspan="6" class="text-center text-muted py-4">로딩 중...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="modal fade" id="addModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">전략 추가</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3">
          <label class="form-label">전략명</label>
          <input type="text" class="form-control" id="s-name" placeholder="삼성전자 MA전략">
        </div>
        <div class="mb-3">
          <label class="form-label">종목코드</label>
          <input type="text" class="form-control" id="s-code" placeholder="005930">
        </div>
        <div class="mb-3">
          <label class="form-label">종목명</label>
          <input type="text" class="form-control" id="s-sname" placeholder="삼성전자">
        </div>
        <div class="mb-3">
          <label class="form-label">전략 유형</label>
          <select class="form-select" id="s-type" onchange="updateParamHint()">
            <option value="ma">이동평균선 (MA/EMA)</option>
            <option value="rsi_macd">RSI / MACD</option>
            <option value="condition">조건식 직접 설정</option>
            <option value="ml">AI/ML 예측 (RandomForest)</option>
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label">파라미터 (JSON)</label>
          <textarea class="form-control font-monospace" id="s-params" rows="5"></textarea>
          <div class="text-muted small mt-1" id="param-hint"></div>
        </div>
        <div class="mb-3">
          <label class="form-label">모드</label>
          <select class="form-select" id="s-mode">
            <option value="paper">모의투자</option>
            <option value="real">실전투자</option>
          </select>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
        <button type="button" class="btn btn-primary" onclick="addStrategy()">추가</button>
      </div>
    </div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script>
const PARAM_DEFAULTS = {
  ma: '{"short_period":5,"long_period":20,"buy_qty":10,"stop_loss_pct":-3,"take_profit_pct":5}',
  rsi_macd: '{"rsi_period":14,"rsi_oversold":30,"rsi_overbought":70,"macd_fast":12,"macd_slow":26,"macd_signal":9,"buy_qty":10}',
  condition: '{"conditions":[{"indicator":"change_rate","operator":">","value":3}],"action":"buy","buy_qty":5}',
  ml: '{"buy_threshold":0.65,"sell_threshold":0.35,"buy_qty":10}',
};
function updateParamHint() {
  const t = document.getElementById("s-type").value;
  document.getElementById("s-params").value = PARAM_DEFAULTS[t] || "{}";
  document.getElementById("param-hint").textContent = "기본 파라미터 예시가 자동 입력됐습니다.";
}
updateParamHint();

function loadStrategies() {
  fetch("/strategies/api/strategies").then(r => r.json()).then(list => {
    const tbody = document.getElementById("strategy-body");
    tbody.textContent = "";
    if (!list.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6; td.className = "text-center text-muted py-4";
      td.textContent = "등록된 전략이 없습니다";
      tr.appendChild(td); tbody.appendChild(tr); return;
    }
    const typeLabel = {ma:"MA/EMA", rsi_macd:"RSI/MACD", condition:"조건식", ml:"AI/ML"};
    list.forEach(s => {
      const tr = document.createElement("tr");
      [s.name, s.stock_code + " " + s.stock_name,
       typeLabel[s.strategy_type] || s.strategy_type,
       s.mode === "real" ? "실전" : "모의"].forEach(text => {
        const td = document.createElement("td");
        td.textContent = text; tr.appendChild(td);
      });
      const tdS = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "badge " + (s.is_active ? "bg-success" : "bg-secondary");
      badge.textContent = s.is_active ? "활성" : "비활성";
      badge.style.cursor = "pointer";
      badge.addEventListener("click", () => {
        fetch("/strategies/api/strategies/" + s.id + "/toggle", {method:"POST"}).then(() => loadStrategies());
      });
      tdS.appendChild(badge); tr.appendChild(tdS);
      const tdB = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "btn btn-sm btn-outline-danger";
      btn.textContent = "삭제";
      btn.addEventListener("click", () => {
        if (!confirm("삭제하시겠습니까?")) return;
        fetch("/strategies/api/strategies/" + s.id, {method:"DELETE"}).then(() => loadStrategies());
      });
      tdB.appendChild(btn); tr.appendChild(tdB);
      tbody.appendChild(tr);
    });
  });
}

function addStrategy() {
  let params;
  try { params = JSON.parse(document.getElementById("s-params").value); }
  catch(e) { alert("파라미터 JSON 형식 오류"); return; }
  fetch("/strategies/api/strategies", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      name: document.getElementById("s-name").value,
      stock_code: document.getElementById("s-code").value,
      stock_name: document.getElementById("s-sname").value,
      strategy_type: document.getElementById("s-type").value,
      params, mode: document.getElementById("s-mode").value,
    }),
  }).then(r => r.json()).then(() => {
    bootstrap.Modal.getInstance(document.getElementById("addModal")).hide();
    loadStrategies();
  });
}
loadStrategies();
</script>
{% endblock %}
```

**Step 5: templates/orders.html 작성**

```html
{% extends "base.html" %}
{% block title %}주문 내역 — KIS 자동매매{% endblock %}
{% block content %}
<h4 class="fw-bold mb-4">주문 내역</h4>
<div class="d-flex gap-2 mb-3">
  <select class="form-select w-auto" id="filter-mode" onchange="loadOrders()">
    <option value="">전체 모드</option>
    <option value="paper">모의</option>
    <option value="real">실전</option>
  </select>
  <select class="form-select w-auto" id="filter-trigger" onchange="loadOrders()">
    <option value="">전체 유형</option>
    <option value="auto">자동</option>
    <option value="auction_manual">동시호가 수동</option>
  </select>
</div>
<div class="card shadow-sm">
  <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light">
        <tr><th>시간</th><th>종목</th><th>구분</th><th>가격</th><th>수량</th><th>상태</th><th>유형</th><th>모드</th></tr>
      </thead>
      <tbody id="order-body">
        <tr><td colspan="8" class="text-center text-muted py-4">로딩 중...</td></tr>
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script>
function loadOrders() {
  let url = "/orders/api/orders?";
  const mode = document.getElementById("filter-mode").value;
  const trigger = document.getElementById("filter-trigger").value;
  if (mode) url += "mode=" + mode + "&";
  if (trigger) url += "trigger=" + trigger;
  fetch(url).then(r => r.json()).then(list => {
    const tbody = document.getElementById("order-body");
    tbody.textContent = "";
    if (!list.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 8; td.className = "text-center text-muted py-4";
      td.textContent = "주문 내역 없음";
      tr.appendChild(td); tbody.appendChild(tr); return;
    }
    list.forEach(o => {
      const tr = document.createElement("tr");
      const isBuy = o.order_type === "buy";
      [
        [o.created_at.replace("T"," ").slice(0,16), ""],
        [o.stock_code, ""],
        [isBuy ? "매수" : "매도", isBuy ? "text-danger" : "text-primary"],
        [Number(o.price).toLocaleString() + "원", ""],
        [o.quantity + "주", ""],
        [o.status, ""],
        [o.trigger === "auto" ? "자동" : "동시호가", ""],
        [o.mode === "real" ? "실전" : "모의", ""],
      ].forEach(([text, cls]) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (cls) td.className = cls;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  });
}
loadOrders();
</script>
{% endblock %}
```

**Step 6: templates/settings.html 작성**

```html
{% extends "base.html" %}
{% block title %}설정 — KIS 자동매매{% endblock %}
{% block content %}
<h4 class="fw-bold mb-4">설정</h4>
<div class="card shadow-sm mb-4">
  <div class="card-header fw-bold">투자 모드 전환</div>
  <div class="card-body">
    <p class="text-muted small mb-3">현재 모드: <strong id="current-mode-label">-</strong></p>
    <div class="d-flex gap-2">
      <button class="btn btn-outline-secondary" onclick="setMode('paper')">모의투자로 전환</button>
      <button class="btn btn-outline-danger" onclick="confirmRealMode()">실전투자로 전환</button>
    </div>
  </div>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-bold">KIS API 토큰</div>
  <div class="card-body">
    <p class="text-muted small mb-3">토큰은 24시간마다 자동 갱신됩니다. 오류 발생 시 수동 갱신하세요.</p>
    <button class="btn btn-outline-primary" onclick="refreshToken()">토큰 수동 갱신</button>
    <div id="token-msg" class="mt-2 text-success small"></div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script>
fetch("/api/settings/mode").then(r => r.json()).then(d => {
  document.getElementById("current-mode-label").textContent = d.mode === "real" ? "실전투자" : "모의투자";
});

function setMode(mode) {
  fetch("/api/settings/mode", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({mode}),
  }).then(r => r.json()).then(d => {
    document.getElementById("current-mode-label").textContent = mode === "real" ? "실전투자" : "모의투자";
    alert(d.message);
    location.reload();
  });
}

function confirmRealMode() {
  if (confirm("실전투자로 전환하면 실제 자금으로 거래됩니다.\n반드시 소액 테스트 후 사용하세요. 계속하시겠습니까?")) {
    setMode("real");
  }
}

function refreshToken() {
  fetch("/api/settings/token-refresh", {method:"POST"})
    .then(r => r.json())
    .then(d => { document.getElementById("token-msg").textContent = d.message; });
}
</script>
{% endblock %}
```

**Step 7: Commit**

```bash
git add templates/ static/
git commit -m "feat: HTML templates (dashboard, strategies, orders, settings) + auction.js SSE popup"
```

---

## Task 8: 실행 및 최종 검증

**Step 1: .env 생성 및 서버 실행**

```bash
cd /home/yms/kis_trader
cp .env.example .env
# .env에 KIS API 키 입력 후:
python run.py
```

Expected: `Running on http://0.0.0.0:6000`

**Step 2: 웹 브라우저 접속 확인**

- `http://192.168.0.108:6000` → 대시보드 렌더링 확인
- `http://192.168.0.108:6000/strategies/` → 전략 관리 페이지
- `http://192.168.0.108:6000/settings/` → 모드 전환 버튼 확인

**Step 3: 전략 등록 테스트**

1. `/strategies/` → "전략 추가" 클릭
2. 종목코드 `005930`, 유형 `ma`, 모드 `paper` 입력 → 추가
3. 목록에 표시 및 활성/비활성 토글 확인

**Step 4: 동시호가 팝업 수동 테스트**

```bash
python -c "
from app import create_app
from db import db
from models import AuctionAlert
from routers.auction import broadcast_auction
from datetime import datetime, timedelta

app = create_app()
with app.app_context():
    a = AuctionAlert(
        stock_code='005930', stock_name='삼성전자',
        suggested_action='buy', suggested_price=74000, suggested_qty=5,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(a)
    db.session.commit()
    broadcast_auction(a.id)
    print('Alert sent, id:', a.id)
"
```

Expected: 브라우저 팝업 표시 → 매수/매도/패스 클릭 시 `/api/auction/decide` 호출

**Step 5: 최종 Commit**

```bash
git add .
git commit -m "feat: KIS 자동매매 시스템 초기 구현 완료

- Flask + APScheduler 단일 앱, 포트 6000
- 4가지 전략: MA/EMA, RSI/MACD, 조건식, ML(RandomForest+joblib)
- 모의/실전 투자 전환 (settings 페이지)
- 동시호가 SSE 팝업 + 수동 매수/매도/패스
- SQLite DB: Strategy, Order, AuctionAlert, PortfolioSnapshot, KisToken"
```

---

## 운영 참고

### 프로세스 유지

```bash
cd /home/yms/kis_trader
nohup python run.py > kis_trader.log 2>&1 &
tail -f kis_trader.log
```

### KIS API 키 발급

1. https://apiportal.koreainvestment.com 접속
2. 앱 등록 → App Key / App Secret 발급
3. 모의투자 전용 키 별도 발급 필요 (실전 키와 다름)
4. `.env` 파일에 입력 후 서버 재시작

### 주의사항

- 실전 전환 후 반드시 소액(1주) 테스트 먼저 진행
- KIS API 호출 횟수 제한: 1초 20건 이내
- 장 시간: 평일 09:00~15:30 (동시호가 포함)
- 모의투자 계좌는 한국투자증권 홈페이지에서 별도 개설 필요
