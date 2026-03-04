import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "kis-trader-dev-only-change-in-production")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'kis_trader.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # KIS API - 모의투자
    KIS_PAPER_APP_KEY = os.getenv("KIS_PAPER_APP_KEY", "")
    KIS_PAPER_APP_SECRET = os.getenv("KIS_PAPER_APP_SECRET", "")
    KIS_PAPER_ACCOUNT_NO = os.getenv("KIS_PAPER_ACCOUNT_NO", "")

    # KIS API - 실전투자
    KIS_REAL_APP_KEY = os.getenv("KIS_REAL_APP_KEY", "")
    KIS_REAL_APP_SECRET = os.getenv("KIS_REAL_APP_SECRET", "")
    KIS_REAL_ACCOUNT_NO = os.getenv("KIS_REAL_ACCOUNT_NO", "")

    KIS_ACCOUNT_SUFFIX = os.getenv("KIS_ACCOUNT_SUFFIX", "01")

    # URL
    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    REAL_BASE_URL  = "https://openapi.koreainvestment.com:9443"

    # 스케줄러
    STRATEGY_INTERVAL_SECONDS = 60
    AUCTION_CHECK_INTERVAL_SECONDS = 30
