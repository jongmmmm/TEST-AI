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
