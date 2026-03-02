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
