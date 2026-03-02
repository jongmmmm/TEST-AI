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
        now = datetime.now()  # KST naive — consistent with expires_at stored by check_auction_and_alert
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
    if app.config.get("TESTING"):
        return None
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
