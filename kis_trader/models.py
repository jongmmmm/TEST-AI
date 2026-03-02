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
    __tablename__ = "kis_tokens"
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(10), unique=True)  # paper|real
    access_token = db.Column(db.Text, default="")
    expires_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
