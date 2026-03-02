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
    now = datetime.now()  # KST naive — consistent with expires_at
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
    alert.decided_at = datetime.now()  # KST naive
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
