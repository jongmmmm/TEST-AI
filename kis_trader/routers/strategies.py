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
