from flask import Blueprint, render_template, jsonify, current_app, request
from kis_api import get_balance, get_current_price, get_index_price
from models import Strategy

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


@bp.route("/api/market-prices")
def market_prices():
    """코스피/코스닥 지수 + 전략 등록 종목 + 추가 종목 시세 조회"""
    mode = current_app.config.get("CURRENT_MODE", "paper")
    result = {"mode": mode, "indices": {}, "stocks": []}

    # 코스피 지수
    try:
        result["indices"]["kospi"] = get_index_price("0001", mode)
    except Exception:
        result["indices"]["kospi"] = None

    # 코스닥 지수
    try:
        result["indices"]["kosdaq"] = get_index_price("1001", mode)
    except Exception:
        result["indices"]["kosdaq"] = None

    # 전략에 등록된 모든 종목 수집
    seen = set()
    stock_list = []
    strategies = Strategy.query.all()
    for s in strategies:
        if s.stock_code not in seen:
            seen.add(s.stock_code)
            stock_list.append((s.stock_code, s.stock_name))

    # 쿼리 파라미터로 추가 종목 (extra=005930,035720)
    extra = request.args.get("extra", "")
    if extra:
        for code in extra.split(","):
            code = code.strip()
            if code and code not in seen:
                seen.add(code)
                stock_list.append((code, ""))

    # 각 종목 시세 조회
    for stock_code, stock_name in stock_list:
        try:
            price_data = get_current_price(stock_code, mode)
            price_data["stock_code"] = stock_code
            price_data["stock_name"] = stock_name
            result["stocks"].append(price_data)
        except Exception:
            result["stocks"].append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "price": 0, "open": 0, "high": 0, "low": 0,
                "change_rate": 0, "volume": 0, "error": True,
            })

    return jsonify(result)


@bp.route("/api/stock-price/<stock_code>")
def stock_price(stock_code):
    """개별 종목 시세 조회"""
    mode = current_app.config.get("CURRENT_MODE", "paper")
    try:
        data = get_current_price(stock_code, mode)
        data["stock_code"] = stock_code
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
