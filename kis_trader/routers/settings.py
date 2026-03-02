from flask import Blueprint, render_template, request, jsonify, current_app

bp = Blueprint("settings", __name__)

@bp.route("/settings/")
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
