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
