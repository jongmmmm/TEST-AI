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
